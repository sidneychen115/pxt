from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.strategies.snapshot_bars import (
    merge_snapshot_close_into_daily,
    quote_mark_price,
)

TZ = ZoneInfo("America/Chicago")


def test_quote_mark_price_last():
    assert quote_mark_price({"last": 100.5}) == 100.5


def test_quote_mark_price_mid():
    assert quote_mark_price({"bid": 99.0, "ask": 101.0}) == 100.0


def test_merge_updates_today_bar():
    # 2024-06-03 is a Monday in CT
    as_of = datetime(2024, 6, 3, 19, 0, tzinfo=timezone.utc)  # 14:00 CT (CDT)
    idx = pd.to_datetime(["2024-06-03"], utc=True)
    daily = pd.DataFrame(
        {
            "open": [400.0],
            "high": [405.0],
            "low": [398.0],
            "close": [401.0],
            "volume": [1e6],
        },
        index=idx,
    )
    out = merge_snapshot_close_into_daily(
        daily, mark_price=410.0, as_of=as_of, tz=TZ
    )
    assert float(out["close"].iloc[-1]) == 410.0
    assert float(out["high"].iloc[-1]) == 410.0
    assert float(out["low"].iloc[-1]) == 398.0


def test_merge_appends_new_session_day():
    as_of = datetime(2024, 6, 4, 19, 0, tzinfo=timezone.utc)
    idx = pd.to_datetime(["2024-06-03"], utc=True)
    daily = pd.DataFrame(
        {
            "open": [400.0],
            "high": [405.0],
            "low": [398.0],
            "close": [401.0],
            "volume": [1e6],
        },
        index=idx,
    )
    out = merge_snapshot_close_into_daily(
        daily, mark_price=412.0, as_of=as_of, tz=TZ
    )
    assert len(out) == 2
    assert float(out["close"].iloc[-1]) == 412.0
