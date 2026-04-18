import numpy as np
import pandas as pd
from src.strategies.base import BaseStrategy, DataContext, TradeSignal
from src.strategies.indicators import Indicators


def _detect_pivots(
    high: pd.Series, low: pd.Series, prd: int
) -> tuple[pd.Series, pd.Series]:
    """Return (pivot_high, pivot_low) series.

    At bar j, ph[j] = high[j-prd] if that bar is the maximum of the
    [j-2*prd : j+1] window (inclusive), nan otherwise.  The prd-bar delay
    means only data available at j is used — no look-ahead.
    """
    ph = pd.Series(np.nan, index=high.index)
    pl = pd.Series(np.nan, index=low.index)
    for j in range(2 * prd, len(high)):
        window_h = high.iloc[j - 2 * prd : j + 1]
        if high.iloc[j - prd] == window_h.max():
            ph.iloc[j] = high.iloc[j - prd]
        window_l = low.iloc[j - 2 * prd : j + 1]
        if low.iloc[j - prd] == window_l.min():
            pl.iloc[j] = low.iloc[j - prd]
    return ph, pl


class PivotSupertrendStrategy(BaseStrategy):
    id = "pivot_supertrend"
    name = "Pivot Point SuperTrend"
    description = (
        "SuperTrend built on pivot-point center line. "
        "Buys on bullish trend flip, sells on bearish trend flip."
    )
    default_symbols = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "pivot_period": 2,
        "atr_factor": 3.0,
        "atr_period": 10,
    }

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
    ) -> list[TradeSignal]:
        return []  # stub — implemented in Task 4
