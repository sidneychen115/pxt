"""Tests for DB coverage detection and backtest OHLC memory cache."""

from datetime import date, datetime, time, timedelta

import pandas as pd

from src.core.app_timezone import app_zone, daily_bar_timestamp_for_session_date
from src.data.bars_merge import (
    BacktestOhlcMemoryCache,
    db_bars_cover_range,
)


def _daily_df(start: date, periods: int) -> pd.DataFrame:
    idx = pd.DatetimeIndex(
        [
            daily_bar_timestamp_for_session_date(start + timedelta(days=i))
            for i in range(periods)
        ]
    )
    return pd.DataFrame({"close": [1.0] * periods}, index=idx)


def test_db_bars_cover_range_daily_full_span():
    start = daily_bar_timestamp_for_session_date(date(2024, 1, 2))
    end = daily_bar_timestamp_for_session_date(date(2024, 1, 10))
    cached = _daily_df(date(2024, 1, 1), 12)
    assert db_bars_cover_range(cached, start, end, "1d")


def test_db_bars_cover_range_daily_missing_head():
    start = daily_bar_timestamp_for_session_date(date(2024, 1, 2))
    end = daily_bar_timestamp_for_session_date(date(2024, 1, 10))
    cached = _daily_df(date(2024, 1, 5), 5)
    assert not db_bars_cover_range(cached, start, end, "1d")


def test_db_bars_cover_range_daily_missing_tail():
    start = daily_bar_timestamp_for_session_date(date(2024, 1, 2))
    end = daily_bar_timestamp_for_session_date(date(2024, 1, 10))
    cached = _daily_df(date(2024, 1, 2), 5)
    assert not db_bars_cover_range(cached, start, end, "1d")


def test_db_bars_cover_range_intraday_exclusive_end():
    """Backtest fetch_end is midnight after end_date; RTH bars end earlier same day."""
    z = app_zone()
    start = datetime.combine(date(2026, 3, 18), time.min, tzinfo=z)
    fetch_end = datetime.combine(date(2026, 4, 18), time.min, tzinfo=z)
    idx = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-03-18 13:30:00", tz="UTC"),
            pd.Timestamp("2026-04-17 19:45:00", tz="UTC"),
        ]
    )
    cached = pd.DataFrame({"close": [1.0, 1.0]}, index=idx)
    assert db_bars_cover_range(cached, start, fetch_end, "15m")


def test_db_bars_cover_range_intraday_missing_tail():
    z = app_zone()
    start = datetime.combine(date(2026, 4, 1), time.min, tzinfo=z)
    fetch_end = datetime.combine(date(2026, 4, 11), time.min, tzinfo=z)
    rth_open = datetime.combine(date(2026, 4, 1), time(9, 30), tzinfo=z)
    idx = pd.date_range(rth_open, periods=20, freq="15min", tz=z)
    cached = pd.DataFrame({"close": [1.0] * len(idx)}, index=idx)
    assert not db_bars_cover_range(cached, start, fetch_end, "15m")


def test_backtest_ohlc_memory_cache_roundtrip():
    cache = BacktestOhlcMemoryCache(max_entries=2)
    z = app_zone()
    start = datetime.combine(date(2026, 1, 1), time.min, tzinfo=z)
    end = datetime.combine(date(2026, 1, 5), time.min, tzinfo=z)
    df = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([start], tz=z))
    cache.put("spy", "1d", start, end, df)
    hit = cache.get("spy", "1d", start, end)
    assert hit is not None
    assert len(hit) == 1
    assert cache.get("QQQ", "1d", start, end) is None
