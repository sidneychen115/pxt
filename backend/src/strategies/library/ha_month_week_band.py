"""Monthly HA open benchmark vs weekly HA close with symmetric dead band."""

from __future__ import annotations

import pandas as pd

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.heikin_ashi import (
    heikin_ashi,
    resample_to_monthly,
    resample_to_weekly_friday,
)


class HaMonthOpenWeeklyCloseBandStrategy(BaseStrategy):
    """
    Benchmark: HA open of the **current calendar month** (monthly candle, partial month OK).
    Signal: at each session, compare **weekly** Heikin-Ashi **close** of the in-progress week
    (week ending Friday) to ``benchmark ± band``.
    Buy when weekly HA close > benchmark + band; sell when < benchmark − band; neutral in between.

    Backtests use ``backtest_fill_mode: same_close`` (class default) so fills match the
    signal bar's close; override via request parameters if needed.
    """

    id = "ha_month_week_band"
    name = "HA Month Open vs Weekly Close (band)"
    description = (
        "Uses current month's monthly Heikin-Ashi open as benchmark vs weekly HA close "
        "(Friday week buckets) with optional symmetric band (band_pct of benchmark + band_abs). "
        "Designed for daily bars; live runs use the latest daily print."
    )
    default_symbols = ["SPY"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "timeframe": "1d",
        "band_pct": 0.0,
        "band_abs": 0.0,
        "backtest_fill_mode": "same_close",
    }
    backtest_fill_mode = "same_close"

    def _params(self, parameters: dict) -> dict:
        return {**self.default_parameters, **parameters}

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        p = self._params(parameters)
        tf = str(p.get("timeframe") or "1d")
        band_pct = float(p.get("band_pct") or 0.0)
        band_abs = float(p.get("band_abs") or 0.0)

        signals: list[TradeSignal] = []

        for symbol in symbols:
            if not symbol:
                continue
            daily = await ctx.get_bars(symbol, tf, limit=900)
            if daily is None or daily.empty or len(daily) < 40:
                continue

            as_of = daily.index[-1]
            month_ohlc = resample_to_monthly(daily)
            week_ohlc = resample_to_weekly_friday(daily)
            if month_ohlc.empty or week_ohlc.empty or len(month_ohlc) < 2:
                continue

            ha_m = heikin_ashi(month_ohlc)
            ha_w = heikin_ashi(week_ohlc)
            bench = float(ha_m["ha_open"].iloc[-1])
            w_close = float(ha_w["ha_close"].iloc[-1])
            if not (pd.notna(bench) and pd.notna(w_close)):
                continue

            delta = abs(bench) * band_pct + band_abs
            upper = bench + delta
            lower = bench - delta

            if w_close > upper:
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="buy",
                        order_type="market",
                        confidence=0.7,
                        reasoning=(
                            f"weekly HA close {w_close:.4f} > bench+band {upper:.4f} "
                            f"(bench=mo HA open {bench:.4f}, as_of {as_of})"
                        ),
                    )
                )
            elif w_close < lower:
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="sell",
                        order_type="market",
                        confidence=0.7,
                        reasoning=(
                            f"weekly HA close {w_close:.4f} < bench−band {lower:.4f} "
                            f"(bench=mo HA open {bench:.4f}, as_of {as_of})"
                        ),
                    )
                )

        return signals
