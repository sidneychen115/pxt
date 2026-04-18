import numpy as np
import pandas as pd
import pytest
from src.strategies.library.pivot_supertrend import _detect_pivots, PivotSupertrendStrategy
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


# ── Pivot detection unit tests ────────────────────────────────────────────────

def test_pivot_high_confirmed_at_correct_bar():
    # high[2]=153 is the peak; with prd=2 it is confirmed at bar j=4
    high = pd.Series([100.0, 102.0, 153.0, 102.0, 100.0, 100.0, 100.0])
    low  = pd.Series([ 90.0,  91.0,  92.0,  91.0,  90.0,  90.0,  90.0])
    ph, _ = _detect_pivots(high, low, prd=2)
    assert pd.isna(ph.iloc[0]), "no pivot before confirmation window"
    assert pd.isna(ph.iloc[1]), "no pivot before confirmation window"
    assert pd.isna(ph.iloc[2]), "no pivot before confirmation window"
    assert pd.isna(ph.iloc[3]), "pivot not yet confirmed at j=3"
    assert ph.iloc[4] == 153.0, "pivot high must be confirmed at j=4"
    assert pd.isna(ph.iloc[5]), "no second pivot expected"
    assert pd.isna(ph.iloc[6]), "no third pivot expected"


def test_pivot_low_confirmed_at_correct_bar():
    high = pd.Series([110.0] * 7)
    low  = pd.Series([100.0, 98.0, 50.0, 98.0, 100.0, 100.0, 100.0])
    _, pl = _detect_pivots(high, low, prd=2)
    assert pd.isna(pl.iloc[0]), "no pivot before confirmation window"
    assert pd.isna(pl.iloc[1]), "no pivot before confirmation window"
    assert pd.isna(pl.iloc[2]), "no pivot before confirmation window"
    assert pd.isna(pl.iloc[3])
    assert pl.iloc[4] == 50.0
    assert pd.isna(pl.iloc[5])
    assert pd.isna(pl.iloc[6])


def test_no_pivot_in_monotonic_series():
    # Strictly ascending: no bar is both the local high/low with prd neighbours lower/higher
    high = pd.Series([float(i) for i in range(10)])
    low  = pd.Series([float(i) - 0.5 for i in range(10)])
    ph, pl = _detect_pivots(high, low, prd=2)
    # No pivot highs (every candidate is lower than the bars after it)
    assert ph.dropna().empty
    # No pivot lows (every candidate is higher than the bars after it)
    assert pl.dropna().empty


def test_multiple_pivots_detected():
    # Two separate pivot highs at indices 2 and 6
    high = pd.Series([100.0, 102.0, 150.0, 102.0, 100.0, 102.0, 160.0, 102.0, 100.0, 100.0])
    low  = pd.Series([ 90.0] * 10)
    ph, _ = _detect_pivots(high, low, prd=2)
    assert ph.iloc[4] == 150.0   # pivot at bar 2, confirmed at bar 4
    assert ph.iloc[8] == 160.0   # pivot at bar 6, confirmed at bar 8


def test_plateau_is_not_a_pivot():
    # Two bars tied for the max — Pine Script would not confirm either
    high = pd.Series([100.0, 102.0, 150.0, 150.0, 100.0, 100.0])
    low  = pd.Series([ 90.0] * 6)
    ph, _ = _detect_pivots(high, low, prd=2)
    assert ph.dropna().empty, "plateau must not produce a pivot"


def test_multiple_pivots_low_series_is_clean():
    # The multi-pivot test only checked highs; verify low series is all NaN for that input
    high = pd.Series([100.0, 102.0, 150.0, 102.0, 100.0, 102.0, 160.0, 102.0, 100.0, 100.0])
    low  = pd.Series([ 90.0] * 10)
    _, pl = _detect_pivots(high, low, prd=2)
    assert pl.dropna().empty, "flat low series must produce no pivot lows"


# ── generate_signals integration tests ───────────────────────────────────────

def make_bullish_flip_df() -> pd.DataFrame:
    """Price series that ends with a bullish SuperTrend flip.

    Phase 1 (bars 0-4): oscillation creates a pivot high at bar 2
    (high=153), confirmed at bar 4.  Center line initialised to ~153.

    Phase 2 (bars 5-39): steady decline 100→50.  No new pivots.
    Center stays at ~153; bands are ~153±6.  TDown ratchets near 159.
    Close stays below TUp (~147) → Trend = -1.

    Phase 3 (bar 40): close=200, crosses above TDown (~159) → Trend flips to 1.
    """
    phase1_close = [100.0, 120.0, 150.0, 120.0, 100.0]
    phase2_close = list(np.linspace(100.0, 50.0, 35))
    phase3_close = [200.0]
    prices = phase1_close + phase2_close + phase3_close  # 41 bars
    n = len(prices)
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.02 for p in prices],
        "low":    [p * 0.98 for p in prices],
        "close":  prices,
        "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


def make_bearish_flip_df() -> pd.DataFrame:
    """Price series that ends with a bearish SuperTrend flip.

    Phase 1 (bars 0-4): oscillation creates a pivot low at bar 2
    (low=49), confirmed at bar 4.  Center line initialised to ~49.

    Phase 2 (bars 5-39): steady rise 100→150.  No new pivots.
    Center stays at ~49; bands are ~49±6.  TUp ratchets near 43.
    Close stays above TDown (~55) → Trend = 1.

    Phase 3 (bar 40): close=30, crosses below TUp (~43) → Trend flips to -1.
    """
    phase1_close = [100.0, 80.0, 50.0, 80.0, 100.0]
    phase2_close = list(np.linspace(100.0, 150.0, 35))
    phase3_close = [30.0]
    prices = phase1_close + phase2_close + phase3_close
    n = len(prices)
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.02 for p in prices],
        "low":    [p * 0.98 for p in prices],
        "close":  prices,
        "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


@pytest.fixture
def strategy():
    return PivotSupertrendStrategy()


async def test_bullish_flip_generates_buy(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].symbol == "SPY"
    assert signals[0].order_type == "market"
    assert 0.0 < signals[0].confidence <= 1.0


async def test_bearish_flip_generates_sell(strategy):
    ctx = MockDataContext(make_bearish_flip_df())
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "sell"
    assert signals[0].symbol == "SPY"


async def test_no_signal_on_flat_price(strategy):
    n = 50
    prices = [100.0] * n
    df = pd.DataFrame({
        "open": prices, "high": [101.0] * n,
        "low":  [99.0]  * n, "close": prices, "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert signals == []


async def test_insufficient_data_no_signal(strategy):
    n = 10  # below limit=34 with defaults
    prices = [100.0] * n
    df = pd.DataFrame({
        "open": prices, "high": [p * 1.01 for p in prices],
        "low":  [p * 0.99 for p in prices], "close": prices, "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert signals == []


async def test_none_data_no_crash(strategy):
    class NullCtx(DataContext):
        async def get_bars(self, symbol, timeframe, limit=200):
            return None
        async def get_option_chain(self, underlying, expiry=None):
            return pd.DataFrame()
        async def get_latest_quote(self, symbol):
            return {}

    signals = await strategy.generate_signals(["SPY"], {}, NullCtx())
    assert signals == []


async def test_empty_symbol_skipped(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    signals = await strategy.generate_signals([""], {}, ctx)
    assert signals == []


async def test_custom_parameters_accepted(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    # Should not crash with non-default parameters
    signals = await strategy.generate_signals(
        ["SPY"], {"pivot_period": 3, "atr_factor": 2.0, "atr_period": 14}, ctx
    )
    assert isinstance(signals, list)
