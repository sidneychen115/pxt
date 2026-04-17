import pytest
from datetime import datetime, timedelta
from src.data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider():
    return YFinanceProvider()


async def test_get_bars_returns_dataframe(provider):
    end = datetime.utcnow()
    start = end - timedelta(days=10)
    df = await provider.get_bars("AAPL", "1d", start, end)
    assert not df.empty
    assert "close" in df.columns
    assert "source" in df.columns
    assert df["source"].iloc[0] == "yfinance"


async def test_get_bars_empty_symbol(provider):
    end = datetime.utcnow()
    start = end - timedelta(days=5)
    df = await provider.get_bars("INVALID_TICKER_XYZ", "1d", start, end)
    assert df.empty or len(df) == 0


async def test_get_latest_quote(provider):
    quote = await provider.get_latest_quote("SPY")
    assert quote["symbol"] == "SPY"
    assert quote["source"] == "yfinance"
