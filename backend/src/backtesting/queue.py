"""DB-backed backtest job queue (API enqueues, worker claims)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update

from src.api.routers.backtests import BacktestRequest
from src.backtesting.exit_policy import ExitPolicy
from src.core.database import async_session_factory
from src.core.models import Backtest


def backtest_request_from_row(bt: Backtest) -> BacktestRequest:
    ep = None
    if bt.exit_policy:
        ep = ExitPolicy.model_validate(bt.exit_policy)
    return BacktestRequest(
        strategy_id=bt.strategy_id,
        start_date=bt.start_date,
        end_date=bt.end_date,
        symbols=list(bt.symbols),
        initial_capital=float(bt.initial_capital),
        parameters=dict(bt.parameters or {}),
        exit_policy=ep,
    )


async def count_running_backtests() -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Backtest).where(Backtest.status == "running")
        )
        return int(result.scalar_one())


async def count_queued_backtests() -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Backtest).where(Backtest.status == "queued")
        )
        return int(result.scalar_one())


async def refresh_queued_backtests(*, running_count: int) -> None:
    """Heartbeat for queued rows so they are not mistaken for dead jobs while waiting."""
    n = await count_queued_backtests()
    if n == 0:
        return
    if running_count > 0:
        msg = f"排队中：当前有 {running_count} 个回测正在运行，其余任务按提交顺序等待空位…"
    else:
        msg = "排队中：等待 worker 领取…"
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        await session.execute(
            update(Backtest)
            .where(Backtest.status == "queued")
            .values(progress_message=msg, progress_updated_at=now)
        )
        await session.commit()


async def claim_next_queued_backtest() -> tuple[int, BacktestRequest] | None:
    """Atomically take the oldest ``queued`` row and mark it ``running``."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Backtest)
            .where(Backtest.status == "queued")
            .order_by(Backtest.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        bt = result.scalar_one_or_none()
        if bt is None:
            return None
        now = datetime.now(timezone.utc)
        await session.execute(
            update(Backtest)
            .where(Backtest.id == bt.id)
            .values(
                status="running",
                progress_phase="worker",
                progress_message="回测 worker 已领取任务…",
                progress_updated_at=now,
            )
        )
        await session.commit()
        return bt.id, backtest_request_from_row(bt)
