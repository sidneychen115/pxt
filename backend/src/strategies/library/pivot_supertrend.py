# backend/src/strategies/library/pivot_supertrend.py
import numpy as np
import pandas as pd
from src.strategies.base import BaseStrategy, DataContext, TradeSignal
from src.strategies.indicators import Indicators


def _detect_pivots(
    high: pd.Series, low: pd.Series, prd: int
) -> tuple[pd.Series, pd.Series]:
    """Return (pivot_high, pivot_low) series.

    At bar j, ph[j] = high[j-prd] if that bar is the strict unique maximum of the
    [j-2*prd : j+1] window (inclusive), nan otherwise.  The prd-bar delay
    means only data available at j is used — no look-ahead.
    """
    ph = pd.Series(np.nan, index=high.index)
    pl = pd.Series(np.nan, index=low.index)
    for j in range(2 * prd, len(high)):
        window_h = high.iloc[j - 2 * prd : j + 1]
        if high.iloc[j - prd] == window_h.max() and (window_h == window_h.max()).sum() == 1:
            ph.iloc[j] = high.iloc[j - prd]
        window_l = low.iloc[j - 2 * prd : j + 1]
        if low.iloc[j - prd] == window_l.min() and (window_l == window_l.min()).sum() == 1:
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
        prd    = int(parameters.get("pivot_period", self.default_parameters["pivot_period"]))
        factor = float(parameters.get("atr_factor",   self.default_parameters["atr_factor"]))
        atr_pd = int(parameters.get("atr_period",   self.default_parameters["atr_period"]))
        limit  = max(prd * 2 + atr_pd + 20, 200)
        min_bars = prd * 2 + atr_pd + 1
        signals: list[TradeSignal] = []

        for symbol in symbols:
            if not symbol:
                continue
            df = await ctx.get_bars(symbol, "1d", limit=limit)
            if df is None or len(df) < min_bars:
                continue

            high  = df["high"].astype(float)
            low   = df["low"].astype(float)
            close = df["close"].astype(float)

            ph, pl = _detect_pivots(high, low, prd)

            # center line: weighted moving average of confirmed pivot points
            center_vals = np.full(len(df), np.nan)
            c = np.nan
            for j in range(len(df)):
                lastpp = (
                    ph.iloc[j] if not pd.isna(ph.iloc[j])
                    else pl.iloc[j] if not pd.isna(pl.iloc[j])
                    else np.nan
                )
                if not pd.isna(lastpp):
                    c = lastpp if pd.isna(c) else (c * 2 + lastpp) / 3
                center_vals[j] = c
            center = pd.Series(center_vals, index=df.index)

            atr = Indicators.atr(df, atr_pd)
            if atr is None or atr.isna().all():
                continue

            up = center - factor * atr
            dn = center + factor * atr

            valid_mask = up.notna() & dn.notna()
            if not valid_mask.any():
                continue
            fi_loc = int(valid_mask.values.argmax())

            tup_vals   = np.full(len(df), np.nan)
            tdown_vals = np.full(len(df), np.nan)
            trend_vals = np.zeros(len(df), dtype=int)

            tup_vals[fi_loc]   = up.iloc[fi_loc]
            tdown_vals[fi_loc] = dn.iloc[fi_loc]
            trend_vals[fi_loc] = 1

            for i in range(fi_loc + 1, len(df)):
                prev_close = close.iloc[i - 1]
                tup_vals[i] = (
                    max(up.iloc[i], tup_vals[i - 1])
                    if prev_close > tup_vals[i - 1]
                    else up.iloc[i]
                )
                tdown_vals[i] = (
                    min(dn.iloc[i], tdown_vals[i - 1])
                    if prev_close < tdown_vals[i - 1]
                    else dn.iloc[i]
                )
                if close.iloc[i] > tdown_vals[i - 1]:
                    trend_vals[i] = 1
                elif close.iloc[i] < tup_vals[i - 1]:
                    trend_vals[i] = -1
                else:
                    trend_vals[i] = trend_vals[i - 1]

            prev_trend = trend_vals[-2]
            curr_trend = trend_vals[-1]

            if curr_trend == 1 and prev_trend == -1:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="buy",
                    order_type="market",
                    confidence=0.70,
                    reasoning=(
                        f"SuperTrend flipped bullish. Trailing stop: {tup_vals[-1]:.2f}"
                    ),
                ))
            elif curr_trend == -1 and prev_trend == 1:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="sell",
                    order_type="market",
                    confidence=0.70,
                    reasoning=(
                        f"SuperTrend flipped bearish. Trailing stop: {tdown_vals[-1]:.2f}"
                    ),
                ))

        return signals
