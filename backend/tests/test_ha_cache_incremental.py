"""Incremental week HA close matches full-series computation."""

import pandas as pd

from src.strategies.heikin_ashi import (
    heikin_ashi,
    heikin_ashi_single_bar,
    resample_to_weekly_mon_fri,
)


def _make_daily(n: int = 200) -> pd.DataFrame:
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


def test_incremental_week_ha_close_matches_full():
    daily = _make_daily()
    week_ohlc = resample_to_weekly_mon_fri(daily)
    assert len(week_ohlc) >= 2

    full_ha = heikin_ashi(week_ohlc)
    expected = float(full_ha["ha_close"].iloc[-1])

    completed = week_ohlc.iloc[:-1]
    cur = week_ohlc.iloc[-1]
    ha_completed = heikin_ashi(completed)
    prev_o = float(ha_completed["ha_open"].iloc[-1])
    prev_c = float(ha_completed["ha_close"].iloc[-1])
    *_, got = heikin_ashi_single_bar(
        float(cur["open"]),
        float(cur["high"]),
        float(cur["low"]),
        float(cur["close"]),
        prev_o,
        prev_c,
    )
    assert got == expected


def test_heikin_ashi_single_bar_first_week():
    *_, ha_c = heikin_ashi_single_bar(10.0, 12.0, 9.0, 11.0, 10.0, 11.0)
    full = heikin_ashi(
        pd.DataFrame(
            {"open": [10], "high": [12], "low": [9], "close": [11]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-01-02", tz="UTC")]),
        )
    )
    assert ha_c == float(full["ha_close"].iloc[0])
