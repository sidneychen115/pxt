"""Project clock: anchored in ``settings.timezone`` (default America/Chicago).

Postgres TIMESTAMPTZ stores absolute instants. By convention:

- Daily / daily-like OHLC bars (1d / 1wk / 1mo from Yahoo) use **midnight local** on that
  **session calendar date** in the app timezone, so UTC storage matches how US sessions are
  labelled in the UI without local-browser drift.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.core.config import settings


def app_zone() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def utc_zone() -> ZoneInfo:
    return timezone.utc


def daily_bar_timestamp_for_session_date(session_date: date) -> datetime:
    """Bar row instant for OHLC keyed by US-equity calendar day (Yahoo trade date labels)."""
    return datetime.combine(session_date, time.min, tzinfo=app_zone())


def session_date_from_utc_naive_daily_label(dt: datetime) -> date:
    """Legacy/normalized Yahoo index: UTC-midnight bar → calendar date used as session label."""
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(utc_zone()).date()


def backtest_span_inclusive(
    start_date: date,
    end_date: date,
) -> tuple[datetime, datetime]:
    """[start_dt, end_exclusive) for querying daily bars spanning ``start_date``…``end_date`` inclusive."""
    start_dt = daily_bar_timestamp_for_session_date(start_date)
    end_exclusive = daily_bar_timestamp_for_session_date(end_date + timedelta(days=1))
    return start_dt, end_exclusive


def api_iso(dt: datetime | None) -> str | None:
    """Serialize API timestamps explicitly in app timezone ISO-8601 (offset included)."""
    if dt is None:
        return None
    tz = utc_zone()
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=tz)
    return aware.astimezone(app_zone()).isoformat()


def equity_daily_session_calendar_date(bar_time: datetime) -> date:
    """Trading session calendar date for US-style daily OHLC rows (:data:`settings.timezone`).

    - Preferred storage is :func:`daily_bar_timestamp_for_session_date` → local midnight rows.
    - Yahoo Finance daily indices are UTC midnight; caches sometimes keep the instant shifted
      by -6h (CST) / -5h (CDT) evening, i.e. ``18:00`` / ``19:00`` UTC. Those map to the **next**
      UTC calendar date as the labelled session / trade date (Fri close row → Mon label pattern).
    - For any other wall time, pick the session date whose canonical anchor is nearest in absolute
      UTC time; ties favor the later calendar day (midpoint between two anchors).
    """
    tz = utc_zone()
    aware = bar_time if bar_time.tzinfo is not None else bar_time.replace(tzinfo=tz)
    chi = aware.astimezone(app_zone())
    if (
        chi.hour == 0
        and chi.minute == 0
        and chi.second == 0
        and chi.microsecond == 0
    ):
        return chi.date()
    u = aware.astimezone(tz)
    if u.minute == 0 and u.second == 0 and u.microsecond == 0:
        if u.hour == 0:
            return u.date()
        if u.hour in (18, 19):
            return u.date() + timedelta(days=1)
    d0 = chi.date()
    best_d = d0
    best_diff: float = float("inf")
    for delta in range(-3, 4):
        d = d0 + timedelta(days=delta)
        anchor = daily_bar_timestamp_for_session_date(d)
        diff = abs((anchor - u).total_seconds())
        if diff < best_diff or (diff == best_diff and d > best_d):
            best_diff = diff
            best_d = d
    return best_d


def api_iso_equity_daily_session(bar_time: datetime | None) -> str | None:
    """API timestamp for equity *session* day — midnight local on that trade date."""
    if bar_time is None:
        return None
    sess = equity_daily_session_calendar_date(bar_time)
    return api_iso(daily_bar_timestamp_for_session_date(sess))
