"""America/Chicago calendar boundaries for HA week (Mon–Fri) and month buckets."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Matches default ``settings.timezone`` (America/Chicago).
_TZ = ZoneInfo("America/Chicago")


def as_of_local(as_of: datetime) -> date:
    if as_of.tzinfo is None:
        return as_of.date()
    return as_of.astimezone(_TZ).date()


def current_week_start(as_of: datetime) -> date:
    """Monday starting the Mon–Fri trading week that contains ``as_of`` (CT)."""
    local = as_of_local(as_of)
    weekday = local.weekday()
    if weekday <= 4:
        return local - timedelta(days=weekday)
    # Sat/Sun: still the Mon–Fri block that ended on the most recent Friday
    return local - timedelta(days=weekday)


def last_completed_week_end(as_of: datetime) -> date:
    """Friday ending the last fully completed Mon–Fri week before the in-progress week."""
    local = as_of_local(as_of)
    weekday = local.weekday()
    if weekday <= 4:
        this_monday = local - timedelta(days=weekday)
        return this_monday - timedelta(days=3)
    # Sat/Sun: last Friday
    return local - timedelta(days=weekday - 4)


def current_calendar_month(as_of: datetime) -> tuple[int, int]:
    local = as_of_local(as_of)
    return local.year, local.month


def previous_calendar_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def lookback_start_months(anchor: date, months: int) -> date:
    """First day of the calendar month ``months`` before ``anchor``'s month."""
    y, m = anchor.year, anchor.month - months
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def lookback_start_weeks(anchor_friday: date, weeks: int) -> date:
    """Calendar start date ``weeks`` before ``anchor_friday`` (for daily bar load)."""
    return anchor_friday - timedelta(weeks=weeks)


def month_bounds_local(year: int, month: int) -> tuple[date, date]:
    """Inclusive start, exclusive end (next month) in local calendar."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def local_date_to_utc_range(start: date, end_exclusive: date) -> tuple[datetime, datetime]:
    """Query range [start, end_exclusive) as UTC datetimes."""
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=_TZ).astimezone(timezone.utc)
    end_dt = datetime.combine(end_exclusive, datetime.min.time(), tzinfo=_TZ).astimezone(
        timezone.utc
    )
    return start_dt, end_dt
