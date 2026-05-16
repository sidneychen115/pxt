"""Quarterly revenue fundamentals (SEC XBRL) persistence."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.models import FundamentalRevenueQuarterly


def calendar_date_as_of(as_of: date | datetime) -> date:
    """Strategy calendar day in ``settings.timezone`` (naive ``datetime`` treated as UTC)."""
    if isinstance(as_of, datetime):
        dt = as_of
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(settings.timezone)).date()
    return as_of


async def insert_revenue_quarterly_ignore_conflicts(
    session: AsyncSession, rows: list[dict]
) -> None:
    """Bulk insert; skip rows already present (same instrument + accession)."""
    if not rows:
        return
    stmt = pg_insert(FundamentalRevenueQuarterly).values(rows).on_conflict_do_nothing(
        constraint="uq_fund_rev_inst_accn"
    )
    await session.execute(stmt)


async def get_latest_quarterly_revenue_as_of(
    session: AsyncSession,
    instrument_id: int,
    as_of: date | datetime,
) -> FundamentalRevenueQuarterly | None:
    """Latest ``Revenues`` fact already filed on or before ``as_of`` (PIT, calendar date in CT).

    Orders by ``filing_date`` then ``period_end`` descending.
    """
    d = calendar_date_as_of(as_of)
    result = await session.execute(
        select(FundamentalRevenueQuarterly)
        .where(
            FundamentalRevenueQuarterly.instrument_id == instrument_id,
            FundamentalRevenueQuarterly.filing_date <= d,
        )
        .order_by(
            FundamentalRevenueQuarterly.filing_date.desc(),
            FundamentalRevenueQuarterly.period_end.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
