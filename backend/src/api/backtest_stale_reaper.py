"""Mark long-stalled `running` backtests as failed (e.g. server/worker died)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from src.api.websocket import ws_manager
from src.core.database import async_session_factory
from src.core.models import Backtest

log = logging.getLogger(__name__)


def stale_after() -> timedelta:
    sec = int(os.environ.get("BACKTEST_STALE_AFTER_SECONDS", "1800"))
    return timedelta(seconds=max(120, sec))


async def run_backtest_stale_reaper(*, interval_sec: float = 45.0) -> None:
    """Background loop: any `running` row with no progress heartbeat for stale_after() → failed."""
    while True:
        await asyncio.sleep(interval_sec)
        try:
            await _reap_once()
        except Exception:
            log.exception("backtest stale reaper tick failed")


async def _reap_once() -> None:
    cutoff = datetime.now(timezone.utc) - stale_after()
    msg = (
        f"运行任务超过 {int(stale_after().total_seconds())} 秒未上报进度，"
        "可能进程已退出、服务已重启或任务被中断。"
    )
    async with async_session_factory() as session:
        result = await session.execute(
            select(Backtest.id).where(
                Backtest.status == "running",
                or_(
                    (Backtest.progress_updated_at.is_not(None))
                    & (Backtest.progress_updated_at < cutoff),
                    Backtest.progress_updated_at.is_(None) & (Backtest.created_at < cutoff),
                ),
            )
        )
        ids = [row[0] for row in result.all()]
        if not ids:
            return
        now = datetime.now(timezone.utc)
        await session.execute(
            update(Backtest)
            .where(Backtest.id.in_(ids))
            .values(
                status="failed",
                error_message=msg,
                progress_phase=None,
                progress_message=None,
                progress_updated_at=None,
                completed_at=now,
            )
        )
        await session.commit()

    for bid in ids:
        await ws_manager.broadcast(
            "backtest_progress",
            {
                "backtest_id": bid,
                "phase": None,
                "message": None,
                "status": "failed",
            },
        )
    log.warning("Marked %d stale running backtest(s) as failed: %s", len(ids), ids)
