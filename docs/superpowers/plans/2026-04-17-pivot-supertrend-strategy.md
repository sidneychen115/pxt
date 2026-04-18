# Pivot Point SuperTrend Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the TradingView "Pivot Point SuperTrend" indicator into the pxt strategy system as a registerable, backtest-compatible strategy that emits buy/sell signals on SuperTrend trend reversals.

**Architecture:** A single new file `pivot_supertrend.py` in the strategy library is auto-discovered by the registry. A module-level `_detect_pivots` helper implements pivot detection with a one-period delay to eliminate look-ahead bias. A new Alembic migration seeds the strategy's DB row so the scheduler and UI can manage it.

**Tech Stack:** Python 3.12, pandas, numpy, pandas-ta (via `Indicators.atr`), SQLAlchemy/Alembic, pytest-asyncio.

---

## File Map

| Action | Path |
|---|---|
| Create | `backend/src/strategies/library/pivot_supertrend.py` |
| Create | `backend/tests/test_pivot_supertrend.py` |
| Create | `backend/alembic/versions/<hash>_seed_pivot_supertrend.py` |

---

## Task 1: Write failing tests for `_detect_pivots`

**Files:**
- Create: `backend/tests/test_pivot_supertrend.py`

- [ ] **Step 1: Create the test file**

```python
# backend/tests/test_pivot_supertrend.py
import numpy as np
import pandas as pd
import pytest
from src.strategies.library.pivot_supertrend import _detect_pivots, PivotSupertrendStrategy
from src.strategies.base import DataContext


class MockDataContext(DataContext):
    def __init__(self, df: pd.DataFrame):
        self._df = df

    async def get_bars(self, symbol, timeframe, limit=200) -> pd.DataFrame:
        return self._df.tail(limit).copy()

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_latest_quote(self, symbol) -> dict:
        return {}


# ── Pivot detection unit tests ────────────────────────────────────────────────

def test_pivot_high_confirmed_at_correct_bar():
    # high[2]=153 is the peak; with prd=2 it is confirmed at bar j=4
    high = pd.Series([100.0, 102.0, 153.0, 102.0, 100.0, 100.0, 100.0])
    low  = pd.Series([ 90.0,  91.0,  92.0,  91.0,  90.0,  90.0,  90.0])
    ph, _ = _detect_pivots(high, low, prd=2)
    assert pd.isna(ph.iloc[3]), "pivot not yet confirmed at j=3"
    assert ph.iloc[4] == 153.0, "pivot high must be confirmed at j=4"
    assert pd.isna(ph.iloc[5]), "no second pivot expected"
    assert pd.isna(ph.iloc[6]), "no third pivot expected"


def test_pivot_low_confirmed_at_correct_bar():
    high = pd.Series([110.0] * 7)
    low  = pd.Series([100.0, 98.0, 50.0, 98.0, 100.0, 100.0, 100.0])
    _, pl = _detect_pivots(high, low, prd=2)
    assert pd.isna(pl.iloc[3])
    assert pl.iloc[4] == 50.0
    assert pd.isna(pl.iloc[5])


def test_no_pivot_in_monotonic_series():
    # Strictly ascending: no bar is both the local high/low with prd neighbours lower/higher
    high = pd.Series([float(i) for i in range(10)])
    low  = pd.Series([float(i) - 0.5 for i in range(10)])
    ph, pl = _detect_pivots(high, low, prd=2)
    # No pivot highs (every candidate is lower than the bars after it)
    assert ph.dropna().empty
    # No pivot lows (every candidate is higher than the bars after it)
    assert pl.dropna().empty


def test_multiple_pivots_detected():
    # Two separate pivot highs at indices 2 and 6
    high = pd.Series([100.0, 102.0, 150.0, 102.0, 100.0, 102.0, 160.0, 102.0, 100.0, 100.0])
    low  = pd.Series([ 90.0] * 10)
    ph, _ = _detect_pivots(high, low, prd=2)
    assert ph.iloc[4] == 150.0   # pivot at bar 2, confirmed at bar 4
    assert ph.iloc[8] == 160.0   # pivot at bar 6, confirmed at bar 8
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_pivot_supertrend.py::test_pivot_high_confirmed_at_correct_bar tests/test_pivot_supertrend.py::test_pivot_low_confirmed_at_correct_bar tests/test_pivot_supertrend.py::test_no_pivot_in_monotonic_series tests/test_pivot_supertrend.py::test_multiple_pivots_detected -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `pivot_supertrend` does not exist yet.

---

## Task 2: Implement `_detect_pivots` and strategy skeleton; make pivot tests pass

**Files:**
- Create: `backend/src/strategies/library/pivot_supertrend.py`

- [ ] **Step 1: Create the strategy file with the helper and a stub class**

```python
# backend/src/strategies/library/pivot_supertrend.py
import numpy as np
import pandas as pd
from src.strategies.base import BaseStrategy, DataContext, TradeSignal
from src.strategies.indicators import Indicators


def _detect_pivots(
    high: pd.Series, low: pd.Series, prd: int
) -> tuple[pd.Series, pd.Series]:
    """Return (pivot_high, pivot_low) series.

    At bar j, ph[j] = high[j-prd] if that bar is the maximum of the
    [j-2*prd : j+1] window (inclusive), nan otherwise.  The prd-bar delay
    means only data available at j is used — no look-ahead.
    """
    ph = pd.Series(np.nan, index=high.index)
    pl = pd.Series(np.nan, index=low.index)
    for j in range(2 * prd, len(high)):
        window_h = high.iloc[j - 2 * prd : j + 1]
        if high.iloc[j - prd] == window_h.max():
            ph.iloc[j] = high.iloc[j - prd]
        window_l = low.iloc[j - 2 * prd : j + 1]
        if low.iloc[j - prd] == window_l.min():
            pl.iloc[j] = low.iloc[j - prd]
    return ph, pl


class PivotSupertrendStrategy(BaseStrategy):
    id = "pivot_supertrend"
    name = "Pivot Point SuperTrend"
    description = (
        "SuperTrend built on pivot-point center line. "
        "Buys on bullish trend flip, sells on bearish trend flip."
    )
    default_symbols = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "pivot_period": 2,
        "atr_factor": 3.0,
        "atr_period": 10,
    }

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
    ) -> list[TradeSignal]:
        return []  # stub — implemented in Task 4
```

- [ ] **Step 2: Run pivot tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_pivot_supertrend.py::test_pivot_high_confirmed_at_correct_bar tests/test_pivot_supertrend.py::test_pivot_low_confirmed_at_correct_bar tests/test_pivot_supertrend.py::test_no_pivot_in_monotonic_series tests/test_pivot_supertrend.py::test_multiple_pivots_detected -v
```

Expected: 4 PASSED.

- [ ] **Step 3: Commit**

```bash
git add backend/src/strategies/library/pivot_supertrend.py backend/tests/test_pivot_supertrend.py
git commit -m "feat: pivot supertrend strategy skeleton + pivot detection helper"
```

---

## Task 3: Write failing tests for `generate_signals`

**Files:**
- Modify: `backend/tests/test_pivot_supertrend.py`

Append the following tests to the end of `backend/tests/test_pivot_supertrend.py`:

- [ ] **Step 1: Append generate_signals tests**

```python
# ── generate_signals integration tests ───────────────────────────────────────

def make_bullish_flip_df() -> pd.DataFrame:
    """Price series that ends with a bullish SuperTrend flip.

    Phase 1 (bars 0-4): oscillation creates a pivot high at bar 2
    (high=153), confirmed at bar 4.  Center line initialised to ~153.

    Phase 2 (bars 5-39): steady decline 100→50.  No new pivots.
    Center stays at ~153; bands are ~153±6.  TDown ratchets near 159.
    Close stays below TUp (~147) → Trend = -1.

    Phase 3 (bar 40): close=200, crosses above TDown (~159) → Trend flips to 1.
    """
    phase1_close = [100.0, 120.0, 150.0, 120.0, 100.0]
    phase2_close = list(np.linspace(100.0, 50.0, 35))
    phase3_close = [200.0]
    prices = phase1_close + phase2_close + phase3_close  # 41 bars
    n = len(prices)
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.02 for p in prices],
        "low":    [p * 0.98 for p in prices],
        "close":  prices,
        "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


def make_bearish_flip_df() -> pd.DataFrame:
    """Price series that ends with a bearish SuperTrend flip.

    Phase 1 (bars 0-4): oscillation creates a pivot low at bar 2
    (low=49), confirmed at bar 4.  Center line initialised to ~49.

    Phase 2 (bars 5-39): steady rise 100→150.  No new pivots.
    Center stays at ~49; bands are ~49±6.  TUp ratchets near 43.
    Close stays above TDown (~55) → Trend = 1.

    Phase 3 (bar 40): close=30, crosses below TUp (~43) → Trend flips to -1.
    """
    phase1_close = [100.0, 80.0, 50.0, 80.0, 100.0]
    phase2_close = list(np.linspace(100.0, 150.0, 35))
    phase3_close = [30.0]
    prices = phase1_close + phase2_close + phase3_close
    n = len(prices)
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.02 for p in prices],
        "low":    [p * 0.98 for p in prices],
        "close":  prices,
        "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


@pytest.fixture
def strategy():
    return PivotSupertrendStrategy()


async def test_bullish_flip_generates_buy(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].symbol == "SPY"
    assert signals[0].order_type == "market"
    assert 0.0 < signals[0].confidence <= 1.0


async def test_bearish_flip_generates_sell(strategy):
    ctx = MockDataContext(make_bearish_flip_df())
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "sell"
    assert signals[0].symbol == "SPY"


async def test_no_signal_on_flat_price(strategy):
    n = 50
    prices = [100.0] * n
    df = pd.DataFrame({
        "open": prices, "high": [101.0] * n,
        "low":  [99.0]  * n, "close": prices, "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert signals == []


async def test_insufficient_data_no_signal(strategy):
    n = 10  # below limit=34 with defaults
    prices = [100.0] * n
    df = pd.DataFrame({
        "open": prices, "high": [p * 1.01 for p in prices],
        "low":  [p * 0.99 for p in prices], "close": prices, "volume": [1_000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {}, ctx)
    assert signals == []


async def test_none_data_no_crash(strategy):
    class NullCtx(DataContext):
        async def get_bars(self, symbol, timeframe, limit=200):
            return None
        async def get_option_chain(self, underlying, expiry=None):
            return pd.DataFrame()
        async def get_latest_quote(self, symbol):
            return {}

    signals = await strategy.generate_signals(["SPY"], {}, NullCtx())
    assert signals == []


async def test_empty_symbol_skipped(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    signals = await strategy.generate_signals([""], {}, ctx)
    assert signals == []


async def test_custom_parameters_accepted(strategy):
    ctx = MockDataContext(make_bullish_flip_df())
    # Should not crash with non-default parameters
    signals = await strategy.generate_signals(
        ["SPY"], {"pivot_period": 3, "atr_factor": 2.0, "atr_period": 14}, ctx
    )
    assert isinstance(signals, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_pivot_supertrend.py::test_bullish_flip_generates_buy tests/test_pivot_supertrend.py::test_bearish_flip_generates_sell tests/test_pivot_supertrend.py::test_no_signal_on_flat_price tests/test_pivot_supertrend.py::test_insufficient_data_no_signal tests/test_pivot_supertrend.py::test_none_data_no_crash tests/test_pivot_supertrend.py::test_empty_symbol_skipped tests/test_pivot_supertrend.py::test_custom_parameters_accepted -v
```

Expected: `test_bullish_flip_generates_buy` and `test_bearish_flip_generates_sell` FAIL (stub returns `[]`). Others should PASS already (stub returns `[]` which satisfies them).

---

## Task 4: Implement `generate_signals`; run all tests

**Files:**
- Modify: `backend/src/strategies/library/pivot_supertrend.py`

- [ ] **Step 1: Replace the stub `generate_signals` with the full implementation**

Replace everything from `async def generate_signals` to the end of the file with:

```python
    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
    ) -> list[TradeSignal]:
        prd    = int(parameters.get("pivot_period", self.default_parameters["pivot_period"]))
        factor = float(parameters.get("atr_factor",   self.default_parameters["atr_factor"]))
        atr_pd = int(parameters.get("atr_period",   self.default_parameters["atr_period"]))
        limit  = prd * 2 + atr_pd + 20
        signals: list[TradeSignal] = []

        for symbol in symbols:
            if not symbol:
                continue
            df = await ctx.get_bars(symbol, "1d", limit=limit)
            if df is None or len(df) < limit:
                continue

            high  = df["high"].astype(float)
            low   = df["low"].astype(float)
            close = df["close"].astype(float)

            ph, pl = _detect_pivots(high, low, prd)

            # center line: weighted moving average of confirmed pivot points
            center_vals = np.full(len(df), np.nan)
            c = np.nan
            for j in range(len(df)):
                lastpp = (
                    ph.iloc[j] if not pd.isna(ph.iloc[j])
                    else pl.iloc[j] if not pd.isna(pl.iloc[j])
                    else np.nan
                )
                if not pd.isna(lastpp):
                    c = lastpp if pd.isna(c) else (c * 2 + lastpp) / 3
                center_vals[j] = c
            center = pd.Series(center_vals, index=df.index)

            atr = Indicators.atr(df, atr_pd)
            if atr is None or atr.isna().all():
                continue

            up = center - factor * atr
            dn = center + factor * atr

            valid_mask = up.notna() & dn.notna()
            if not valid_mask.any():
                continue
            fi_loc = int(valid_mask.values.argmax())

            tup_vals   = np.full(len(df), np.nan)
            tdown_vals = np.full(len(df), np.nan)
            trend_vals = np.zeros(len(df), dtype=int)

            tup_vals[fi_loc]   = up.iloc[fi_loc]
            tdown_vals[fi_loc] = dn.iloc[fi_loc]
            trend_vals[fi_loc] = 1

            for i in range(fi_loc + 1, len(df)):
                prev_close = close.iloc[i - 1]
                tup_vals[i] = (
                    max(up.iloc[i], tup_vals[i - 1])
                    if prev_close > tup_vals[i - 1]
                    else up.iloc[i]
                )
                tdown_vals[i] = (
                    min(dn.iloc[i], tdown_vals[i - 1])
                    if prev_close < tdown_vals[i - 1]
                    else dn.iloc[i]
                )
                if close.iloc[i] > tdown_vals[i - 1]:
                    trend_vals[i] = 1
                elif close.iloc[i] < tup_vals[i - 1]:
                    trend_vals[i] = -1
                else:
                    trend_vals[i] = trend_vals[i - 1]

            prev_trend = trend_vals[-2]
            curr_trend = trend_vals[-1]

            if curr_trend == 1 and prev_trend == -1:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="buy",
                    order_type="market",
                    confidence=0.70,
                    reasoning=(
                        f"SuperTrend flipped bullish. Trailing stop: {tup_vals[-1]:.2f}"
                    ),
                ))
            elif curr_trend == -1 and prev_trend == 1:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction="sell",
                    order_type="market",
                    confidence=0.70,
                    reasoning=(
                        f"SuperTrend flipped bearish. Trailing stop: {tdown_vals[-1]:.2f}"
                    ),
                ))

        return signals
```

- [ ] **Step 2: Run all tests in the file**

```bash
cd backend && python -m pytest tests/test_pivot_supertrend.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_api.py --ignore=tests/test_repository.py --ignore=tests/test_models.py --ignore=tests/test_yfinance_provider.py --ignore=tests/test_signal_processor.py
```

Expected: all non-DB tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/strategies/library/pivot_supertrend.py backend/tests/test_pivot_supertrend.py
git commit -m "feat: implement PivotSupertrendStrategy with look-ahead-free pivot detection"
```

---

## Task 5: Alembic migration to seed the DB row

**Files:**
- Create: `backend/alembic/versions/<hash>_seed_pivot_supertrend.py`

- [ ] **Step 1: Generate the migration file**

```bash
cd backend && alembic revision -m "seed_pivot_supertrend"
```

Note the generated filename, e.g. `backend/alembic/versions/abc123_seed_pivot_supertrend.py`.

- [ ] **Step 2: Replace the generated file's `upgrade` and `downgrade` with**

```python
def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
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


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'pivot_supertrend';")
```

Keep the auto-generated header (revision IDs, Create Date) — only replace the two functions.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: seed pivot_supertrend strategy row in DB"
```

---

## Self-Review

**Spec coverage:**
- ✅ File `pivot_supertrend.py` created in library (auto-discovered)
- ✅ Class metadata: `id`, `name`, `description`, `default_symbols`, `default_timeframes`, `default_frequency`, `default_parameters`
- ✅ `_detect_pivots`: delay-corrected, no look-ahead
- ✅ Center line: weighted `(c*2 + lastpp) / 3`
- ✅ ATR bands via `Indicators.atr`
- ✅ Trailing stop ratchet for `TUp` and `TDown`
- ✅ Trend logic: 1 / -1 / carry-forward
- ✅ Signals only on last-bar flip; pure signal mode (option A)
- ✅ DB seed migration (`is_active=false` by default)
- ✅ No frontend changes needed

**Placeholder scan:** None found.

**Type consistency:** `_detect_pivots` returns `tuple[pd.Series, pd.Series]` — used consistently in Task 2 and Task 4. `TradeSignal` fields match `base.py` definition throughout.
