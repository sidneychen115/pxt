"""Shared HA cold-start lookback from daily history."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.strategies.ha_cache.calendar import lookback_start_months, lookback_start_weeks
from src.strategies.heikin_ashi import heikin_ashi, resample_to_monthly, resample_to_weekly_mon_fri

_TZ = ZoneInfo("America/Chicago")


def ha_lookback_months() -> int:
    return max(12, int(settings.ha_lookback_months))


def ha_lookback_weeks() -> int:
    return max(24, int(settings.ha_lookback_weeks))


def lookback_daily_start(anchor_day: date) -> date:
    return lookback_start_months(anchor_day, ha_lookback_months())


def lookback_daily_start_for_week(anchor_friday: date) -> date:
    """Daily history window for rebuilding a week anchor (same idea as month anchor)."""
    return lookback_start_weeks(anchor_friday, ha_lookback_weeks())


def friday_week_end_from_label(ts) -> date:
    """Map a weekly resample index label to its Friday week-end (CT)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert(_TZ)
    days_to_fri = (4 - t.weekday()) % 7
    fri = t + timedelta(days=days_to_fri)
    return fri.date()


def month_ha_open_close(
    daily: pd.DataFrame,
    year: int,
    month: int,
) -> tuple[float, float] | None:
    monthly = resample_to_monthly(daily)
    if monthly.empty:
        return None
    ha = heikin_ashi(monthly)
    for ts, row in ha.iterrows():
        local = pd.Timestamp(ts).tz_convert(_TZ)
        if local.year == year and local.month == month:
            return float(row["ha_open"]), float(row["ha_close"])
    return None


def week_ha_open_close(
    daily: pd.DataFrame,
    week_end: date,
) -> tuple[float, float] | None:
    """HA open/close for the Mon–Fri week ending on ``week_end`` (Friday, CT)."""
    weekly = resample_to_weekly_mon_fri(daily)
    if weekly.empty:
        return None
    ha = heikin_ashi(weekly)
    for ts, row in ha.iterrows():
        if friday_week_end_from_label(ts) == week_end:
            return float(row["ha_open"]), float(row["ha_close"])
    return None
