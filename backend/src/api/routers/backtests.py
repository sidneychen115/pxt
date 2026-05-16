from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone, time
from typing import TYPE_CHECKING, Any


from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from src.api.deps import get_current_user
from src.core.database import get_session, async_session_factory
from src.core.models import Backtest, BacktestTrade, BacktestEquityCurve, Instrument, Strategy, User
from src.api.websocket import ws_manager
from src.backtesting.exit_policy import ExitPolicy
from src.core.app_timezone import (
    api_iso,
    api_iso_equity_daily_session,
    app_zone,
    daily_bar_timestamp_for_session_date,
    equity_daily_session_calendar_date,
)


async def _merge_cached_with_yfinance(
    sym: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    cached: "pd.DataFrame",
    instrument_id: int,
    *,
    provider: "YFinanceProvider | None" = None,
) -> "pd.DataFrame":
    """Fill [start, end] using DB ``cached`` series and yfinance for head/tail gaps only."""
    from src.data.providers.yfinance_provider import YFinanceProvider
    from src.data.repository import save_bars

    prov = provider or YFinanceProvider()

    async def _fetch_and_save(fetch_start: datetime, fetch_end: datetime) -> "pd.DataFrame":
        df = await prov.get_bars(sym, timeframe, fetch_start, fetch_end)
        if not df.empty:
            async with async_session_factory() as session:
                await save_bars(session, instrument_id, timeframe, df)
                await session.commit()
        return df

    if cached.empty:
        return await _fetch_and_save(start, end)

    parts = [cached]

    ix_tz = cached.index.tz
    start_ts = _pandas_ts_aligned_to_index_tz(start, ix_tz)
    first_raw = cached.index[0]
    ft = first_raw.to_pydatetime() if hasattr(first_raw, "to_pydatetime") else first_raw
    first_ts = _pandas_ts_aligned_to_index_tz(ft, ix_tz)

    if first_ts > start_ts:
        df_head = await _fetch_and_save(start_ts.to_pydatetime(), first_ts.to_pydatetime())
        if not df_head.empty:
            parts.insert(0, df_head)

    end_ts = _pandas_ts_aligned_to_index_tz(end, ix_tz)
    last_raw = cached.index[-1]
    lt = last_raw.to_pydatetime() if hasattr(last_raw, "to_pydatetime") else last_raw
    last_ts = _pandas_ts_aligned_to_index_tz(lt, ix_tz)

    if last_ts < end_ts:
        df_tail = await _fetch_and_save(last_ts.to_pydatetime(), end_ts.to_pydatetime())
        if not df_tail.empty:
            df_tail = df_tail[df_tail.index > last_raw]
            if not df_tail.empty:
                parts.append(df_tail)

    if len(parts) == 1:
        return parts[0]
    return pd.concat(parts).sort_index()


if TYPE_CHECKING:
    import pandas as pd
    from src.data.providers.yfinance_provider import YFinanceProvider

router = APIRouter()
_log = logging.getLogger(__name__)


async def _require_backtest(
    backtest_id: int, user: User, session: AsyncSession
) -> Backtest:
    result = await session.execute(
        select(Backtest).where(Backtest.id == backtest_id, Backtest.user_id == user.id)
    )
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(404, "Backtest not found.")
    return bt


async def _pnl_aggregate_by_symbol(session: AsyncSession, backtest_id: int) -> list[dict[str, Any]]:
    """Per-symbol realized P&L sum and trade row count from ``backtest_trades``."""
    stmt = (
        select(
            BacktestTrade.symbol,
            func.coalesce(func.sum(BacktestTrade.pnl), 0).label("total_pnl"),
            func.count().label("trade_count"),
        )
        .where(BacktestTrade.backtest_id == backtest_id)
        .group_by(BacktestTrade.symbol)
        .order_by(BacktestTrade.symbol.asc())
    )
    result = await session.execute(stmt)
    return [
        {
            "symbol": row.symbol,
            "total_pnl": float(row.total_pnl),
            "trade_count": int(row.trade_count),
        }
        for row in result.all()
    ]


# yfinance intraday caps (see YFinanceProvider); used for validation and messages
_INTRADAY_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h"})


def _benchmark_symbol_from_params(parameters: dict) -> str:
    """Ticker used for buy-hold / alpha (defaults SPY); normalize for cache keys."""
    s = str(parameters.get("benchmark_symbol") or "SPY").strip().upper()
    return s or "SPY"


class BacktestRequest(BaseModel):
    strategy_id: str
    start_date: date
    end_date: date
    symbols: list[str]
    initial_capital: float = 100_000.0
    parameters: dict = {}
    exit_policy: ExitPolicy | None = None


@router.get("/")
async def list_backtests(
    strategy_id: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Do not load llm_evaluation (often huge TEXT / TOAST) for the list — it was dominating I/O and JSON size.
    query = (
        select(Backtest)
        .where(Backtest.user_id == user.id)
        .options(defer(Backtest.llm_evaluation))
        .order_by(desc(Backtest.created_at))
        .limit(limit)
    )
    if strategy_id:
        query = query.where(Backtest.strategy_id == strategy_id)
    result = await session.execute(query)
    return [_backtest_summary(b, include_llm=False) for b in result.scalars().all()]


@router.post("/")
async def trigger_backtest(
    req: BacktestRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    started = datetime.now(timezone.utc)
    bt = Backtest(
        user_id=user.id,
        strategy_id=req.strategy_id,
        start_date=req.start_date,
        end_date=req.end_date,
        symbols=req.symbols,
        initial_capital=req.initial_capital,
        parameters=req.parameters,
        exit_policy=req.exit_policy.model_dump(mode="json") if req.exit_policy else None,
        status="running",
        progress_updated_at=started,
    )
    session.add(bt)
    await session.commit()
    await session.refresh(bt)
    background_tasks.add_task(_run_backtest, bt.id, req)
    return {"id": bt.id, "status": "running"}


@router.get("/{backtest_id}")
async def get_backtest(
    backtest_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bt = await _require_backtest(backtest_id, user, session)
    summary = _backtest_summary(bt)
    if bt.status == "completed":
        summary["pnl_by_symbol"] = await _pnl_aggregate_by_symbol(session, backtest_id)
    else:
        summary["pnl_by_symbol"] = None
    return summary


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: int,
    sort_by: str = "entry_time",
    order: str = "asc",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bt = await _require_backtest(backtest_id, user, session)
    tf = await _resolve_timeframe_from_params(bt.strategy_id, bt.parameters or {})
    _ALLOWED_SORT = {"entry_time", "exit_time", "pnl", "pnl_pct", "symbol", "hold_days"}
    col_name = sort_by if sort_by in _ALLOWED_SORT else "entry_time"
    col = getattr(BacktestTrade, col_name)
    direction = col.asc() if order == "asc" else col.desc()
    result = await session.execute(
        select(BacktestTrade)
        .where(BacktestTrade.backtest_id == backtest_id)
        .order_by(direction)
    )
    trades = result.scalars().all()
    use_sess = tf in _DAILY_LIKE_TIMEFRAMES
    iso_bar = api_iso_equity_daily_session if use_sess else api_iso
    return [
        {
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "quantity": float(t.quantity), "entry_time": iso_bar(t.entry_time),
            "entry_price": float(t.entry_price),
            "exit_time": iso_bar(t.exit_time) if t.exit_time else None,
            "exit_price": float(t.exit_price) if t.exit_price else None,
            "pnl": float(t.pnl) if t.pnl else None,
            "pnl_pct": float(t.pnl_pct) if t.pnl_pct else None,
            "hold_days": float(t.hold_days) if t.hold_days else None,
            "exit_reason": t.exit_reason,
            "entry_signal": t.entry_signal,
        }
        for t in trades
    ]


@router.get("/{backtest_id}/equity")
async def get_equity_curve(
    backtest_id: int,
    max_points: int = Query(4000, ge=200, le=50_000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_backtest(backtest_id, user, session)
    result = await session.execute(
        select(BacktestEquityCurve)
        .where(BacktestEquityCurve.backtest_id == backtest_id)
        .order_by(BacktestEquityCurve.ts)
    )
    points = result.scalars().all()
    if len(points) > max_points:
        n = len(points)
        # Evenly subsample indices so charts stay representative without huge payloads.
        take = max_points
        idxs = {int(round(i * (n - 1) / (take - 1))) for i in range(take)}
        points = [points[i] for i in sorted(idxs)]
    return [
        {"ts": api_iso(p.ts), "equity": float(p.equity),
         "cash": float(p.cash), "drawdown": float(p.drawdown) if p.drawdown else None}
        for p in points
    ]


_DAILY_LIKE_TIMEFRAMES = frozenset({"1d", "1wk", "1mo"})


def _pandas_ts_aligned_to_index_tz(ts_raw: datetime, index_tz):
    """Match bar index tz (Chicago for migrated daily caches; UTC legacy intraday)."""
    import pandas as pd

    ts = pd.Timestamp(ts_raw)
    if index_tz is None:
        return ts.tz_localize(timezone.utc) if ts.tz is None else ts.tz_convert(timezone.utc)
    if ts.tz is None:
        return ts.tz_localize(timezone.utc).tz_convert(index_tz)
    return ts.tz_convert(index_tz)


def _encode_ohlc_bar_time(timeframe: str, ts: datetime) -> str | int:
    """Chart time: equity session calendar YYYY-MM-DD for daily+; unix seconds UTC for intraday."""
    if timeframe in _DAILY_LIKE_TIMEFRAMES:
        t = ts
        if getattr(ts, "tzinfo", None) is None:
            t = ts.replace(tzinfo=timezone.utc)
        sess = equity_daily_session_calendar_date(t)
        return sess.strftime("%Y-%m-%d")
    t = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
    if getattr(t, "tzinfo", None) is None:
        t = t.replace(tzinfo=timezone.utc)
    else:
        t = t.astimezone(timezone.utc)
    return int(t.timestamp())


def _trade_event_bar_index(index: pd.DatetimeIndex, event_time: datetime) -> int | None:
    if index.empty or event_time is None:
        return None
    t = _pandas_ts_aligned_to_index_tz(event_time, index.tz)
    pos = int(index.get_indexer([t], method="nearest")[0])
    if pos < 0:
        return None
    return pos


def _subsample_ohlc_row_indices(n: int, max_points: int, preserve: set[int]) -> list[int]:
    """Evenly subsample [0..n-1], always including preserve (trade bars)."""
    preserve = {p for p in preserve if 0 <= p < n}
    if n <= max_points:
        return list(range(n))
    if not preserve:
        return sorted({int(round(i * (n - 1) / (max_points - 1))) for i in range(max_points)})
    kept = set(preserve)
    if len(kept) > max_points:
        tp = sorted(kept)
        return [tp[int(round(j * (len(tp) - 1) / (max_points - 1)))] for j in range(max_points)]
    remaining = max_points - len(kept)
    pool = [i for i in range(n) if i not in kept]
    if not pool:
        return sorted(kept)
    if remaining == 1:
        picks = {pool[len(pool) // 2]}
    else:
        picks = {pool[int(round(j * (len(pool) - 1) / (remaining - 1)))] for j in range(remaining)}
    return sorted(kept | picks)


@router.get("/{backtest_id}/ohlc")
async def get_backtest_ohlc(
    backtest_id: int,
    symbol: str = Query(..., min_length=1),
    max_points: int = Query(4000, ge=200, le=50_000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """OHLC bars for one symbol over the backtest window (same fetch path as the engine)."""
    bt = await _require_backtest(backtest_id, user, session)
    if symbol not in bt.symbols:
        raise HTTPException(400, "symbol is not part of this backtest.")
    if bt.status != "completed":
        raise HTTPException(409, "OHLC is only available for completed backtests.")

    timeframe = await _resolve_timeframe_from_params(bt.strategy_id, bt.parameters or {})
    z = app_zone()
    if timeframe in _INTRADAY_TIMEFRAMES:
        start = datetime.combine(bt.start_date, time.min, tzinfo=z)
        end = datetime.combine(bt.end_date + timedelta(days=1), time.min, tzinfo=z)
        days_span = (end - start).days
        if days_span > 730:
            raise HTTPException(
                400,
                f"yfinance intraday data ({timeframe}) is limited to about 730 days; this range is {days_span} days.",
            )
    else:
        start = daily_bar_timestamp_for_session_date(bt.start_date)
        end = daily_bar_timestamp_for_session_date(bt.end_date)

    trades_result = await session.execute(
        select(BacktestTrade).where(
            BacktestTrade.backtest_id == backtest_id,
            BacktestTrade.symbol == symbol,
        )
    )
    symbol_trades = trades_result.scalars().all()

    df = await _fetch_with_cache(symbol, timeframe, start, end)
    if df.empty:
        return {"symbol": symbol, "timeframe": timeframe, "bars": []}

    preserve: set[int] = set()
    idx = df.index
    for t in symbol_trades:
        ei = _trade_event_bar_index(idx, t.entry_time)
        if ei is not None:
            preserve.add(ei)
        if t.exit_time is not None:
            xi = _trade_event_bar_index(idx, t.exit_time)
            if xi is not None:
                preserve.add(xi)

    row_ix = _subsample_ohlc_row_indices(len(df), max_points, preserve)
    sub = df.iloc[row_ix]
    bars = []
    for ts, row in sub.iterrows():
        tnorm = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if getattr(tnorm, "tzinfo", None) is None:
            tnorm = tnorm.replace(tzinfo=timezone.utc)
        bars.append(
            {
                "time": _encode_ohlc_bar_time(timeframe, tnorm),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )
    return {"symbol": symbol, "timeframe": timeframe, "bars": bars}


def _backtest_summary(bt: Backtest, *, include_llm: bool = True) -> dict:
    return {
        "id": bt.id, "strategy_id": bt.strategy_id,
        "start_date": bt.start_date, "end_date": bt.end_date,
        "symbols": bt.symbols, "initial_capital": float(bt.initial_capital),
        "status": bt.status,
        "total_return": float(bt.total_return) if bt.total_return else None,
        "annualized_return": float(bt.annualized_return) if bt.annualized_return else None,
        "sharpe_ratio": float(bt.sharpe_ratio) if bt.sharpe_ratio else None,
        "max_drawdown": float(bt.max_drawdown) if bt.max_drawdown else None,
        "win_rate": float(bt.win_rate) if bt.win_rate else None,
        "profit_factor": float(bt.profit_factor) if bt.profit_factor else None,
        "total_trades": bt.total_trades,
        "avg_hold_days": float(bt.avg_hold_days) if bt.avg_hold_days else None,
        "benchmark_total_return": float(bt.benchmark_total_return) if bt.benchmark_total_return is not None else None,
        "alpha_vs_benchmark": float(bt.alpha_vs_benchmark) if bt.alpha_vs_benchmark is not None else None,
        "llm_evaluation": bt.llm_evaluation if include_llm else None,
        "llm_model": bt.llm_model,
        "created_at": api_iso(bt.created_at), "completed_at": api_iso(bt.completed_at),
        "parameters": bt.parameters or {},
        "exit_policy": bt.exit_policy,
        "progress_phase": bt.progress_phase,
        "progress_message": bt.progress_message,
        "progress_updated_at": api_iso(bt.progress_updated_at),
        "error_message": bt.error_message,
    }


async def _resolve_timeframe_from_params(strategy_id: str, parameters: dict | None) -> str:
    """Use parameters['timeframe'] if set; otherwise first timeframe from Strategy row; else 1d."""
    default_tf = "1d"
    params = parameters or {}
    async with async_session_factory() as session:
        row = await session.get(Strategy, strategy_id)
    if row is not None and row.timeframes:
        default_tf = row.timeframes[0] or default_tf
    override = params.get("timeframe")
    if override not in (None, ""):
        return str(override)
    return default_tf


async def _resolve_backtest_timeframe(req: BacktestRequest) -> str:
    return await _resolve_timeframe_from_params(req.strategy_id, req.parameters)


async def _set_backtest_progress(backtest_id: int, phase: str, message: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    _log.info("backtest %s progress phase=%s message=%s", backtest_id, phase, message)
    async with async_session_factory() as session:
        await session.execute(
            update(Backtest).where(Backtest.id == backtest_id).values(
                progress_phase=phase,
                progress_message=message,
                progress_updated_at=now,
            )
        )
        await session.commit()
    await ws_manager.broadcast(
        "backtest_progress",
        {
            "backtest_id": backtest_id,
            "phase": phase,
            "message": message,
            "progress_updated_at": api_iso(now),
        },
    )


def _engine_bar_progress(backtest_id: int):
    async def on_bar(done: int, total: int) -> None:
        pct = (100 * done // total) if total else 0
        await _set_backtest_progress(
            backtest_id,
            "engine",
            f"回测引擎: 已模拟 {done}/{total} 根K线（约 {pct}%）",
        )

    return on_bar


async def _fetch_with_cache(sym: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Return bars for sym in [start, end], using DB cache and filling gaps from yfinance."""
    from src.data.repository import get_bars_range, upsert_instrument

    async with async_session_factory() as session:
        instrument = await upsert_instrument(session, sym, "stock")
        await session.commit()
        instrument_id = instrument.id
        cached = await get_bars_range(session, instrument_id, timeframe, start, end)
    return await _merge_cached_with_yfinance(
        sym, timeframe, start, end, cached, instrument_id
    )


async def _run_backtest(backtest_id: int, req: BacktestRequest):
    from src.backtesting.engine import BacktestEngine
    from src.backtesting.evaluator import LLMEvaluator
    from src.strategies.registry import REGISTRY, discover_strategies
    discover_strategies()
    try:
        timeframe = await _resolve_backtest_timeframe(req)
        z = app_zone()
        if timeframe in _INTRADAY_TIMEFRAMES:
            sim_start = datetime.combine(req.start_date, time.min, tzinfo=z)
            sim_end = datetime.combine(req.end_date + timedelta(days=1), time.min, tzinfo=z)
        else:
            sim_start = daily_bar_timestamp_for_session_date(req.start_date)
            sim_end = daily_bar_timestamp_for_session_date(req.end_date)
        if sim_start > sim_end:
            raise ValueError("Invalid date range: start_date must be on or before end_date.")
        try:
            warmup_m = int((req.parameters or {}).get("backtest_warmup_months", 24))
        except (TypeError, ValueError):
            warmup_m = 24
        warmup_m = max(0, min(warmup_m, 120))
        if timeframe in _INTRADAY_TIMEFRAMES:
            fetch_start_date = req.start_date - relativedelta(months=warmup_m)
            data_start = datetime.combine(fetch_start_date, time.min, tzinfo=z)
        else:
            fetch_start_date = req.start_date - relativedelta(months=warmup_m)
            data_start = daily_bar_timestamp_for_session_date(fetch_start_date)
        if data_start > sim_start:
            data_start = sim_start
        fetch_end = sim_end
        if timeframe in _INTRADAY_TIMEFRAMES:
            days_span = (fetch_end - data_start).days
            if days_span > 730:
                raise ValueError(
                    f"yfinance intraday data ({timeframe}) is limited to about 730 days; "
                    f"warmup+window span is {days_span} days. Shorten the backtest window or set "
                    "parameters.backtest_warmup_months lower."
                )
        bench_sym = _benchmark_symbol_from_params(req.parameters)
        unique_syms = list(dict.fromkeys([*req.symbols, bench_sym]))

        from src.data.providers.yfinance_provider import YFinanceProvider
        from src.data.repository import get_bars_range_for_symbols, upsert_instrument

        await _set_backtest_progress(
            backtest_id,
            "fetching_data",
            f"拉取行情: {len(unique_syms)} 标的批量读库…",
        )
        async with async_session_factory() as session:
            for sym in unique_syms:
                await upsert_instrument(session, sym, "stock")
            await session.commit()
            id_rows = await session.execute(
                select(Instrument.id, Instrument.symbol).where(Instrument.symbol.in_(unique_syms))
            )
            id_by_sym = {row.symbol: row.id for row in id_rows}
            cached_map = await get_bars_range_for_symbols(
                session, unique_syms, timeframe, data_start, fetch_end
            )

        provider = YFinanceProvider()
        await _set_backtest_progress(
            backtest_id,
            "fetching_data",
            "拉取行情: 补全缺口（标的 + 基准并行请求）…",
        )

        async def _fill_one(sym: str):
            return await _merge_cached_with_yfinance(
                sym,
                timeframe,
                data_start,
                fetch_end,
                cached_map[sym],
                id_by_sym[sym],
                provider=provider,
            )

        filled_list = await asyncio.gather(*[_fill_one(s) for s in req.symbols])
        data: dict = {}
        for sym, df in zip(req.symbols, filled_list, strict=True):
            if not df.empty:
                data[sym] = {timeframe: df}
        if not data:
            raise ValueError(
                f"No data fetched for any symbol (timeframe={timeframe}, "
                f"{req.start_date}–{req.end_date}). "
                "Check symbols, network, and for 1h/lower TFs keep the range within ~730 days."
            )
        if bench_sym not in data:
            df_bench = await _fill_one(bench_sym)
            if not df_bench.empty:
                data[bench_sym] = {timeframe: df_bench}
        await _set_backtest_progress(backtest_id, "engine", "回测引擎计算中…")
        strategy = REGISTRY[req.strategy_id]()
        run_params = dict(req.parameters)
        run_params.setdefault("timeframe", timeframe)
        bt_fill = run_params.get("backtest_fill_mode")
        if bt_fill in (None, ""):
            bt_fill = getattr(type(strategy), "backtest_fill_mode", "next_open")
        fill_mode = str(bt_fill).strip()
        if fill_mode not in ("next_open", "same_close"):
            fill_mode = "next_open"
        engine = BacktestEngine(
            initial_capital=req.initial_capital,
            exit_policy=req.exit_policy,
            fill_mode=fill_mode,
        )
        if req.exit_policy is not None:
            run_params.setdefault(
                "entry_price_check_mode", req.exit_policy.entry_price_check_mode
            )
        metrics = await engine.run(
            strategy,
            req.symbols,
            run_params,
            data,
            timeframe,
            simulation_start=sim_start,
            simulation_end=sim_end,
            bar_progress=_engine_bar_progress(backtest_id),
        )
        from src.backtesting.benchmark import enrich_metrics_with_benchmark

        metrics = enrich_metrics_with_benchmark(
            metrics, data, benchmark_symbol=bench_sym, timeframe=timeframe
        )
        llm_text, llm_model = None, None
        await _set_backtest_progress(backtest_id, "llm_eval", "LLM 策略评估中…")
        try:
            evaluator = LLMEvaluator()
            llm_text, llm_model = await evaluator.evaluate(metrics, strategy.name, strategy.description)
        except Exception:
            _log.warning("LLM evaluation skipped (no API key or provider error)")
        async with async_session_factory() as session:
            for t in metrics.trades:
                session.add(BacktestTrade(
                    backtest_id=backtest_id, symbol=t.symbol, direction=t.direction,
                    quantity=t.quantity, entry_time=t.entry_time, entry_price=t.entry_price,
                    exit_time=t.exit_time, exit_price=t.exit_price,
                    pnl=t.pnl, pnl_pct=t.pnl_pct, hold_days=t.hold_days,
                    exit_reason=t.exit_reason, entry_signal=t.entry_signal,
                ))
            # Compute drawdown series from equity curve
            equity_series = metrics.equity_curve
            rolling_max = equity_series.expanding().max()
            drawdown_series = (equity_series - rolling_max) / rolling_max

            for ts, equity in equity_series.items():
                session.add(BacktestEquityCurve(
                    backtest_id=backtest_id, ts=ts,
                    equity=float(equity),
                    cash=float(equity),   # cash approximation (engine doesn't expose per-ts cash)
                    drawdown=float(drawdown_series[ts]),
                ))
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(
                    status="completed",
                    total_return=metrics.total_return,
                    annualized_return=metrics.annualized_return,
                    sharpe_ratio=metrics.sharpe_ratio,
                    max_drawdown=metrics.max_drawdown,
                    win_rate=metrics.win_rate,
                    profit_factor=metrics.profit_factor,
                    total_trades=metrics.total_trades,
                    avg_hold_days=metrics.avg_hold_days,
                    benchmark_total_return=metrics.benchmark_total_return,
                    alpha_vs_benchmark=metrics.alpha_vs_benchmark,
                    llm_evaluation=llm_text,
                    llm_model=llm_model,
                    completed_at=datetime.now(timezone.utc),
                    progress_phase=None,
                    progress_message=None,
                    progress_updated_at=None,
                )
            )
            await session.commit()
        await ws_manager.broadcast(
            "backtest_progress",
            {"backtest_id": backtest_id, "phase": None, "message": None, "status": "completed"},
        )
    except Exception as e:
        _log.exception("Backtest %d failed", backtest_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(
                    status="failed",
                    error_message=str(e),
                    progress_phase=None,
                    progress_message=None,
                    progress_updated_at=None,
                )
            )
            await session.commit()
        await ws_manager.broadcast(
            "backtest_progress",
            {"backtest_id": backtest_id, "phase": None, "message": None, "status": "failed"},
        )
