# PXT Trading System — Phase D: Backtesting + Signal Processing + API

> **For agentic workers:** Complete Phase C before starting. REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement the backtesting engine (look-ahead safe), LLM evaluator, signal processor with email notifier, and the full FastAPI backend with WebSocket support.

**Tech Stack:** SQLAlchemy async, anthropic/openai SDKs, aiosmtplib, FastAPI WebSocket

---

## File Map

| File | Purpose |
|---|---|
| `backend/src/backtesting/data_context.py` | `BacktestDataContext` — time-sliced, no look-ahead |
| `backend/src/backtesting/engine.py` | Simulation loop, position tracking |
| `backend/src/backtesting/metrics.py` | `BacktestMetrics` dataclass + calculation |
| `backend/src/backtesting/evaluator.py` | `LLMEvaluator` + provider dispatch |
| `backend/src/llm/providers/base.py` | `BaseLLMProvider` ABC |
| `backend/src/llm/providers/claude.py` | Anthropic Claude |
| `backend/src/llm/providers/openai_provider.py` | OpenAI |
| `backend/src/llm/providers/ollama.py` | Ollama (local) |
| `backend/src/signals/notifiers/base.py` | `BaseNotifier` ABC |
| `backend/src/signals/notifiers/email.py` | SMTP email notifier |
| `backend/src/signals/processor.py` | Polls pending signals, dispatches notifiers |
| `backend/src/api/main.py` | FastAPI app + lifespan |
| `backend/src/api/websocket.py` | WebSocket connection manager |
| `backend/src/api/routers/strategies.py` | Strategy CRUD endpoints |
| `backend/src/api/routers/signals.py` | Signal list/detail |
| `backend/src/api/routers/backtests.py` | Trigger + results + drill-down |
| `backend/src/api/routers/system.py` | Health + events |
| `backend/tests/test_backtest_engine.py` | Backtest engine tests |
| `backend/tests/test_api.py` | API smoke tests |

---

## Task 12: Backtest Data Context + Engine

- [ ] **Step 1: Write `backend/src/backtesting/data_context.py`**

```python
from datetime import date, datetime
import pandas as pd
from src.strategies.base import DataContext


class BacktestDataContext(DataContext):
    """
    Injects pre-loaded historical data sliced at current_time.
    Prevents look-ahead: strategy only sees bars with bar_time < current_time.
    Orders fill at next bar's open price (not current close).
    """

    def __init__(
        self,
        data: dict[str, dict[str, pd.DataFrame]],  # {symbol: {timeframe: df}}
        current_time: datetime,
    ):
        self._data = data
        self._current_time = current_time

    def advance(self, new_time: datetime) -> None:
        self._current_time = new_time

    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        df = self._data.get(symbol, {}).get(timeframe)
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        past = df[df.index < self._current_time]
        return past.tail(limit)

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        return pd.DataFrame()  # Historical option chain not available from free sources

    async def get_latest_quote(self, symbol: str) -> dict:
        df = await self.get_bars(symbol, "1d", limit=1)
        if df.empty:
            return {}
        return {"symbol": symbol, "last": float(df["close"].iloc[-1])}
```

- [ ] **Step 2: Write `backend/src/backtesting/metrics.py`**

```python
from dataclasses import dataclass, field
from decimal import Decimal
import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    quantity: float
    entry_time: object
    entry_price: float
    exit_time: object = None
    exit_price: float = None
    exit_reason: str = "end_of_backtest"
    entry_signal: dict = field(default_factory=dict)
    exit_signal: dict = field(default_factory=dict)

    @property
    def pnl(self) -> float | None:
        if self.exit_price is None:
            return None
        multiplier = 1 if self.direction == "buy" else -1
        return multiplier * (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_pct(self) -> float | None:
        if self.exit_price is None or self.entry_price == 0:
            return None
        multiplier = 1 if self.direction == "buy" else -1
        return multiplier * (self.exit_price - self.entry_price) / self.entry_price

    @property
    def hold_days(self) -> float | None:
        if self.exit_time is None:
            return None
        return (self.exit_time - self.entry_time).days


@dataclass
class BacktestMetrics:
    initial_capital: float
    final_equity: float
    trades: list[TradeRecord]
    equity_curve: pd.Series  # index=datetime, values=equity

    @property
    def total_return(self) -> float:
        return (self.final_equity - self.initial_capital) / self.initial_capital

    @property
    def annualized_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        days = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
        if days <= 0:
            return 0.0
        return (1 + self.total_return) ** (365 / days) - 1

    @property
    def sharpe_ratio(self) -> float:
        daily = self.equity_curve.pct_change().dropna()
        if daily.std() == 0:
            return 0.0
        return float(daily.mean() / daily.std() * np.sqrt(252))

    @property
    def max_drawdown(self) -> float:
        rolling_max = self.equity_curve.cummax()
        drawdown = (self.equity_curve - rolling_max) / rolling_max
        return float(drawdown.min())

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.pnl is not None]
        if not closed:
            return 0.0
        winners = sum(1 for t in closed if t.pnl > 0)
        return winners / len(closed)

    @property
    def profit_factor(self) -> float:
        closed = [t for t in self.trades if t.pnl is not None]
        gross_profit = sum(t.pnl for t in closed if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in closed if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def avg_hold_days(self) -> float:
        days = [t.hold_days for t in self.trades if t.hold_days is not None]
        return sum(days) / len(days) if days else 0.0
```

- [ ] **Step 3: Write `backend/src/backtesting/engine.py`**

```python
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
from src.strategies.base import BaseStrategy
from src.backtesting.data_context import BacktestDataContext
from src.backtesting.metrics import BacktestMetrics, TradeRecord


class BacktestEngine:
    def __init__(self, initial_capital: float = 100_000.0):
        self._capital = initial_capital

    async def run(
        self,
        strategy: BaseStrategy,
        symbols: list[str],
        parameters: dict,
        data: dict[str, dict[str, pd.DataFrame]],
        timeframe: str = "1d",
    ) -> BacktestMetrics:
        """
        Simulate strategy on historical data.
        data: {symbol: {timeframe: pd.DataFrame with DatetimeIndex}}
        """
        # Build sorted list of bar timestamps (simulation steps)
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
        positions: dict[str, TradeRecord] = {}  # symbol -> open trade
        closed_trades: list[TradeRecord] = []
        equity_series: dict[datetime, float] = {}

        for i, current_time in enumerate(all_times[:-1]):
            next_time = all_times[i + 1]
            ctx = BacktestDataContext(data, current_time)

            signals = await strategy.generate_signals(symbols, parameters, ctx)

            # Fill orders at next bar's open price
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

                if sig.direction == "buy" and sym not in positions:
                    qty = sig.quantity or max(1, int(cash * 0.1 / fill_price))
                    cost = qty * fill_price
                    if cost <= cash:
                        cash -= cost
                        positions[sym] = TradeRecord(
                            symbol=sym, direction="buy", quantity=qty,
                            entry_time=fill_time, entry_price=fill_price,
                            entry_signal={"reasoning": sig.reasoning},
                        )
                elif sig.direction == "sell" and sym in positions:
                    trade = positions.pop(sym)
                    trade.exit_time = fill_time
                    trade.exit_price = fill_price
                    trade.exit_reason = "signal"
                    cash += trade.quantity * fill_price
                    closed_trades.append(trade)

            # Mark-to-market equity
            portfolio_value = cash
            for sym, trade in positions.items():
                tf_df = data.get(sym, {}).get(timeframe)
                if tf_df is not None:
                    past = tf_df[tf_df.index <= current_time]
                    if not past.empty:
                        portfolio_value += trade.quantity * float(past["close"].iloc[-1])
            equity_series[current_time] = portfolio_value

        # Close open positions at last bar's close
        last_time = all_times[-1]
        for sym, trade in positions.items():
            tf_df = data.get(sym, {}).get(timeframe)
            if tf_df is not None and not tf_df.empty:
                last_price = float(tf_df["close"].iloc[-1])
                cash += trade.quantity * last_price
                trade.exit_time = last_time
                trade.exit_price = last_price
                trade.exit_reason = "end_of_backtest"
                closed_trades.append(trade)

        equity_series[last_time] = cash
        equity_curve = pd.Series(equity_series).sort_index()

        return BacktestMetrics(
            initial_capital=self._capital,
            final_equity=cash,
            trades=closed_trades,
            equity_curve=equity_curve,
        )
```

- [ ] **Step 4: Write `backend/tests/test_backtest_engine.py`**

```python
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from src.backtesting.engine import BacktestEngine
from src.strategies.library.ma_crossover import MovingAverageCrossover


def make_trending_data(symbol="SPY", n=60, trend="up"):
    rng = np.random.default_rng(0)
    if trend == "up":
        prices = np.linspace(100, 150, n) + rng.normal(0, 1, n)
    else:
        prices = np.linspace(150, 100, n) + rng.normal(0, 1, n)
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")
    df = pd.DataFrame({
        "open": prices * 0.99, "high": prices * 1.01,
        "low": prices * 0.98, "close": prices,
        "volume": [10000] * n,
    }, index=idx)
    return {symbol: {"1d": df}}


async def test_backtest_runs_without_error():
    engine = BacktestEngine(initial_capital=10_000)
    strategy = MovingAverageCrossover()
    data = make_trending_data("SPY", 60, "up")
    metrics = await engine.run(strategy, ["SPY"], {"fast": 5, "slow": 20}, data, "1d")
    assert metrics.initial_capital == 10_000
    assert metrics.final_equity > 0
    assert isinstance(metrics.equity_curve, pd.Series)


async def test_backtest_metrics_range():
    engine = BacktestEngine(initial_capital=10_000)
    strategy = MovingAverageCrossover()
    data = make_trending_data("SPY", 60)
    metrics = await engine.run(strategy, ["SPY"], {"fast": 5, "slow": 20}, data, "1d")
    assert -1.0 <= metrics.total_return <= 10.0
    assert 0.0 <= metrics.win_rate <= 1.0
    assert metrics.max_drawdown <= 0.0


async def test_look_ahead_prevention():
    """BacktestDataContext must not return future bars."""
    from src.backtesting.data_context import BacktestDataContext
    idx = pd.date_range("2023-01-02", periods=10, freq="B", tz="UTC")
    df = pd.DataFrame({"open": range(10), "high": range(10), "low": range(10),
                       "close": range(10), "volume": [100] * 10}, index=idx)
    data = {"SPY": {"1d": df}}
    cutoff = idx[4]  # can see bars 0-3 only
    ctx = BacktestDataContext(data, cutoff)
    result = await ctx.get_bars("SPY", "1d", limit=200)
    assert len(result) == 4
    assert all(result.index < cutoff)
```

- [ ] **Step 5: Run backtest tests**

```bash
cd /home/imxichen/projects/pxt/backend
uv run pytest tests/test_backtest_engine.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/backtesting/ backend/tests/test_backtest_engine.py
git commit -m "feat: backtest engine with look-ahead prevention and metrics"
```

---

## Task 13: LLM Providers + Evaluator

- [ ] **Step 1: Write `backend/src/llm/providers/base.py`**

```python
from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Send prompt, return text response."""
```

- [ ] **Step 2: Write `backend/src/llm/providers/claude.py`**

```python
import anthropic
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class ClaudeProvider(BaseLLMProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, prompt: str) -> str:
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
```

- [ ] **Step 3: Write `backend/src/llm/providers/openai_provider.py`**

```python
from openai import AsyncOpenAI
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return response.choices[0].message.content
```

- [ ] **Step 4: Write `backend/src/llm/providers/ollama.py`**

```python
import httpx
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str = "llama3"):
        self._model = model
        self._base_url = settings.ollama_base_url

    async def complete(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["response"]
```

- [ ] **Step 5: Write `backend/src/backtesting/evaluator.py`**

```python
from src.backtesting.metrics import BacktestMetrics
from src.core.config import settings
from src.llm.providers.base import BaseLLMProvider


def _get_provider() -> BaseLLMProvider:
    provider = settings.llm_provider
    if provider == "claude":
        from src.llm.providers.claude import ClaudeProvider
        return ClaudeProvider()
    if provider == "openai":
        from src.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if provider == "ollama":
        from src.llm.providers.ollama import OllamaProvider
        return OllamaProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")


class LLMEvaluator:
    async def evaluate(
        self,
        metrics: BacktestMetrics,
        strategy_name: str,
        strategy_description: str,
    ) -> tuple[str, str]:
        """Returns (evaluation_text, model_name)."""
        provider = _get_provider()
        prompt = f"""You are an expert quantitative analyst. Evaluate the following trading strategy backtest results.

Strategy: {strategy_name}
Description: {strategy_description}

Backtest Results:
- Total Return: {metrics.total_return:.2%}
- Annualized Return: {metrics.annualized_return:.2%}
- Sharpe Ratio: {metrics.sharpe_ratio:.2f}
- Max Drawdown: {metrics.max_drawdown:.2%}
- Win Rate: {metrics.win_rate:.2%}
- Profit Factor: {metrics.profit_factor:.2f}
- Total Trades: {metrics.total_trades}
- Avg Hold Days: {metrics.avg_hold_days:.1f}

Please provide:
1. Overall assessment of the strategy's risk-adjusted performance
2. Notable strengths (if any)
3. Key weaknesses or risks
4. Specific improvement suggestions
5. Verdict: is this strategy worth trading live? (Yes / No / Needs Work)

Be concise and direct. Use bullet points."""
        evaluation = await provider.complete(prompt)
        model_name = settings.llm_provider
        return evaluation, model_name
```

- [ ] **Step 6: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/llm/ backend/src/backtesting/evaluator.py
git commit -m "feat: LLM providers (Claude/OpenAI/Ollama) and backtest evaluator"
```

---

## Task 14: Signal Processor + Email Notifier

- [ ] **Step 1: Write `backend/src/signals/notifiers/base.py`**

```python
from abc import ABC, abstractmethod
from src.core.models import TradeSignalRecord


class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, signal: TradeSignalRecord, instrument_symbol: str) -> bool:
        """Send notification. Returns True on success."""
```

- [ ] **Step 2: Write `backend/src/signals/notifiers/email.py`**

```python
import aiosmtplib
from email.message import EmailMessage
from src.core.config import settings
from src.signals.notifiers.base import BaseNotifier
from src.core.models import TradeSignalRecord


class EmailNotifier(BaseNotifier):
    async def send(self, signal: TradeSignalRecord, instrument_symbol: str) -> bool:
        msg = EmailMessage()
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notify_email
        msg["Subject"] = f"[PXT] {signal.direction.upper()} Signal — {instrument_symbol}"
        direction_emoji = "🟢" if signal.direction == "buy" else "🔴"
        msg.set_content(f"""{direction_emoji} Trade Signal Generated

Symbol:     {instrument_symbol}
Direction:  {signal.direction.upper()}
Order Type: {signal.order_type}
Quantity:   {signal.quantity or 'Not specified'}
Limit:      {signal.limit_price or 'N/A'}
Stop:       {signal.stop_price or 'N/A'}
Confidence: {float(signal.confidence or 0):.0%}
Strategy:   {signal.strategy_id}
Time:       {signal.signal_time}

Reasoning:
{signal.reasoning or 'No reasoning provided.'}

---
This is an automated notification from PXT Trading System.
Do NOT act on this without your own due diligence.
""")
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Email send failed: %s", e)
            return False
```

- [ ] **Step 3: Write `backend/src/signals/processor.py`**

```python
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory
from src.core.models import TradeSignalRecord, Instrument, Option
from src.core.config import settings
from src.signals.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


def _get_notifier() -> BaseNotifier:
    from src.signals.notifiers.email import EmailNotifier
    return EmailNotifier()
    # Phase 2: return SchwabTrader() when settings.notifier == "schwab"


class SignalProcessor:
    async def process_pending(self) -> int:
        """Process all pending signals. Returns count processed."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(TradeSignalRecord)
                .where(TradeSignalRecord.status == "pending")
                .order_by(TradeSignalRecord.created_at)
                .limit(50)
            )
            signals = result.scalars().all()

        processed = 0
        notifier = _get_notifier()
        for signal in signals:
            symbol = await self._get_symbol(signal)
            success = await notifier.send(signal, symbol)
            new_status = "notified" if success else "pending"
            async with async_session_factory() as session:
                await session.execute(
                    update(TradeSignalRecord)
                    .where(TradeSignalRecord.id == signal.id)
                    .values(status=new_status)
                )
                await session.commit()
            if success:
                processed += 1
                logger.info("Signal %d notified for %s", signal.id, symbol)
        return processed

    async def _get_symbol(self, signal: TradeSignalRecord) -> str:
        async with async_session_factory() as session:
            if signal.stock_id:
                result = await session.execute(
                    select(Instrument.symbol).where(Instrument.id == signal.stock_id)
                )
                return result.scalar_one_or_none() or "UNKNOWN"
            if signal.option_id:
                result = await session.execute(
                    select(Option.symbol).where(Option.id == signal.option_id)
                )
                return result.scalar_one_or_none() or "UNKNOWN"
        return "UNKNOWN"
```

- [ ] **Step 4: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/signals/ 
git commit -m "feat: signal processor and email notifier"
```

---

## Task 15: FastAPI App + All Routers

- [ ] **Step 1: Write `backend/src/api/websocket.py`**

```python
import asyncio
import json
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def broadcast(self, channel: str, data: dict) -> None:
        message = json.dumps({"channel": channel, "data": data})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


ws_manager = WebSocketManager()
```

- [ ] **Step 2: Write `backend/src/api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.api.websocket import ws_manager
from src.api.routers import strategies, signals, backtests, system
from src.scheduler.runner import StrategyScheduler

_scheduler: StrategyScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    _scheduler = StrategyScheduler()
    await _scheduler.start()
    app.state.scheduler = _scheduler
    yield
    await _scheduler.stop()


app = FastAPI(title="PXT Trading System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(system.router, prefix="/api/system", tags=["system"])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
```

- [ ] **Step 3: Write `backend/src/api/routers/strategies.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import Strategy

router = APIRouter()


class StrategyUpdate(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    run_frequency: str | None = None
    parameters: dict | None = None
    is_active: bool | None = None
    max_symbols: int | None = None


@router.get("/")
async def list_strategies(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.name))
    strategies = result.scalars().all()
    return [
        {
            "id": s.id, "name": s.name, "description": s.description,
            "is_active": s.is_active, "symbols": s.symbols,
            "timeframes": s.timeframes, "run_frequency": s.run_frequency,
            "parameters": s.parameters, "max_symbols": s.max_symbols,
        }
        for s in strategies
    ]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")
    return {"id": s.id, "name": s.name, "description": s.description,
            "is_active": s.is_active, "symbols": s.symbols,
            "timeframes": s.timeframes, "run_frequency": s.run_frequency,
            "parameters": s.parameters, "max_symbols": s.max_symbols}


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update.")
    if "symbols" in updates and len(updates["symbols"]) > 50:
        raise HTTPException(400, "Exceeds max_symbols limit.")
    await session.execute(
        update(Strategy).where(Strategy.id == strategy_id).values(**updates)
    )
    await session.commit()
    # Hot-reload scheduler job
    from src.api.main import _scheduler
    if _scheduler:
        await _scheduler.reload_strategy(strategy_id)
    return {"ok": True}
```

- [ ] **Step 4: Write `backend/src/api/routers/signals.py`**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import TradeSignalRecord

router = APIRouter()


@router.get("/")
async def list_signals(
    strategy_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = select(TradeSignalRecord).order_by(desc(TradeSignalRecord.created_at))
    if strategy_id:
        query = query.where(TradeSignalRecord.strategy_id == strategy_id)
    if status:
        query = query.where(TradeSignalRecord.status == status)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    signals = result.scalars().all()
    return [
        {
            "id": s.id, "strategy_id": s.strategy_id,
            "stock_id": s.stock_id, "option_id": s.option_id,
            "signal_time": s.signal_time, "direction": s.direction,
            "quantity": float(s.quantity) if s.quantity else None,
            "order_type": s.order_type,
            "limit_price": float(s.limit_price) if s.limit_price else None,
            "confidence": float(s.confidence) if s.confidence else None,
            "reasoning": s.reasoning, "status": s.status,
            "created_at": s.created_at,
        }
        for s in signals
    ]


@router.get("/{signal_id}")
async def get_signal(signal_id: int, session: AsyncSession = Depends(get_session)):
    from fastapi import HTTPException
    result = await session.execute(
        select(TradeSignalRecord).where(TradeSignalRecord.id == signal_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Signal not found.")
    return {
        "id": s.id, "strategy_id": s.strategy_id,
        "stock_id": s.stock_id, "option_id": s.option_id,
        "signal_time": s.signal_time, "direction": s.direction,
        "quantity": float(s.quantity) if s.quantity else None,
        "order_type": s.order_type,
        "limit_price": float(s.limit_price) if s.limit_price else None,
        "stop_price": float(s.stop_price) if s.stop_price else None,
        "confidence": float(s.confidence) if s.confidence else None,
        "reasoning": s.reasoning, "status": s.status,
        "metadata": s.metadata_, "created_at": s.created_at,
    }
```

- [ ] **Step 5: Write `backend/src/api/routers/backtests.py`**

```python
import asyncio
from datetime import date
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session, async_session_factory
from src.core.models import Backtest, BacktestTrade, BacktestEquityCurve

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_id: str
    start_date: date
    end_date: date
    symbols: list[str]
    initial_capital: float = 100_000.0
    parameters: dict = {}


@router.get("/")
async def list_backtests(
    strategy_id: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    query = select(Backtest).order_by(desc(Backtest.created_at)).limit(limit)
    if strategy_id:
        query = query.where(Backtest.strategy_id == strategy_id)
    result = await session.execute(query)
    return [_backtest_summary(b) for b in result.scalars().all()]


@router.post("/")
async def trigger_backtest(
    req: BacktestRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    bt = Backtest(
        strategy_id=req.strategy_id,
        start_date=req.start_date,
        end_date=req.end_date,
        symbols=req.symbols,
        initial_capital=req.initial_capital,
        parameters=req.parameters,
        status="running",
    )
    session.add(bt)
    await session.commit()
    await session.refresh(bt)
    background_tasks.add_task(_run_backtest, bt.id, req)
    return {"id": bt.id, "status": "running"}


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Backtest).where(Backtest.id == backtest_id))
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(404, "Backtest not found.")
    return _backtest_summary(bt)


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: int,
    sort_by: str = "entry_time",
    order: str = "asc",
    session: AsyncSession = Depends(get_session),
):
    col = getattr(BacktestTrade, sort_by, BacktestTrade.entry_time)
    direction = col.asc() if order == "asc" else col.desc()
    result = await session.execute(
        select(BacktestTrade)
        .where(BacktestTrade.backtest_id == backtest_id)
        .order_by(direction)
    )
    trades = result.scalars().all()
    return [
        {
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "quantity": float(t.quantity), "entry_time": t.entry_time,
            "entry_price": float(t.entry_price),
            "exit_time": t.exit_time,
            "exit_price": float(t.exit_price) if t.exit_price else None,
            "pnl": float(t.pnl) if t.pnl else None,
            "pnl_pct": float(t.pnl_pct) if t.pnl_pct else None,
            "hold_days": float(t.hold_days) if t.hold_days else None,
            "exit_reason": t.exit_reason,
            "entry_signal": t.entry_signal,
        }
        for t in trades
    ]


@router.get("/{backtest_id}/equity")
async def get_equity_curve(backtest_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(BacktestEquityCurve)
        .where(BacktestEquityCurve.backtest_id == backtest_id)
        .order_by(BacktestEquityCurve.ts)
    )
    points = result.scalars().all()
    return [
        {"ts": p.ts, "equity": float(p.equity),
         "cash": float(p.cash), "drawdown": float(p.drawdown) if p.drawdown else None}
        for p in points
    ]


def _backtest_summary(bt: Backtest) -> dict:
    return {
        "id": bt.id, "strategy_id": bt.strategy_id,
        "start_date": bt.start_date, "end_date": bt.end_date,
        "symbols": bt.symbols, "initial_capital": float(bt.initial_capital),
        "status": bt.status,
        "total_return": float(bt.total_return) if bt.total_return else None,
        "annualized_return": float(bt.annualized_return) if bt.annualized_return else None,
        "sharpe_ratio": float(bt.sharpe_ratio) if bt.sharpe_ratio else None,
        "max_drawdown": float(bt.max_drawdown) if bt.max_drawdown else None,
        "win_rate": float(bt.win_rate) if bt.win_rate else None,
        "profit_factor": float(bt.profit_factor) if bt.profit_factor else None,
        "total_trades": bt.total_trades,
        "avg_hold_days": float(bt.avg_hold_days) if bt.avg_hold_days else None,
        "llm_evaluation": bt.llm_evaluation,
        "llm_model": bt.llm_model,
        "created_at": bt.created_at, "completed_at": bt.completed_at,
    }


async def _run_backtest(backtest_id: int, req: BacktestRequest):
    """Background task: fetch data, run engine, save results."""
    from datetime import datetime, timezone
    from src.backtesting.engine import BacktestEngine
    from src.backtesting.evaluator import LLMEvaluator
    from src.data.providers.yfinance_provider import YFinanceProvider
    from src.strategies.registry import REGISTRY, discover_strategies
    from src.core.models import BacktestTrade as BtTrade, BacktestEquityCurve as BtEquity
    discover_strategies()
    try:
        provider = YFinanceProvider()
        start = datetime(req.start_date.year, req.start_date.month, req.start_date.day)
        end = datetime(req.end_date.year, req.end_date.month, req.end_date.day)
        data: dict = {}
        for sym in req.symbols:
            df = await provider.get_bars(sym, "1d", start, end)
            if not df.empty:
                data[sym] = {"1d": df}
        if not data:
            raise ValueError("No data fetched for any symbol.")
        strategy = REGISTRY[req.strategy_id]()
        engine = BacktestEngine(initial_capital=req.initial_capital)
        metrics = await engine.run(strategy, req.symbols, req.parameters, data, "1d")
        evaluator = LLMEvaluator()
        llm_text, llm_model = await evaluator.evaluate(metrics, strategy.name, strategy.description)
        async with async_session_factory() as session:
            # Save trade records
            for t in metrics.trades:
                session.add(BtTrade(
                    backtest_id=backtest_id, symbol=t.symbol, direction=t.direction,
                    quantity=t.quantity, entry_time=t.entry_time, entry_price=t.entry_price,
                    exit_time=t.exit_time, exit_price=t.exit_price,
                    pnl=t.pnl, pnl_pct=t.pnl_pct, hold_days=t.hold_days,
                    exit_reason=t.exit_reason, entry_signal=t.entry_signal,
                ))
            # Save equity curve
            for ts, equity in metrics.equity_curve.items():
                session.add(BtEquity(
                    backtest_id=backtest_id, ts=ts,
                    equity=equity, cash=equity, drawdown=None,
                ))
            # Update backtest summary
            from sqlalchemy import update
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(
                    status="completed",
                    total_return=metrics.total_return,
                    annualized_return=metrics.annualized_return,
                    sharpe_ratio=metrics.sharpe_ratio,
                    max_drawdown=metrics.max_drawdown,
                    win_rate=metrics.win_rate,
                    profit_factor=metrics.profit_factor if metrics.profit_factor != float("inf") else None,
                    total_trades=metrics.total_trades,
                    avg_hold_days=metrics.avg_hold_days,
                    llm_evaluation=llm_text,
                    llm_model=llm_model,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as e:
        async with async_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Backtest).where(Backtest.id == backtest_id).values(
                    status="failed", error_message=str(e)
                )
            )
            await session.commit()
```

- [ ] **Step 6: Write `backend/src/api/routers/system.py`**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import SystemEvent

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/events")
async def list_events(
    level: str | None = None,
    event_type: str | None = None,
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_session),
):
    query = select(SystemEvent).order_by(desc(SystemEvent.created_at)).limit(limit)
    if level:
        query = query.where(SystemEvent.level == level)
    if event_type:
        query = query.where(SystemEvent.event_type == event_type)
    result = await session.execute(query)
    events = result.scalars().all()
    return [
        {"id": e.id, "event_type": e.event_type, "level": e.level,
         "message": e.message, "details": e.details, "created_at": e.created_at}
        for e in events
    ]
```

- [ ] **Step 7: Verify backend starts**

```bash
cd /home/imxichen/projects/pxt/backend
uv run uvicorn src.api.main:app --reload --port 8000
```

Expected: Server starts, no import errors. Visit `http://localhost:8000/api/system/health` → `{"status":"ok"}`.

- [ ] **Step 8: Commit**

```bash
cd /home/imxichen/projects/pxt
git add backend/src/api/
git commit -m "feat: FastAPI app with all routers and WebSocket support"
```

---

**Phase D complete.** Continue with Phase E: `2026-04-17-trading-system-phase-e.md`
