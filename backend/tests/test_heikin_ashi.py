import pytest
import pandas as pd

from src.strategies.heikin_ashi import (
    heikin_ashi,
    resample_to_monthly,
    resample_to_weekly_friday,
    resample_to_weekly_mon_fri,
)


def test_heikin_ashi_first_bar():
    df = pd.DataFrame(
        {
            "open": [10.0],
            "high": [12.0],
            "low": [9.0],
            "close": [11.0],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-02", tz="UTC")]),
    )
    ha = heikin_ashi(df)
    assert ha["ha_close"].iloc[0] == pytest.approx((10 + 12 + 9 + 11) / 4)
    assert ha["ha_open"].iloc[0] == pytest.approx((10 + 11) / 2)


def test_resample_monthly_partial():
    idx = pd.date_range("2024-01-02", periods=8, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": list(range(8)),
            "high": list(range(8)),
            "low": list(range(8)),
            "close": list(range(8)),
            "volume": [100] * 8,
        },
        index=idx,
    )
    m = resample_to_monthly(df)
    assert len(m) >= 1
    assert m["close"].iloc[-1] == df["close"].iloc[-1]


def test_resample_weekly_mon_fri_alias():
    idx = pd.date_range("2024-01-02", periods=10, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        },
        index=idx,
    )
    assert not resample_to_weekly_mon_fri(df).empty
    pd.testing.assert_frame_equal(
        resample_to_weekly_friday(df),
        resample_to_weekly_mon_fri(df),
    )


def test_resample_weekly_friday():
    idx = pd.date_range("2024-01-02", periods=10, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        },
        index=idx,
    )
    w = resample_to_weekly_friday(df)
    assert not w.empty
