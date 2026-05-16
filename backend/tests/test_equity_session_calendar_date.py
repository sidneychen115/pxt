"""Session calendar-date mapping for US daily OHLC (Yahoo-aligned).

Requires Postgres test DB (see tests/conftest.py autouse fixtures).
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.core.app_timezone import (
    api_iso,
    api_iso_equity_daily_session,
    daily_bar_timestamp_for_session_date,
    equity_daily_session_calendar_date,
)


def test_yahoo_cst_evening_maps_to_next_utc_trade_date():
    bar = datetime(2020, 1, 9, 18, 0, 0, tzinfo=timezone.utc)
    assert equity_daily_session_calendar_date(bar) == date(2020, 1, 10)


def test_yahoo_cdt_evening():
    bar = datetime(2020, 7, 5, 19, 0, 0, tzinfo=timezone.utc)
    assert equity_daily_session_calendar_date(bar) == date(2020, 7, 6)


def test_utc_midnight_yahoo_style():
    bar = datetime(2020, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    assert equity_daily_session_calendar_date(bar) == date(2020, 1, 10)


def test_canonical_local_midnight_chicago():
    z = ZoneInfo("America/Chicago")
    anchor = datetime(2020, 1, 13, tzinfo=z)
    assert equity_daily_session_calendar_date(anchor) == date(2020, 1, 13)


def test_api_iso_equity_daily_session_matches_anchor():
    bar = datetime(2020, 1, 9, 18, 0, 0, tzinfo=timezone.utc)
    want = daily_bar_timestamp_for_session_date(date(2020, 1, 10))
    assert api_iso_equity_daily_session(bar) == api_iso(want)

