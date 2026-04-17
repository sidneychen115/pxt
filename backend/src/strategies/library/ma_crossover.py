import pandas as pd
from src.strategies.base import BaseStrategy, DataContext, TradeSignal
from src.strategies.indicators import Indicators


class MovingAverageCrossover(BaseStrategy):
    """
    Buy when fast EMA crosses above slow EMA.
    Sell when fast EMA crosses below slow EMA.
    Default: EMA10 vs EMA30 on daily bars.
    """

    id = "ma_crossover"
    name = "Moving Average Crossover"
    description = "EMA crossover strategy: buy on golden cross, sell on death cross."
    default_symbols = ["SPY"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {"fast": 10, "slow": 30}

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
    ) -> list[TradeSignal]:
        fast = parameters.get("fast", self.default_parameters["fast"])
        slow = parameters.get("slow", self.default_parameters["slow"])
        signals: list[TradeSignal] = []

        for symbol in symbols:
            df = await ctx.get_bars(symbol, "1d", limit=slow + 10)
            if df is None or len(df) < slow + 2:
                continue

            fast_ema = Indicators.ema(df, fast)
            slow_ema = Indicators.ema(df, slow)

            if fast_ema.isna().iloc[-2:].any() or slow_ema.isna().iloc[-2:].any():
                continue

            prev_above = fast_ema.iloc[-2] > slow_ema.iloc[-2]
            curr_above = fast_ema.iloc[-1] > slow_ema.iloc[-1]

            if not prev_above and curr_above:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="buy",
                    order_type="market",
                    confidence=0.75,
                    reasoning=(
                        f"EMA{fast} ({fast_ema.iloc[-1]:.2f}) crossed above "
                        f"EMA{slow} ({slow_ema.iloc[-1]:.2f})"
                    ),
                ))
            elif prev_above and not curr_above:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="sell",
                    order_type="market",
                    confidence=0.75,
                    reasoning=(
                        f"EMA{fast} ({fast_ema.iloc[-1]:.2f}) crossed below "
                        f"EMA{slow} ({slow_ema.iloc[-1]:.2f})"
                    ),
                ))

        return signals
