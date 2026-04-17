# PXT Trading System — Phase B: Data Layer

> **For agentic workers:** Complete Phase A before starting this phase. REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement data providers (yfinance + Schwab), data repository, and collector orchestration.

**Architecture:** `DataProvider` ABC → concrete providers → `DataRepository` writes to DB → `DataCollector` aggregates strategy requirements and schedules fetching.

**Tech Stack:** yfinance, schwab-py, SQLAlchemy async, pandas

---

## File Map

| File | Purpose |
|---|---|
| `backend/src/data/providers/base.py` | `DataProvider` ABC |
| `backend/src/data/providers/yfinance_provider.py` | Yahoo Finance implementation |
| `backend/src/data/providers/schwab.py` | Schwab implementation via schwab-py |
| `backend/src/data/providers/polygon.py` | Polygon stub |
| `backend/src/data/repository.py` | DB read/write for market data |
| `backend/src/data/collector.py` | Aggregates collection plan, orchestrates fetching |
| `backend/tests/test_yfinance_provider.py` | Provider unit tests |
| `backend/tests/test_repository.py` | Repository tests |

---

## Task 5: Data Provider Interface + YFinance

**Files:**
- Create: `backend/src/data/providers/base.py`
- Create: `backend/src/data/providers/yfinance_provider.py`
- Create: `backend/tests/test_yfinance_provider.py`

- [ ] **Step 1: Write `backend/src/data/providers/base.py`**

```python
from abc import ABC, abstractmethod
from datetime import date, datetime
import pandas as pd


class DataProvider(ABC):
    """
    All providers return DataFrames with these standardised columns:
    - bars: index=DatetimeIndex(UTC), columns=[open, high, low, close, volume, vwap, source]
    - option_chain: columns=[symbol, underlying, expiry, strike, option_type,
                              bid, ask, last, volume, open_interest,
                              iv, delta, gamma, theta, vega]
    - quote: dict with keys [symbol, bid, ask, last, volume, timestamp]
    """

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars. timeframe: '1m','5m','15m','30m','1h','4h','1d','1wk','1mo'"""

    @abstractmethod
    async def get_option_chain(
        self,
        underlying: str,
        expiry: date | None = None,
    ) -> pd.DataFrame:
        """Return current option chain snapshot."""

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> dict:
        """Return latest bid/ask/last quote."""


# Timeframe mapping: internal → yfinance interval strings
YFINANCE_INTERVALS: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",   # yfinance has no 4h; caller must resample
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}
```

- [ ] **Step 2: Write `backend/src/data/providers/yfinance_provider.py`**

```python
import asyncio
from datetime import date, datetime
from functools import partial
import pandas as pd
import yfinance as yf
from src.data.providers.base import DataProvider, YFINANCE_INTERVALS


class YFinanceProvider(DataProvider):
    """
    Runs yfinance (synchronous) in a thread pool executor.
    Limits: 1m data ≤7 days, 5m-30m ≤60 days, 1h ≤730 days, 1d+ unlimited.
    """

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        interval = YFINANCE_INTERVALS.get(timeframe, "1d")
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            None,
            partial(
                yf.download,
                tickers=symbol,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
                auto_adjust=True,
                progress=False,
            ),
        )
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])
        # yfinance returns MultiIndex columns when downloading single ticker with auto_adjust
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"adj close": "close"})
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df["vwap"] = None
        df["source"] = "yfinance"
        df.index = pd.to_datetime(df.index, utc=True)
        return df.dropna(subset=["open", "close"])

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, underlying)
        expiry_str = expiry.strftime("%Y-%m-%d") if expiry else None
        opt = await loop.run_in_executor(None, ticker.option_chain, expiry_str)
        calls = opt.calls.copy()
        calls["option_type"] = "call"
        puts = opt.puts.copy()
        puts["option_type"] = "put"
        df = pd.concat([calls, puts], ignore_index=True)
        df["underlying"] = underlying
        df["source"] = "yfinance"
        return df.rename(columns={
            "contractSymbol": "symbol",
            "lastPrice": "last",
            "impliedVolatility": "iv",
            "openInterest": "open_interest",
        })

    async def get_latest_quote(self, symbol: str) -> dict:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
        info = await loop.run_in_executor(None, lambda: ticker.fast_info)
        return {
            "symbol": symbol,
            "last": getattr(info, "last_price", None),
            "bid": getattr(info, "bid", None),
            "ask": getattr(info, "ask", None),
            "volume": getattr(info, "three_month_average_volume", None),
            "timestamp": datetime.utcnow(),
            "source": "yfinance",
        }
```

- [ ] **Step 3: Write `backend/tests/test_yfinance_provider.py`**

```python
import pytest
from datetime import datetime, timedelta
from src.data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider():
    return YFinanceProvider()


async def test_get_bars_returns_dataframe(provider):
    end = datetime.utcnow()
    start = end - timedelta(days=10)
    df = await provider.get_bars("AAPL", "1d", start, end)
    assert not df.empty
    assert "close" in df.columns
    assert "source" in df.columns
    assert df["source"].iloc[0] == "yfinance"


async def test_get_bars_empty_symbol(provider):
    end = datetime.utcnow()
    start = end - timedelta(days=5)
    df = await provider.get_bars("INVALID_TICKER_XYZ", "1d", start, end)
    assert df.empty or len(df) == 0


async def test_get_latest_quote(provider):
    quote = await provider.get_latest_quote("SPY")
    assert quote["symbol"] == "SPY"
    assert quote["source"] == "yfinance"
```

- [ ] **Step 4: Run tests (requires internet)**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_yfinance_provider.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/data/providers/base.py backend/src/data/providers/yfinance_provider.py backend/tests/test_yfinance_provider.py
git commit -m "feat: DataProvider interface + YFinanceProvider"
```

---

## Task 6: Schwab Provider

**Files:**
- Create: `backend/src/data/providers/schwab.py`
- Create: `backend/src/data/providers/polygon.py`

**Note:** Schwab OAuth requires a one-time browser login to create the token file. Run `uv run python -c "from src.data.providers.schwab import SchwabProvider; import asyncio; asyncio.run(SchwabProvider.authenticate())"` to perform initial auth.

- [ ] **Step 1: Write `backend/src/data/providers/schwab.py`**

```python
import asyncio
from datetime import date, datetime
from functools import partial
import pandas as pd
import schwab
from schwab.client import Client
from src.core.config import settings
from src.data.providers.base import DataProvider

# Schwab frequency mappings
_FREQ_MAP = {
    "1m":  (Client.PriceHistory.FrequencyType.MINUTE, 1),
    "5m":  (Client.PriceHistory.FrequencyType.MINUTE, 5),
    "15m": (Client.PriceHistory.FrequencyType.MINUTE, 15),
    "30m": (Client.PriceHistory.FrequencyType.MINUTE, 30),
    "1h":  (Client.PriceHistory.FrequencyType.MINUTE, 60),
    "1d":  (Client.PriceHistory.FrequencyType.DAILY, 1),
    "1wk": (Client.PriceHistory.FrequencyType.WEEKLY, 1),
    "1mo": (Client.PriceHistory.FrequencyType.MONTHLY, 1),
}


class SchwabProvider(DataProvider):
    def __init__(self):
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = schwab.auth.client_from_token_file(
                settings.schwab_token_path,
                settings.schwab_api_key,
                settings.schwab_app_secret,
            )
        return self._client

    @staticmethod
    async def authenticate():
        """One-time browser-based OAuth flow. Run once to create the token file."""
        schwab.auth.easy_client(
            settings.schwab_api_key,
            settings.schwab_app_secret,
            "https://127.0.0.1",
            settings.schwab_token_path,
        )

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        client = self._get_client()
        freq_type, freq = _FREQ_MAP.get(timeframe, (Client.PriceHistory.FrequencyType.DAILY, 1))
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                client.get_price_history,
                symbol,
                frequency_type=freq_type,
                frequency=freq,
                start_datetime=start,
                end_datetime=end,
                need_extended_hours_data=False,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        candles = data.get("candles", [])
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])
        df = pd.DataFrame(candles)
        df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
        df = df.set_index("datetime").rename(columns={"volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df["vwap"] = None
        df["source"] = "schwab"
        return df

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        client = self._get_client()
        loop = asyncio.get_running_loop()
        kwargs = {"symbol": underlying}
        if expiry:
            kwargs["from_date"] = expiry
            kwargs["to_date"] = expiry
        resp = await loop.run_in_executor(None, partial(client.get_option_chain, **kwargs))
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for exp_date, strikes in {**data.get("callExpDateMap", {}), **data.get("putExpDateMap", {})}.items():
            exp = exp_date.split(":")[0]
            for strike_str, options in strikes.items():
                for opt in options:
                    rows.append({
                        "symbol": opt["symbol"],
                        "underlying": underlying,
                        "expiry": exp,
                        "strike": float(strike_str),
                        "option_type": "call" if opt["putCall"] == "CALL" else "put",
                        "bid": opt.get("bid"),
                        "ask": opt.get("ask"),
                        "last": opt.get("last"),
                        "volume": opt.get("totalVolume"),
                        "open_interest": opt.get("openInterest"),
                        "iv": opt.get("volatility"),
                        "delta": opt.get("delta"),
                        "gamma": opt.get("gamma"),
                        "theta": opt.get("theta"),
                        "vega": opt.get("vega"),
                        "source": "schwab",
                    })
        return pd.DataFrame(rows)

    async def get_latest_quote(self, symbol: str) -> dict:
        client = self._get_client()
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, partial(client.get_quote, symbol))
        resp.raise_for_status()
        data = resp.json().get(symbol, {})
        quote = data.get("quote", {})
        return {
            "symbol": symbol,
            "bid": quote.get("bidPrice"),
            "ask": quote.get("askPrice"),
            "last": quote.get("lastPrice"),
            "volume": quote.get("totalVolume"),
            "timestamp": datetime.utcnow(),
            "source": "schwab",
        }
```

- [ ] **Step 2: Write `backend/src/data/providers/polygon.py` (stub)**

```python
from datetime import date, datetime
import pandas as pd
from src.data.providers.base import DataProvider


class PolygonProvider(DataProvider):
    """Paid provider stub. Implement when Polygon API key is available."""

    async def get_bars(self, symbol, timeframe, start, end) -> pd.DataFrame:
        raise NotImplementedError("Polygon provider not yet implemented")

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        raise NotImplementedError("Polygon provider not yet implemented")

    async def get_latest_quote(self, symbol) -> dict:
        raise NotImplementedError("Polygon provider not yet implemented")
```

- [ ] **Step 3: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/data/providers/schwab.py backend/src/data/providers/polygon.py
git commit -m "feat: SchwabProvider + PolygonProvider stub"
```

---

## Task 7: Data Repository & Collector

**Files:**
- Create: `backend/src/data/repository.py`
- Create: `backend/src/data/collector.py`
- Create: `backend/tests/test_repository.py`

- [ ] **Step 1: Write `backend/src/data/repository.py`**

```python
from datetime import datetime
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models import Instrument, OhlcvBar


async def upsert_instrument(session: AsyncSession, symbol: str, type_: str, **kwargs) -> Instrument:
    stmt = (
        insert(Instrument)
        .values(symbol=symbol, type=type_, **kwargs)
        .on_conflict_do_update(index_elements=["symbol"], set_={"name": kwargs.get("name")})
        .returning(Instrument)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def save_bars(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    df: pd.DataFrame,
) -> int:
    """Insert bars, skip duplicates. Returns count of new rows inserted."""
    if df.empty:
        return 0
    rows = [
        {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "bar_time": idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
            "vwap": float(row["vwap"]) if pd.notna(row.get("vwap")) else None,
            "source": row["source"],
        }
        for idx, row in df.iterrows()
    ]
    stmt = insert(OhlcvBar).values(rows).on_conflict_do_nothing()
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def get_bars(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    limit: int = 200,
    end_before: datetime | None = None,
) -> pd.DataFrame:
    query = (
        select(OhlcvBar)
        .where(OhlcvBar.instrument_id == instrument_id, OhlcvBar.timeframe == timeframe)
    )
    if end_before:
        query = query.where(OhlcvBar.bar_time < end_before)
    query = query.order_by(OhlcvBar.bar_time.desc()).limit(limit)
    result = await session.execute(query)
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap"])
    df = pd.DataFrame([
        {"bar_time": b.bar_time, "open": float(b.open), "high": float(b.high),
         "low": float(b.low), "close": float(b.close),
         "volume": b.volume, "vwap": float(b.vwap) if b.vwap else None}
        for b in bars
    ]).set_index("bar_time").sort_index()
    return df


async def get_latest_bar_time(
    session: AsyncSession, instrument_id: int, timeframe: str
) -> datetime | None:
    result = await session.execute(
        select(OhlcvBar.bar_time)
        .where(OhlcvBar.instrument_id == instrument_id, OhlcvBar.timeframe == timeframe)
        .order_by(OhlcvBar.bar_time.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row
```

- [ ] **Step 2: Write `backend/tests/test_repository.py`**

```python
import pytest
import pandas as pd
from datetime import datetime, timezone
from src.core.models import Instrument
from src.data.repository import upsert_instrument, save_bars, get_bars


async def test_save_and_get_bars(session):
    inst = await upsert_instrument(session, "TSLA", "stock", name="Tesla")
    df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [1000, 2000],
        "vwap": [None, None],
        "source": ["yfinance", "yfinance"],
    }, index=pd.to_datetime(["2024-01-02", "2024-01-03"], utc=True))
    count = await save_bars(session, inst.id, "1d", df)
    assert count == 2
    result = await get_bars(session, inst.id, "1d", limit=10)
    assert len(result) == 2
    assert "close" in result.columns


async def test_save_bars_deduplication(session):
    inst = await upsert_instrument(session, "NVDA", "stock")
    df = pd.DataFrame({
        "open": [200.0], "high": [201.0], "low": [199.0], "close": [200.5],
        "volume": [500], "vwap": [None], "source": ["yfinance"],
    }, index=pd.to_datetime(["2024-01-04"], utc=True))
    await save_bars(session, inst.id, "1d", df)
    count2 = await save_bars(session, inst.id, "1d", df)  # same data again
    assert count2 == 0  # ON CONFLICT DO NOTHING
```

- [ ] **Step 3: Write `backend/src/data/collector.py`**

```python
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Strategy
from src.data.providers.base import DataProvider
from src.data.providers.yfinance_provider import YFinanceProvider
from src.data.providers.schwab import SchwabProvider
from src.data import repository
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Default historical backfill depth per timeframe
BACKFILL_DAYS: dict[str, int] = {
    "1m": 7, "5m": 60, "15m": 60, "30m": 60,
    "1h": 730, "4h": 730, "1d": 730, "1wk": 1825, "1mo": 3650,
}


def _select_provider(timeframe: str, days_back: int) -> DataProvider:
    """Route to cheapest free source that covers the requested history."""
    if timeframe in ("1m",) and days_back <= 7:
        return YFinanceProvider()
    if timeframe in ("5m", "15m", "30m") and days_back <= 60:
        return YFinanceProvider()
    if timeframe in ("1h",) and days_back <= 730:
        return YFinanceProvider()
    if timeframe == "1d":
        return YFinanceProvider()
    return YFinanceProvider()  # fallback


class DataCollector:
    def __init__(self):
        self._yfinance = YFinanceProvider()

    async def build_collection_plan(self) -> dict[str, set[str]]:
        """Scan active strategies and return {symbol: {timeframes}} merged plan."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active == True)
            )
            strategies = result.scalars().all()
        plan: dict[str, set[str]] = {}
        for s in strategies:
            for sym in s.symbols:
                plan.setdefault(sym, set()).update(s.timeframes)
        return plan

    async def sync_symbol_timeframe(
        self, symbol: str, timeframe: str
    ) -> None:
        """Fetch missing bars for one symbol+timeframe and upsert into DB."""
        async with async_session_factory() as session:
            inst = await repository.upsert_instrument(session, symbol, "stock")
            latest = await repository.get_latest_bar_time(session, inst.id, timeframe)
            now = datetime.utcnow()
            if latest:
                start = latest + timedelta(minutes=1)
            else:
                days = BACKFILL_DAYS.get(timeframe, 730)
                start = now - timedelta(days=days)
            if start >= now:
                return
            days_back = (now - start).days + 1
            provider = _select_provider(timeframe, days_back)
            try:
                df = await provider.get_bars(symbol, timeframe, start, now)
                if not df.empty:
                    await repository.save_bars(session, inst.id, timeframe, df)
                    logger.info("Synced %s %s: %d bars", symbol, timeframe, len(df))
            except Exception as e:
                logger.error("Failed to sync %s %s: %s", symbol, timeframe, e)

    async def run_full_sync(self) -> None:
        """Sync all symbols+timeframes from the collection plan, with batching."""
        plan = await self.build_collection_plan()
        tasks = [
            self.sync_symbol_timeframe(sym, tf)
            for sym, timeframes in plan.items()
            for tf in timeframes
        ]
        batch_size = settings.data_batch_size
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            await asyncio.gather(*batch)
            if i + batch_size < len(tasks):
                await asyncio.sleep(settings.data_batch_delay)
```

- [ ] **Step 4: Run repository tests**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_repository.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/data/repository.py backend/src/data/collector.py backend/tests/test_repository.py
git commit -m "feat: data repository and collector"
```

---

**Phase B complete.** Continue with Phase C: `2026-04-17-trading-system-phase-c.md`
