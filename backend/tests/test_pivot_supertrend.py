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
    assert pd.isna(ph.iloc[3]), "pivot not yet confirmed at j=3"
    assert ph.iloc[4] == 153.0, "pivot high must be confirmed at j=4"
    assert pd.isna(ph.iloc[5]), "no second pivot expected"
    assert pd.isna(ph.iloc[6]), "no third pivot expected"


def test_pivot_low_confirmed_at_correct_bar():
    high = pd.Series([110.0] * 7)
    low  = pd.Series([100.0, 98.0, 50.0, 98.0, 100.0, 100.0, 100.0])
    _, pl = _detect_pivots(high, low, prd=2)
    assert pd.isna(pl.iloc[3])
    assert pl.iloc[4] == 50.0
    assert pd.isna(pl.iloc[5])


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
