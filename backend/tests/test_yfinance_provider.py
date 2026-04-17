import pytest
from datetime import datetime, timedelta, timezone
from src.data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider():
    return YFinanceProvider()


async def test_get_bars_returns_dataframe(provider):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=10)
    df = await provider.get_bars("AAPL", "1d", start, end)
    assert not df.empty
    assert "close" in df.columns
    assert "source" in df.columns
    assert df["source"].iloc[0] == "yfinance"
    expected_cols = {"open", "high", "low", "close", "volume", "vwap", "source"}
    assert expected_cols.issubset(set(df.columns))
    assert df.index.tz is not None  # UTC-aware index


async def test_get_bars_empty_symbol(provider):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=5)
    df = await provider.get_bars("INVALID_TICKER_XYZ", "1d", start, end)
    assert df.empty or len(df) == 0


async def test_get_latest_quote(provider):
    quote = await provider.get_latest_quote("SPY")
    assert quote["symbol"] == "SPY"
    assert quote["source"] == "yfinance"
    assert "last" in quote
    assert "bid" in quote
    assert "ask" in quote
    assert "volume" in quote
    assert "timestamp" in quote
    assert quote["timestamp"].tzinfo is not None  # timezone-aware
