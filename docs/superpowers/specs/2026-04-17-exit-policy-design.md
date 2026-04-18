# Exit Policy Design for Backtest Engine

**Date:** 2026-04-17
**Status:** Approved

## Overview

Add configurable per-backtest exit rules to the `BacktestEngine`. Currently the engine only exits positions via explicit strategy sell signals or forced liquidation at backtest end. This spec adds stop-loss, take-profit, and trailing stop support, all configurable per backtest and persisted in the DB.

---

## Section 1: ExitPolicy Data Model

New file: `backend/src/backtesting/exit_policy.py`

```python
from pydantic import BaseModel, model_validator
from typing import Literal

class ExitPolicy(BaseModel):
    # Stop loss (mutually exclusive)
    stop_loss_pct: float | None = None     # e.g. 0.05 = exit on 5% loss
    stop_loss_abs: float | None = None     # e.g. 500.0 = exit on $500 loss

    # Take profit (mutually exclusive)
    take_profit_pct: float | None = None   # e.g. 0.15 = exit on 15% gain
    take_profit_abs: float | None = None   # e.g. 2000.0 = exit on $2000 gain

    # Trailing stop
    trailing_stop_pct: float | None = None      # e.g. 0.05 = exit when price falls 5% from peak
    trailing_activate_pct: float | None = None  # None = active immediately from entry
                                                 # 0.05 = activate after 5% gain
                                                 # If take_profit also configured, TP price acts as activation threshold

    # Price check granularity
    price_check_mode: Literal["close", "ohlc"] = "close"

    @model_validator(mode="after")
    def validate_fields(self):
        if self.stop_loss_pct and self.stop_loss_abs:
            raise ValueError("Use either stop_loss_pct or stop_loss_abs, not both")
        if self.take_profit_pct and self.take_profit_abs:
            raise ValueError("Use either take_profit_pct or take_profit_abs, not both")
        if self.trailing_activate_pct and not self.trailing_stop_pct:
            raise ValueError("trailing_activate_pct requires trailing_stop_pct")
        return self
```

All fields are optional. An `ExitPolicy` with all fields `None` is valid and has no effect.

---

## Section 2: Engine Internal Position State

Add a private `_PositionState` dataclass inside `engine.py` (not exported):

```python
@dataclass
class _PositionState:
    trade: TradeRecord
    peak_price: float          # highest price since entry (for trailing stop)
    trailing_active: bool = False  # whether trailing stop is currently active
```

The `positions` dict type changes from `dict[str, TradeRecord]` to `dict[str, _PositionState]`.

`BacktestEngine.__init__` gains a new parameter:
```python
def __init__(
    self,
    initial_capital: float = 100_000.0,
    exit_policy: ExitPolicy | None = None,
):
```

---

## Section 3: Per-Bar Exit Check Logic

### Loop Order (per bar `i`)

1. Update `peak_price` for all open positions (close mode: use close price; ohlc mode: use high)
2. Check trailing stop activation thresholds
3. Check exit conditions → produce `policy_exits` list
4. Execute `policy_exits` (remove from positions, settle cash)
5. Call `strategy.generate_signals()` on remaining open positions (existing logic, unchanged)

Exit policy runs **before** strategy signals. If both trigger on the same bar, exit policy wins (position already closed when signal is processed).

### Exit Condition Priority (when multiple conditions trigger on the same bar)

1. Stop loss (highest priority — capital protection)
2. Trailing stop (when active)
3. Fixed take profit (when trailing not yet active)

### Fill Price and Time

| Mode | Stop Loss | Take Profit / Trailing | Fill Time |
|------|-----------|------------------------|-----------|
| `close` | close price triggers, next bar open fills | same | `next_bar_open` |
| `ohlc` | `low <= stop_price` → fill at `stop_price` | `high >= tp_price` → fill at `tp_price` | `current_time` (intrabar) |

### Fixed Take Profit → Trailing Stop Transition

When both `take_profit_*` and `trailing_stop_pct` are configured:
- Fixed take profit price acts as the trailing activation threshold (overrides `trailing_activate_pct`)
- Once `peak_price >= take_profit_price`, `trailing_active = True`
- After activation, fixed take profit is no longer checked; trailing stop takes over
- This locks in profit while allowing the position to run further

### exit_reason Values

`"signal"` | `"stop_loss"` | `"take_profit"` | `"trailing_stop"` | `"end_of_backtest"`

---

## Section 4: API Layer and Database

### BacktestRequest

```python
class BacktestRequest(BaseModel):
    strategy_id: str
    start_date: date
    end_date: date
    symbols: list[str]
    initial_capital: float = 100_000.0
    parameters: dict = {}
    exit_policy: ExitPolicy | None = None   # NEW
```

### Database Changes

- `Backtest` table: add `exit_policy JSONB NULL` column via Alembic migration
- `BacktestTrade` table: `exit_reason` column already exists (text); new enum values are backward-compatible

### Data Flow

```
POST /backtests/
  → BacktestRequest.exit_policy saved to Backtest.exit_policy in DB
  → _run_backtest reads exit_policy, passes to BacktestEngine(exit_policy=...)
  → Engine runs, TradeRecord.exit_reason set to specific reason
  → BacktestTrade rows written with exit_reason

GET /backtests/{id}
  → Response includes exit_policy (for UI to display the config used)
```

### Frontend (React)

- Backtest creation form: add collapsible "Exit Rules" section with inputs for all ExitPolicy fields plus price_check_mode selector
- TypeScript type `BacktestRequest` gains `exit_policy` field
- Backtest detail page: trade list gains `exit_reason` column

---

## Section 5: Test Strategy

All tests use synthetic OHLCV data (no DB or YFinance dependency). Follows existing `conftest` savepoint pattern.

### `tests/backtesting/test_exit_policy.py` — Engine behavior

| Test | Scenario |
|------|----------|
| `test_stop_loss_pct_close` | Close price breaches stop → fills at next bar open |
| `test_stop_loss_ohlc` | Intrabar low hits stop price → fills at stop price |
| `test_take_profit_pct` | Close price exceeds TP level → exit |
| `test_trailing_stop_immediate` | No activation threshold, trails from entry |
| `test_trailing_stop_with_activate` | Trailing activates only after price gains X% |
| `test_tp_activates_trailing` | Fixed TP price reached → switches to trailing stop |
| `test_policy_beats_signal_same_bar` | SL and strategy sell on same bar → SL exit wins |
| `test_no_policy_unchanged` | `exit_policy=None` → behavior identical to current engine |

### `tests/backtesting/test_exit_policy_model.py` — Model validation

- `stop_loss_pct` + `stop_loss_abs` both set → `ValueError`
- `trailing_activate_pct` without `trailing_stop_pct` → `ValueError`
- All fields `None` → valid
