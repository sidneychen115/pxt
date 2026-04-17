import pytest
import pandas as pd
import numpy as np
from src.strategies.library.ma_crossover import MovingAverageCrossover
from src.strategies.base import DataContext


class MockDataContext(DataContext):
    def __init__(self, df: pd.DataFrame):
        self._df = df

    async def get_bars(self, symbol, timeframe, limit=200) -> pd.DataFrame:
        return self._df.tail(limit).copy()

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_latest_quote(self, symbol) -> dict:
        return {}


def make_crossover_df(direction: str) -> pd.DataFrame:
    """Build a price series that produces a crossover on the last bar.

    For a golden cross: price gradually declines (fast EMA < slow EMA),
    then spikes sharply so fast EMA crosses above slow EMA on the last bar.

    For a death cross: price gradually rises (fast EMA > slow EMA),
    then crashes sharply so fast EMA crosses below slow EMA on the last bar.
    """
    n = 50
    if direction == "golden":
        prices = list(np.linspace(130, 80, n - 1)) + [140.0]
    else:
        prices = list(np.linspace(80, 130, n - 1)) + [70.0]
    return pd.DataFrame({
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


@pytest.fixture
def strategy():
    return MovingAverageCrossover()


async def test_golden_cross_generates_buy(strategy):
    ctx = MockDataContext(make_crossover_df("golden"))
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].symbol == "SPY"


async def test_death_cross_generates_sell(strategy):
    ctx = MockDataContext(make_crossover_df("death"))
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "sell"


async def test_no_crossover_no_signal(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 50, "high": [101.0] * 50,
        "low": [99.0] * 50, "close": [100.0] * 50, "volume": [1000] * 50,
    }, index=pd.date_range("2023-01-01", periods=50, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert signals == []


async def test_insufficient_data_no_signal(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 5, "high": [101.0] * 5,
        "low": [99.0] * 5, "close": [100.0] * 5, "volume": [1000] * 5,
    }, index=pd.date_range("2023-01-01", periods=5, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert signals == []


async def test_get_bars_returns_none_no_crash(strategy):
    """Strategy should skip symbol gracefully when context returns None."""
    class NullDataContext(DataContext):
        async def get_bars(self, symbol, timeframe, limit=200):
            return None
        async def get_option_chain(self, underlying, expiry=None):
            return pd.DataFrame()
        async def get_latest_quote(self, symbol):
            return {}

    ctx = NullDataContext()
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert signals == []


async def test_fast_greater_than_slow_no_crash(strategy):
    """Inverted parameters (fast > slow) should produce no signal, not crash."""
    ctx = MockDataContext(make_crossover_df("golden"))
    signals = await strategy.generate_signals(["SPY"], {"fast": 40, "slow": 20}, ctx)
    assert signals == []
