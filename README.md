# pxt — Personal Algorithmic Trading System

A personal algorithmic trading platform for US equities. Collects OHLCV data, runs rule-based strategies on a schedule, sends trade signals via email, and provides a web dashboard for monitoring and backtesting.

## Features

- **Data collection** — OHLCV bars from yfinance (free) or Charles Schwab (live); stored in PostgreSQL with deduplication
- **Strategy library** — plugin-style `BaseStrategy` interface; add a new strategy by dropping a file in `src/strategies/library/`
- **Scheduler** — runs strategies on cron schedules (APScheduler); concurrent multi-strategy execution with per-strategy timeouts
- **Signal processing** — pending signals delivered via email; extensible notifier interface for future broker integration
- **Backtesting** — look-ahead-free engine; DB-cached historical data; per-trade records; equity curve; LLM evaluation (Claude / OpenAI / Ollama)
- **REST + WebSocket API** — FastAPI backend; real-time signal push over WebSocket
- **React dashboard** — Dashboard, Strategies, Signals, Backtests, System pages built with TanStack Query and TradingView Lightweight Charts
- **Docker** — multi-stage production build; single `docker compose up` deployment

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+, TypeScript |
| Backend | FastAPI, SQLAlchemy 2.0 async, APScheduler 3.x |
| Database | PostgreSQL (asyncpg) |
| Migrations | Alembic |
| Data | yfinance, schwab-py, pandas-ta |
| LLM | Anthropic Claude, OpenAI, Ollama |
| Frontend | React 18, Vite, TanStack Query v5, Tailwind CSS |
| Charts | TradingView Lightweight Charts |
| Package manager | uv |
| Container | Docker + nginx |

## Project Structure

```
pxt/
├── backend/
│   ├── src/
│   │   ├── api/            # FastAPI app, routers, WebSocket
│   │   ├── backtesting/    # Engine, metrics, LLM evaluator
│   │   ├── core/           # Config, database, ORM models
│   │   ├── data/           # Providers (yfinance, Schwab, Polygon), repository, collector
│   │   ├── llm/            # LLM provider abstraction (Claude, OpenAI, Ollama)
│   │   ├── scheduler/      # APScheduler strategy runner
│   │   ├── signals/        # Signal processor, email notifier
│   │   └── strategies/     # BaseStrategy, indicators, registry, library/
│   ├── alembic/            # DB migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/          # Dashboard, Strategies, Signals, Backtests, System
│       ├── components/     # Layout, EquityChart, shared UI
│       ├── hooks/          # useWebSocket
│       └── api/            # Typed API client
└── docker/
    ├── Dockerfile.backend
    ├── Dockerfile.frontend
    ├── docker-compose.yml
    └── nginx.conf
```

## Local Development

### Prerequisites

- Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+
- PostgreSQL running locally (or use the shared Docker container below)

### 1. Start PostgreSQL

```bash
docker run -d --name pxt-db \
  -e POSTGRES_USER=cx_user \
  -e POSTGRES_PASSWORD=cx_pass \
  -p 5432:5432 postgres:16
```

Then create the databases:

```bash
docker exec -it pxt-db psql -U cx_user -c "CREATE DATABASE pxt;"
docker exec -it pxt-db psql -U cx_user -c "CREATE DATABASE pxt_test;"
```

### 2. Configure environment

Copy `.env` and fill in your API keys:

```bash
cp .env .env.local   # or edit .env directly
```

Key variables:

```env
DATABASE_URL=postgresql+asyncpg://cx_user:cx_pass@localhost:5432/pxt

# Data providers (at least one required for live data)
SCHWAB_API_KEY=
SCHWAB_APP_SECRET=
POLYGON_API_KEY=

# Email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
NOTIFY_EMAIL=

# LLM for backtest evaluation (claude | openai | ollama)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. Run migrations

```bash
cd backend
uv run alembic upgrade head
```

### 4. Start backend

```bash
cd backend
uv run uvicorn src.api.main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs

### 5. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at http://localhost:5173

### 6. Run tests

```bash
cd backend
uv run pytest tests/ -v
```

## Adding a Strategy

Create `backend/src/strategies/library/my_strategy.py`:

```python
from src.strategies.base import BaseStrategy, DataContext, TradeSignal
from src.strategies.indicators import Indicators

class MyStrategy(BaseStrategy):
    id = "my_strategy"
    name = "My Strategy"
    description = "Short description for LLM evaluation."
    default_symbols = ["AAPL", "MSFT"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"   # weekdays at 4pm CT
    default_parameters = {"period": 14}

    async def generate_signals(self, symbols, parameters, ctx: DataContext) -> list[TradeSignal]:
        signals = []
        for symbol in symbols:
            df = await ctx.get_bars(symbol, "1d", limit=50)
            if df is None or df.empty:
                continue
            # ... your logic ...
            signals.append(TradeSignal(
                symbol=symbol,
                direction="buy",        # "buy" | "sell"
                order_type="market",
                confidence=0.8,
                reasoning="reason string",
            ))
        return signals
```

The strategy is auto-discovered at startup — no registration needed.

## Backtesting

Trigger a backtest via the dashboard or API:

```bash
curl -X POST http://localhost:8000/api/backtests/ \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_crossover",
    "start_date": "2022-01-01",
    "end_date": "2024-12-31",
    "symbols": ["SPY", "QQQ"],
    "initial_capital": 100000
  }'
```

Historical data is cached in PostgreSQL after the first fetch — repeated backtests over the same date range run entirely from local data.

## Docker Deployment

The stack is defined in `docker/docker-compose.yml`: **PostgreSQL**, **FastAPI**, and **nginx** serving the built React app. The DB user, password, and database match the local development example (`cx_user` / `cx_pass` / `pxt`). Postgres is **not** published on the host port `5432` (so it does not conflict with a Postgres you may already run locally); the backend reaches it on the Docker network as hostname `postgres`. To expose `5432` on the host, use `docker/docker-compose.postgres.yml` or add a port mapping only when you need it.

### Start

```bash
cd docker
docker compose up -d --build
```

- **Dashboard (browser):** http://localhost:3000 — nginx proxies `/api/` and `/ws` to the backend container.
- **Backend (direct):** http://localhost:8000 — same API as local `uvicorn`; optional for debugging or `/docs`.

### Environment in containers

Compose sets overrides so in-container networking works; your repo `.env` is still loaded for secrets (`env_file`), but these matter for Docker:

| Variable | Notes |
|----------|--------|
| `DATABASE_URL` | Set in Compose to `postgresql+asyncpg://cx_user:cx_pass@postgres:5432/pxt`. Do **not** use `localhost` as the DB host inside the backend container — use the `postgres` service name (as in Compose). |
| `OLLAMA_BASE_URL` | Set to `http://host.docker.internal:11434` so the backend can reach Ollama on the **host** (Linux uses `extra_hosts: host-gateway`; macOS/Windows Docker Desktop usually resolve `host.docker.internal` without it). |

### Migrations (Alembic)

On a **new** Postgres volume the API will not start until tables exist — run this once before first use (or after pulling new migrations):

```bash
cd docker
docker compose run --rm backend /app/.venv/bin/alembic upgrade head
```

### Optional: Schwab token file

The backend mounts `schwab_token.json` from the repo root. Create an empty file if you do not use Schwab yet: `touch schwab_token.json`.

### Postgres only (without app containers)

```bash
cd docker
docker compose -f docker-compose.postgres.yml up -d
```

Use `DATABASE_URL=postgresql+asyncpg://cx_user:cx_pass@localhost:5432/pxt` on the host.

### Health check

```bash
curl -s http://localhost:3000/api/system/health
curl -s http://localhost:8000/api/system/health
```

## Roadmap

- [ ] Automated trade execution via Schwab API (Phase 2)
- [ ] Options strategy support
- [ ] Strategy discovery from web sources (Phase 2)
- [ ] Multi-market support (crypto, futures)
