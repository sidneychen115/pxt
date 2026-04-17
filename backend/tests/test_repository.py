import pytest
import pandas as pd
from datetime import datetime, timezone
from src.data.repository import upsert_instrument, save_bars, get_bars


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
    }, index=pd.to_datetime(["2024-01-02", "2024-01-03"], utc=True))
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
    }, index=pd.to_datetime(["2024-01-04"], utc=True))
    await save_bars(session, inst.id, "1d", df)
    count2 = await save_bars(session, inst.id, "1d", df)  # same data again
    assert count2 == 0  # ON CONFLICT DO NOTHING
