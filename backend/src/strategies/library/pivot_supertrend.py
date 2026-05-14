# backend/src/strategies/library/pivot_supertrend.py
from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.indicators import Indicators
from src.strategies.library.adaptive_turtle import compute_atr_position_size


def _atr_regime_passes(
    atr: pd.Series,
    *,
    enabled: bool,
    regime_period: int,
    min_ratio: float,
    max_ratio: float | None,
) -> bool:
    """Require ATR near its moving average: filters dead chop (too low) and optional chaos (too high)."""
    if not enabled or atr is None or len(atr) < regime_period + 1:
        return True
    ma = atr.rolling(regime_period).mean().iloc[-1]
    last = float(atr.iloc[-1])
    if pd.isna(ma) or ma <= 0 or not np.isfinite(last):
        return True
    r = last / float(ma)
    if r < min_ratio:
        return False
    if max_ratio is not None and r > max_ratio:
        return False
    return True


def _volume_confirms_flip(
    df: pd.DataFrame, vol_period: int, mult: float
) -> bool:
    """Trend-flip volume confirmation: last bar volume vs SMA(volume). mult<=0 disables."""
    if mult <= 0:
        return True
    if "volume" not in df.columns or len(df) < vol_period + 1:
        return True
    v = df["volume"].astype(float)
    ma_v = v.rolling(vol_period).mean().iloc[-1]
    last_v = float(v.iloc[-1])
    if pd.isna(ma_v) or ma_v <= 0:
        return True
    return last_v >= mult * float(ma_v)


class PivotSupertrendStrategy(BaseStrategy):
    id = "pivot_supertrend"
    name = "Pivot Point SuperTrend"
    description = (
        "SuperTrend built on a pivot-point center line. "
        "Buys on bullish trend flips, sells on bearish flips. "
        "Optional: SPY 200d MA long filter, ATR regime filter (skip chop), "
        "volume confirmation on flips, ATR-based position sizing, and SuperTrend-level initial stops. "
        "Include SPY in symbols when using the benchmark filter. "
        "For buy-and-hold comparison, include SPY in the backtest symbol list; "
        "alpha vs SPY is reported on completed backtests. "
        "Tighter loss cutting: set exit_policy.stop_loss_pct on the backtest, "
        "and/or rely on stop_price from the SuperTrend band (enabled by default)."
    )
    default_symbols = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "pivot_period": 2,
        "atr_factor": 3.0,
        "atr_period": 10,
        "timeframe": "1d",
        # Benchmark: only open new longs when benchmark > long MA (insufficient history → no filter).
        "benchmark_symbol": "SPY",
        "benchmark_ma_period": 200,
        "use_benchmark_long_filter": True,
        # ATR regime: ATR vs its MA over regime_period (disabled by default for backward compatibility).
        "use_atr_regime_filter": False,
        "atr_regime_period": 20,
        "min_atr_vs_ma_ratio": 0.85,
        "max_atr_vs_ma_ratio": None,
        # Volume: last bar volume >= mult × SMA(volume); mult 0 = off.
        "volume_ma_period": 20,
        "volume_confirm_mult": 0.0,
        # Sizing: 0 = engine default (cash fraction); >0 = Turtle-style ATR risk.
        "dollar_risk_pct": 0.0,
        # Initial stop at SuperTrend band (passed as TradeSignal.stop_price for backtests).
        "use_supertrend_stop_price": True,
    }

    def _equity_and_cash(
        self, portfolio: PortfolioSnapshot | None, parameters: dict
    ) -> tuple[float, float]:
        default_live = float(parameters.get("account_equity", 100_000.0))
        if portfolio is None:
            eq = default_live
            cash = float(parameters.get("account_cash", eq))
            return eq, cash
        eq = portfolio.equity
        if eq is None or eq <= 0:
            eq = float(portfolio.cash) if portfolio.cash is not None else default_live
        cash = float(portfolio.cash) if portfolio.cash is not None else eq
        return eq, max(cash, 0.0)

    async def _benchmark_bull(
        self, ctx: DataContext, benchmark_symbol: str, ma_period: int
    ) -> bool:
        """True if benchmark close > MA(close); True if data insufficient (filter skipped)."""
        need = max(ma_period + 5, 50)
        bench = await ctx.get_bars(benchmark_symbol, "1d", limit=need)
        if bench is None or len(bench) < ma_period:
            return True
        close = bench["close"]
        ma = close.rolling(ma_period).mean().iloc[-1]
        last = close.iloc[-1]
        if pd.isna(ma) or pd.isna(last):
            return True
        return bool(last > ma)

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        prd = int(parameters.get("pivot_period", self.default_parameters["pivot_period"]))
        factor = float(parameters.get("atr_factor", self.default_parameters["atr_factor"]))
        atr_pd = int(parameters.get("atr_period", self.default_parameters["atr_period"]))
        tf = str(parameters.get("timeframe", self.default_parameters["timeframe"]))

        benchmark_symbol = str(
            parameters.get("benchmark_symbol", self.default_parameters["benchmark_symbol"])
        )
        benchmark_ma = int(
            parameters.get("benchmark_ma_period", self.default_parameters["benchmark_ma_period"])
        )
        use_bench_filter = bool(
            parameters.get(
                "use_benchmark_long_filter",
                self.default_parameters["use_benchmark_long_filter"],
            )
        )

        use_atr_regime = bool(
            parameters.get("use_atr_regime_filter", self.default_parameters["use_atr_regime_filter"])
        )
        atr_regime_pd = int(
            parameters.get("atr_regime_period", self.default_parameters["atr_regime_period"])
        )
        min_atr_r = float(
            parameters.get("min_atr_vs_ma_ratio", self.default_parameters["min_atr_vs_ma_ratio"])
        )
        raw_max = parameters.get("max_atr_vs_ma_ratio", self.default_parameters["max_atr_vs_ma_ratio"])
        max_atr_r: float | None
        if raw_max is None or raw_max == "":
            max_atr_r = None
        else:
            max_atr_r = float(raw_max)

        vol_pd = int(parameters.get("volume_ma_period", self.default_parameters["volume_ma_period"]))
        vol_mult = float(parameters.get("volume_confirm_mult", self.default_parameters["volume_confirm_mult"]))

        raw_risk = parameters.get("dollar_risk_pct", self.default_parameters["dollar_risk_pct"])
        try:
            dollar_risk_pct = float(raw_risk)
        except (TypeError, ValueError):
            dollar_risk_pct = float(self.default_parameters["dollar_risk_pct"])
        if dollar_risk_pct < 0:
            dollar_risk_pct = 0.0
        if dollar_risk_pct > 0.25:
            dollar_risk_pct = 0.25

        use_st_stop = bool(
            parameters.get(
                "use_supertrend_stop_price",
                self.default_parameters["use_supertrend_stop_price"],
            )
        )

        limit = max(prd * 2 + atr_pd + 20, 200, benchmark_ma + 5, atr_regime_pd + 5, vol_pd + 5)
        min_bars = prd * 2 + atr_pd + 1

        is_bull_benchmark = (
            await self._benchmark_bull(ctx, benchmark_symbol, benchmark_ma)
            if use_bench_filter
            else True
        )

        equity, cash_budget = self._equity_and_cash(portfolio, parameters)
        signals: list[TradeSignal] = []

        for symbol in symbols:
            if not symbol:
                continue
            df = await ctx.get_bars(symbol, tf, limit=limit)
            if df is None or len(df) < min_bars:
                continue

            high = df["high"].astype(float)
            low = df["low"].astype(float)
            close = df["close"].astype(float)

            ph, pl = _detect_pivots(high, low, prd)

            center_vals = np.full(len(df), np.nan)
            c = np.nan
            for j in range(len(df)):
                lastpp = (
                    ph.iloc[j]
                    if not pd.isna(ph.iloc[j])
                    else pl.iloc[j]
                    if not pd.isna(pl.iloc[j])
                    else np.nan
                )
                if not pd.isna(lastpp):
                    c = lastpp if pd.isna(c) else (c * 2 + lastpp) / 3
                center_vals[j] = c
            center = pd.Series(center_vals, index=df.index)

            atr = Indicators.atr(df, atr_pd)
            if atr is None or atr.isna().all():
                continue

            if not _atr_regime_passes(
                atr,
                enabled=use_atr_regime,
                regime_period=atr_regime_pd,
                min_ratio=min_atr_r,
                max_ratio=max_atr_r,
            ):
                continue

            up = center - factor * atr
            dn = center + factor * atr

            valid_mask = up.notna() & dn.notna()
            if not valid_mask.any():
                continue
            fi_loc = int(valid_mask.values.argmax())

            tup_vals = np.full(len(df), np.nan)
            tdown_vals = np.full(len(df), np.nan)
            trend_vals = np.zeros(len(df), dtype=int)

            tup_vals[fi_loc] = up.iloc[fi_loc]
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

            last_atr = float(atr.iloc[-1])
            last_close = float(close.iloc[-1])
            buy_qty: float | None = None
            if dollar_risk_pct > 0:
                buy_qty = compute_atr_position_size(
                    equity, cash_budget, last_close, last_atr, dollar_risk_pct
                )

            st_stop = float(tup_vals[-1]) if use_st_stop and np.isfinite(tup_vals[-1]) else None

            bullish_flip = curr_trend == 1 and prev_trend == -1
            bearish_flip = curr_trend == -1 and prev_trend == 1

            if bullish_flip:
                if use_bench_filter and not is_bull_benchmark:
                    continue
                if not _volume_confirms_flip(df, vol_pd, vol_mult):
                    continue
                parts = [
                    f"SuperTrend flipped bullish. Trailing support (TUp): {tup_vals[-1]:.2f}",
                ]
                if use_bench_filter:
                    parts.append(f"benchmark>{benchmark_ma}d MA filter OK ({benchmark_symbol})")
                if use_atr_regime:
                    parts.append("ATR regime OK")
                if vol_mult > 0:
                    parts.append(f"volume≥{vol_mult}×SMA({vol_pd})")
                if dollar_risk_pct > 0 and buy_qty is not None:
                    parts.append(
                        f"ATR({atr_pd})={last_atr:.2f} risk_pct={dollar_risk_pct:.4f} qty={int(buy_qty)}"
                    )
                elif dollar_risk_pct > 0:
                    parts.append("ATR sizing skipped (invalid ATR or qty), default sizing")

                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="buy",
                        order_type="market",
                        quantity=buy_qty if dollar_risk_pct > 0 else None,
                        stop_price=st_stop,
                        confidence=0.72,
                        reasoning="; ".join(parts),
                    )
                )
            elif bearish_flip:
                if not _volume_confirms_flip(df, vol_pd, vol_mult):
                    continue
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="sell",
                        order_type="market",
                        confidence=0.72,
                        reasoning=(
                            f"SuperTrend flipped bearish. Trailing resistance (TDown): {tdown_vals[-1]:.2f}"
                        ),
                    )
                )

        return signals


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
