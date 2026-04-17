from datetime import date, datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session, async_session_factory
from src.core.models import Backtest, BacktestTrade, BacktestEquityCurve

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_id: str
    start_date: date
    end_date: date
    symbols: list[str]
    initial_capital: float = 100_000.0
    parameters: dict = {}


@router.get("/")
async def list_backtests(
    strategy_id: str | None = None,
    limit: int = 20,
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
    col = getattr(BacktestTrade, sort_by, BacktestTrade.entry_time)
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
    }


async def _run_backtest(backtest_id: int, req: BacktestRequest):
    from src.backtesting.engine import BacktestEngine
    from src.backtesting.evaluator import LLMEvaluator
    from src.data.providers.yfinance_provider import YFinanceProvider
    from src.strategies.registry import REGISTRY, discover_strategies
    discover_strategies()
    try:
        provider = YFinanceProvider()
        start = datetime(req.start_date.year, req.start_date.month, req.start_date.day, tzinfo=timezone.utc)
        end = datetime(req.end_date.year, req.end_date.month, req.end_date.day, tzinfo=timezone.utc)
        data: dict = {}
        for sym in req.symbols:
            df = await provider.get_bars(sym, "1d", start, end)
            if not df.empty:
                data[sym] = {"1d": df}
        if not data:
            raise ValueError("No data fetched for any symbol.")
        strategy = REGISTRY[req.strategy_id]()
        engine = BacktestEngine(initial_capital=req.initial_capital)
        metrics = await engine.run(strategy, req.symbols, req.parameters, data, "1d")
        evaluator = LLMEvaluator()
        llm_text, llm_model = await evaluator.evaluate(metrics, strategy.name, strategy.description)
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
                )
            )
            await session.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Backtest %d failed", backtest_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(status="failed")
            )
            await session.commit()
