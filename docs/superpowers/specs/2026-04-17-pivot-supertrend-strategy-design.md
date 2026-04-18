# Pivot Point SuperTrend Strategy — Design Spec

**Date:** 2026-04-17  
**Status:** Approved

## Overview

Port the TradingView "Pivot Point SuperTrend" indicator (`strategy_input_raw/pivot_tv`) into the pxt strategy system as a fully registered, backtest-compatible strategy that generates buy/sell signals on SuperTrend trend reversals.

---

## Source Algorithm (TradingView)

Key inputs:
- `pivot_period` (default 2) — bars on each side to confirm a pivot high/low
- `atr_factor` (default 3.0) — multiplier for ATR bands
- `atr_period` (default 10) — ATR lookback

Signal logic:
- Buy when `Trend` flips from -1 → 1 (price crosses above trailing stop)
- Sell when `Trend` flips from 1 → -1 (price crosses below trailing stop)

---

## File Structure

**New file:** `backend/src/strategies/library/pivot_supertrend.py`

Auto-discovered by `registry.py` via `pkgutil.iter_modules` — no manual registration needed.

**New migration:** `backend/alembic/versions/<hash>_seed_pivot_supertrend.py`

Inserts one row into the `strategies` table so the scheduler and API can manage it.

---

## Class Definition

```python
class PivotSupertrendStrategy(BaseStrategy):
    id = "pivot_supertrend"
    name = "Pivot Point SuperTrend"
    description = "SuperTrend built on pivot-point center line. Buys on bullish trend flip, sells on bearish trend flip."
    default_symbols = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "pivot_period": 2,
        "atr_factor": 3.0,
        "atr_period": 10,
    }
```

---

## Core Algorithm (No Look-Ahead)

`generate_signals()` fetches `limit = pivot_period * 2 + atr_period + 20` bars per symbol.

### Step 1 — Pivot High/Low Detection (Delay-Corrected)

At bar `j`, check whether `high[j - prd]` is the maximum of `high[j-2*prd : j+1]` (inclusive of `j`, exclusive upper bound in Python slice). If yes, `ph[j] = high[j - prd]`, otherwise `nan`. Same logic for `pl` using `low`.

This mirrors TradingView's `pivothigh(prd, prd)` exactly: the pivot at bar `i` is confirmed `prd` bars later at bar `j = i + prd`, using only data available at `j`.

### Step 2 — Center Line

Iterates forward over all bars. When `ph[j]` or `pl[j]` is not `nan`:
- First pivot: `center = lastpp`
- Subsequent: `center = (center * 2 + lastpp) / 3`

Carries forward (`ffill`) between pivots.

### Step 3 — ATR Bands

```
Up[j]  = center[j] - atr_factor × ATR(atr_period)[j]
Dn[j]  = center[j] + atr_factor × ATR(atr_period)[j]
```

ATR uses `Indicators.atr(df, atr_period)`.

### Step 4 — Trailing Stop Lines

```
TUp[j]   = max(Up[j], TUp[j-1])   if close[j-1] > TUp[j-1]   else Up[j]
TDown[j] = min(Dn[j], TDown[j-1]) if close[j-1] < TDown[j-1] else Dn[j]
```

Initialized from first valid bar.

### Step 5 — Trend

```
Trend[j] = 1   if close[j] > TDown[j-1]
         = -1  if close[j] < TUp[j-1]
         = Trend[j-1]  otherwise
```

### Step 6 — Signal Generation (Last Bar Only)

```
Trend[-1] == 1  and Trend[-2] == -1  →  buy  (bullish flip)
Trend[-1] == -1 and Trend[-2] == 1   →  sell (bearish flip)
```

Signal carries `confidence=0.70` and a reasoning string with the trailing stop level.

---

## Minimum Bar Requirement

`limit = pivot_period * 2 + atr_period + 20`

With defaults: `2*2 + 10 + 20 = 34 bars`. Guard: skip symbol if `len(df) < limit`.

---

## DB Seeding (Migration)

New Alembic migration inserts:

```python
op.execute("""
    INSERT INTO strategies (id, name, description, is_active, symbols, timeframes,
                            run_frequency, parameters, max_symbols, updated_at)
    VALUES (
        'pivot_supertrend',
        'Pivot Point SuperTrend',
        'SuperTrend built on pivot-point center line. Buys on bullish trend flip, sells on bearish trend flip.',
        false,
        ARRAY['SPY','QQQ','AAPL','TSLA','NVDA'],
        ARRAY['1d'],
        '0 16 * * 1-5',
        '{"pivot_period": 2, "atr_factor": 3.0, "atr_period": 10}'::jsonb,
        50,
        now()
    )
    ON CONFLICT (id) DO NOTHING;
""")
```

`is_active = false` by default — user enables via UI.

---

## No Frontend Changes Required

The strategy appears automatically in the Strategies page once the DB row exists. Parameters (`pivot_period`, `atr_factor`, `atr_period`) are editable via the existing JSON parameters editor.

---

## Testing

- Unit test pivot detection with a synthetic price series where pivots are known
- Backtest over SPY 2020–2024 to verify no look-ahead (equity curve should not show perfect foresight)
- Confirm buy/sell signals alternate correctly (no double-buy without intervening sell)
