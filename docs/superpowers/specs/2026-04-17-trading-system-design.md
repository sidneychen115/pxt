# Trading System Design

**Date:** 2026-04-17  
**Project:** pxt — Personal Stock Trading System  
**Status:** Approved

---

## 1. Overview

A personal algorithmic trading system supporting US equities and options (phase 1), with future expansion to multi-market including crypto (phase 2). Built in Python, runs locally on Windows first, then deployable via Docker to cloud (AWS etc.).

**Core goals:**
- Collect multi-timeframe OHLCV and options data from free sources (Schwab + yfinance)
- Run multiple configurable strategies concurrently, each with its own symbol list and schedule
- Deliver trade signals via email (phase 1) and auto-execute via Schwab API (phase 2)
- Backtest strategies against historical data with full drill-down trade records and LLM evaluation
- Monitor everything via a React web dashboard

---

## 2. Architecture

### 2.1 Overall Architecture

```
┌─────────────────────────────────────────────────┐
│                  Trading System                  │
│                                                 │
│  ┌───────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  Data     │  │ Strategy │  │  Backtest   │  │
│  │ Collector │  │  Engine  │  │   Engine    │  │
│  └─────┬─────┘  └────┬─────┘  └──────┬──────┘  │
│        │             │               │          │
│        └─────────────┼───────────────┘          │
│                      │                          │
│               ┌──────▼──────┐                   │
│               │  PostgreSQL │                   │
│               └──────┬──────┘                   │
│                      │                          │
│   ┌──────────┐  ┌────▼──────┐  ┌────────────┐  │
│   │Scheduler │  │  FastAPI  │  │  Signal    │  │
│   │(APSched) │  │ Dashboard │  │ Processor  │  │
│   └──────────┘  └───────────┘  └────────────┘  │
└─────────────────────────────────────────────────┘
```

All modules share state through PostgreSQL — no direct inter-module calls. The Scheduler triggers strategy runs; the Signal Processor polls the signals table and dispatches notifications/orders.

### 2.2 Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI + uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| DB migrations | Alembic |
| Scheduler | APScheduler 4.x |
| Technical indicators | pandas-ta |
| Frontend | React 18 + Vite + TypeScript |
| Financial charts | TradingView Lightweight Charts |
| Package manager | uv |

### 2.3 Repository Structure

Monorepo with two top-level directories:

```
pxt/
├── backend/
├── frontend/
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
└── .env.example
```

Local development: `uvicorn` + `vite dev` run independently. Production: `docker-compose up`.

---

## 3. Database Schema

**Timezone:** All `TIMESTAMPTZ` values are stored as UTC internally by PostgreSQL. The application layer and frontend display times in `America/Chicago`.

### 3.1 instruments — Stocks, ETFs, Crypto

```sql
CREATE TABLE instruments (
    id       SERIAL PRIMARY KEY,
    symbol   VARCHAR(20) NOT NULL UNIQUE,
    type     VARCHAR(10) NOT NULL,  -- 'stock', 'etf', 'crypto'
    exchange VARCHAR(20),
    currency VARCHAR(10) DEFAULT 'USD',
    name     VARCHAR(100)
);
```

### 3.2 options — Options Contracts

```sql
CREATE TABLE options (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(30) NOT NULL UNIQUE,  -- OCC standard: 'AAPL240119C00150000'
    underlying  VARCHAR(20) NOT NULL REFERENCES instruments(symbol),
    expiry      DATE NOT NULL,
    strike      NUMERIC(12,4) NOT NULL,
    option_type VARCHAR(4) NOT NULL,   -- 'call', 'put'
    multiplier  INTEGER DEFAULT 100
);
CREATE INDEX idx_options_underlying ON options(underlying, expiry, strike);
```

### 3.3 ohlcv_bars — Multi-timeframe K-line Data

Single table for all timeframes. The `timeframe` column distinguishes periods. Unique constraint on `(instrument_id, timeframe, bar_time)` prevents duplicates.

```sql
CREATE TABLE ohlcv_bars (
    id            BIGSERIAL PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    timeframe     VARCHAR(5) NOT NULL,   -- '5m','15m','30m','1h','4h','1d','1w','1mo'
    bar_time      TIMESTAMPTZ NOT NULL,  -- bar open time, UTC
    open          NUMERIC(16,6) NOT NULL,
    high          NUMERIC(16,6) NOT NULL,
    low           NUMERIC(16,6) NOT NULL,
    close         NUMERIC(16,6) NOT NULL,
    volume        BIGINT DEFAULT 0,
    vwap          NUMERIC(16,6),
    source        VARCHAR(20) NOT NULL,  -- 'schwab', 'yfinance', 'polygon'
    UNIQUE(instrument_id, timeframe, bar_time)
);
CREATE INDEX idx_bars ON ohlcv_bars(instrument_id, timeframe, bar_time DESC);
```

### 3.4 option_chain_snapshots — Options Chain Snapshots

```sql
CREATE TABLE option_chain_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    option_id     INTEGER NOT NULL REFERENCES options(id),
    snapshot_time TIMESTAMPTZ NOT NULL,
    bid           NUMERIC(12,4),
    ask           NUMERIC(12,4),
    last          NUMERIC(12,4),
    volume        INTEGER,
    open_interest INTEGER,
    iv            NUMERIC(8,6),
    delta         NUMERIC(8,6),
    gamma         NUMERIC(8,6),
    theta         NUMERIC(8,6),
    vega          NUMERIC(8,6),
    source        VARCHAR(20) NOT NULL
);
CREATE INDEX idx_chain ON option_chain_snapshots(option_id, snapshot_time DESC);
```

### 3.5 strategies — Strategy Configuration

```sql
CREATE TABLE strategies (
    id            VARCHAR(50) PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    symbols       TEXT[] NOT NULL,        -- e.g. ['AAPL','MSFT']
    timeframes    TEXT[] NOT NULL,        -- e.g. ['1d','1h']
    run_frequency VARCHAR(50) NOT NULL,   -- cron: '0 16 * * 1-5' or interval: '15m'
    parameters    JSONB DEFAULT '{}',
    max_symbols   INTEGER DEFAULT 50,     -- hard cap enforced at registration
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.6 trade_signals — Trade Signals

```sql
CREATE TABLE trade_signals (
    id            BIGSERIAL PRIMARY KEY,
    strategy_id   VARCHAR(50) NOT NULL REFERENCES strategies(id),
    -- Exactly one of stock_id or option_id is non-null
    stock_id      INTEGER REFERENCES instruments(id),
    option_id     INTEGER REFERENCES options(id),
    signal_time   TIMESTAMPTZ NOT NULL,
    direction     VARCHAR(10) NOT NULL,   -- 'buy', 'sell', 'hold'
    quantity      NUMERIC(16,4),
    order_type    VARCHAR(10) NOT NULL,   -- 'market', 'limit', 'stop'
    limit_price   NUMERIC(16,6),
    stop_price    NUMERIC(16,6),
    confidence    NUMERIC(4,3),           -- 0.0–1.0
    reasoning     TEXT,
    status        VARCHAR(20) DEFAULT 'pending',  -- 'pending','notified','executed','cancelled'
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    CHECK (
        (stock_id IS NOT NULL AND option_id IS NULL) OR
        (stock_id IS NULL AND option_id IS NOT NULL)
    )
);
-- Expression index to prevent duplicate signals for same strategy+instrument+time
CREATE UNIQUE INDEX idx_signals_unique ON trade_signals(
    strategy_id, COALESCE(stock_id::text, option_id::text), signal_time
);
CREATE INDEX idx_signals_strategy ON trade_signals(strategy_id, created_at DESC);
CREATE INDEX idx_signals_status ON trade_signals(status, created_at DESC);
```

### 3.7 backtests — Backtest Runs and Summary

```sql
CREATE TABLE backtests (
    id                BIGSERIAL PRIMARY KEY,
    strategy_id       VARCHAR(50) NOT NULL REFERENCES strategies(id),
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    symbols           TEXT[] NOT NULL,
    initial_capital   NUMERIC(16,2) NOT NULL,
    parameters        JSONB DEFAULT '{}',
    status            VARCHAR(20) DEFAULT 'running',  -- 'running','completed','failed'
    -- Summary metrics
    total_return      NUMERIC(10,4),
    annualized_return NUMERIC(10,4),
    sharpe_ratio      NUMERIC(8,4),
    max_drawdown      NUMERIC(8,4),
    win_rate          NUMERIC(6,4),
    profit_factor     NUMERIC(8,4),
    total_trades      INTEGER,
    avg_hold_days     NUMERIC(8,2),
    -- LLM evaluation
    llm_evaluation    TEXT,
    llm_model         VARCHAR(50),
    error_message     TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);
```

### 3.8 backtest_trades — Per-trade Drill-down Records

```sql
CREATE TABLE backtest_trades (
    id           BIGSERIAL PRIMARY KEY,
    backtest_id  BIGINT NOT NULL REFERENCES backtests(id),
    symbol       VARCHAR(30) NOT NULL,
    direction    VARCHAR(10) NOT NULL,
    quantity     NUMERIC(16,4) NOT NULL,
    entry_time   TIMESTAMPTZ NOT NULL,
    entry_price  NUMERIC(16,6) NOT NULL,
    exit_time    TIMESTAMPTZ,
    exit_price   NUMERIC(16,6),
    pnl          NUMERIC(16,6),
    pnl_pct      NUMERIC(8,4),
    hold_days    NUMERIC(8,2),
    exit_reason  VARCHAR(50),   -- 'signal','stop_loss','take_profit','end_of_backtest'
    entry_signal JSONB,
    exit_signal  JSONB
);
CREATE INDEX idx_bt_trades ON backtest_trades(backtest_id, entry_time);
```

### 3.9 backtest_equity_curve — Daily Equity for Charting

```sql
CREATE TABLE backtest_equity_curve (
    id          BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT NOT NULL REFERENCES backtests(id),
    ts          TIMESTAMPTZ NOT NULL,
    equity      NUMERIC(16,2) NOT NULL,
    cash        NUMERIC(16,2) NOT NULL,
    drawdown    NUMERIC(8,4)
);
CREATE INDEX idx_bt_equity ON backtest_equity_curve(backtest_id, ts);
```

### 3.10 system_events — System Monitoring Log

```sql
CREATE TABLE system_events (
    id         BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,  -- 'data_sync','strategy_run','signal','error'
    level      VARCHAR(10) DEFAULT 'info',
    message    TEXT NOT NULL,
    details    JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_system_events ON system_events(event_type, created_at DESC);
```

---

## 4. Data Collection Module

### 4.1 Provider Interface

```python
class DataProvider(ABC):
    async def get_bars(self, symbol: str, timeframe: str,
                       start: datetime, end: datetime) -> pd.DataFrame: ...
    async def get_option_chain(self, underlying: str,
                                expiry: date | None = None) -> pd.DataFrame: ...
    async def get_latest_quote(self, symbol: str) -> dict: ...
```

Implementations: `SchwabProvider`, `YFinanceProvider`, `PolygonProvider`.

### 4.2 Data Source Routing (Free-first)

| Need | Primary (free) | Fallback (paid) |
|---|---|---|
| Real-time quotes + option chain | Schwab | — |
| Daily/weekly history (10yr+) | yfinance | Polygon |
| Hourly history (≤2yr) | yfinance | Schwab / Polygon |
| Minute history (≤60 days) | yfinance | Schwab (≤180d) |
| Minute history (>60 days) | Schwab (≤180d) | Polygon |
| Historical option chain | No free source | Polygon / CBOE |

### 4.3 Collector Orchestration

On startup the `DataCollector` scans all active strategies and builds a merged collection plan:

```python
# Example merged plan:
{
    'AAPL': {'1d', '5m', '15m'},
    'MSFT': {'1d'},
    'SPY':  {'1h', '1d'},
}
```

Data is fetched once and shared across all strategies. Collection tasks run before strategy tasks at the same scheduled time. Insert uses `ON CONFLICT DO NOTHING` for deduplication.

New symbols trigger a historical backfill (configurable depth, default 2 years daily).

### 4.4 Key Details

- All timestamps stored as UTC; displayed in `America/Chicago`
- All providers return a standardised DataFrame (column names, types) before writing to DB
- Collection plan is rebuilt whenever a strategy is added, modified, or removed

---

## 5. Strategy Library

### 5.1 Indicators Layer

`pandas-ta` wrapped in a thin `Indicators` class to standardise call signatures:

```python
class Indicators:
    @staticmethod
    def sma(df, period) -> pd.Series: ...
    @staticmethod
    def ema(df, period) -> pd.Series: ...
    @staticmethod
    def macd(df, fast=12, slow=26, signal=9) -> pd.DataFrame: ...
    @staticmethod
    def rsi(df, period=14) -> pd.Series: ...
    @staticmethod
    def bbands(df, period=20) -> pd.DataFrame: ...
```

### 5.2 DataContext Interface

```python
class DataContext(ABC):
    async def get_bars(self, symbol: str, timeframe: str,
                       limit: int = 200) -> pd.DataFrame: ...
    async def get_option_chain(self, underlying: str,
                                expiry: date | None = None) -> pd.DataFrame: ...
    async def get_latest_quote(self, symbol: str) -> dict: ...
```

`LiveDataContext` reads from DB. `BacktestDataContext` slices data by simulation time (see §7).

### 5.3 BaseStrategy Interface

```python
@dataclass
class TradeSignal:
    symbol: str
    direction: Literal["buy", "sell", "hold"]
    order_type: Literal["market", "limit", "stop"]
    quantity: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    confidence: float = 1.0
    reasoning: str = ""
    option_symbol: str | None = None  # options only

class BaseStrategy(ABC):
    id: str
    name: str
    description: str
    default_symbols: list[str] = []
    default_timeframes: list[str] = ["1d"]
    default_frequency: str = "0 16 * * 1-5"
    default_parameters: dict = {}

    @abstractmethod
    async def generate_signals(
        self, symbols: list[str], parameters: dict, ctx: DataContext
    ) -> list[TradeSignal]: ...
```

### 5.4 Strategy Registration

Strategies placed in `backend/src/strategies/library/` are auto-discovered at startup — no manual registration needed. Each file exports exactly one `BaseStrategy` subclass.

---

## 6. Scheduler

APScheduler with `AsyncIOScheduler` (timezone: `America/Chicago`). Each active strategy in the DB is registered as a job using its `run_frequency` (cron expression or interval string).

**Multi-strategy concurrency:**
- Strategies execute as asyncio coroutines — they run concurrently without blocking each other
- Data collection jobs for the same time slot run before strategy jobs
- Each strategy run has a configurable timeout (default 300s); timeout is logged as a system error

**Concurrency limits:**

| Parameter | Default | Description |
|---|---|---|
| `max_symbols_per_strategy` | 50 | Enforced at strategy registration |
| `batch_size` | 20 | Symbols fetched per concurrent batch within DataContext |
| `batch_delay` | 0.5s | Pause between batches to avoid API rate limits |
| `run_timeout` | 300s | Max execution time per strategy run |

Dashboard strategy config changes trigger a hot-reload of the affected job — no service restart needed.

---

## 7. Backtesting Engine

### 7.1 Preventing Look-ahead Bias

`BacktestDataContext` enforces a strict time boundary:

```python
async def get_bars(self, symbol, timeframe, limit=200) -> pd.DataFrame:
    df = self._data[symbol][timeframe]
    past_only = df[df["bar_time"] < self._current_time]
    return past_only.tail(limit)
```

Order fills use the **next bar's open price**, not the current bar's close.

### 7.2 Execution Flow

1. Load all required historical data into memory for the date range
2. Advance simulation clock step-by-step (per strategy timeframe)
3. At each step: slice data → run `strategy.generate_signals()` → simulate fill → update portfolio
4. After all steps: compute metrics → write `backtests`, `backtest_trades`, `backtest_equity_curve`
5. Trigger LLM evaluation asynchronously

### 7.3 Performance Metrics

`total_return`, `annualized_return`, `sharpe_ratio`, `max_drawdown`, `win_rate`, `profit_factor`, `total_trades`, `avg_hold_days`.

### 7.4 Drill-down

Dashboard drill-down path: Backtest list → Summary + equity curve chart → Trade list (sortable by time/pnl/duration) → Single trade detail (K-line context with entry/exit annotations).

### 7.5 LLM Evaluation

```python
class BaseLLMProvider(ABC):
    async def complete(self, prompt: str) -> str: ...

# Implementations: ClaudeProvider, OpenAIProvider, OllamaProvider
```

Active provider is selected via `llm_provider` config key. Evaluation prompt includes strategy description, all metrics, and a trade log summary. Result stored in `backtests.llm_evaluation`.

---

## 8. Signal Processing

`SignalProcessor` polls `trade_signals` where `status = 'pending'` every 60 seconds.

```python
class BaseNotifier(ABC):
    async def send(self, signal: TradeSignal, instrument: str) -> bool: ...

# Phase 1: EmailNotifier (SMTP — Gmail/Outlook)
# Phase 2: SchwabTrader (Schwab Orders API)
```

Active notifier is selected via config. Switching to phase 2 requires only a config change.

---

## 9. Web Dashboard

### 9.1 Backend API

```
GET/PUT /api/strategies, /api/strategies/{id}
GET     /api/signals, /api/signals/{id}
GET     /api/backtests
POST    /api/backtests               # trigger new backtest
GET     /api/backtests/{id}
GET     /api/backtests/{id}/trades
GET     /api/backtests/{id}/equity
GET     /api/system/health
GET     /api/system/events
WS      /ws/signals                  # real-time signal push
WS      /ws/system                   # system event push
```

### 9.2 Frontend Pages

| Page | Key content |
|---|---|
| Dashboard | System status, today's signals, active strategies |
| Strategies | List, enable/disable, config editor |
| Signals | Filterable list + detail view |
| Backtests | Trigger form, list, drill-down detail (summary → equity curve → trades → single trade) |
| System | Live event log, data sync status per symbol |

### 9.3 Real-time Strategy

| Data | Method |
|---|---|
| New signals | WebSocket push |
| System events | WebSocket push |
| Backtest progress | WebSocket push |
| K-line charts | 30s polling |

---

## 10. Configuration

All settings loaded from `.env` via `pydantic-settings`:

```
DATABASE_URL
SCHWAB_API_KEY / SCHWAB_API_SECRET
POLYGON_API_KEY           # optional
SMTP_HOST / SMTP_USER / SMTP_PASSWORD / NOTIFY_EMAIL
LLM_PROVIDER              # claude | openai | ollama
ANTHROPIC_API_KEY
OPENAI_API_KEY
OLLAMA_BASE_URL
TIMEZONE=America/Chicago
MAX_SYMBOLS_PER_STRATEGY=50
STRATEGY_RUN_TIMEOUT=300
```

---

## 11. Project Directory Layout

```
pxt/
├── backend/
│   ├── src/
│   │   ├── core/           # config, database, models
│   │   ├── data/           # providers (schwab/yfinance/polygon), collector, repository
│   │   ├── strategies/     # base, indicators, registry, library/
│   │   ├── backtesting/    # engine, data_context, metrics, evaluator
│   │   ├── llm/            # providers (claude/openai/ollama)
│   │   ├── signals/        # processor, notifiers (email/schwab_trader)
│   │   ├── scheduler/      # runner
│   │   └── api/            # main, websocket, routers/
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   ├── package.json
│   └── vite.config.ts
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
└── .env.example
```

---

## 12. Phase Roadmap

| Phase | Scope |
|---|---|
| **Phase 1** | Data collection (Schwab + yfinance), strategy library, email notifications, backtesting engine + LLM eval, React dashboard |
| **Phase 2** | Schwab auto-trading, strategy discovery (web search + auto-backtest pipeline) |
