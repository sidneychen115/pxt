from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from src.core.database import get_session, async_session_factory
from src.core.models import Backtest, BacktestTrade, BacktestEquityCurve, Strategy
from src.api.websocket import ws_manager
from src.backtesting.exit_policy import ExitPolicy

if TYPE_CHECKING:
    import pandas as pd

router = APIRouter()
_log = logging.getLogger(__name__)

# yfinance intraday caps (see YFinanceProvider); used for validation and messages
_INTRADAY_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h"})


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
    session: AsyncSession = Depends(get_session),
):
    # Do not load llm_evaluation (often huge TEXT / TOAST) for the list — it was dominating I/O and JSON size.
    query = (
        select(Backtest)
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
    session: AsyncSession = Depends(get_session),
):
    started = datetime.now(timezone.utc)
    bt = Backtest(
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
async def get_backtest(backtest_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Backtest).where(Backtest.id == backtest_id))
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(404, "Backtest not found.")
    return _backtest_summary(bt)


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: int,
    sort_by: str = "entry_time",
    order: str = "asc",
    session: AsyncSession = Depends(get_session),
):
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
    return [
        {
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "quantity": float(t.quantity), "entry_time": t.entry_time,
            "entry_price": float(t.entry_price),
            "exit_time": t.exit_time,
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
    session: AsyncSession = Depends(get_session),
):
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
        {"ts": p.ts, "equity": float(p.equity),
         "cash": float(p.cash), "drawdown": float(p.drawdown) if p.drawdown else None}
        for p in points
    ]


_DAILY_LIKE_TIMEFRAMES = frozenset({"1d", "1wk", "1mo"})


def _encode_ohlc_bar_time(timeframe: str, ts: datetime) -> str | int:
    """Chart time: business-day string for daily+ aggregates, UTC unix seconds for intraday."""
    if timeframe in _DAILY_LIKE_TIMEFRAMES:
        t = ts
        if getattr(ts, "tzinfo", None):
            t = ts.astimezone(timezone.utc)
        return t.strftime("%Y-%m-%d")
    t = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
    if getattr(t, "tzinfo", None) is None:
        t = t.replace(tzinfo=timezone.utc)
    else:
        t = t.astimezone(timezone.utc)
    return int(t.timestamp())


def _trade_event_bar_index(index: pd.DatetimeIndex, event_time: datetime) -> int | None:
    import pandas as pd

    if index.empty or event_time is None:
        return None
    t = pd.Timestamp(event_time)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
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
    session: AsyncSession = Depends(get_session),
):
    """OHLC bars for one symbol over the backtest window (same fetch path as the engine)."""
    result = await session.execute(select(Backtest).where(Backtest.id == backtest_id))
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(404, "Backtest not found.")
    if symbol not in bt.symbols:
        raise HTTPException(400, "symbol is not part of this backtest.")
    if bt.status != "completed":
        raise HTTPException(409, "OHLC is only available for completed backtests.")

    timeframe = await _resolve_timeframe_from_params(bt.strategy_id, bt.parameters or {})
    start = datetime(bt.start_date.year, bt.start_date.month, bt.start_date.day, tzinfo=timezone.utc)
    end = datetime(bt.end_date.year, bt.end_date.month, bt.end_date.day, tzinfo=timezone.utc) + timedelta(days=1)
    if timeframe in _INTRADAY_TIMEFRAMES:
        days_span = (end - start).days
        if days_span > 730:
            raise HTTPException(
                400,
                f"yfinance intraday data ({timeframe}) is limited to about 730 days; this range is {days_span} days.",
            )

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
        "created_at": bt.created_at, "completed_at": bt.completed_at,
        "parameters": bt.parameters or {},
        "exit_policy": bt.exit_policy,
        "progress_phase": bt.progress_phase,
        "progress_message": bt.progress_message,
        "progress_updated_at": bt.progress_updated_at,
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
            "progress_updated_at": now.isoformat(),
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
    import pandas as pd
    from src.data.providers.yfinance_provider import YFinanceProvider
    from src.data.repository import get_bars_range, save_bars, upsert_instrument

    provider = YFinanceProvider()

    async with async_session_factory() as session:
        instrument = await upsert_instrument(session, sym, "stock")
        await session.commit()
        instrument_id = instrument.id
        cached = await get_bars_range(session, instrument_id, timeframe, start, end)

    async def _fetch_and_save(fetch_start: datetime, fetch_end: datetime) -> "pd.DataFrame":
        df = await provider.get_bars(sym, timeframe, fetch_start, fetch_end)
        if not df.empty:
            async with async_session_factory() as session:
                await save_bars(session, instrument_id, timeframe, df)
                await session.commit()
        return df

    if cached.empty:
        return await _fetch_and_save(start, end)

    parts = [cached]

    # Fill missing head
    first_cached = cached.index[0]
    if first_cached.to_pydatetime().replace(tzinfo=timezone.utc) > start:
        df_head = await _fetch_and_save(start, first_cached.to_pydatetime().replace(tzinfo=timezone.utc))
        if not df_head.empty:
            parts.insert(0, df_head)

    # Fill missing tail
    last_cached = cached.index[-1]
    if last_cached.to_pydatetime().replace(tzinfo=timezone.utc) < end:
        df_tail = await _fetch_and_save(last_cached.to_pydatetime().replace(tzinfo=timezone.utc), end)
        if not df_tail.empty:
            df_tail = df_tail[df_tail.index > last_cached]
            if not df_tail.empty:
                parts.append(df_tail)

    if len(parts) == 1:
        return parts[0]
    return pd.concat(parts).sort_index()


async def _run_backtest(backtest_id: int, req: BacktestRequest):
    from src.backtesting.engine import BacktestEngine
    from src.backtesting.evaluator import LLMEvaluator
    from src.strategies.registry import REGISTRY, discover_strategies
    discover_strategies()
    try:
        timeframe = await _resolve_backtest_timeframe(req)
        start = datetime(req.start_date.year, req.start_date.month, req.start_date.day, tzinfo=timezone.utc)
        # Exclusive end at start of day after end_date so [start, end) includes all bars on end_date
        # (avoids empty range when start_date == end_date and fixes yfinance daily/hourly end semantics).
        end = datetime(req.end_date.year, req.end_date.month, req.end_date.day, tzinfo=timezone.utc) + timedelta(days=1)
        if start >= end:
            raise ValueError("Invalid date range: start_date must be on or before end_date.")
        if timeframe in _INTRADAY_TIMEFRAMES:
            days_span = (end - start).days
            if days_span > 730:
                raise ValueError(
                    f"yfinance intraday data ({timeframe}) is limited to about 730 days; "
                    f"this range is {days_span} days. Shorten the backtest window."
                )
        data: dict = {}
        n_sym = len(req.symbols)
        await _set_backtest_progress(
            backtest_id,
            "fetching_data",
            f"拉取行情数据 (0/{n_sym})" if n_sym else "拉取行情数据",
        )
        for i, sym in enumerate(req.symbols, start=1):
            await _set_backtest_progress(
                backtest_id,
                "fetching_data",
                f"拉取行情数据: {sym} ({i}/{n_sym})",
            )
            df = await _fetch_with_cache(sym, timeframe, start, end)
            if not df.empty:
                data[sym] = {timeframe: df}
        if not data:
            raise ValueError(
                f"No data fetched for any symbol (timeframe={timeframe}, "
                f"{req.start_date}–{req.end_date}). "
                "Check symbols, network, and for 1h/lower TFs keep the range within ~730 days."
            )
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
            bar_progress=_engine_bar_progress(backtest_id),
        )
        from src.backtesting.benchmark import enrich_metrics_with_benchmark

        bench_sym = str(req.parameters.get("benchmark_symbol", "SPY"))
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
