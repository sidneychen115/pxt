"""PostgreSQL advisory lock so only one API worker runs scheduler / stale reaper."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text

from src.core.database import engine

log = logging.getLogger(__name__)

# Arbitrary cluster-wide id for "embedded background leader" (scheduler + stale reaper).
_PXT_API_LEADER_LOCK_KEY = 84_920_134


@asynccontextmanager
async def api_background_leader() -> AsyncIterator[bool]:
    """Yield True if this process holds the leader lock for the app lifetime."""
    conn = await engine.connect()
    is_leader = False
    try:
        result = await conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": _PXT_API_LEADER_LOCK_KEY},
        )
        is_leader = bool(result.scalar())
        if is_leader:
            log.info("This API worker is the background-task leader (scheduler + stale reaper).")
        else:
            log.info("Another API worker holds the background-task leader lock.")
        yield is_leader
    finally:
        if is_leader:
            try:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _PXT_API_LEADER_LOCK_KEY},
                )
            finally:
                await conn.close()
        elif not conn.closed:
            await conn.close()
