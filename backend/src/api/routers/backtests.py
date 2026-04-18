from datetime import date, datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session, async_session_factory
from src.core.models import Backtest, BacktestTrade, BacktestEquityCurve
from src.api.websocket import ws_manager
from src.backtesting.exit_policy import ExitPolicy

router = APIRouter()


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
    query = select(Backtest).order_by(desc(Backtest.created_at)).limit(limit)
    if strategy_id:
        query = query.where(Backtest.strategy_id == strategy_id)
    result = await session.execute(query)
    return [_backtest_summary(b) for b in result.scalars().all()]


@router.post("/")
async def trigger_backtest(
    req: BacktestRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    bt = Backtest(
        strategy_id=req.strategy_id,
        start_date=req.start_date,
        end_date=req.end_date,
        symbols=req.symbols,
        initial_capital=req.initial_capital,
        parameters=req.parameters,
        exit_policy=req.exit_policy.model_dump(mode="json") if req.exit_policy else None,
        status="running",
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
    _ALLOWED_SORT = {"entry_time", "exit_time", "pnl", "pnl_pct", "symbol"}
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
async def get_equity_curve(backtest_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(BacktestEquityCurve)
        .where(BacktestEquityCurve.backtest_id == backtest_id)
        .order_by(BacktestEquityCurve.ts)
    )
    points = result.scalars().all()
    return [
        {"ts": p.ts, "equity": float(p.equity),
         "cash": float(p.cash), "drawdown": float(p.drawdown) if p.drawdown else None}
        for p in points
    ]


def _backtest_summary(bt: Backtest) -> dict:
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
        "llm_evaluation": bt.llm_evaluation,
        "llm_model": bt.llm_model,
        "created_at": bt.created_at, "completed_at": bt.completed_at,
        "parameters": bt.parameters or {},
        "exit_policy": bt.exit_policy,
        "progress_phase": bt.progress_phase,
        "progress_message": bt.progress_message,
    }


async def _set_backtest_progress(backtest_id: int, phase: str, message: str | None = None) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(Backtest).where(Backtest.id == backtest_id).values(
                progress_phase=phase,
                progress_message=message,
            )
        )
        await session.commit()
    await ws_manager.broadcast(
        "backtest_progress",
        {"backtest_id": backtest_id, "phase": phase, "message": message},
    )


async def _fetch_with_cache(sym: str, timeframe: str, start: datetime, end: datetime) -> "pd.DataFrame":
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
        start = datetime(req.start_date.year, req.start_date.month, req.start_date.day, tzinfo=timezone.utc)
        end = datetime(req.end_date.year, req.end_date.month, req.end_date.day, tzinfo=timezone.utc)
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
            df = await _fetch_with_cache(sym, "1d", start, end)
            if not df.empty:
                data[sym] = {"1d": df}
        if not data:
            raise ValueError("No data fetched for any symbol.")
        await _set_backtest_progress(backtest_id, "engine", "回测引擎计算中…")
        strategy = REGISTRY[req.strategy_id]()
        engine = BacktestEngine(
            initial_capital=req.initial_capital,
            exit_policy=req.exit_policy,
        )
        metrics = await engine.run(strategy, req.symbols, req.parameters, data, "1d")
        llm_text, llm_model = None, None
        await _set_backtest_progress(backtest_id, "llm_eval", "LLM 策略评估中…")
        try:
            evaluator = LLMEvaluator()
            llm_text, llm_model = await evaluator.evaluate(metrics, strategy.name, strategy.description)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("LLM evaluation skipped (no API key or provider error)")
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
                    llm_evaluation=llm_text,
                    llm_model=llm_model,
                    completed_at=datetime.now(timezone.utc),
                    progress_phase=None,
                    progress_message=None,
                )
            )
            await session.commit()
        await ws_manager.broadcast(
            "backtest_progress",
            {"backtest_id": backtest_id, "phase": None, "message": None, "status": "completed"},
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Backtest %d failed", backtest_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(
                    status="failed",
                    error_message=str(e),
                    progress_phase=None,
                    progress_message=None,
                )
            )
            await session.commit()
        await ws_manager.broadcast(
            "backtest_progress",
            {"backtest_id": backtest_id, "phase": None, "message": None, "status": "failed"},
        )
