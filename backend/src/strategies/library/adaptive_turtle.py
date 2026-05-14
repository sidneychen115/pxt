"""
Adaptive Turtle–style Donchian breakout with benchmark trend filter.

Original sketch lived at `strategy_input_raw/turtle_raw.py`; this module is the
framework-compatible implementation (async `get_bars`, `TradeSignal` list).

Position sizing (optional): classic Turtle-style dollar risk per unit using ATR
as dollar volatility per share — ``quantity ≈ floor((equity × dollar_risk_pct) / ATR)``,
capped by affordable shares from cash. Set ``dollar_risk_pct`` to 0 to use the
backtest engine default (fixed cash fraction).
"""

from __future__ import annotations

import math

import pandas as pd

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.indicators import Indicators


def compute_atr_position_size(
    equity: float,
    cash: float,
    last_close: float,
    atr: float,
    dollar_risk_pct: float,
) -> float | None:
    """
    Turtle-style size: risk ``dollar_risk_pct`` of equity per position, where
    per-share volatility is approximated by ATR. Returns integer share count as float,
    or None if sizing should be deferred to the engine (invalid inputs).
    """
    if equity <= 0 or cash <= 0 or last_close <= 0:
        return None
    if not math.isfinite(atr) or atr <= 0:
        return None
    if not (0 < dollar_risk_pct <= 1.0):
        return None
    qty_from_risk = (equity * dollar_risk_pct) / atr
    max_shares = cash / last_close
    qty = min(qty_from_risk, max_shares)
    if qty < 1:
        return None
    return float(int(qty))


class AdaptiveTurtleStrategy(BaseStrategy):
    """
    Donchian breakout:
    - Buy when close breaks above the prior bar's N-day high (entry channel).
    - Sell when close breaks below the prior bar's M-day low (exit channel).
    - Optional bull filter: benchmark close > benchmark's long MA (default SPY vs 200d).

    Include the benchmark symbol (e.g. SPY) in the backtest `symbols` if you use
    the filter; otherwise the filter is skipped when benchmark history is missing.

    Buys use ATR-based position sizing when ``dollar_risk_pct`` > 0: risk that
    fraction of account equity per new entry, using ``atr_period``-day ATR as $
    volatility per share. Live runs without a portfolio snapshot should pass
    ``account_equity`` (and optionally ``account_cash``) in parameters.
    """

    id = "adaptive_turtle"
    name = "Adaptive Turtle (Donchian)"
    description = (
        "Donchian breakout with optional SPY trend filter and ATR-based position sizing. "
        "Buy on N-day high breakout when benchmark is above its MA; "
        "sell on M-day low breakdown. Add SPY to symbols when using the filter."
    )
    default_symbols = ["SPY", "QQQ", "AAPL"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "fast_period": 20,
        "slow_period": 10,
        "benchmark_symbol": "SPY",
        "benchmark_ma_period": 200,
        "atr_period": 20,
        "dollar_risk_pct": 0.01,
    }

    def _equity_and_cash(
        self, portfolio: PortfolioSnapshot | None, parameters: dict
    ) -> tuple[float, float]:
        """Equity for risk budget and cash for affordability cap."""
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

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        fast_period = int(parameters.get("fast_period", self.default_parameters["fast_period"]))
        slow_period = int(parameters.get("slow_period", self.default_parameters["slow_period"]))
        benchmark_symbol = str(parameters.get("benchmark_symbol", self.default_parameters["benchmark_symbol"]))
        benchmark_ma = int(parameters.get("benchmark_ma_period", self.default_parameters["benchmark_ma_period"]))
        atr_period = int(parameters.get("atr_period", self.default_parameters["atr_period"]))
        raw_risk = parameters.get("dollar_risk_pct", self.default_parameters["dollar_risk_pct"])
        try:
            dollar_risk_pct = float(raw_risk)
        except (TypeError, ValueError):
            dollar_risk_pct = float(self.default_parameters["dollar_risk_pct"])
        if dollar_risk_pct < 0:
            dollar_risk_pct = 0.0
        if dollar_risk_pct > 0.25:
            dollar_risk_pct = 0.25

        min_bars = max(fast_period, slow_period, atr_period, 5) + 3

        is_bull_market = await self._benchmark_bull(
            ctx, benchmark_symbol, benchmark_ma
        )

        equity, cash_budget = self._equity_and_cash(portfolio, parameters)

        signals: list[TradeSignal] = []

        for symbol in symbols:
            if not symbol:
                continue

            df = await ctx.get_bars(symbol, "1d", limit=max(min_bars, benchmark_ma + 5))
            if df is None or len(df) < min_bars:
                continue

            high_n = df["high"].rolling(window=fast_period).max()
            low_n = df["low"].rolling(window=slow_period).min()

            prev_breakout_high = high_n.shift(1).iloc[-1]
            prev_breakout_low = low_n.shift(1).iloc[-1]
            close = float(df["close"].iloc[-1])

            if pd.isna(prev_breakout_high) or pd.isna(prev_breakout_low):
                continue

            atr_series = Indicators.atr(df, atr_period)
            atr_last = float(atr_series.iloc[-1]) if atr_series is not None else float("nan")
            if pd.isna(atr_last):
                atr_last = float("nan")

            buy_qty: float | None = None
            if dollar_risk_pct > 0:
                buy_qty = compute_atr_position_size(
                    equity, cash_budget, close, atr_last, dollar_risk_pct
                )

            if close > prev_breakout_high and is_bull_market:
                reasoning = (
                    f"Close {close:.2f} > prior {fast_period}d high {prev_breakout_high:.2f}; "
                    f"benchmark filter={is_bull_market}"
                )
                if dollar_risk_pct > 0 and buy_qty is not None:
                    reasoning += (
                        f"; ATR({atr_period})={atr_last:.2f}, "
                        f"risk_pct={dollar_risk_pct:.4f}, qty={int(buy_qty)}"
                    )
                elif dollar_risk_pct > 0:
                    reasoning += (
                        f"; ATR sizing skipped (ATR={atr_last}), default sizing"
                    )
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="buy",
                        order_type="market",
                        quantity=buy_qty if dollar_risk_pct > 0 else None,
                        confidence=0.7,
                        reasoning=reasoning,
                    )
                )
            elif close < prev_breakout_low:
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="sell",
                        order_type="market",
                        confidence=0.7,
                        reasoning=(
                            f"Close {close:.2f} < prior {slow_period}d low {prev_breakout_low:.2f} "
                            f"(exit channel)"
                        ),
                    )
                )

        return signals

    async def _benchmark_bull(
        self, ctx: DataContext, benchmark_symbol: str, ma_period: int
    ) -> bool:
        """True if benchmark close > MA(close); True if data insufficient (no filter)."""
        need = max(ma_period + 5, 50)
        spy_df = await ctx.get_bars(benchmark_symbol, "1d", limit=need)
        if spy_df is None or len(spy_df) < ma_period:
            return True
        close = spy_df["close"]
        ma = close.rolling(ma_period).mean().iloc[-1]
        last = close.iloc[-1]
        if pd.isna(ma) or pd.isna(last):
            return True
        return bool(last > ma)
