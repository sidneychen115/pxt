# User Profile & Multi-Tenant Trading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user isolation (`cx`, `cc`) with login/switch, per-user strategy subscriptions, position ledger with manual signal execution, position-aware signal filtering, and scoped dashboard/signals/backtests/positions UI.

**Architecture:** New SQL tables (`users`, `user_strategies`, `user_positions`, `position_fills`) + `user_id` on existing signal/backtest tables. FastAPI dependency resolves current user from `X-User-Id` header (frontend mirrors in `localStorage`). Scheduler registers jobs per `(user_id, strategy_id)` from `user_strategies`. Shared `positions/service.py` handles fills, weighted average cost, and pre-insert signal filtering.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, pytest, React 18 + Vite + TanStack Query + axios

**Spec:** [../specs/2026-05-15-user-profile-design.md](../specs/2026-05-15-user-profile-design.md)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/core/models.py` | Modify | `User`, `UserStrategy`, `UserPosition`, `PositionFill`; `user_id` on signals/backtests/presets |
| `backend/alembic/versions/…_user_profile.py` | Create | Schema + seed users + migrate data to `cc` |
| `backend/src/positions/service.py` | Create | Fills, net position, summary, signal filter |
| `backend/src/positions/__init__.py` | Create | Package export |
| `backend/src/api/deps.py` | Create | `get_current_user`, optional user for health |
| `backend/src/api/routers/auth.py` | Create | List users, session probe |
| `backend/src/api/routers/me_strategies.py` | Create | CRUD user strategies + pool list |
| `backend/src/api/routers/me_positions.py` | Create | List positions + summary |
| `backend/src/api/routers/signals.py` | Modify | Scope by user; `POST /{id}/execute` |
| `backend/src/api/routers/strategies.py` | Modify | Pool-only catalog (read) |
| `backend/src/api/routers/backtests.py` | Modify | Scope create/list by user |
| `backend/src/api/routers/backtest_presets.py` | Modify | Scope by user |
| `backend/src/api/main.py` | Modify | Routers, CORS header `X-User-Id` |
| `backend/src/scheduler/runner.py` | Modify | Load `user_strategies`, job id per user |
| `backend/tests/test_positions.py` | Create | Position math + filter |
| `backend/tests/test_auth_api.py` | Create | 401 without header |
| `backend/tests/test_signal_execute.py` | Create | Execute buy/sell rules |
| `frontend/src/context/AuthContext.tsx` | Create | user id, setUser, localStorage |
| `frontend/src/api/client.ts` | Modify | Attach `X-User-Id` interceptor |
| `frontend/src/api/auth.ts` | Create | fetch users, session |
| `frontend/src/api/meStrategies.ts` | Create | User strategy APIs |
| `frontend/src/api/positions.ts` | Create | Positions APIs |
| `frontend/src/pages/Login.tsx` | Create | User picker |
| `frontend/src/pages/Positions.tsx` | Create | Holdings table |
| `frontend/src/pages/Dashboard.tsx` | Modify | Summary metrics + limit 3 signals |
| `frontend/src/pages/Signals.tsx` | Modify | Execute modal |
| `frontend/src/pages/Strategies.tsx` | Modify | My strategies + add from pool |
| `frontend/src/components/Layout.tsx` | Modify | User switcher, Positions nav |
| `frontend/src/App.tsx` | Modify | Routes, auth guard |

---

## Task 1: Database models & Alembic migration

**Files:**
- Modify: `backend/src/core/models.py`
- Create: `backend/alembic/versions/<rev>_user_profile.py`

- [ ] **Step 1: Add models to `models.py`**

Add after existing imports / before or after `Strategy`:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class UserStrategy(Base):
    __tablename__ = "user_strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(50), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    run_frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_symbols: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "strategy_id", name="uq_user_strategy"),)


class UserPosition(Base):
    __tablename__ = "user_positions"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class PositionFill(Base):
    __tablename__ = "position_fills"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.id"), nullable=False)
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("trade_signals.id", ondelete="SET NULL"))
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy | sell
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
```

Add to `TradeSignalRecord`, `Backtest`, `BacktestPreset` (find class in same file):

```python
user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
```

(Nullable only in migration before backfill; model can use nullable=False after migration applied.)

- [ ] **Step 2: Generate migration**

Run from `backend/`:

```bash
uv run alembic revision -m "user_profile"
```

Edit the new revision:

1. `op.create_table('users', …)`
2. `op.execute("INSERT INTO users (username) VALUES ('cx'), ('cc')")` — capture ids via subquery in later steps
3. `op.create_table('user_strategies', …)`
4. `op.create_table('user_positions', …)`
5. `op.create_table('position_fills', …)`
6. Add `user_id` nullable to `trade_signals`, `backtests`, `backtest_presets`
7. Backfill: `UPDATE … SET user_id = (SELECT id FROM users WHERE username = 'cc')`
8. Copy strategies → user_strategies for cc:

```sql
INSERT INTO user_strategies (user_id, strategy_id, symbols, timeframes, run_frequency, parameters, is_active, max_symbols, updated_at)
SELECT u.id, s.id, s.symbols, s.timeframes, s.run_frequency, s.parameters, s.is_active, s.max_symbols, s.updated_at
FROM strategies s
CROSS JOIN users u WHERE u.username = 'cc';
```

9. `ALTER COLUMN user_id SET NOT NULL` + FK on three tables
10. `downgrade()` reverses in safe order

- [ ] **Step 3: Apply migration locally**

```bash
cd backend && uv run alembic upgrade head
```

Expected: tables exist; `\d user_strategies` shows rows for cc only.

- [ ] **Step 4: Commit**

```bash
git add backend/src/core/models.py backend/alembic/versions/*_user_profile.py
git commit -m "feat(db): add users, user_strategies, positions, user_id columns"
```

---

## Task 2: Position service + signal filter (TDD)

**Files:**
- Create: `backend/src/positions/service.py`
- Create: `backend/tests/test_positions.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_positions.py
from decimal import Decimal
import pytest
from src.positions.service import apply_fill, filter_signals_for_positions, position_summary_from_rows

def test_apply_fill_buy_weighted_avg():
    qty, avg = apply_fill(None, "buy", Decimal("10"), Decimal("100"))
    assert qty == Decimal("10") and avg == Decimal("100")
    qty2, avg2 = apply_fill((qty, avg), "buy", Decimal("10"), Decimal("120"))
    assert qty2 == Decimal("20") and avg2 == Decimal("110")

def test_apply_fill_sell_partial():
    qty, avg = apply_fill((Decimal("20"), Decimal("100")), "sell", Decimal("5"), Decimal("110"))
    assert qty == Decimal("15") and avg == Decimal("100")

def test_filter_drops_buy_when_holding():
    positions = {"AAPL": Decimal("1")}
    signals = [{"symbol": "AAPL", "direction": "buy"}, {"symbol": "MSFT", "direction": "buy"}]
    out = filter_signals_for_positions(signals, positions)
    assert len(out) == 1 and out[0]["symbol"] == "MSFT"

def test_filter_drops_sell_when_flat():
    positions = {"AAPL": Decimal("1")}
    signals = [{"symbol": "AAPL", "direction": "sell"}, {"symbol": "MSFT", "direction": "sell"}]
    out = filter_signals_for_positions(signals, positions)
    assert len(out) == 1 and out[0]["symbol"] == "AAPL"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/test_positions.py -v
```

- [ ] **Step 3: Implement `service.py`**

```python
from decimal import Decimal
from typing import Any

def apply_fill(
    current: tuple[Decimal, Decimal] | None,
    side: str,
    quantity: Decimal,
    fill_price: Decimal,
) -> tuple[Decimal, Decimal]:
    if quantity <= 0 or fill_price <= 0:
        raise ValueError("quantity and fill_price must be positive")
    if side == "buy":
        if current is None:
            return quantity, fill_price
        q0, a0 = current
        new_q = q0 + quantity
        new_avg = (q0 * a0 + quantity * fill_price) / new_q
        return new_q, new_avg
    if side == "sell":
        if current is None:
            raise ValueError("no position to sell")
        q0, a0 = current
        if quantity > q0:
            raise ValueError("sell quantity exceeds position")
        return q0 - quantity, a0
    raise ValueError(f"invalid side: {side}")

def filter_signals_for_positions(
    signals: list[Any],
    positions_by_symbol: dict[str, Decimal],
) -> list[Any]:
    out = []
    for sig in signals:
        sym = sig.symbol if hasattr(sig, "symbol") else sig["symbol"]
        direction = sig.direction if hasattr(sig, "direction") else sig["direction"]
        qty = positions_by_symbol.get(sym, Decimal(0))
        if direction == "buy" and qty > 0:
            continue
        if direction == "sell" and qty <= 0:
            continue
        out.append(sig)
    return out

def position_summary_from_rows(rows: list[tuple[Decimal, Decimal, Decimal | None]]) -> dict:
    """rows: (quantity, avg_cost, mark_price|None) per symbol."""
    open_symbols = sum(1 for q, _, _ in rows if q > 0)
    total_shares = sum(q for q, _, _ in rows if q > 0)
    value = Decimal(0)
    for q, avg, mark in rows:
        if q <= 0:
            continue
        px = mark if mark is not None else avg
        value += q * px
    return {
        "open_symbols": open_symbols,
        "total_shares": float(total_shares),
        "position_value": float(value),
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && uv run pytest tests/test_positions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/positions/ backend/tests/test_positions.py
git commit -m "feat: position fill math and signal filtering helpers"
```

---

## Task 3: API auth dependency & auth router

**Files:**
- Create: `backend/src/api/deps.py`
- Create: `backend/src/api/routers/auth.py`
- Modify: `backend/src/api/main.py`
- Create: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Implement `deps.py`**

```python
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models import User

async def get_current_user(
    session: AsyncSession,
    x_user_id: int | None = Header(None, alias="X-User-Id"),
) -> User:
    if x_user_id is None:
        raise HTTPException(401, "Missing X-User-Id header.")
    result = await session.execute(select(User).where(User.id == x_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Invalid user.")
    return user
```

Use pattern in routers:

```python
from fastapi import Depends
from src.api.deps import get_current_user
from src.core.database import get_session

async def list_signals(..., user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
```

Note: combine deps with a small wrapper if needed:

```python
async def current_user_dep(
    session: AsyncSession = Depends(get_session),
    x_user_id: int | None = Header(None, alias="X-User-Id"),
) -> User:
    return await get_current_user(session, x_user_id)
```

- [ ] **Step 2: Auth router (no password)**

```python
# backend/src/api/routers/auth.py
@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).order_by(User.username))
    return [{"id": u.id, "username": u.username} for u in result.scalars()]

@router.get("/session")
async def get_session_user(user: User = Depends(current_user_dep)):
    return {"id": user.id, "username": user.username}
```

Mount at `prefix="/api/auth"` **without** user dependency on `/users` and optionally allow `GET /api/system/health` without auth (already on system router).

- [ ] **Step 3: Update CORS in `main.py`**

```python
allow_headers=["*", "X-User-Id"],
```

- [ ] **Step 4: Test 401**

```python
# test_auth_api.py — use httpx AsyncClient with app
async def test_signals_require_user(client):
    r = await client.get("/api/signals/")
    assert r.status_code == 401
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/deps.py backend/src/api/routers/auth.py backend/src/api/main.py backend/tests/test_auth_api.py
git commit -m "feat(api): auth users list and X-User-Id dependency"
```

---

## Task 4: User strategies API (pool + me)

**Files:**
- Modify: `backend/src/api/routers/strategies.py` — pool catalog only
- Create: `backend/src/api/routers/me_strategies.py`
- Create: `backend/src/api/routers/me_strategies_serialize.py` (optional helper)

- [ ] **Step 1: Change `GET /api/strategies/`** to return pool rows (all `strategies` table) without user fields; document as catalog. Remove or deprecate `PUT /{id}` on global strategies (pool metadata is read-only in UI; user edits go to me).

- [ ] **Step 2: `me_strategies` router**

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/api/me/strategies` | List current user's `user_strategies` joined with pool name |
| POST | `/api/me/strategies` | Body `{ strategy_id }` — copy defaults from pool row + strategy class defaults |
| PUT | `/api/me/strategies/{id}` | Update symbols, timeframes, run_frequency, parameters, is_active, max_symbols |
| DELETE | `/api/me/strategies/{id}` | Remove subscription |

On POST conflict `uq_user_strategy` → 409.

- [ ] **Step 3: After PUT/POST/DELETE call scheduler reload**

Reuse existing `request.app.state.scheduler.reload_strategy` — extend signature to `reload_user_strategy(user_id: int, strategy_id: str)` that removes job `strategy_{user_id}_{strategy_id}` and re-adds if active.

- [ ] **Step 4: Manual test**

```bash
curl -H "X-User-Id: 1" http://localhost:8000/api/me/strategies
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): per-user strategy subscriptions and pool catalog"
```

---

## Task 5: Positions API

**Files:**
- Create: `backend/src/api/routers/me_positions.py`

- [ ] **Step 1: `GET /api/me/positions/summary`**

Query `user_positions` join `instruments`; for mark price use latest `ohlcv_bars.close` for `1d` or `get_latest_quote` only if already used elsewhere — **YAGNI:** use `avg_cost` as mark when no bar (per spec).

Return `position_summary_from_rows(...)`.

- [ ] **Step 2: `GET /api/me/positions`**

Return list: `symbol`, `quantity`, `avg_cost`, `mark_price`, `market_value`, `updated_at`.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): position list and dashboard summary"
```

---

## Task 6: Signal execute + user scope on signals

**Files:**
- Modify: `backend/src/api/routers/signals.py`
- Create: `backend/tests/test_signal_execute.py`

- [ ] **Step 1: Add `user_id` filter** to all queries: `.where(TradeSignalRecord.user_id == user.id)`.

- [ ] **Step 2: `POST /api/signals/{signal_id}/execute`**

Body: `{ "quantity": number, "fill_price": number }`

Logic:
1. Load signal for `user.id`; 404 if missing
2. If `status == "executed"` → 409
3. If `status` not in `pending`, `notified` → 400
4. Resolve `instrument_id` from `stock_id`
5. Load/create `UserPosition`
6. `side = "buy" if signal.direction == "buy" else "sell"`
7. `apply_fill(...)`; on ValueError → 400
8. Insert `PositionFill`; upsert `UserPosition`; set signal `status = "executed"`
9. Commit

- [ ] **Step 3: Tests with session fixture** — seed user, instrument, signal; execute buy then assert position; execute sell partial.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(api): user-scoped signals and manual execute"
```

---

## Task 7: Backtests & presets user scope

**Files:**
- Modify: `backend/src/api/routers/backtests.py`
- Modify: `backend/src/api/routers/backtest_presets.py`

- [ ] **Step 1: Inject `current_user_dep` on list/create/get/delete**

- [ ] **Step 2: `BacktestRequest` create** — set `user_id=user.id` on insert

- [ ] **Step 3: Verify backtest background task still works** (no user change in engine)

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(api): scope backtests and presets by user"
```

---

## Task 8: Scheduler multi-user + signal filter

**Files:**
- Modify: `backend/src/scheduler/runner.py`

- [ ] **Step 1: Replace `_register_all_jobs` strategy loop**

```python
select(UserStrategy).where(UserStrategy.is_active.is_(True))
```

For each row, job id = `f"strategy_{us.user_id}_{us.strategy_id}"`, kwargs `user_id`, `strategy_id`.

- [ ] **Step 2: `_run_strategy(self, user_id: int, strategy_id: str)`**

Load `UserStrategy` + verify REGISTRY; build params from user row; load positions map:

```python
positions = await load_positions_by_symbol(session, user_id)
```

After `generate_signals`, filter:

```python
from src.positions.service import filter_signals_for_positions
signals = filter_signals_for_positions(signals, positions)
```

- [ ] **Step 3: `_save_signals`** — pass `user_id`; set on each `TradeSignalRecord`.

- [ ] **Step 4: `reload_strategy` → `reload_user_strategy(user_id, strategy_id)`** — update strategies router / me_strategies to call new method.

- [ ] **Step 5: Integration smoke** — two users, same strategy_id, different symbols in DB; run job manually or wait for schedule; signals have correct `user_id`.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(scheduler): per-user strategy jobs and position-aware signal filter"
```

---

## Task 9: Frontend auth layer

**Files:**
- Create: `frontend/src/context/AuthContext.tsx`
- Create: `frontend/src/api/auth.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: AuthContext**

```tsx
const STORAGE_KEY = 'pxt_user_id'
// state: userId, username, setUser(id, name), clearUser()
// hydrate from localStorage on mount
```

- [ ] **Step 2: axios interceptor**

```typescript
client.interceptors.request.use((config) => {
  const id = localStorage.getItem('pxt_user_id')
  if (id) config.headers['X-User-Id'] = id
  return config
})
```

- [ ] **Step 3: Login page** — fetch `/api/auth/users`, buttons for each user → `setUser` → `navigate('/dashboard')`

- [ ] **Step 4: Protected routes wrapper** — if no userId, `<Navigate to="/login" />`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(frontend): login and X-User-Id auth context"
```

---

## Task 10: Layout user switcher + Positions page

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/pages/Positions.tsx`
- Create: `frontend/src/api/positions.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Nav** — add Positions (`/positions`, Wallet icon)

- [ ] **Step 2: Header area** — show `username`; dropdown "Switch user" → navigate `/login` or inline modal listing users (same as login API)

- [ ] **Step 3: Positions page** — `useQuery` `GET /api/me/positions`; read-only table

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(frontend): positions page and user switcher"
```

---

## Task 11: Dashboard redesign (summary + 3 signals)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/api/signals.ts` (if needed — pass `limit: 3`)

- [ ] **Step 1: Fetch `GET /api/me/positions/summary`** — three metric cards: Open Symbols, Total Shares, Position Value

- [ ] **Step 2: Active strategies** — `fetchMeStrategies` filtered `is_active`

- [ ] **Step 3: Recent signals** — `fetchSignals({ limit: 3 })` only; add link to `/signals`

- [ ] **Step 4: Layout** — reduce signal card padding; remove extra empty list height; leave `min-h` section for future widgets

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(frontend): dashboard position summary and max 3 signals"
```

---

## Task 12: Strategies page (my list + pool)

**Files:**
- Modify: `frontend/src/pages/Strategies.tsx`
- Create: `frontend/src/api/meStrategies.ts`

- [ ] **Step 1: Split UI** — section "My strategies" (editable like today); section "Add from pool" listing catalog strategies not yet subscribed

- [ ] **Step 2: Wire PUT/DELETE/POST to `/api/me/strategies`**

- [ ] **Step 3: Remove editing global pool** (no PUT to `/api/strategies/{id}` from UI)

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(frontend): per-user strategy management"
```

---

## Task 13: Signals execute UI

**Files:**
- Modify: `frontend/src/pages/Signals.tsx`

- [ ] **Step 1: Modal component** `ExecuteSignalModal` — fields quantity (number), fill_price (number); title 开仓 vs 平仓 from direction

- [ ] **Step 2: Show button** only when `status` in `pending` | `notified` and direction buy/sell

- [ ] **Step 3: `POST /api/signals/{id}/execute`** on submit; invalidate `signals` and `positions` queries

- [ ] **Step 4: Error toast** for 400/409 messages

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(frontend): manual open/close from signals"
```

---

## Task 14: Backtests pages user scope

**Files:**
- Modify: `frontend/src/pages/Backtests.tsx`, `BacktestPresets.tsx` if they pass user implicitly via header only — no code change if API scoped

- [ ] **Step 1: Smoke test** — login as cx vs cc see different backtest lists

- [ ] **Step 2: Commit** (only if fixes needed)

---

## Task 15: End-to-end verification

- [ ] **Step 1: Run backend tests**

```bash
cd backend && uv run pytest tests/test_positions.py tests/test_auth_api.py tests/test_signal_execute.py -v
```

- [ ] **Step 2: Manual checklist**

| Step | Action |
|------|--------|
| 1 | Login as `cc` — see migrated strategies/signals/backtests |
| 2 | Login as `cx` — empty strategies; add one from pool |
| 3 | Run strategy or wait — signal has `user_id` |
| 4 | Execute buy on signal — position appears on `/positions` and dashboard summary |
| 5 | Next run — no duplicate buy for same symbol |
| 6 | Execute sell — partial OK; signal executed |
| 7 | Switch user — data changes |
| 8 | Dashboard shows ≤3 signals |

- [ ] **Step 3: Update spec status** (optional) — mark implementation complete in spec

---

## Spec Coverage Checklist

| Spec section | Task |
|--------------|------|
| Users cx/cc seed | Task 1 |
| Login + switch | Tasks 3, 9, 10 |
| user_strategies pool model | Tasks 1, 4, 8, 12 |
| Manual execute + fills | Tasks 2, 6, 13 |
| Position filter | Tasks 2, 8 |
| Migrate data to cc | Task 1 |
| Dashboard summary + 3 signals | Task 11 |
| /positions page | Task 10 |
| Backtests/presets scope | Task 7, 14 |
| System global | No change |
| Phase 2 auto trade | Out of scope |

---

## Migration Reminder (for operator)

After pulling:

```bash
cd backend && uv run alembic upgrade head
```

Restart backend (scheduler reload). Frontend hard refresh if needed.
