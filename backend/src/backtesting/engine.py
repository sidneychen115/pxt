import asyncio
from datetime import datetime
import pandas as pd
from src.strategies.base import BaseStrategy
from src.backtesting.data_context import BacktestDataContext
from src.backtesting.metrics import BacktestMetrics, TradeRecord


class BacktestEngine:
    def __init__(self, initial_capital: float = 100_000.0):
        self._capital = initial_capital

    async def run(
        self,
        strategy: BaseStrategy,
        symbols: list[str],
        parameters: dict,
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str = "1d",
    ) -> BacktestMetrics:
        """
        Simulate strategy on historical data.
        data: {symbol: {timeframe: pd.DataFrame with DatetimeIndex}}
        """
        # Build sorted list of bar timestamps (simulation steps)
        all_times = sorted({
            ts
            for sym_data in data.values()
            for tf, df in sym_data.items()
            if tf == timeframe
            for ts in df.index
        })
        if len(all_times) < 2:
            raise ValueError("Insufficient data for backtesting.")

        cash = self._capital
        positions: dict[str, TradeRecord] = {}  # symbol -> open trade
        closed_trades: list[TradeRecord] = []
        equity_series: dict[datetime, float] = {}

        for i, current_time in enumerate(all_times[:-1]):
            next_time = all_times[i + 1]
            ctx = BacktestDataContext(data, current_time)

            signals = await strategy.generate_signals(symbols, parameters, ctx)

            # Fill orders at next bar's open price
            for sig in signals:
                sym = sig.symbol
                next_df = data.get(sym, {}).get(timeframe)
                if next_df is None:
                    continue
                future = next_df[next_df.index >= next_time]
                if future.empty:
                    continue
                fill_price = float(future["open"].iloc[0])
                fill_time = future.index[0]

                if sig.direction == "buy" and sym not in positions:
                    qty = sig.quantity or max(1, int(cash * 0.1 / fill_price))
                    cost = qty * fill_price
                    if cost <= cash:
                        cash -= cost
                        positions[sym] = TradeRecord(
                            symbol=sym, direction="buy", quantity=qty,
                            entry_time=fill_time, entry_price=fill_price,
                            entry_signal={"reasoning": sig.reasoning},
                        )
                elif sig.direction == "sell" and sym in positions:
                    trade = positions.pop(sym)
                    trade.exit_time = fill_time
                    trade.exit_price = fill_price
                    trade.exit_reason = "signal"
                    cash += trade.quantity * fill_price
                    closed_trades.append(trade)

            # Mark-to-market equity
            portfolio_value = cash
            for sym, trade in positions.items():
                tf_df = data.get(sym, {}).get(timeframe)
                if tf_df is not None:
                    past = tf_df[tf_df.index <= current_time]
                    if not past.empty:
                        portfolio_value += trade.quantity * float(past["close"].iloc[-1])
            equity_series[current_time] = portfolio_value

        # Close open positions at last bar's close
        last_time = all_times[-1]
        for sym, trade in list(positions.items()):
            tf_df = data.get(sym, {}).get(timeframe)
            if tf_df is not None and not tf_df.empty:
                last_price = float(tf_df["close"].iloc[-1])
                cash += trade.quantity * last_price
                trade.exit_time = last_time
                trade.exit_price = last_price
                trade.exit_reason = "end_of_backtest"
                closed_trades.append(trade)

        equity_series[last_time] = cash
        equity_curve = pd.Series(equity_series).sort_index()

        return BacktestMetrics(
            initial_capital=self._capital,
            final_equity=cash,
            trades=closed_trades,
            equity_curve=equity_curve,
        )
