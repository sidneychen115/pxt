import pandas as pd
from datetime import date
from src.core.app_timezone import daily_bar_timestamp_for_session_date
from src.data.repository import (
    get_bars_range_for_symbols,
    upsert_instrument,
    save_bars,
    get_bars,
)


async def test_save_and_get_bars(session):
    inst = await upsert_instrument(session, "TSLA", "stock", name="Tesla")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [1000, 2000],
        "vwap": [None, None],
        "source": ["yfinance", "yfinance"],
    }, index=pd.DatetimeIndex([
        pd.Timestamp(daily_bar_timestamp_for_session_date(date(2024, 1, 2))),
        pd.Timestamp(daily_bar_timestamp_for_session_date(date(2024, 1, 3))),
    ]))
    count = await save_bars(session, inst.id, "1d", df)
    assert count == 2
    result = await get_bars(session, inst.id, "1d", limit=10)
    assert len(result) == 2
    assert "close" in result.columns


async def test_save_bars_deduplication(session):
    inst = await upsert_instrument(session, "NVDA", "stock")
    df = pd.DataFrame({
        "open": [200.0], "high": [201.0], "low": [199.0], "close": [200.5],
        "volume": [500], "vwap": [None], "source": ["yfinance"],
    }, index=pd.DatetimeIndex([
        pd.Timestamp(daily_bar_timestamp_for_session_date(date(2024, 1, 4))),
    ]))
    await save_bars(session, inst.id, "1d", df)
    count2 = await save_bars(session, inst.id, "1d", df)  # same data again
    assert count2 == 0  # ON CONFLICT DO NOTHING


async def test_get_bars_range_for_symbols_multi(session):
    a = await upsert_instrument(session, "AAA", "stock")
    b = await upsert_instrument(session, "BBB", "stock")
    d1 = date(2024, 2, 1)
    d2 = date(2024, 2, 2)
    t1 = pd.Timestamp(daily_bar_timestamp_for_session_date(d1))
    t2 = pd.Timestamp(daily_bar_timestamp_for_session_date(d2))
    df_a = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [10, 20],
            "vwap": [None, None],
            "source": ["yfinance", "yfinance"],
        },
        index=pd.DatetimeIndex([t1, t2]),
    )
    await save_bars(session, a.id, "1d", df_a)
    df_b = pd.DataFrame(
        {
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.2],
            "volume": [100],
            "vwap": [None],
            "source": ["yfinance"],
        },
        index=pd.DatetimeIndex([t1]),
    )
    await save_bars(session, b.id, "1d", df_b)
    start = t1.to_pydatetime()
    end = t2.to_pydatetime()
    out = await get_bars_range_for_symbols(session, ["AAA", "BBB", "CCC"], "1d", start, end)
    assert len(out["AAA"]) == 2
    assert len(out["BBB"]) == 1
    assert out["CCC"].empty
