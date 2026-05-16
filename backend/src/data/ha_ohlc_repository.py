"""Persistence for finalized / partial HA OHLC bars."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import HaOhlcBar


async def upsert_ha_bars(session: AsyncSession, rows: list[dict]) -> None:
    """Insert or update rows on (instrument_id, timeframe, bar_time)."""
    if not rows:
        return
    ins = pg_insert(HaOhlcBar).values(rows)
    stmt = ins.on_conflict_do_update(
        index_elements=["instrument_id", "timeframe", "bar_time"],
        set_={
            "ha_open": ins.excluded.ha_open,
            "ha_high": ins.excluded.ha_high,
            "ha_low": ins.excluded.ha_low,
            "ha_close": ins.excluded.ha_close,
            "is_final": ins.excluded.is_final,
            "source": ins.excluded.source,
            "computed_at": ins.excluded.computed_at,
        },
    )
    await session.execute(stmt)


async def delete_partial_ha_rows(
    session: AsyncSession, instrument_id: int, timeframe: str
) -> None:
    """Remove in-progress bars (e.g. before full recompute); optional housekeeping."""
    await session.execute(
        delete(HaOhlcBar).where(
            HaOhlcBar.instrument_id == instrument_id,
            HaOhlcBar.timeframe == timeframe,
            HaOhlcBar.is_final.is_(False),
        )
    )


async def get_last_finalized_ha_bar(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
) -> HaOhlcBar | None:
    """Latest completed bar (``is_final=True``) by ``bar_time``."""
    result = await session.execute(
        select(HaOhlcBar)
        .where(
            HaOhlcBar.instrument_id == instrument_id,
            HaOhlcBar.timeframe == timeframe,
            HaOhlcBar.is_final.is_(True),
        )
        .order_by(HaOhlcBar.bar_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_partial_ha_bar(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
) -> HaOhlcBar | None:
    """In-progress period row (``is_final=False``), if present."""
    result = await session.execute(
        select(HaOhlcBar)
        .where(
            HaOhlcBar.instrument_id == instrument_id,
            HaOhlcBar.timeframe == timeframe,
            HaOhlcBar.is_final.is_(False),
        )
        .order_by(HaOhlcBar.bar_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_ha_bar_at_or_before(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    bar_time,
    *,
    finalized_only: bool = True,
) -> HaOhlcBar | None:
    """Point-in-time helper: last bar with ``bar_time`` ≤ anchor (e.g. backtest day)."""
    q = select(HaOhlcBar).where(
        HaOhlcBar.instrument_id == instrument_id,
        HaOhlcBar.timeframe == timeframe,
        HaOhlcBar.bar_time <= bar_time,
    )
    if finalized_only:
        q = q.where(HaOhlcBar.is_final.is_(True))
    q = q.order_by(HaOhlcBar.bar_time.desc()).limit(1)
    result = await session.execute(q)
    return result.scalar_one_or_none()
