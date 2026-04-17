# PXT Trading System — Phase A: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the monorepo, configure the database connection, define all ORM models, and run the initial Alembic migration.

**Architecture:** Python monorepo under `backend/`, React under `frontend/`. All DB tables created via Alembic migration. SQLAlchemy 2.0 async throughout.

**Tech Stack:** Python 3.12+, uv, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic-settings, PostgreSQL 16

---

## File Map

| File | Purpose |
|---|---|
| `backend/pyproject.toml` | All Python dependencies |
| `backend/src/core/config.py` | `Settings` via pydantic-settings |
| `backend/src/core/database.py` | Async engine, session factory, `get_session` |
| `backend/src/core/models.py` | All 10 SQLAlchemy ORM models |
| `backend/alembic/env.py` | Alembic async env |
| `backend/alembic/versions/001_initial_schema.py` | Initial migration |
| `backend/tests/conftest.py` | pytest fixtures |
| `.env.example` | All config keys |
| `.gitignore` | Git ignores |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `frontend/` (empty scaffold)
- Create: `.env`, `.env.example`, `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
cd /home/imxichen/projects/pxt
mkdir -p backend/src/core backend/src/data/providers backend/src/strategies/library
mkdir -p backend/src/backtesting backend/src/llm/providers
mkdir -p backend/src/signals/notifiers backend/src/scheduler backend/src/api/routers
mkdir -p backend/tests backend/alembic/versions
mkdir -p frontend/src/api frontend/src/pages frontend/src/components frontend/src/hooks frontend/src/types
mkdir -p docker docs/superpowers/plans
touch backend/src/__init__.py backend/src/core/__init__.py
touch backend/src/data/__init__.py backend/src/data/providers/__init__.py
touch backend/src/strategies/__init__.py backend/src/strategies/library/__init__.py
touch backend/src/backtesting/__init__.py backend/src/llm/__init__.py backend/src/llm/providers/__init__.py
touch backend/src/signals/__init__.py backend/src/signals/notifiers/__init__.py
touch backend/src/scheduler/__init__.py backend/src/api/__init__.py backend/src/api/routers/__init__.py
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "pxt-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic-settings>=2.6",
    "apscheduler>=4.0",
    "pandas-ta>=0.3",
    "pandas>=2.2",
    "numpy>=1.26",
    "yfinance>=0.2",
    "schwab-py>=1.4",
    "anthropic>=0.40",
    "openai>=1.56",
    "httpx>=0.28",
    "aiosmtplib>=3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

- [ ] **Step 3: Install dependencies**

```bash
cd /home/imxichen/projects/pxt/backend
uv sync --extra dev
```

Expected: uv creates `.venv/` and installs all packages.

- [ ] **Step 4: Create `.env.example`**

```bash
cat > /home/imxichen/projects/pxt/.env.example << 'EOF'
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pxt
SCHWAB_API_KEY=
SCHWAB_APP_SECRET=
SCHWAB_TOKEN_PATH=./schwab_token.json
POLYGON_API_KEY=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
NOTIFY_EMAIL=
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
TIMEZONE=America/Chicago
MAX_SYMBOLS_PER_STRATEGY=50
STRATEGY_RUN_TIMEOUT=300
DATA_BATCH_SIZE=20
DATA_BATCH_DELAY=0.5
EOF
```

- [ ] **Step 5: Create `.env` from example and fill in DATABASE_URL**

```bash
cp /home/imxichen/projects/pxt/.env.example /home/imxichen/projects/pxt/.env
# Edit .env and set DATABASE_URL to your local Postgres instance
```

- [ ] **Step 6: Create `.gitignore`**

```bash
cat > /home/imxichen/projects/pxt/.gitignore << 'EOF'
.env
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
node_modules/
dist/
.DS_Store
schwab_token.json
EOF
```

- [ ] **Step 7: Initialize git and first commit**

```bash
cd /home/imxichen/projects/pxt
git init
git add .
git commit -m "chore: project scaffolding"
```

---

## Task 2: Core Config & Database

**Files:**
- Create: `backend/src/core/config.py`
- Create: `backend/src/core/database.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write `backend/src/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str
    schwab_api_key: str = ""
    schwab_app_secret: str = ""
    schwab_token_path: str = "./schwab_token.json"
    polygon_api_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email: str = ""
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    timezone: str = "America/Chicago"
    max_symbols_per_strategy: int = 50
    strategy_run_timeout: int = 300
    data_batch_size: int = 20
    data_batch_delay: float = 0.5


settings = Settings()
```

- [ ] **Step 2: Write `backend/src/core/database.py`**

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 3: Write `backend/tests/conftest.py`**

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.database import Base

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/pxt_test"


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DB_URL, echo=False)


@pytest.fixture(autouse=True, scope="session")
async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
```

- [ ] **Step 4: Create test Postgres database**

```bash
psql -U postgres -c "CREATE DATABASE pxt_test;"
psql -U postgres -c "CREATE DATABASE pxt;"
```

- [ ] **Step 5: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/core/ backend/tests/conftest.py
git commit -m "feat: core config and database connection"
```

---

## Task 3: ORM Models

**Files:**
- Create: `backend/src/core/models.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write `backend/src/core/models.py`**

```python
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, Date, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # stock, etf, crypto
    exchange: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    name: Mapped[str | None] = mapped_column(String(100))

    bars: Mapped[list["OhlcvBar"]] = relationship(back_populates="instrument")


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    underlying: Mapped[str] = mapped_column(String(20), ForeignKey("instruments.symbol"), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # call, put
    multiplier: Mapped[int] = mapped_column(Integer, default=100)

    __table_args__ = (
        Index("idx_options_underlying", "underlying", "expiry", "strike"),
    )


class OhlcvBar(Base):
    __tablename__ = "ohlcv_bars"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    bar_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="bars")

    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "bar_time"),
        Index("idx_bars", "instrument_id", "timeframe", "bar_time"),
    )


class OptionChainSnapshot(Base):
    __tablename__ = "option_chain_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    option_id: Mapped[int] = mapped_column(Integer, ForeignKey("options.id"), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    last: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(Integer)
    open_interest: Mapped[int | None] = mapped_column(Integer)
    iv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("idx_chain", "option_id", "snapshot_time"),
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    run_frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    max_symbols: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class TradeSignalRecord(Base):
    __tablename__ = "trade_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(50), ForeignKey("strategies.id"), nullable=False)
    stock_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("instruments.id"))
    option_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("options.id"))
    signal_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reasoning: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "(stock_id IS NOT NULL AND option_id IS NULL) OR "
            "(stock_id IS NULL AND option_id IS NOT NULL)",
            name="ck_signal_instrument",
        ),
        Index("idx_signals_strategy", "strategy_id", "created_at"),
        Index("idx_signals_status", "status", "created_at"),
    )


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(50), ForeignKey("strategies.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="running")
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    annualized_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    total_trades: Mapped[int | None] = mapped_column(Integer)
    avg_hold_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    llm_evaluation: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest")
    equity_curve: Mapped[list["BacktestEquityCurve"]] = relationship(back_populates="backtest")


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtests.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    hold_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    exit_reason: Mapped[str | None] = mapped_column(String(50))
    entry_signal: Mapped[dict | None] = mapped_column(JSONB)
    exit_signal: Mapped[dict | None] = mapped_column(JSONB)

    backtest: Mapped["Backtest"] = relationship(back_populates="trades")

    __table_args__ = (
        Index("idx_bt_trades", "backtest_id", "entry_time"),
    )


class BacktestEquityCurve(Base):
    __tablename__ = "backtest_equity_curve"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtests.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    backtest: Mapped["Backtest"] = relationship(back_populates="equity_curve")

    __table_args__ = (
        Index("idx_bt_equity", "backtest_id", "ts"),
    )


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_system_events", "event_type", "created_at"),
    )
```

- [ ] **Step 2: Write `backend/tests/test_models.py`**

```python
import pytest
from sqlalchemy import select
from src.core.models import Instrument, OhlcvBar, Strategy


async def test_instrument_create(session):
    inst = Instrument(symbol="AAPL", type="stock", exchange="NASDAQ", name="Apple Inc.")
    session.add(inst)
    await session.commit()
    result = await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
    found = result.scalar_one()
    assert found.symbol == "AAPL"
    assert found.type == "stock"


async def test_strategy_create(session):
    s = Strategy(
        id="test_strat",
        name="Test",
        symbols=["AAPL"],
        timeframes=["1d"],
        run_frequency="0 16 * * 1-5",
    )
    session.add(s)
    await session.commit()
    result = await session.execute(select(Strategy).where(Strategy.id == "test_strat"))
    found = result.scalar_one()
    assert found.symbols == ["AAPL"]
```

- [ ] **Step 3: Run tests**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_models.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/core/models.py backend/tests/test_models.py
git commit -m "feat: ORM models for all 10 tables"
```

---

## Task 4: Alembic Migration

**Files:**
- Create: `backend/alembic.ini`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial_schema.py`

- [ ] **Step 1: Initialize Alembic**

```bash
cd /home/imxichen/projects/pxt/backend
uv run alembic init alembic
```

- [ ] **Step 2: Overwrite `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from src.core.config import settings
from src.core.database import Base
import src.core.models  # noqa: F401 — registers all models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Generate initial migration**

```bash
cd /home/imxichen/projects/pxt/backend
uv run alembic revision --autogenerate -m "initial_schema"
```

Expected: Creates `alembic/versions/XXXX_initial_schema.py` with all table definitions.

- [ ] **Step 4: Apply migration to both databases**

```bash
uv run alembic upgrade head
# verify pxt_test too
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pxt_test uv run alembic upgrade head
```

Expected: All 10 tables created in both databases.

- [ ] **Step 5: Verify tables exist**

```bash
psql -U postgres -d pxt -c "\dt"
```

Expected: Lists `instruments`, `options`, `ohlcv_bars`, `option_chain_snapshots`, `strategies`, `trade_signals`, `backtests`, `backtest_trades`, `backtest_equity_curve`, `system_events`.

- [ ] **Step 6: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/alembic/ backend/alembic.ini
git commit -m "feat: Alembic migration — initial schema"
```

---

**Phase A complete.** Continue with Phase B (Data Layer): `2026-04-17-trading-system-phase-b.md`
