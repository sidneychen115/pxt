"""Monthly HA open benchmark vs weekly HA close with symmetric dead band."""

from __future__ import annotations

import pandas as pd

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.ha_cache import service as ha_cache
from src.strategies.ha_cache.backtest import month_ha_open_backtest, week_ha_close_backtest
from src.strategies.live_context import LiveDataContext


class HaMonthOpenWeeklyCloseBandStrategy(BaseStrategy):
    """
    Benchmark: HA open of the **current calendar month** (monthly candle, partial month OK).
    Signal: at each session, compare **weekly** Heikin-Ashi **close** of the in-progress week
    (Mon–Fri week ending Friday) to ``benchmark ± band``.
    Buy when weekly HA close > benchmark + band; sell when < benchmark − band; neutral in between.

    Live runs (``LiveDataContext``): month HA open is cached per calendar month (≤1 prior
    month of dailies on cold start); week HA close uses current-week dailies only plus a
    prior-week anchor (≤1 week of dailies when the anchor rolls). Backtests use full history.
    """

    id = "ha_month_week_band"
    name = "HA Month Open vs Weekly Close (band)"
    description = (
        "Uses current month's monthly Heikin-Ashi open as benchmark vs weekly HA close "
        "(Mon–Fri week buckets, Friday label) with optional symmetric band "
        "(band_pct of benchmark + band_abs). "
        "Designed for daily bars; live runs use the latest daily print."
    )
    default_symbols = ["SPY"]
    default_timeframes = ["1d"]
    default_frequency = "0 14 * * 1-5"  # weekdays 14:00 America/Chicago; snapshot close at run
    default_parameters = {
        "timeframe": "1d",
        "band_pct": 0.0,
        "band_abs": 0.0,
        "backtest_fill_mode": "same_close",
        # confidence = clip(floor + excess_scale * excess, floor, cap); excess = band breakout depth
        "confidence_floor": 0.5,
        "confidence_cap": 1.0,
        "confidence_excess_scale": 0.25,
    }
    backtest_fill_mode = "same_close"

    def _params(self, parameters: dict) -> dict:
        return {**self.default_parameters, **parameters}

    @staticmethod
    def _confidence_from_breakout(
        bench: float,
        w_close: float,
        upper: float,
        lower: float,
        delta: float,
        direction: str,
        *,
        floor: float,
        cap: float,
        excess_scale: float,
        bench_epsilon: float = 1e-6,
    ) -> tuple[float, float]:
        """Map band breakout depth to [floor, cap]. Returns (confidence, excess)."""
        if direction == "buy":
            if delta > 0:
                excess = (w_close - upper) / delta
            else:
                excess = (w_close - bench) / max(abs(bench), bench_epsilon)
        else:
            if delta > 0:
                excess = (lower - w_close) / delta
            else:
                excess = (bench - w_close) / max(abs(bench), bench_epsilon)
        excess = max(0.0, float(excess))
        confidence = floor + excess_scale * excess
        return min(cap, max(floor, confidence)), excess

    async def _live_eval(
        self,
        ctx: LiveDataContext,
        symbol: str,
        band_pct: float,
        band_abs: float,
        confidence_floor: float,
        confidence_cap: float,
        confidence_excess_scale: float,
    ) -> TradeSignal | None:
        bench = await ha_cache.month_ha_open(ctx._session, symbol)
        if bench is None:
            await ctx.log_step(f"{symbol}: skip — month HA open unavailable")
            return None

        daily = await ctx.get_bars(symbol, "1d", limit=12)
        if daily is None or daily.empty:
            await ctx.log_step(f"{symbol}: skip — no daily bars")
            return None
        w_close = await ha_cache.week_ha_close(ctx._session, symbol, daily)
        if w_close is None:
            await ctx.log_step(f"{symbol}: skip — week HA close unavailable")
            return None

        delta = abs(bench) * band_pct + band_abs
        upper = bench + delta
        lower = bench - delta
        as_of = daily.index[-1]
        sig = self._signal_from_values(
            symbol,
            bench,
            w_close,
            band_pct,
            band_abs,
            as_of,
            confidence_floor=confidence_floor,
            confidence_cap=confidence_cap,
            confidence_excess_scale=confidence_excess_scale,
        )
        if sig is not None:
            await ctx.log_step(
                f"{symbol}: {sig.direction.upper()} — {sig.reasoning}",
                symbol=symbol,
                bench=round(float(bench), 4),
                week_ha_close=round(float(w_close), 4),
                upper=round(float(upper), 4),
                lower=round(float(lower), 4),
                direction=sig.direction,
            )
        else:
            await ctx.log_step(
                f"{symbol}: neutral — week HA close {w_close:.4f} within band "
                f"[{lower:.4f}, {upper:.4f}] (bench {bench:.4f})",
                symbol=symbol,
                bench=round(float(bench), 4),
                week_ha_close=round(float(w_close), 4),
                upper=round(float(upper), 4),
                lower=round(float(lower), 4),
                direction="hold",
            )
        return sig

    def _backtest_eval(
        self,
        daily: pd.DataFrame,
        symbol: str,
        band_pct: float,
        band_abs: float,
        confidence_floor: float,
        confidence_cap: float,
        confidence_excess_scale: float,
    ) -> TradeSignal | None:
        if daily.empty or len(daily) < 40:
            return None

        as_of = daily.index[-1]
        as_of_dt = as_of.to_pydatetime() if hasattr(as_of, "to_pydatetime") else as_of

        bench = month_ha_open_backtest(daily, as_of_dt)
        w_close = week_ha_close_backtest(daily, as_of_dt)
        if bench is None or w_close is None:
            return None

        return self._signal_from_values(
            symbol,
            bench,
            w_close,
            band_pct,
            band_abs,
            daily.index[-1],
            confidence_floor=confidence_floor,
            confidence_cap=confidence_cap,
            confidence_excess_scale=confidence_excess_scale,
        )

    def _signal_from_values(
        self,
        symbol: str,
        bench: float,
        w_close: float,
        band_pct: float,
        band_abs: float,
        as_of,
        *,
        confidence_floor: float = 0.5,
        confidence_cap: float = 1.0,
        confidence_excess_scale: float = 0.25,
    ) -> TradeSignal | None:
        if not (pd.notna(bench) and pd.notna(w_close)):
            return None

        delta = abs(bench) * band_pct + band_abs
        upper = bench + delta
        lower = bench - delta

        if w_close > upper:
            conf, excess = self._confidence_from_breakout(
                bench,
                w_close,
                upper,
                lower,
                delta,
                "buy",
                floor=confidence_floor,
                cap=confidence_cap,
                excess_scale=confidence_excess_scale,
            )
            return TradeSignal(
                symbol=symbol,
                direction="buy",
                order_type="market",
                confidence=conf,
                reasoning=(
                    f"weekly HA close {w_close:.4f} > bench+band {upper:.4f} "
                    f"(bench=mo HA open {bench:.4f}, excess={excess:.2f}×band, "
                    f"strength={conf:.0%}, as_of {as_of})"
                ),
            )
        if w_close < lower:
            conf, excess = self._confidence_from_breakout(
                bench,
                w_close,
                upper,
                lower,
                delta,
                "sell",
                floor=confidence_floor,
                cap=confidence_cap,
                excess_scale=confidence_excess_scale,
            )
            return TradeSignal(
                symbol=symbol,
                direction="sell",
                order_type="market",
                confidence=conf,
                reasoning=(
                    f"weekly HA close {w_close:.4f} < bench−band {lower:.4f} "
                    f"(bench=mo HA open {bench:.4f}, excess={excess:.2f}×band, "
                    f"strength={conf:.0%}, as_of {as_of})"
                ),
            )
        return None

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        p = self._params(parameters)
        band_pct = float(p.get("band_pct") or 0.0)
        band_abs = float(p.get("band_abs") or 0.0)
        confidence_floor = float(p.get("confidence_floor") or 0.5)
        confidence_cap = float(p.get("confidence_cap") or 1.0)
        confidence_excess_scale = float(p.get("confidence_excess_scale") or 0.25)

        signals: list[TradeSignal] = []
        use_cache = isinstance(ctx, LiveDataContext)
        conf_kw = dict(
            confidence_floor=confidence_floor,
            confidence_cap=confidence_cap,
            confidence_excess_scale=confidence_excess_scale,
        )

        for symbol in symbols:
            if not symbol:
                continue
            if use_cache:
                sig = await self._live_eval(ctx, symbol, band_pct, band_abs, **conf_kw)
            else:
                tf = str(p.get("timeframe") or "1d")
                daily = await ctx.get_bars(symbol, tf, limit=900)
                sig = self._backtest_eval(daily, symbol, band_pct, band_abs, **conf_kw)
            if sig is not None:
                signals.append(sig)

        return signals
