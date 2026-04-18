from dataclasses import dataclass
from datetime import datetime
import pandas as pd
from src.strategies.base import BaseStrategy
from src.backtesting.data_context import BacktestDataContext
from src.backtesting.exit_policy import ExitPolicy
from src.backtesting.metrics import BacktestMetrics, TradeRecord


@dataclass
class _PositionState:
    trade: TradeRecord
    peak_price: float
    trailing_active: bool = False
    stop_price: float | None = None
    take_profit_price: float | None = None


class BacktestEngine:
    def __init__(self, initial_capital: float = 100_000.0, exit_policy: ExitPolicy | None = None):
        self._capital = initial_capital
        self._exit_policy = exit_policy

    async def run(
        self,
        strategy: BaseStrategy,
        symbols: list[str],
        parameters: dict,
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str = "1d",
    ) -> BacktestMetrics:
        """Simulate strategy on historical data.
        data: {symbol: {timeframe: pd.DataFrame with DatetimeIndex}}
        """
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
        positions: dict[str, _PositionState] = {}
        # Invariant: a sym in pending_close_exits must NOT also be in positions.
        # Always call positions.pop(sym) when moving a state here.
        pending_close_exits: dict[str, tuple[str, _PositionState]] = {}
        closed_trades: list[TradeRecord] = []
        equity_series: dict[datetime, float] = {}

        for i, current_time in enumerate(all_times[:-1]):
            next_time = all_times[i + 1]

            # Settle pending close-mode exits at this bar's open
            for sym, (reason, state) in list(pending_close_exits.items()):
                bar_df = data.get(sym, {}).get(timeframe)
                if bar_df is not None:
                    row = bar_df[bar_df.index == current_time]
                    if not row.empty:
                        fill_price = float(row["open"].iloc[0])
                        state.trade.exit_time = current_time
                        state.trade.exit_price = fill_price
                        state.trade.exit_reason = reason
                        cash += state.trade.quantity * fill_price
                        closed_trades.append(state.trade)
            pending_close_exits.clear()

            # Fill orders at next bar's open price
            ctx = BacktestDataContext(data, current_time)
            signals = await strategy.generate_signals(symbols, parameters, ctx)

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

                # Note: "sell" signals only close existing long positions; short selling not supported.
                if sig.direction == "buy" and sym not in positions:
                    qty = sig.quantity or max(1, int(cash * 0.1 / fill_price))
                    cost = qty * fill_price
                    if cost <= cash:
                        cash -= cost
                        trade = TradeRecord(
                            symbol=sym, direction="buy", quantity=qty,
                            entry_time=fill_time, entry_price=fill_price,
                            entry_signal={"reasoning": sig.reasoning},
                        )
                        positions[sym] = _PositionState(
                            trade=trade,
                            peak_price=fill_price,
                        )
                elif sig.direction == "sell" and sym in positions:
                    state = positions.pop(sym)
                    state.trade.exit_time = fill_time
                    state.trade.exit_price = fill_price
                    state.trade.exit_reason = "signal"
                    cash += state.trade.quantity * fill_price
                    closed_trades.append(state.trade)

            # Mark-to-market equity
            portfolio_value = cash
            for sym, state in positions.items():
                tf_df = data.get(sym, {}).get(timeframe)
                if tf_df is not None:
                    past = tf_df[tf_df.index < next_time]
                    if not past.empty:
                        portfolio_value += state.trade.quantity * float(past["close"].iloc[-1])
            equity_series[current_time] = portfolio_value

        # Settle any pending close-mode exits at last bar's close
        last_time = all_times[-1]
        for sym, (reason, state) in list(pending_close_exits.items()):
            bar_df = data.get(sym, {}).get(timeframe)
            if bar_df is not None and not bar_df.empty:
                last_price = float(bar_df["close"].iloc[-1])
                state.trade.exit_time = last_time
                state.trade.exit_price = last_price
                state.trade.exit_reason = reason
                cash += state.trade.quantity * last_price
                closed_trades.append(state.trade)

        # Close open positions at last bar's close
        for sym, state in list(positions.items()):
            tf_df = data.get(sym, {}).get(timeframe)
            if tf_df is not None and not tf_df.empty:
                last_price = float(tf_df["close"].iloc[-1])
                cash += state.trade.quantity * last_price
                state.trade.exit_time = last_time
                state.trade.exit_price = last_price
                state.trade.exit_reason = "end_of_backtest"
                closed_trades.append(state.trade)

        equity_series[last_time] = cash
        equity_curve = pd.Series(equity_series).sort_index()

        return BacktestMetrics(
            initial_capital=self._capital,
            final_equity=cash,
            trades=closed_trades,
            equity_curve=equity_curve,
        )
