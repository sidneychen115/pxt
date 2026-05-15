"""Persistence for monthly HA open and weekly HA anchor rows."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import HaMonthAnchorCache, HaMonthOpenCache, HaWeekAnchorCache


async def get_month_open(
    session: AsyncSession,
    instrument_id: int,
    calendar_year: int,
    calendar_month: int,
) -> float | None:
    result = await session.execute(
        select(HaMonthOpenCache.ha_open).where(
            HaMonthOpenCache.instrument_id == instrument_id,
            HaMonthOpenCache.calendar_year == calendar_year,
            HaMonthOpenCache.calendar_month == calendar_month,
        )
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None


async def upsert_month_open(
    session: AsyncSession,
    instrument_id: int,
    calendar_year: int,
    calendar_month: int,
    ha_open: float,
) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        insert(HaMonthOpenCache)
        .values(
            instrument_id=instrument_id,
            calendar_year=calendar_year,
            calendar_month=calendar_month,
            ha_open=ha_open,
            computed_at=now,
        )
        .on_conflict_do_update(
            index_elements=["instrument_id", "calendar_year", "calendar_month"],
            set_={"ha_open": ha_open, "computed_at": now},
        )
    )
    await session.execute(stmt)


async def get_month_anchor(
    session: AsyncSession,
    instrument_id: int,
) -> HaMonthAnchorCache | None:
    result = await session.execute(
        select(HaMonthAnchorCache).where(
            HaMonthAnchorCache.instrument_id == instrument_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_month_anchor(
    session: AsyncSession,
    instrument_id: int,
    calendar_year: int,
    calendar_month: int,
    ha_open: float,
    ha_close: float,
) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        insert(HaMonthAnchorCache)
        .values(
            instrument_id=instrument_id,
            calendar_year=calendar_year,
            calendar_month=calendar_month,
            ha_open=ha_open,
            ha_close=ha_close,
            computed_at=now,
        )
        .on_conflict_do_update(
            index_elements=["instrument_id"],
            set_={
                "calendar_year": calendar_year,
                "calendar_month": calendar_month,
                "ha_open": ha_open,
                "ha_close": ha_close,
                "computed_at": now,
            },
        )
    )
    await session.execute(stmt)


async def get_week_anchor(
    session: AsyncSession,
    instrument_id: int,
) -> HaWeekAnchorCache | None:
    result = await session.execute(
        select(HaWeekAnchorCache).where(
            HaWeekAnchorCache.instrument_id == instrument_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_week_anchor(
    session: AsyncSession,
    instrument_id: int,
    week_end_date: date,
    ha_open: float,
    ha_close: float,
) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        insert(HaWeekAnchorCache)
        .values(
            instrument_id=instrument_id,
            week_end_date=week_end_date,
            ha_open=ha_open,
            ha_close=ha_close,
            computed_at=now,
        )
        .on_conflict_do_update(
            index_elements=["instrument_id"],
            set_={
                "week_end_date": week_end_date,
                "ha_open": ha_open,
                "ha_close": ha_close,
                "computed_at": now,
            },
        )
    )
    await session.execute(stmt)
