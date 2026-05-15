"""Backtest HA paths use Mon–Fri weeks (aligned with live)."""

from datetime import datetime, timezone

import pandas as pd

from src.strategies.ha_cache.backtest import month_ha_open_backtest, week_ha_close_backtest
from src.strategies.ha_cache.bars import mon_fri_bars
from src.strategies.heikin_ashi import heikin_ashi, resample_to_weekly_mon_fri


def _make_daily(n: int = 900) -> pd.DataFrame:
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


def test_mon_fri_excludes_weekend_rows_if_present():
    idx = pd.to_datetime(
        ["2024-06-07", "2024-06-08", "2024-06-10"], utc=True
    )  # Fri, Sat, Mon
    df = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3]},
        index=idx,
    )
    out = mon_fri_bars(df)
    assert len(out) == 2


def test_backtest_week_ha_close_matches_incremental_at_as_of():
    daily = _make_daily(900)
    as_of = daily.index[-1].to_pydatetime()
    got = week_ha_close_backtest(daily, as_of)
    assert got is not None

    # Full-series last bar close should match incremental when history is long enough
    w = resample_to_weekly_mon_fri(daily)
    full_close = float(heikin_ashi(w)["ha_close"].iloc[-1])
    assert got == full_close


def test_month_ha_open_backtest_returns_float():
    daily = _make_daily(200)
    as_of = daily.index[-1].to_pydatetime()
    bench = month_ha_open_backtest(daily, as_of)
    assert bench is not None
    assert bench > 0
