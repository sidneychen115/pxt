"""Structured system events for a single strategy scheduler run."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import SystemEvent

_EVENT_TYPE = "strategy_run"


class StrategyRunLogger:
    """Emits start / step / complete / fail rows linked by ``run_id`` in ``details``."""

    def __init__(self, session: AsyncSession, strategy_id: str) -> None:
        self._session = session
        self.strategy_id = strategy_id
        self.run_id = uuid.uuid4().hex[:12]
        self._started_at = datetime.now(timezone.utc)

    def _base_details(self) -> dict:
        return {"run_id": self.run_id, "strategy_id": self.strategy_id}

    async def start(self, message: str, **extra) -> None:
        await self._emit("info", message, phase="start", **extra)

    async def step(self, message: str, *, level: str = "info", **extra) -> None:
        await self._emit(level, message, phase="step", **extra)

    async def complete(self, message: str, **extra) -> None:
        elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        await self._emit(
            "info",
            message,
            phase="complete",
            elapsed_s=round(elapsed, 2),
            **extra,
        )

    async def fail(self, message: str, *, level: str = "error", **extra) -> None:
        elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        await self._emit(
            level,
            message,
            phase="fail",
            elapsed_s=round(elapsed, 2),
            **extra,
        )

    async def _emit(self, level: str, message: str, *, phase: str, **extra) -> None:
        details = {
            **self._base_details(),
            "phase": phase,
            "started_at": self._started_at.isoformat(),
            **extra,
        }
        self._session.add(
            SystemEvent(
                event_type=_EVENT_TYPE,
                level=level,
                message=message,
                details=details,
                created_at=datetime.now(timezone.utc),
            )
        )
        await self._session.commit()
