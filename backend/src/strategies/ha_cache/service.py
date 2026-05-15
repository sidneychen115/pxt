"""Minimal daily-window HA paths for ha_month_week_band live runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Instrument
from src.data import repository
from src.strategies.ha_cache import repository as ha_repo
from src.strategies.ha_cache.calendar import (
    as_of_local,
    current_calendar_month,
    current_week_start,
    last_completed_week_end,
    local_date_to_utc_range,
    month_bounds_local,
    previous_calendar_month,
)
from src.strategies.ha_cache.bars import mon_fri_bars
from src.strategies.ha_cache.lookback import (
    lookback_daily_start,
    lookback_daily_start_for_week,
    month_ha_open_close,
    week_ha_open_close,
)
from src.strategies.ha_cache.ohlc_agg import aggregate_ohlc
from src.strategies.heikin_ashi import heikin_ashi_single_bar

_WEEK_LOOKBACK_PAD = 3


async def _instrument_id(session: AsyncSession, symbol: str) -> int | None:
    result = await session.execute(
        select(Instrument.id).where(Instrument.symbol == symbol)
    )
    return result.scalar_one_or_none()


async def _load_daily_range(
    session: AsyncSession,
    instrument_id: int,
    start: date,
    end_exclusive: date,
) -> pd.DataFrame:
    start_utc, end_utc = local_date_to_utc_range(start, end_exclusive)
    return await repository.get_bars_range(session, instrument_id, "1d", start_utc, end_utc)


async def load_dailies_current_week(
    session: AsyncSession,
    symbol: str,
    *,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Daily bars for the in-progress Mon–Fri week only (+ small pad)."""
    instrument_id = await _instrument_id(session, symbol)
    if instrument_id is None:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    as_of = as_of or datetime.now(timezone.utc)
    week_start = current_week_start(as_of)
    load_start = week_start - timedelta(days=_WEEK_LOOKBACK_PAD)
    end_exclusive = as_of_local(as_of) + timedelta(days=1)
    daily = await _load_daily_range(session, instrument_id, load_start, end_exclusive)
    return mon_fri_bars(daily)


async def _ensure_month_anchor(
    session: AsyncSession,
    instrument_id: int,
    completed_year: int,
    completed_month: int,
) -> tuple[float, float] | None:
    """Rebuild last completed month HA from ``ha_lookback_months`` of dailies."""
    _, end_exclusive = month_bounds_local(completed_year, completed_month)
    start = lookback_daily_start(date(completed_year, completed_month, 1))
    daily = await _load_daily_range(session, instrument_id, start, end_exclusive)
    pair = month_ha_open_close(daily, completed_year, completed_month)
    if pair is None:
        return None
    ha_o, ha_c = pair
    await ha_repo.upsert_month_anchor(
        session, instrument_id, completed_year, completed_month, ha_o, ha_c
    )
    return ha_o, ha_c


async def month_ha_open(
    session: AsyncSession,
    symbol: str,
    *,
    as_of: datetime | None = None,
) -> float | None:
    """Current calendar month HA open; cached per month."""
    instrument_id = await _instrument_id(session, symbol)
    if instrument_id is None:
        return None

    as_of = as_of or datetime.now(timezone.utc)
    year, month = current_calendar_month(as_of)

    cached = await ha_repo.get_month_open(session, instrument_id, year, month)
    if cached is not None:
        return cached

    comp_y, comp_m = previous_calendar_month(year, month)
    anchor = await ha_repo.get_month_anchor(session, instrument_id)
    if anchor is not None and anchor.calendar_year == comp_y and anchor.calendar_month == comp_m:
        prev_o, prev_c = float(anchor.ha_open), float(anchor.ha_close)
    else:
        rebuilt = await _ensure_month_anchor(session, instrument_id, comp_y, comp_m)
        if rebuilt is None:
            return None
        prev_o, prev_c = rebuilt

    bench = (prev_o + prev_c) / 2.0
    await ha_repo.upsert_month_open(session, instrument_id, year, month, bench)
    await session.commit()
    return bench


async def _ensure_week_anchor(
    session: AsyncSession,
    instrument_id: int,
    completed_friday: date,
) -> tuple[float, float] | None:
    """Rebuild last completed Mon–Fri week HA from ``ha_lookback_weeks`` of dailies."""
    end_exclusive = completed_friday + timedelta(days=1)
    start = lookback_daily_start_for_week(completed_friday)
    daily = await _load_daily_range(session, instrument_id, start, end_exclusive)
    pair = week_ha_open_close(daily, completed_friday)
    if pair is None:
        return None
    ha_o, ha_c = pair
    await ha_repo.upsert_week_anchor(
        session, instrument_id, completed_friday, ha_o, ha_c
    )
    return ha_o, ha_c


async def week_ha_close(
    session: AsyncSession,
    symbol: str,
    daily: pd.DataFrame,
    *,
    as_of: datetime | None = None,
) -> float | None:
    """In-progress week HA close; ``daily`` should be current-week bars (snapshot close applied)."""
    as_of = as_of or datetime.now(timezone.utc)
    daily = mon_fri_bars(daily)
    ohlc = aggregate_ohlc(daily)
    if ohlc is None:
        daily = await load_dailies_current_week(session, symbol, as_of=as_of)
        ohlc = aggregate_ohlc(daily)
    if ohlc is None:
        return None

    o, h, l, c = ohlc
    instrument_id = await _instrument_id(session, symbol)
    if instrument_id is None:
        return None

    completed_friday = last_completed_week_end(as_of)
    anchor = await ha_repo.get_week_anchor(session, instrument_id)
    if anchor is not None and anchor.week_end_date == completed_friday:
        prev_o, prev_c = float(anchor.ha_open), float(anchor.ha_close)
    else:
        rebuilt = await _ensure_week_anchor(session, instrument_id, completed_friday)
        if rebuilt is None:
            return None
        prev_o, prev_c = rebuilt
        await session.commit()

    *_, ha_close = heikin_ashi_single_bar(o, h, l, c, prev_o, prev_c)
    return ha_close
