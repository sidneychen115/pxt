# Exit Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-backtest configurable stop-loss, take-profit, and trailing stop exit rules to the BacktestEngine, persisted in the DB and configurable from the API and UI.

**Architecture:** A new `ExitPolicy` pydantic model holds all exit parameters. `BacktestEngine` accepts an optional `ExitPolicy` and checks exit conditions each bar before processing strategy signals. Positions are tracked via an internal `_PositionState` dataclass that carries precomputed stop/TP prices and trailing state.

**Tech Stack:** Python, Pydantic v2, pandas, SQLAlchemy 2 async, Alembic, FastAPI, React, TypeScript

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/src/backtesting/exit_policy.py` | ExitPolicy pydantic model + validators |
| Modify | `backend/src/backtesting/engine.py` | _PositionState, exit check logic, helper methods |
| Modify | `backend/src/core/models.py` | Add `exit_policy JSONB` column to `Backtest` |
| Create | `backend/alembic/versions/<hash>_add_exit_policy_to_backtest.py` | DB migration |
| Modify | `backend/src/api/routers/backtests.py` | BacktestRequest + _run_backtest wiring |
| Modify | `frontend/src/types/index.ts` | ExitPolicy interface, update Backtest type |
| Modify | `frontend/src/api/backtests.ts` | Add exit_policy to triggerBacktest |
| Modify | Frontend backtest form component | ExitPolicy form fields (find via grep) |
| Create | `backend/tests/test_exit_policy_model.py` | ExitPolicy validator tests |
| Modify | `backend/tests/test_backtest_engine.py` | (no changes needed) |
| Create | `backend/tests/test_exit_policy_engine.py` | Engine exit behavior tests |

---

## Task 1: ExitPolicy Model + Validation Tests

**Files:**
- Create: `backend/src/backtesting/exit_policy.py`
- Create: `backend/tests/test_exit_policy_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_exit_policy_model.py
import pytest
from src.backtesting.exit_policy import ExitPolicy


def test_stop_loss_mutual_exclusion():
    with pytest.raises(ValueError, match="stop_loss"):
        ExitPolicy(stop_loss_pct=0.05, stop_loss_abs=500.0)


def test_take_profit_mutual_exclusion():
    with pytest.raises(ValueError, match="take_profit"):
        ExitPolicy(take_profit_pct=0.15, take_profit_abs=2000.0)


def test_trailing_activate_requires_trailing_stop():
    with pytest.raises(ValueError, match="trailing_stop_pct"):
        ExitPolicy(trailing_activate_pct=0.05)


def test_all_none_is_valid():
    policy = ExitPolicy()
    assert policy.stop_loss_pct is None
    assert policy.trailing_stop_pct is None
    assert policy.price_check_mode == "close"


def test_valid_combined_policy():
    policy = ExitPolicy(
        stop_loss_pct=0.05,
        take_profit_pct=0.15,
        trailing_stop_pct=0.03,
        price_check_mode="ohlc",
    )
    assert policy.stop_loss_pct == 0.05
    assert policy.price_check_mode == "ohlc"


def test_trailing_with_activation_valid():
    policy = ExitPolicy(trailing_stop_pct=0.05, trailing_activate_pct=0.10)
    assert policy.trailing_activate_pct == 0.10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_exit_policy_model.py -v
```

Expected: `ModuleNotFoundError` (file doesn't exist yet)

- [ ] **Step 3: Create ExitPolicy model**

```python
# backend/src/backtesting/exit_policy.py
from __future__ import annotations
from pydantic import BaseModel, model_validator
from typing import Literal


class ExitPolicy(BaseModel):
    stop_loss_pct: float | None = None
    stop_loss_abs: float | None = None
    take_profit_pct: float | None = None
    take_profit_abs: float | None = None
    trailing_stop_pct: float | None = None
    trailing_activate_pct: float | None = None
    price_check_mode: Literal["close", "ohlc"] = "close"

    @model_validator(mode="after")
    def _validate(self) -> ExitPolicy:
        if self.stop_loss_pct is not None and self.stop_loss_abs is not None:
            raise ValueError("Specify stop_loss_pct or stop_loss_abs, not both")
        if self.take_profit_pct is not None and self.take_profit_abs is not None:
            raise ValueError("Specify take_profit_pct or take_profit_abs, not both")
        if self.trailing_activate_pct is not None and self.trailing_stop_pct is None:
            raise ValueError("trailing_activate_pct requires trailing_stop_pct")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_exit_policy_model.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtesting/exit_policy.py backend/tests/test_exit_policy_model.py
git commit -m "feat: add ExitPolicy pydantic model with validators"
```

---

## Task 2: Engine _PositionState Refactor (No Behavior Change)

**Files:**
- Modify: `backend/src/backtesting/engine.py`

This task introduces `_PositionState` and wires `exit_policy` into `__init__`, but adds no exit logic yet. Existing tests must still pass.

- [ ] **Step 1: Replace engine.py with refactored version**

Full replacement of `backend/src/backtesting/engine.py`:

```python
import asyncio
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
```

- [ ] **Step 2: Run existing engine tests to verify no regressions**

```bash
cd backend && python -m pytest tests/test_backtest_engine.py -v
```

Expected: 4 passed (same as before)

- [ ] **Step 3: Commit**

```bash
git add backend/src/backtesting/engine.py
git commit -m "refactor: introduce _PositionState in BacktestEngine, wire exit_policy param"
```

---

## Task 3: Stop Loss Implementation (TDD)

**Files:**
- Modify: `backend/src/backtesting/engine.py`
- Create: `backend/tests/test_exit_policy_engine.py`

- [ ] **Step 1: Write failing stop-loss tests**

```python
# backend/tests/test_exit_policy_engine.py
import pytest
import pandas as pd
from src.backtesting.engine import BacktestEngine
from src.backtesting.exit_policy import ExitPolicy
from src.strategies.base import BaseStrategy, TradeSignal


def make_bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Build OHLCV DataFrame. Each row is (open, high, low, close)."""
    dates = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=dates, columns=["open", "high", "low", "close"])
    df["volume"] = 1000
    return df


class _BuyOnceStrategy(BaseStrategy):
    """Buy on the first bar (0 bars visible), never sell."""
    name = "_test_buy_once"

    def __init__(self):
        self._bought = False

    async def generate_signals(self, symbols, parameters, ctx):
        sym = symbols[0]
        bars = await ctx.get_bars(sym, "1d")
        if len(bars) == 0 and not self._bought:
            self._bought = True
            return [TradeSignal(symbol=sym, direction="buy", reasoning="test")]
        return []


async def test_stop_loss_pct_close():
    # Buy fills at t1 open=100. SL=5% → stop at 95.
    # t2: close=93 < 95 → SL queued. t3: fill at open=92.
    bars = make_bars([
        (100, 101, 99, 100),  # t0: buy signal (0 bars visible)
        (100, 102, 99, 101),  # t1: buy fills at open=100; close=101 > 95 → hold
        (101, 102, 90, 93),   # t2: close=93 < 95 → SL queued
        (92,  92,  92, 92),   # t3: SL fills at open=92
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_pct=0.05),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert len(metrics.trades) == 1
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(92.0)


async def test_stop_loss_abs_close():
    # Buy 10 shares at 100 = $1000 cost. SL abs=$200 → stop at 100-200/10=80.
    # t2: close=79 < 80 → SL queued. t3: fill at open=78.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),  # t1: buy 10 shares at 100
        (101, 102, 75, 79),   # t2: close=79 < 80 → SL queued
        (78,  78,  78, 78),   # t3: fill at 78
    ])

    class _BuyFixedQtyStrategy(BaseStrategy):
        name = "_test_fixed_qty"
        def __init__(self):
            self._bought = False
        async def generate_signals(self, symbols, parameters, ctx):
            sym = symbols[0]
            bars = await ctx.get_bars(sym, "1d")
            if len(bars) == 0 and not self._bought:
                self._bought = True
                return [TradeSignal(symbol=sym, direction="buy", reasoning="test", quantity=10)]
            return []

    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_abs=200.0),
    )
    metrics = await engine.run(_BuyFixedQtyStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(78.0)


async def test_stop_loss_ohlc():
    # Buy at t1 open=100. SL=5% → stop=95. t2: low=90 < 95 → fill at 95 immediately.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),  # t1: buy at 100
        (101, 102, 90, 93),   # t2: low=90 < 95 → fill at 95 (stop price)
        (92,  92,  92, 92),   # t3: not reached for this trade
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_pct=0.05, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(95.0)


async def test_no_policy_behavior_unchanged():
    # Without exit_policy, position holds through SL-triggering bars → end_of_backtest.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 102, 90, 93),   # would trigger SL if policy existed
        (92,  92,  92, 92),
    ])
    engine = BacktestEngine(initial_capital=10_000)
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert metrics.trades[0].exit_reason == "end_of_backtest"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py -v
```

Expected: 4 FAILED (exit policy logic not implemented yet)

- [ ] **Step 3: Add helper methods and stop-loss exit block to engine.py**

Add these methods to `BacktestEngine` (after `__init__`, before `run`):

```python
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
    """Update peak_price (trailing activation added in Task 5)."""
    ep = self._exit_policy
    check_price = float(bar["high"]) if ep.price_check_mode == "ohlc" else float(bar["close"])
    state.peak_price = max(state.peak_price, check_price)

def _check_exit(self, state: _PositionState, bar: pd.Series) -> str | None:
    """Return exit reason if position should exit this bar, else None."""
    ep = self._exit_policy
    if ep.price_check_mode == "ohlc":
        low = float(bar["low"])
        if state.stop_price is not None and low <= state.stop_price:
            return "stop_loss"
    else:
        close = float(bar["close"])
        if state.stop_price is not None and close <= state.stop_price:
            return "stop_loss"
    return None

def _ohlc_fill_price(self, state: _PositionState, reason: str) -> float:
    """Compute exact fill price for intrabar (ohlc mode) exits."""
    ep = self._exit_policy
    if reason == "stop_loss":
        return state.stop_price
    if reason == "take_profit":
        return state.take_profit_price
    if reason == "trailing_stop":
        return state.peak_price * (1 - ep.trailing_stop_pct)
    raise ValueError(f"Unknown exit reason for ohlc fill: {reason}")
```

In the `run` method, update position creation to precompute prices:

```python
# Replace the existing _PositionState construction in the buy handler:
positions[sym] = _PositionState(
    trade=trade,
    peak_price=fill_price,
    stop_price=self._compute_stop_price(fill_price, qty),
    take_profit_price=self._compute_tp_price(fill_price, qty),
)
```

Add the exit policy check block in `run`, **between** the `pending_close_exits.clear()` settlement and the `ctx = BacktestDataContext(...)` strategy call:

```python
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
            if self._exit_policy.price_check_mode == "ohlc":
                fill_price = self._ohlc_fill_price(state, reason)
                state.trade.exit_time = current_time
                state.trade.exit_price = fill_price
                state.trade.exit_reason = reason
                cash += state.trade.quantity * fill_price
                closed_trades.append(state.trade)
                del positions[sym]
            else:
                pending_close_exits[sym] = (reason, positions.pop(sym))
```

- [ ] **Step 4: Run stop-loss tests**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
cd backend && python -m pytest -v
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/backtesting/engine.py backend/tests/test_exit_policy_engine.py
git commit -m "feat: implement stop-loss exit in BacktestEngine (close + ohlc modes)"
```

---

## Task 4: Take Profit Implementation (TDD)

**Files:**
- Modify: `backend/src/backtesting/engine.py`
- Modify: `backend/tests/test_exit_policy_engine.py`

- [ ] **Step 1: Add failing take-profit tests**

Append to `backend/tests/test_exit_policy_engine.py`:

```python
async def test_take_profit_pct_close():
    # Buy at t1 open=100. TP=15% → tp=115.
    # t2: close=116 >= 115 → TP queued. t3: fill at open=117.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # t1: buy at 100; close=101 < 115 → hold
        (101, 120, 100, 116),  # t2: close=116 >= 115 → TP queued
        (117, 120, 116, 118),  # t3: fill at open=117
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_pct=0.15),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(117.0)


async def test_take_profit_abs_close():
    # Buy 10 shares at 100 = $1000. TP abs=$200 → tp=100+200/10=120.
    # t2: close=121 >= 120 → TP queued. t3: fill at open=122.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 125, 100, 121),
        (122, 125, 120, 123),
    ])

    class _BuyFixedQtyStrategy(BaseStrategy):
        name = "_test_fixed_qty2"
        def __init__(self):
            self._bought = False
        async def generate_signals(self, symbols, parameters, ctx):
            sym = symbols[0]
            bars = await ctx.get_bars(sym, "1d")
            if len(bars) == 0 and not self._bought:
                self._bought = True
                return [TradeSignal(symbol=sym, direction="buy", reasoning="test", quantity=10)]
            return []

    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_abs=200.0),
    )
    metrics = await engine.run(_BuyFixedQtyStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(122.0)


async def test_take_profit_ohlc():
    # Buy at t1 open=100. TP=15% → tp=115. t2: high=116 >= 115 → fill at 115 exactly.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # t1: buy at 100
        (101, 116, 100, 112),  # t2: high=116 >= 115 → fill at 115
        (112, 113, 111, 112),  # t3: not reached
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_pct=0.15, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(115.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py::test_take_profit_pct_close -v
```

Expected: FAILED (take_profit not in `_check_exit` yet)

- [ ] **Step 3: Extend `_check_exit` to handle take profit**

Replace `_check_exit` in `engine.py`:

```python
def _check_exit(self, state: _PositionState, bar: pd.Series) -> str | None:
    """Return exit reason if position should exit this bar, else None."""
    ep = self._exit_policy
    if ep.price_check_mode == "ohlc":
        low = float(bar["low"])
        high = float(bar["high"])
        # Priority 1: stop loss
        if state.stop_price is not None and low <= state.stop_price:
            return "stop_loss"
        # Priority 2: trailing stop — added in Task 5
        # Priority 3: fixed take profit (only if trailing not active)
        if not state.trailing_active and state.take_profit_price is not None:
            if high >= state.take_profit_price:
                return "take_profit"
    else:
        close = float(bar["close"])
        if state.stop_price is not None and close <= state.stop_price:
            return "stop_loss"
        if not state.trailing_active and state.take_profit_price is not None:
            if close >= state.take_profit_price:
                return "take_profit"
    return None
```

- [ ] **Step 4: Run take-profit tests**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py -v
```

Expected: all 7 tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtesting/engine.py backend/tests/test_exit_policy_engine.py
git commit -m "feat: implement take-profit exit in BacktestEngine (close + ohlc modes)"
```

---

## Task 5: Trailing Stop Implementation (TDD)

**Files:**
- Modify: `backend/src/backtesting/engine.py`
- Modify: `backend/tests/test_exit_policy_engine.py`

- [ ] **Step 1: Add failing trailing stop tests**

Append to `backend/tests/test_exit_policy_engine.py`:

```python
async def test_trailing_stop_immediate():
    # trailing_stop_pct=0.05, no activation threshold → active from entry.
    # Buy at t1 open=100. peak starts at 100.
    # t1: close=110 → peak=110, trail=104.5; close=110 > 104.5 → hold
    # t2: close=108 → peak still 110, trail=104.5; close=108 > 104.5 → hold
    # t3: close=104 → close=104 < 104.5 → TS queued; fill at t4 open=103
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 111, 99, 110),   # t1: buy at 100; peak=110
        (110, 112, 107, 108),  # t2: peak=110, trail=104.5; hold
        (108, 109, 103, 104),  # t3: close=104 < 104.5 → TS queued
        (103, 104, 102, 103),  # t4: fill at open=103
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(103.0)


async def test_trailing_stop_ohlc():
    # trailing_stop_pct=0.05, ohlc mode. peak updates on bar high.
    # Buy at t1 open=100.
    # t1: high=115 → peak=115, trail=109.25; low=110 > 109.25 → hold
    # t2: high=116 → peak=116, trail=110.2; low=108 < 110.2 → TS at 110.2
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 115, 110, 113),  # t1: buy at 100; peak=115, trail=109.25; low=110 > 109.25 → hold
        (113, 116, 108, 111),  # t2: peak=116, trail=110.2; low=108 < 110.2 → TS at 110.2
        (108, 109, 107, 108),
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(116 * 0.95)  # 110.2


async def test_trailing_stop_with_activate():
    # trailing_stop_pct=0.05, trailing_activate_pct=0.10 → activates when price >= 110.
    # Buy at t1 open=100.
    # t1: close=105 < 110 → not active, peak=105
    # t2: close=112 >= 110 → active, peak=112, trail=106.4; close=112 > 106.4 → hold
    # t3: close=106 < 106.4 → TS queued; fill at t4 open=105
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 106, 99, 105),   # t1: buy at 100; peak=105 < 110 → not active
        (105, 113, 104, 112),  # t2: peak=112 >= 110 → active; trail=106.4; hold
        (112, 113, 105, 106),  # t3: close=106 < 106.4 → TS queued
        (105, 106, 104, 105),  # t4: fill at open=105
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05, trailing_activate_pct=0.10),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(105.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py::test_trailing_stop_immediate -v
```

Expected: FAILED (trailing logic not implemented)

- [ ] **Step 3: Implement trailing stop in `_update_state` and `_check_exit`**

Replace `_update_state` in `engine.py`:

```python
def _update_state(self, state: _PositionState, bar: pd.Series) -> None:
    """Update peak_price and check trailing stop activation."""
    ep = self._exit_policy
    check_price = float(bar["high"]) if ep.price_check_mode == "ohlc" else float(bar["close"])
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
```

Replace `_check_exit` in `engine.py`:

```python
def _check_exit(self, state: _PositionState, bar: pd.Series) -> str | None:
    """Return exit reason if position should exit this bar, else None."""
    ep = self._exit_policy
    if ep.price_check_mode == "ohlc":
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
```

- [ ] **Step 4: Run all exit policy tests**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py -v
```

Expected: all 10 tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtesting/engine.py backend/tests/test_exit_policy_engine.py
git commit -m "feat: implement trailing stop in BacktestEngine (immediate + activation threshold)"
```

---

## Task 6: TP→Trailing Transition + Policy-Beats-Signal (TDD)

**Files:**
- Modify: `backend/tests/test_exit_policy_engine.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_exit_policy_engine.py`:

```python
async def test_tp_activates_trailing():
    # take_profit_pct=0.15 (tp=115), trailing_stop_pct=0.05.
    # TP price (115) acts as trailing activation; no fixed TP exit.
    # Buy at t1 open=100.
    # t1: close=116 >= 115 → trailing activates; peak=116, trail=110.2; hold (no fixed TP exit)
    # t2: close=111 → peak=116, trail=110.2; close=111 > 110.2 → hold
    # t3: close=109 < 110.2 → TS queued; fill at t4 open=108
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 117, 99, 116),   # t1: buy at 100; close=116 >= 115 → trailing activates
        (116, 118, 110, 111),  # t2: close=111 > 110.2 → hold
        (111, 112, 108, 109),  # t3: close=109 < 110.2 → TS queued
        (108, 109, 107, 108),  # t4: fill at open=108
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_pct=0.15, trailing_stop_pct=0.05),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert len(metrics.trades) == 1
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(108.0)
    assert trade.entry_price == pytest.approx(100.0)


async def test_policy_beats_signal_same_bar():
    # SL and strategy sell both triggered at t2 (close mode). Policy runs first → SL wins.
    # Strategy: buy at n=0, sell at n=2 bars visible.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # t1: buy fills at 100
        (101, 102, 90, 93),    # t2: close=93 < 95 (SL 5%) → SL queued; sell signal also fires
        (92,  92,  92, 92),    # t3: SL fills at open=92
    ])

    class _BuyThenSellAt2(BaseStrategy):
        name = "_test_buy_sell_at2"
        def __init__(self):
            self._bought = False
        async def generate_signals(self, symbols, parameters, ctx):
            sym = symbols[0]
            bars_data = await ctx.get_bars(sym, "1d")
            n = len(bars_data)
            sigs = []
            if n == 0 and not self._bought:
                self._bought = True
                sigs.append(TradeSignal(symbol=sym, direction="buy", reasoning="test"))
            if n == 2:
                sigs.append(TradeSignal(symbol=sym, direction="sell", reasoning="test sell"))
            return sigs

    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_pct=0.05),
    )
    metrics = await engine.run(_BuyThenSellAt2(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert len(metrics.trades) == 1
    assert metrics.trades[0].exit_reason == "stop_loss"
    assert metrics.trades[0].exit_price == pytest.approx(92.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py::test_tp_activates_trailing tests/test_exit_policy_engine.py::test_policy_beats_signal_same_bar -v
```

Expected: `test_tp_activates_trailing` FAILED; `test_policy_beats_signal_same_bar` should already PASS (pending_close_exits removes from positions before strategy signals)

- [ ] **Step 3: Verify `_update_state` already handles TP-as-activation**

The `_update_state` from Task 5 already contains:
```python
if state.take_profit_price is not None:
    if state.peak_price >= state.take_profit_price:
        state.trailing_active = True
```

If `test_tp_activates_trailing` still fails, the issue is that `_check_exit` exits on fixed TP *before* `_update_state` sets `trailing_active`. Fix by moving the trailing activation check to *before* the TP exit check. The current `_check_exit` order is correct (checks `not state.trailing_active` for TP). But `_update_state` must run *before* `_check_exit`.

Verify the engine call order in `run()` is:
```python
self._update_state(state, bar)   # updates peak + trailing_active
reason = self._check_exit(state, bar)  # reads trailing_active
```

This order is already correct from Task 3. The test should pass. If not, re-examine the bar price data to ensure `peak_price` reaches `take_profit_price` in the same bar that `close >= take_profit_price`.

- [ ] **Step 4: Run all exit policy tests**

```bash
cd backend && python -m pytest tests/test_exit_policy_engine.py -v
```

Expected: all 12 tests pass

- [ ] **Step 5: Run full test suite**

```bash
cd backend && python -m pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_exit_policy_engine.py
git commit -m "test: add TP→trailing transition and policy-beats-signal tests"
```

---

## Task 7: DB Model + Alembic Migration

**Files:**
- Modify: `backend/src/core/models.py:159`
- Create: `backend/alembic/versions/<hash>_add_exit_policy_to_backtest.py`

- [ ] **Step 1: Add `exit_policy` column to Backtest model**

In `backend/src/core/models.py`, add one line after `completed_at` (line 159):

```python
# Before (line 158-162):
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest")

# After:
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    exit_policy: Mapped[dict | None] = mapped_column(JSONB)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest")
```

- [ ] **Step 2: Generate Alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add_exit_policy_to_backtest"
```

Expected output: `Generating .../alembic/versions/<hash>_add_exit_policy_to_backtest.py ... done`

- [ ] **Step 3: Inspect generated migration**

Open the generated file and verify it contains:
```python
op.add_column('backtests', sa.Column('exit_policy', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
```

If the migration also includes a `drop_column` for any existing column, that's a problem — investigate before proceeding.

- [ ] **Step 4: Apply migration to both databases**

```bash
cd backend && alembic upgrade head
DATABASE_URL=postgresql+asyncpg://pxt:pxt@localhost:5432/pxt_test alembic upgrade head
```

Expected: `Running upgrade ... -> <hash>, add_exit_policy_to_backtest`

- [ ] **Step 5: Commit**

```bash
git add backend/src/core/models.py backend/alembic/versions/
git commit -m "feat: add exit_policy JSONB column to backtests table"
```

---

## Task 8: API Wiring

**Files:**
- Modify: `backend/src/api/routers/backtests.py`

- [ ] **Step 1: Update `BacktestRequest` and `trigger_backtest`**

In `backend/src/api/routers/backtests.py`:

Add import after existing imports:
```python
from src.backtesting.exit_policy import ExitPolicy
```

Update `BacktestRequest`:
```python
class BacktestRequest(BaseModel):
    strategy_id: str
    start_date: date
    end_date: date
    symbols: list[str]
    initial_capital: float = 100_000.0
    parameters: dict = {}
    exit_policy: ExitPolicy | None = None  # NEW
```

In `trigger_backtest`, update the `Backtest(...)` creation to include `exit_policy`:
```python
bt = Backtest(
    strategy_id=req.strategy_id,
    start_date=req.start_date,
    end_date=req.end_date,
    symbols=req.symbols,
    initial_capital=req.initial_capital,
    parameters=req.parameters,
    exit_policy=req.exit_policy.model_dump() if req.exit_policy else None,  # NEW
    status="running",
)
```

- [ ] **Step 2: Update `_run_backtest` to pass exit_policy to engine**

In `_run_backtest` (around line 198), replace:
```python
engine = BacktestEngine(initial_capital=req.initial_capital)
```
with:
```python
engine = BacktestEngine(
    initial_capital=req.initial_capital,
    exit_policy=req.exit_policy,  # already an ExitPolicy instance, pass directly
)
```

- [ ] **Step 3: Update `_backtest_summary` to return exit_policy**

Add `exit_policy` to the dict in `_backtest_summary`:
```python
def _backtest_summary(bt: Backtest) -> dict:
    return {
        ...existing fields...,
        "exit_policy": bt.exit_policy,  # NEW — add after "completed_at"
    }
```

- [ ] **Step 4: Smoke test the API**

```bash
cd backend && python -m pytest tests/test_api.py -v
```

Expected: existing API tests still pass (exit_policy is optional, backward-compatible)

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/routers/backtests.py
git commit -m "feat: wire exit_policy through BacktestRequest API and _run_backtest"
```

---

## Task 9: Frontend Types + API + Form

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/backtests.ts`
- Modify: backtest creation form component (find with `grep -r "triggerBacktest\|BacktestRequest\|initial_capital" frontend/src --include="*.tsx" -l`)

- [ ] **Step 1: Add ExitPolicy type and update Backtest in `types/index.ts`**

Add after the `Signal` interface (around line 28):

```typescript
export interface ExitPolicy {
  stop_loss_pct?: number | null
  stop_loss_abs?: number | null
  take_profit_pct?: number | null
  take_profit_abs?: number | null
  trailing_stop_pct?: number | null
  trailing_activate_pct?: number | null
  price_check_mode?: 'close' | 'ohlc'
}
```

Update `Backtest` interface to add `exit_policy`:
```typescript
export interface Backtest {
  ...existing fields...
  exit_policy?: ExitPolicy | null  // add after completed_at
}
```

- [ ] **Step 2: Update `triggerBacktest` in `api/backtests.ts`**

```typescript
export const triggerBacktest = (data: {
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  parameters: Record<string, unknown>
  exit_policy?: ExitPolicy | null  // NEW
}) => client.post<{ id: number; status: string }>('/backtests', data).then(r => r.data)
```

Add `import type { ..., ExitPolicy } from '../types'` to the existing import line.

- [ ] **Step 3: Find the backtest creation form component**

```bash
grep -r "triggerBacktest\|initial_capital" /home/imxichen/projects/pxt/frontend/src --include="*.tsx" -l
```

Open the found file and locate the form submit handler.

- [ ] **Step 4: Add ExitPolicy state to the form component**

Add state for exit policy fields in the form component. Example (adapt to the actual component's pattern):

```typescript
const [exitPolicy, setExitPolicy] = useState<{
  stop_loss_pct: string
  take_profit_pct: string
  trailing_stop_pct: string
  trailing_activate_pct: string
  price_check_mode: 'close' | 'ohlc'
}>({
  stop_loss_pct: '',
  take_profit_pct: '',
  trailing_stop_pct: '',
  trailing_activate_pct: '',
  price_check_mode: 'close',
})
```

In the submit handler, build `exit_policy` from state:
```typescript
const ep: ExitPolicy = {
  stop_loss_pct: exitPolicy.stop_loss_pct ? parseFloat(exitPolicy.stop_loss_pct) / 100 : null,
  take_profit_pct: exitPolicy.take_profit_pct ? parseFloat(exitPolicy.take_profit_pct) / 100 : null,
  trailing_stop_pct: exitPolicy.trailing_stop_pct ? parseFloat(exitPolicy.trailing_stop_pct) / 100 : null,
  trailing_activate_pct: exitPolicy.trailing_activate_pct ? parseFloat(exitPolicy.trailing_activate_pct) / 100 : null,
  price_check_mode: exitPolicy.price_check_mode,
}
const hasExitPolicy = ep.stop_loss_pct || ep.take_profit_pct || ep.trailing_stop_pct
await triggerBacktest({
  ...existingFields,
  exit_policy: hasExitPolicy ? ep : null,
})
```

- [ ] **Step 5: Add Exit Rules section to the form JSX**

Add a collapsible section in the form JSX (adapt to existing UI component style):

```tsx
<details>
  <summary>Exit Rules (optional)</summary>
  <div>
    <label>
      Stop Loss %
      <input
        type="number"
        placeholder="e.g. 5 for 5%"
        value={exitPolicy.stop_loss_pct}
        onChange={e => setExitPolicy(p => ({ ...p, stop_loss_pct: e.target.value }))}
      />
    </label>
    <label>
      Take Profit %
      <input
        type="number"
        placeholder="e.g. 15 for 15%"
        value={exitPolicy.take_profit_pct}
        onChange={e => setExitPolicy(p => ({ ...p, take_profit_pct: e.target.value }))}
      />
    </label>
    <label>
      Trailing Stop %
      <input
        type="number"
        placeholder="e.g. 5 for 5%"
        value={exitPolicy.trailing_stop_pct}
        onChange={e => setExitPolicy(p => ({ ...p, trailing_stop_pct: e.target.value }))}
      />
    </label>
    <label>
      Trailing Activate % (optional)
      <input
        type="number"
        placeholder="e.g. 10 to activate after 10% gain"
        value={exitPolicy.trailing_activate_pct}
        onChange={e => setExitPolicy(p => ({ ...p, trailing_activate_pct: e.target.value }))}
      />
    </label>
    <label>
      Price Check Mode
      <select
        value={exitPolicy.price_check_mode}
        onChange={e => setExitPolicy(p => ({ ...p, price_check_mode: e.target.value as 'close' | 'ohlc' }))}
      >
        <option value="close">Close (fill at next open)</option>
        <option value="ohlc">OHLC (intrabar fill at trigger price)</option>
      </select>
    </label>
  </div>
</details>
```

- [ ] **Step 6: Display exit_reason in trades table**

Find the component that renders `BacktestTrade` rows. The `exit_reason` field already exists in the `BacktestTrade` type and is returned by the API. Verify it's being displayed; add a column if it isn't:

```bash
grep -r "exit_reason\|BacktestTrade" /home/imxichen/projects/pxt/frontend/src --include="*.tsx" -l
```

If the column is missing, add:
```tsx
<td>{trade.exit_reason ?? '—'}</td>
```

with a corresponding `<th>Exit Reason</th>` in the header.

- [ ] **Step 7: Run TypeScript type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no type errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/backtests.ts frontend/src/
git commit -m "feat: add ExitPolicy UI — form fields, types, and exit_reason display"
```
