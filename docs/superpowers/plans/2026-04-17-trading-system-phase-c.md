# PXT Trading System — Phase C: Strategy Layer + Scheduler

> **For agentic workers:** Complete Phase B before starting this phase. REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement the strategy base classes, indicators wrapper, live data context, strategy registry, an example strategy, and the APScheduler runner.

**Tech Stack:** pandas-ta, APScheduler 4.x, SQLAlchemy async

---

## File Map

| File | Purpose |
|---|---|
| `backend/src/strategies/base.py` | `TradeSignal`, `DataContext` ABC, `BaseStrategy` ABC |
| `backend/src/strategies/indicators.py` | `Indicators` wrapping pandas-ta |
| `backend/src/strategies/live_context.py` | `LiveDataContext` reads from DB |
| `backend/src/strategies/registry.py` | Auto-discovers strategies in `library/` |
| `backend/src/strategies/library/ma_crossover.py` | Moving average crossover example |
| `backend/src/scheduler/runner.py` | `StrategyScheduler` with APScheduler |
| `backend/tests/test_indicators.py` | Indicator unit tests |
| `backend/tests/test_strategy_registry.py` | Registry tests |
| `backend/tests/test_ma_crossover.py` | Strategy integration test |

---

## Task 8: Strategy Base + Indicators

**Files:**
- Create: `backend/src/strategies/base.py`
- Create: `backend/src/strategies/indicators.py`
- Create: `backend/tests/test_indicators.py`

- [ ] **Step 1: Write `backend/src/strategies/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
import pandas as pd


@dataclass
class TradeSignal:
    symbol: str
    direction: Literal["buy", "sell", "hold"]
    order_type: Literal["market", "limit", "stop"]
    quantity: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    confidence: float = 1.0          # 0.0–1.0
    reasoning: str = ""
    option_symbol: str | None = None  # set for options trades


class DataContext(ABC):
    """Interface for retrieving market data. Injected into strategies at runtime."""

    @abstractmethod
    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """Return DataFrame with columns [open, high, low, close, volume], DatetimeIndex."""

    @abstractmethod
    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        """Return current option chain snapshot."""

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> dict:
        """Return latest quote dict."""


class BaseStrategy(ABC):
    """
    All strategies inherit from this. Strategy code is identical for live and backtest;
    only the injected DataContext differs.
    """

    id: str                          # must match strategies.id in DB
    name: str
    description: str = ""
    default_symbols: list[str] = []
    default_timeframes: list[str] = ["1d"]
    default_frequency: str = "0 16 * * 1-5"   # cron: weekdays at 4pm CT
    default_parameters: dict = {}

    @abstractmethod
    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
    ) -> list[TradeSignal]:
        """Core strategy logic. Must not access any data beyond what ctx provides."""
```

- [ ] **Step 2: Write `backend/src/strategies/indicators.py`**

```python
import pandas as pd
import pandas_ta as ta


class Indicators:
    """Thin wrapper around pandas-ta. All methods accept a DataFrame with a 'close' column."""

    @staticmethod
    def sma(df: pd.DataFrame, period: int) -> pd.Series:
        return ta.sma(df["close"], length=period)

    @staticmethod
    def ema(df: pd.DataFrame, period: int) -> pd.Series:
        return ta.ema(df["close"], length=period)

    @staticmethod
    def macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        return result  # columns: MACD_f_s_sig, MACDh_f_s_sig, MACDs_f_s_sig

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        return ta.rsi(df["close"], length=period)

    @staticmethod
    def bbands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        return ta.bbands(df["close"], length=period, std=std)
        # columns: BBL_p_s, BBM_p_s, BBU_p_s, BBB_p_s, BBP_p_s

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        return ta.atr(df["high"], df["low"], df["close"], length=period)

    @staticmethod
    def stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
        return ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        return ta.adx(df["high"], df["low"], df["close"], length=period)
```

- [ ] **Step 3: Write failing test `backend/tests/test_indicators.py`**

```python
import pytest
import pandas as pd
import numpy as np
from src.strategies.indicators import Indicators


@pytest.fixture
def sample_df():
    n = 100
    rng = np.random.default_rng(42)
    prices = 100 + rng.standard_normal(n).cumsum()
    return pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": rng.integers(1000, 10000, n),
    })


def test_sma_length(sample_df):
    result = Indicators.sma(sample_df, 10)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_df)
    assert result.iloc[:9].isna().all()   # first 9 are NaN
    assert not pd.isna(result.iloc[9])


def test_ema_length(sample_df):
    result = Indicators.ema(sample_df, 20)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_df)


def test_macd_columns(sample_df):
    result = Indicators.macd(sample_df)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] == 3


def test_rsi_range(sample_df):
    result = Indicators.rsi(sample_df, 14)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_bbands_columns(sample_df):
    result = Indicators.bbands(sample_df, 20)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] == 5
```

- [ ] **Step 4: Run tests**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_indicators.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/strategies/base.py backend/src/strategies/indicators.py backend/tests/test_indicators.py
git commit -m "feat: strategy base classes and indicators wrapper"
```

---

## Task 9: Live Data Context + Strategy Registry

**Files:**
- Create: `backend/src/strategies/live_context.py`
- Create: `backend/src/strategies/registry.py`
- Create: `backend/tests/test_strategy_registry.py`

- [ ] **Step 1: Write `backend/src/strategies/live_context.py`**

```python
from datetime import date
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.core.models import Instrument
from src.data import repository
from src.strategies.base import DataContext


class LiveDataContext(DataContext):
    """Reads market data from the local PostgreSQL database."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_instrument_id(self, symbol: str) -> int | None:
        result = await self._session.execute(
            select(Instrument.id).where(Instrument.symbol == symbol)
        )
        return result.scalar_one_or_none()

    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        instrument_id = await self._get_instrument_id(symbol)
        if instrument_id is None:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return await repository.get_bars(self._session, instrument_id, timeframe, limit)

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        # Option chain is always fetched live from Schwab, not stored for real-time use
        from src.data.providers.schwab import SchwabProvider
        provider = SchwabProvider()
        return await provider.get_option_chain(underlying, expiry)

    async def get_latest_quote(self, symbol: str) -> dict:
        from src.data.providers.schwab import SchwabProvider
        provider = SchwabProvider()
        return await provider.get_latest_quote(symbol)
```

- [ ] **Step 2: Write `backend/src/strategies/registry.py`**

```python
import importlib
import inspect
import pkgutil
from src.strategies.base import BaseStrategy

REGISTRY: dict[str, type[BaseStrategy]] = {}


def discover_strategies() -> None:
    """Auto-discover all BaseStrategy subclasses in src/strategies/library/."""
    import src.strategies.library as library_pkg
    for _, module_name, _ in pkgutil.iter_modules(library_pkg.__path__):
        module = importlib.import_module(f"src.strategies.library.{module_name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseStrategy) and obj is not BaseStrategy and hasattr(obj, "id"):
                REGISTRY[obj.id] = obj


def get_strategy(strategy_id: str) -> BaseStrategy:
    if strategy_id not in REGISTRY:
        raise KeyError(f"Strategy '{strategy_id}' not found. Available: {list(REGISTRY)}")
    return REGISTRY[strategy_id]()
```

- [ ] **Step 3: Write `backend/tests/test_strategy_registry.py`**

```python
from src.strategies.registry import discover_strategies, REGISTRY, get_strategy


def test_discover_finds_ma_crossover():
    REGISTRY.clear()
    discover_strategies()
    assert "ma_crossover" in REGISTRY


def test_get_strategy_returns_instance():
    discover_strategies()
    strategy = get_strategy("ma_crossover")
    assert hasattr(strategy, "generate_signals")


def test_get_strategy_unknown_raises():
    import pytest
    discover_strategies()
    with pytest.raises(KeyError):
        get_strategy("nonexistent_strategy_xyz")
```

- [ ] **Step 4: Run tests (will fail until Task 10 creates ma_crossover)**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_strategy_registry.py -v
```

Expected: FAIL — "ma_crossover not in REGISTRY" (correct; implement in Task 10).

- [ ] **Step 5: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/strategies/live_context.py backend/src/strategies/registry.py backend/tests/test_strategy_registry.py
git commit -m "feat: LiveDataContext and strategy registry"
```

---

## Task 10: MA Crossover Example Strategy

**Files:**
- Create: `backend/src/strategies/library/ma_crossover.py`
- Create: `backend/tests/test_ma_crossover.py`

- [ ] **Step 1: Write `backend/src/strategies/library/ma_crossover.py`**

```python
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
```

- [ ] **Step 2: Write `backend/tests/test_ma_crossover.py`**

```python
import pytest
import pandas as pd
import numpy as np
from datetime import date
from src.strategies.library.ma_crossover import MovingAverageCrossover
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


def make_crossover_df(direction: str) -> pd.DataFrame:
    """Build a price series that produces a crossover on the last bar."""
    n = 50
    if direction == "golden":
        # Price rises sharply on last bar to trigger golden cross
        prices = [100.0] * (n - 1) + [130.0]
    else:
        # Price drops sharply on last bar to trigger death cross
        prices = [130.0] * (n - 1) + [80.0]
    return pd.DataFrame({
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1000] * n,
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))


@pytest.fixture
def strategy():
    return MovingAverageCrossover()


async def test_golden_cross_generates_buy(strategy):
    ctx = MockDataContext(make_crossover_df("golden"))
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].symbol == "SPY"


async def test_death_cross_generates_sell(strategy):
    ctx = MockDataContext(make_crossover_df("death"))
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert len(signals) == 1
    assert signals[0].direction == "sell"


async def test_no_crossover_no_signal(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 50, "high": [101.0] * 50,
        "low": [99.0] * 50, "close": [100.0] * 50, "volume": [1000] * 50,
    }, index=pd.date_range("2023-01-01", periods=50, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert signals == []


async def test_insufficient_data_no_signal(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 5, "high": [101.0] * 5,
        "low": [99.0] * 5, "close": [100.0] * 5, "volume": [1000] * 5,
    }, index=pd.date_range("2023-01-01", periods=5, freq="B"))
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {"fast": 5, "slow": 20}, ctx)
    assert signals == []
```

- [ ] **Step 3: Run all strategy tests**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_ma_crossover.py tests/test_strategy_registry.py tests/test_indicators.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/strategies/library/ma_crossover.py backend/tests/test_ma_crossover.py
git commit -m "feat: MovingAverageCrossover example strategy"
```

---

## Task 11: Scheduler Runner

**Files:**
- Create: `backend/src/scheduler/runner.py`

- [ ] **Step 1: Write `backend/src/scheduler/runner.py`**

```python
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Strategy, SystemEvent
from src.strategies.base import DataContext
from src.strategies.live_context import LiveDataContext
from src.strategies.registry import REGISTRY, discover_strategies
from src.data.collector import DataCollector
from src.signals.processor import SignalProcessor

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.timezone)


class StrategyScheduler:
    def __init__(self):
        self._scheduler = AsyncScheduler()
        self._collector = DataCollector()
        self._signal_processor = SignalProcessor()

    async def start(self) -> None:
        discover_strategies()
        await self._register_all_jobs()
        await self._scheduler.start_in_background()
        logger.info("Scheduler started.")

    async def stop(self) -> None:
        await self._scheduler.stop()

    async def _register_all_jobs(self) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active == True)
            )
            strategies = result.scalars().all()

        # Data sync job: runs every 5 minutes during market hours (CT)
        await self._scheduler.add_schedule(
            self._run_data_sync,
            CronTrigger(minute="*/5", hour="8-15", day_of_week="mon-fri", timezone=TZ),
            id="data_sync",
        )

        # Signal processor: runs every 60 seconds
        await self._scheduler.add_schedule(
            self._run_signal_processor,
            CronTrigger(minute="*", timezone=TZ),
            id="signal_processor",
        )

        for config in strategies:
            await self._register_strategy_job(config)

    async def _register_strategy_job(self, config: Strategy) -> None:
        if config.id not in REGISTRY:
            logger.warning("Strategy '%s' in DB but not in registry — skipping.", config.id)
            return
        await self._scheduler.add_schedule(
            self._run_strategy,
            CronTrigger.from_crontab(config.run_frequency, timezone=TZ),
            kwargs={"strategy_id": config.id},
            id=f"strategy_{config.id}",
            replace_existing=True,
        )
        logger.info("Registered strategy job: %s @ %s", config.id, config.run_frequency)

    async def reload_strategy(self, strategy_id: str) -> None:
        """Hot-reload a single strategy job after config change."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            config = result.scalar_one_or_none()
        if config and config.is_active:
            await self._register_strategy_job(config)
        else:
            await self._scheduler.remove_schedule(f"strategy_{strategy_id}")

    async def _run_data_sync(self) -> None:
        try:
            await self._collector.run_full_sync()
        except Exception as e:
            await self._log_event("data_sync", "error", str(e))

    async def _run_signal_processor(self) -> None:
        try:
            await self._signal_processor.process_pending()
        except Exception as e:
            await self._log_event("signal_processor", "error", str(e))

    async def _run_strategy(self, strategy_id: str) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            config = result.scalar_one_or_none()
            if not config:
                return

            strategy = REGISTRY[strategy_id]()
            ctx = LiveDataContext(session)
            try:
                async with asyncio.timeout(settings.strategy_run_timeout):
                    signals = await strategy.generate_signals(
                        config.symbols, config.parameters, ctx
                    )
                await self._save_signals(session, config, signals)
                await self._log_event(
                    "strategy_run", "info",
                    f"Strategy {strategy_id} generated {len(signals)} signal(s).",
                    session=session,
                )
            except TimeoutError:
                await self._log_event(
                    "strategy_run", "error",
                    f"Strategy {strategy_id} timed out after {settings.strategy_run_timeout}s.",
                    session=session,
                )
            except Exception as e:
                await self._log_event(
                    "strategy_run", "error",
                    f"Strategy {strategy_id} failed: {e}",
                    session=session,
                )

    async def _save_signals(self, session, config: Strategy, signals) -> None:
        from src.core.models import TradeSignalRecord, Instrument
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy import select as sa_select
        now = datetime.now(timezone.utc)
        for sig in signals:
            inst_result = await session.execute(
                sa_select(Instrument.id).where(Instrument.symbol == sig.symbol)
            )
            stock_id = inst_result.scalar_one_or_none()
            if stock_id is None:
                continue
            stmt = pg_insert(TradeSignalRecord).values(
                strategy_id=config.id,
                stock_id=stock_id,
                signal_time=now,
                direction=sig.direction,
                order_type=sig.order_type,
                quantity=sig.quantity,
                limit_price=sig.limit_price,
                stop_price=sig.stop_price,
                confidence=sig.confidence,
                reasoning=sig.reasoning,
                status="pending",
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()

    async def _log_event(
        self, event_type: str, level: str, message: str, session=None
    ) -> None:
        close_after = session is None
        if session is None:
            session = async_session_factory()
            await session.__aenter__()
        try:
            session.add(SystemEvent(event_type=event_type, level=level, message=message))
            await session.commit()
        finally:
            if close_after:
                await session.__aexit__(None, None, None)
        if level == "error":
            logger.error("[%s] %s", event_type, message)
        else:
            logger.info("[%s] %s", event_type, message)
```

- [ ] **Step 2: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/scheduler/runner.py
git commit -m "feat: APScheduler strategy runner with hot-reload and timeout"
```

---

**Phase C complete.** Continue with Phase D: `2026-04-17-trading-system-phase-d.md`
