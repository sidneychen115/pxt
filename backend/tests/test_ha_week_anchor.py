"""Week anchor rebuild matches monthly-style lookback + Mon–Fri weeks."""

from datetime import date, datetime, timezone

import pandas as pd

from src.strategies.ha_cache.calendar import last_completed_week_end
from src.strategies.ha_cache.lookback import week_ha_open_close


def _make_daily(n: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2023-06-01", periods=n, freq="B", tz="UTC")
    base = pd.Series(range(n), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": base + 100,
            "high": base + 101,
            "low": base + 99,
            "close": base + 100.5,
            "volume": 1000,
        },
        index=idx,
    )


def test_week_ha_open_close_finds_completed_friday():
    daily = _make_daily(900)
    as_of = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    fri = last_completed_week_end(as_of)
    pair = week_ha_open_close(daily, fri)
    assert pair is not None
    ha_o, ha_c = pair
    assert ha_o > 0 and ha_c > 0


def test_week_ha_open_close_wrong_friday_returns_none():
    daily = _make_daily(80)
    assert week_ha_open_close(daily, date(1999, 1, 1)) is None
