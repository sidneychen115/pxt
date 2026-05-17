import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


def _simulation_bar_indices(
    all_times: list,
    *,
    simulation_start: datetime | None,
    simulation_end: datetime | None,
    fill_mode: str,
) -> tuple[list[int], int]:
    """Indices into ``all_times`` for the user-visible window. Warm-up bars stay in ``data`` only.

    Returns ``(bar_list, i1)`` where ``i1`` is the last bar index included in the simulation.
    """
    n = len(all_times)
    if n < 2:
        raise ValueError("Insufficient data for backtesting.")
    ts_list = [pd.Timestamp(t) for t in all_times]
    if simulation_start is None:
        i0 = 0
    else:
        s0 = pd.Timestamp(simulation_start)
        i0 = next((i for i, t in enumerate(ts_list) if t >= s0), None)
        if i0 is None:
            raise ValueError("simulation_start is after all available bars.")
    if simulation_end is None:
        i1 = n - 1
    else:
        s1 = pd.Timestamp(simulation_end)
        i1 = None
        for j in range(n - 1, -1, -1):
            if ts_list[j] <= s1:
                i1 = j
                break
        if i1 is None:
            raise ValueError("simulation_end is before all available bars.")
    if i1 < i0:
        raise ValueError("Simulation date window has no bars.")
    if fill_mode == "same_close":
        bar_list = list(range(i0, min(i1 + 1, n)))
    else:
        bar_list = list(range(i0, i1))
    if not bar_list:
        raise ValueError("No bars in simulation window for this fill_mode.")
    return bar_list, i1
from src.strategies.base import BaseStrategy, PortfolioSnapshot, TradeSignal
from src.backtesting.data_context import BacktestDataContext
from src.backtesting.exit_policy import ExitPolicy
from src.backtesting.metrics import BacktestMetrics, TradeRecord
from src.backtesting.position_sizing import (
    DEFAULT_BACKTEST_POSITION_PCT,
    buy_quantity_for_signal,
)


@dataclass
class _PositionState:
    trade: TradeRecord
    peak_price: float
    trailing_active: bool = False
    stop_price: float | None = None
    take_profit_price: float | None = None


MAX_SIGNAL_ROUNDS_PER_BAR = 64


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100_000.0,
        exit_policy: ExitPolicy | None = None,
        fill_mode: str = "next_open",
        position_pct: float = DEFAULT_BACKTEST_POSITION_PCT,
    ):
        self._capital = initial_capital
        self._exit_policy = exit_policy
        self._position_pct = max(0.0, min(1.0, float(position_pct)))
        if fill_mode not in ("next_open", "same_close"):
            raise ValueError("fill_mode must be 'next_open' or 'same_close'")
        self._fill_mode = fill_mode

    def _try_execute_signal(
        self,
        sig: TradeSignal,
        *,
        cash: float,
        positions: dict[str, _PositionState],
        closed_trades: list[TradeRecord],
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str,
        next_time: datetime,
        current_time: datetime | None = None,
    ) -> tuple[bool, float]:
        """Execute one signal. ``next_open`` fills at next bar's open; ``same_close`` at current bar's close."""
        sym = sig.symbol
        next_df = data.get(sym, {}).get(timeframe)
        if next_df is None:
            return False, cash

        if self._fill_mode == "same_close":
            if current_time is None:
                return False, cash
            bar = next_df[next_df.index == current_time]
            if bar.empty:
                return False, cash
            fill_price = float(bar["close"].iloc[0])
            fill_time = current_time
        else:
            future = next_df[next_df.index >= next_time]
            if future.empty:
                return False, cash
            fill_price = float(future["open"].iloc[0])
            fill_time = future.index[0]

        if sig.direction == "buy" and sym not in positions:
            qty = buy_quantity_for_signal(
                cash=cash,
                fill_price=fill_price,
                position_pct=self._position_pct,
                signal_quantity=sig.quantity,
            )
            if qty <= 0:
                return False, cash
            cost = qty * fill_price
            if cost <= cash:
                new_cash = cash - cost
                trade = TradeRecord(
                    symbol=sym, direction="buy", quantity=qty,
                    entry_time=fill_time, entry_price=fill_price,
                    entry_signal={"reasoning": sig.reasoning},
                )
                # Long: stop price must be below entry. The *higher* the stop, the *tighter* the max loss.
                # If both exit_policy and strategy (e.g. SuperTrend band) provide a stop, take max() so
                # policy stop_loss_pct always caps risk; strategy can only tighten, not widen past policy.
                strat_stop = float(sig.stop_price) if sig.stop_price is not None else None
                policy_stop = self._compute_stop_price(fill_price, qty)
                candidates: list[float] = []
                if policy_stop is not None and policy_stop > 0 and policy_stop < fill_price:
                    candidates.append(policy_stop)
                if strat_stop is not None and strat_stop > 0 and strat_stop < fill_price:
                    candidates.append(strat_stop)
                initial_stop = max(candidates) if candidates else None
                positions[sym] = _PositionState(
                    trade=trade,
                    peak_price=fill_price,
                    stop_price=initial_stop,
                    take_profit_price=self._compute_tp_price(fill_price, qty),
                )
                return True, new_cash
            return False, cash

        if sig.direction == "sell" and sym in positions:
            if self._exit_policy and self._exit_policy.disable_sell_signal:
                return False, cash
            state = positions.pop(sym)
            state.trade.exit_time = fill_time
            state.trade.exit_price = fill_price
            state.trade.exit_reason = "signal"
            new_cash = cash + state.trade.quantity * fill_price
            closed_trades.append(state.trade)
            return True, new_cash

        return False, cash

    def _compute_stop_price(self, entry: float, qty: float) -> float | None:
        ep = self._exit_policy
        if ep is None:
            return None
        if ep.stop_loss_pct is not None:
            return entry * (1 - ep.stop_loss_pct)
        if ep.stop_loss_abs is not None:
            return entry - ep.stop_loss_abs / qty
        return None

    def _compute_tp_price(self, entry: float, qty: float) -> float | None:
        ep = self._exit_policy
        if ep is None:
            return None
        if ep.take_profit_pct is not None:
            return entry * (1 + ep.take_profit_pct)
        if ep.take_profit_abs is not None:
            return entry + ep.take_profit_abs / qty
        return None

    def _update_state(self, state: _PositionState, bar: pd.Series) -> None:
        """Update peak_price and check trailing stop activation."""
        ep = self._exit_policy
        if ep is None:
            return
        check_price = (
            float(bar["high"]) if ep.exit_price_check_mode == "ohlc" else float(bar["close"])
        )
        state.peak_price = max(state.peak_price, check_price)

        if ep.trailing_stop_pct is not None and not state.trailing_active:
            if state.take_profit_price is not None:
                # TP price acts as trailing activation threshold (handled in Task 6)
                if state.peak_price >= state.take_profit_price:
                    state.trailing_active = True
            elif ep.trailing_activate_pct is not None:
                if state.peak_price >= state.trade.entry_price * (1 + ep.trailing_activate_pct):
                    state.trailing_active = True
            else:
                # No activation threshold → active immediately
                state.trailing_active = True

    def _check_exit(self, state: _PositionState, bar: pd.Series) -> str | None:
        """Return exit reason if position should exit this bar, else None."""
        ep = self._exit_policy
        if ep is None:
            return None
        if ep.exit_price_check_mode == "ohlc":
            low = float(bar["low"])
            high = float(bar["high"])
            # Priority 1: stop loss
            if state.stop_price is not None and low <= state.stop_price:
                return "stop_loss"
            # Priority 2: trailing stop (when active)
            if state.trailing_active and ep.trailing_stop_pct is not None:
                trail_price = state.peak_price * (1 - ep.trailing_stop_pct)
                if low <= trail_price:
                    return "trailing_stop"
            # Priority 3: fixed take profit (only if trailing not yet active)
            if not state.trailing_active and state.take_profit_price is not None:
                if high >= state.take_profit_price:
                    return "take_profit"
        else:
            close = float(bar["close"])
            if state.stop_price is not None and close <= state.stop_price:
                return "stop_loss"
            if state.trailing_active and ep.trailing_stop_pct is not None:
                trail_price = state.peak_price * (1 - ep.trailing_stop_pct)
                if close <= trail_price:
                    return "trailing_stop"
            if not state.trailing_active and state.take_profit_price is not None:
                if close >= state.take_profit_price:
                    return "take_profit"
        return None

    def _ohlc_fill_price(self, state: _PositionState, reason: str) -> float:
        """Compute exact fill price for intrabar (ohlc mode) exits."""
        ep = self._exit_policy
        if reason == "stop_loss":
            assert state.stop_price is not None
            return state.stop_price
        if reason == "take_profit":
            assert state.take_profit_price is not None, "take_profit exit with no TP price configured"
            return state.take_profit_price
        if reason == "trailing_stop":
            assert ep is not None and ep.trailing_stop_pct is not None
            return state.peak_price * (1 - ep.trailing_stop_pct)
        raise ValueError(f"Unknown exit reason for ohlc fill: {reason}")

    def _account_equity(
        self,
        cash: float,
        positions: dict[str, _PositionState],
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str,
        as_of: datetime,
    ) -> float:
        """Cash plus open positions marked at ``as_of`` bar's close (per symbol)."""
        total = cash
        for sym, state in positions.items():
            tf_df = data.get(sym, {}).get(timeframe)
            if tf_df is None or tf_df.empty:
                continue
            eligible = tf_df[tf_df.index <= as_of]
            if eligible.empty:
                continue
            px = float(eligible["close"].iloc[-1])
            total += state.trade.quantity * px
        return total

    async def run(
        self,
        strategy: BaseStrategy,
        symbols: list[str],
        parameters: dict,
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str = "1d",
        *,
        simulation_start: datetime | None = None,
        simulation_end: datetime | None = None,
        bar_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> BacktestMetrics:
        """Simulate strategy on historical data.
        data: {symbol: {timeframe: pd.DataFrame with DatetimeIndex}}

        
        If ``simulation_start`` / ``simulation_end`` are set, bars before start are only used
        for strategies (e.g. long lookback HA); equity and fills are computed from start onward.
        """
        all_times = sorted({
            ts
            for sym_data in data.values()
            for tf, df in sym_data.items()
            if tf == timeframe
            for ts in df.index
        })
        bar_list, i1 = _simulation_bar_indices(
            all_times,
            simulation_start=simulation_start,
            simulation_end=simulation_end,
            fill_mode=self._fill_mode,
        )
        last_time = all_times[i1]

        # Yield so the event loop can serve HTTP polls / WS right after entering engine phase.
        await asyncio.sleep(0)

        cash = self._capital
        positions: dict[str, _PositionState] = {}
        # Invariant: a sym in pending_close_exits must NOT also be in positions.
        # Always call positions.pop(sym) when moving a state here.
        pending_close_exits: dict[str, tuple[str, _PositionState]] = {}
        closed_trades: list[TradeRecord] = []
        equity_series: dict[datetime, float] = {}

        n_bars = len(bar_list)
        report_stride = max(1, min(2500, n_bars // 80)) if n_bars else 1

        for step, i in enumerate(bar_list):
            current_time = all_times[i]
            next_time = all_times[i + 1] if i + 1 < len(all_times) else None
            # Cooperate with asyncio so polling can observe progress_phase while the engine runs.
            await asyncio.sleep(0)
            if bar_progress and n_bars:
                done = step + 1
                if step == 0 or done == n_bars or done % report_stride == 0:
                    await bar_progress(done, n_bars)

            # Settle pending close-mode exits at this bar's open (market stop: fill at open, including
            # gap-through — consistent with a protective stop that executes when trading resumes).
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

            # Check exit policy on current bar (runs before strategy signals)
            if self._exit_policy:
                for sym in list(positions):
                    state = positions[sym]
                    bar_df = data.get(sym, {}).get(timeframe)
                    if bar_df is None:
                        continue
                    row = bar_df[bar_df.index == current_time]
                    if row.empty:
                        continue
                    bar = row.iloc[0]
                    self._update_state(state, bar)
                    reason = self._check_exit(state, bar)
                    if reason:
                        if self._exit_policy.exit_price_check_mode == "ohlc":
                            fill_price = self._ohlc_fill_price(state, reason)
                            state.trade.exit_time = current_time
                            state.trade.exit_price = fill_price
                            state.trade.exit_reason = reason
                            cash += state.trade.quantity * fill_price
                            closed_trades.append(state.trade)
                            del positions[sym]
                        else:
                            # Invariant: positions.pop(sym) is paired with adding to pending_close_exits
                            pending_close_exits[sym] = (reason, positions.pop(sym))

            # Strategy signals; recall after each successful fill with updated cash.
            round_i = 0
            inclusive = self._fill_mode == "same_close"
            while round_i < MAX_SIGNAL_ROUNDS_PER_BAR:
                ctx = BacktestDataContext(data, current_time, inclusive_end=inclusive)
                equity = self._account_equity(cash, positions, data, timeframe, current_time)
                snapshot = PortfolioSnapshot(
                    cash=cash,
                    initial_capital=self._capital,
                    equity=equity,
                    positions={sym: float(st.trade.quantity) for sym, st in positions.items()},
                )
                signals = await strategy.generate_signals(symbols, parameters, ctx, portfolio=snapshot)
                if not signals:
                    break
                progressed = False
                for sig in signals:
                    filled, new_cash = self._try_execute_signal(
                        sig,
                        cash=cash,
                        positions=positions,
                        closed_trades=closed_trades,
                        data=data,
                        timeframe=timeframe,
                        next_time=next_time if next_time is not None else current_time,
                        current_time=current_time,
                    )
                    if filled:
                        cash = new_cash
                        progressed = True
                        round_i += 1
                        break
                if not progressed:
                    break

            # Mark-to-market equity
            portfolio_value = cash
            for sym, state in positions.items():
                tf_df = data.get(sym, {}).get(timeframe)
                if tf_df is not None:
                    if next_time is not None:
                        past = tf_df[tf_df.index < next_time]
                    else:
                        past = tf_df[tf_df.index <= current_time]
                    if not past.empty:
                        portfolio_value += state.trade.quantity * float(past["close"].iloc[-1])
            equity_series[current_time] = portfolio_value

        # Settle any pending close-mode exits at last bar's open
        for sym, (reason, state) in list(pending_close_exits.items()):
            bar_df = data.get(sym, {}).get(timeframe)
            if bar_df is not None and not bar_df.empty:
                last_bar = bar_df[bar_df.index == last_time]
                if not last_bar.empty:
                    fill_price = float(last_bar["open"].iloc[0])
                else:
                    import logging
                    logging.getLogger(__name__).warning(
                        "pending close exit for %s: last bar missing, falling back to last close", sym
                    )
                    fill_price = float(bar_df["close"].iloc[-1])
                state.trade.exit_time = last_time
                state.trade.exit_price = fill_price
                state.trade.exit_reason = reason
                cash += state.trade.quantity * fill_price
                closed_trades.append(state.trade)

        # Close open positions at last bar's close
        for sym, state in list(positions.items()):
            tf_df = data.get(sym, {}).get(timeframe)
            if tf_df is not None and not tf_df.empty:
                el = tf_df[tf_df.index <= last_time]
                if el.empty:
                    last_price = float(tf_df["close"].iloc[-1])
                else:
                    last_price = float(el["close"].iloc[-1])
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
