# User Profile & Multi-Tenant Trading Design

**Date:** 2026-05-15  
**Project:** pxt — Personal Stock Trading System  
**Status:** Approved (requirements confirmed in chat)

---

## 1. Overview

Introduce **users** so two traders (`cx`, `cc`) can share one deployment with isolated strategy configs, signals, backtests, and live position books. Authentication is intentionally minimal: pick a user from a list (no password, no registration).

**Phase 1 (this spec):** users, login/switch, per-user strategy pool, scheduler + signals scoped by user, manual open/close from signals, position-aware signal filtering, positions UI, data migration.

**Phase 2 (out of scope):** Schwab auto-execution and automatic position recording on broker fill.

---

## 2. Goals & Non-Goals

### Goals

- Seed users `cx` and `cc`; login page for first visit; **switch user anytime** from chrome (header/sidebar).
- Global **strategy pool** (`strategies` table) + per-user **subscriptions** (`user_strategies`) with independent `symbols`, `timeframes`, `parameters`, `is_active`.
- Scheduler runs only active **(user_id, strategy_id)** pairs using that user's config.
- `trade_signals` and `backtests` (and `backtest_presets`) scoped by `user_id`.
- **Manual** position ledger: execute buy/sell signals with share count + fill price; update net positions; mark signal `executed`.
- **Filter** generated signals using user's net position per symbol before insert.
- Dashboard: read-only **position summary** + **at most 3** recent signals; full signal list on `/signals`.
- Dedicated **`/positions`** route for full holdings table (read-only).

### Non-Goals (Phase 1)

- Passwords, registration, roles/permissions.
- Options positions or short selling.
- Auto-recording positions when signals are generated or emailed.
- Broker integration (Schwab execute).
- Chinese display names for users.
- Editing positions directly on Dashboard (summary is read-only).

---

## 3. Confirmed Requirements (Decision Log)

| ID | Topic | Decision |
|----|--------|----------|
| Q1 | Strategy model | **A:** Global pool + `user_strategies` with per-user config |
| Q3 | Position granularity | **A:** Aggregate by `user_id + symbol` (across strategies) |
| Q4 | Auto record positions | **C:** Manual only in Phase 1; auto on broker fill in Phase 2 |
| Q5 | Legacy data | **B:** Existing signals/backtests → `cc`; `cx` starts empty |
| Q6 | Signal execution | **A:** One-shot per signal → `executed`; buy=开仓, sell=平仓; require **shares + fill price** |
| Q7 | Instruments | **A:** US stocks/ETFs long only; partial close allowed; weighted average cost |
| UI | User switch | Anytime via UI; no logout required to switch |
| UI | Positions | **P:** `/positions` full table; Dashboard summary only |
| UI | Dashboard signals | **Max 3** recent signals; more vertical space for stats / future widgets |
| UI | Display names | Username only (`cx`, `cc`) |

---

## 4. Architecture

### 4.1 High-Level Flow

```
Login / Switch User → session stores user_id
        ↓
API middleware resolves current user (header or cookie)
        ↓
┌──────────────────┬─────────────────────┬──────────────────┐
│ user_strategies  │ Scheduler (per user) │ Manual execute   │
│ (config)         │ → generate_signals   │ on Signals page  │
│                  │ → position filter    │ → fills ledger   │
│                  │ → trade_signals      │ → user_positions │
└──────────────────┴─────────────────────┴──────────────────┘
        ↓
Dashboard (stats + ≤3 signals)    /positions (full table)
```

### 4.2 Strategy Pool vs User Config

| Layer | Table | Purpose |
|-------|--------|---------|
| **Pool** | `strategies` | Strategy type catalog: `id` matches code `REGISTRY`, `name`, `description`, optional defaults |
| **User** | `user_strategies` | `user_id`, `strategy_id`, `symbols[]`, `timeframes[]`, `run_frequency`, `parameters`, `is_active`, `max_symbols`, timestamps |

- **Add:** insert `user_strategies` row (copy sensible defaults from pool row or strategy class defaults).
- **Remove:** delete user's row only; pool unchanged.
- **Edit:** update user's row only.

Scheduler registers APScheduler jobs as `strategy_{user_id}_{strategy_id}` (or equivalent), loading config from `user_strategies`.

### 4.3 Authentication & Session

**No password.** Two endpoints (illustrative):

- `GET /api/auth/users` — list `[{ id, username }]` for login picker.
- `POST /api/auth/session` — body `{ user_id }` → set session (HTTP-only cookie recommended) **or** return token; frontend also mirrors `user_id` in `localStorage` for SPA reload.

**Switch user:** same as login; replace session; invalidate client query cache and refetch.

**API guard:** except `GET /api/auth/*`, `GET /api/system/health`, and WebSocket handshake policy TBD — require valid session / `X-User-Id` matching a real user.

**CORS:** allow credentials if using cookies.

### 4.4 Positions & Fills

**Net position** — `user_positions`:

| Column | Notes |
|--------|--------|
| `user_id` | FK users |
| `instrument_id` | FK instruments |
| `quantity` | `NUMERIC`, ≥ 0 |
| `avg_cost` | weighted average cost per share |
| `updated_at` | last fill |

Unique on `(user_id, instrument_id)`.

**Ledger** — `position_fills` (or `user_trade_fills`):

| Column | Notes |
|--------|--------|
| `user_id`, `instrument_id` | |
| `signal_id` | nullable FK `trade_signals` |
| `side` | `buy` / `sell` |
| `quantity`, `fill_price` | required |
| `filled_at` | TIMESTAMPTZ |

**Buy fill:** increase quantity; update `avg_cost` via weighted average.

**Sell fill:** decrease quantity; reduce cost basis proportionally; reject if `sell_qty > position.quantity`.

**Manual execute API** (example):

- `POST /api/signals/{id}/execute` — body `{ quantity, fill_price }`
- Validates: signal belongs to current user; status in `pending` | `notified`; direction matches action; sell quantity ≤ position.
- Writes fill, updates `user_positions`, sets signal `status = executed`.

Open/close UI lives on **Signals** page, not Dashboard or Positions.

### 4.5 Signal Filtering (Live Runs)

Before inserting `trade_signals` for a scheduled run:

1. Load user's net positions map `symbol → quantity`.
2. Build `PortfolioSnapshot` (cash optional / unused in Phase 1 filter) or apply explicit rules:
   - `quantity > 0` → drop signals with `direction == buy` for that symbol.
   - `quantity == 0` (no row or zero) → drop `direction == sell`.
3. Persist only filtered signals with `user_id` set.

Filtering is **per user**, not per strategy (Q3=A).

### 4.6 Signals & Backtests

- Add `user_id` NOT NULL (after migration) to `trade_signals`, `backtests`, `backtest_presets`.
- All list/create APIs default to session user.
- Email notifier unchanged globally; email body may include username later.

### 4.7 Data Migration

1. Create `users`; seed `cx`, `cc`.
2. Create `user_strategies`, `user_positions`, `position_fills`.
3. Add nullable `user_id` to signals/backtests/presets → backfill **cc** → set NOT NULL + FK.
4. For each existing `strategies` row: copy to `user_strategies` for **cc** (preserve symbols, timeframes, parameters, `is_active`).
5. `cx` has no `user_strategies` until added via UI.
6. Keep `strategies` as pool; strip or retain global `is_active` — scheduler **must not** use global `is_active` alone after migration.

### 4.8 Dashboard Layout (Phase 1)

**Top:** metric cards — system health (global ok), active strategies count (user), today's signal count (user).

**Position summary (read-only):**

| Metric | Definition |
|--------|------------|
| Open symbols | Count of positions with `quantity > 0` |
| Total shares | Sum of `quantity` across positions |
| Position value | Sum of `quantity * mark_price`; if mark unavailable, use `avg_cost` |

**Recent signals:** fetch `limit=3` only; compact row (badge, symbol, strategy, time); link "View all" → `/signals`.

**Reserved space:** layout leaves room below summary for future widgets (P&L, alerts, etc.).

**No** execute buttons on Dashboard.

### 4.9 Positions Page (`/positions`)

- Table: symbol, quantity, avg cost, market value (if quote available), last updated.
- Read-only in Phase 1; no inline edit.
- Optional link to related recent signals for symbol (nice-to-have).

### 4.10 System Page

Remains **global** (health, scheduler events, data sync logs).

---

## 5. API Surface (Incremental)

| Area | Changes |
|------|---------|
| Auth | `GET /users`, `POST /session`, `GET /session`, `DELETE /session` |
| Strategies pool | `GET /api/strategies/pool` or reuse `GET /api/strategies` for catalog |
| User strategies | `GET/POST/PUT/DELETE /api/me/strategies` |
| Signals | filter by user; `POST .../execute` |
| Positions | `GET /api/me/positions`, `GET /api/me/positions/summary` |
| Backtests / presets | scope by user on CRUD |
| Scheduler | internal: load `user_strategies` where `is_active` |

---

## 6. Frontend Routes

| Route | Access |
|-------|--------|
| `/login` | unauthenticated |
| `/dashboard` | auth; summary + ≤3 signals |
| `/positions` | auth; full holdings |
| `/strategies`, `/signals`, `/backtests/*` | auth; user-scoped |
| `/system` | auth; global read |

**Layout:** show `username` + "Switch user" control.

**Guard:** redirect to `/login` if no session.

---

## 7. Error Handling

| Case | Behavior |
|------|----------|
| Execute sell > position | 400 with clear message |
| Execute already `executed` signal | 409 |
| Execute signal owned by other user | 403 |
| Scheduler: strategy not in REGISTRY | skip job, log warning |
| Missing instrument for symbol | skip signal row, log |

---

## 8. Testing Strategy

- Migration test: legacy rows assigned to `cc`; `cx` empty.
- Position math: weighted avg on multiple buys; partial sell.
- Filter: user with AAPL position → no buy for AAPL; no sell without position.
- Scheduler: two users same `strategy_id`, different symbols → independent signals.
- Auth: API without session → 401.
- Frontend: Dashboard never requests more than 3 signals.

---

## 9. Phasing

### Phase 1 (this document)

All sections above except broker auto-execute.

### Phase 2

- Schwab notifier executes orders.
- On confirmed fill → write `position_fills` automatically (same ledger as manual).
- Optional: pass live `PortfolioSnapshot` into strategies for sizing.

---

## 10. Open Implementation Notes

- **Mark price for position value:** reuse quote batch / last close from DB; document fallback to `avg_cost`.
- **WebSocket:** scope `signals` channel by `user_id` or filter client-side in Phase 1.
- **Global `strategies.is_active`:** deprecate for scheduling post-migration; pool row may still expose metadata only.

---

## 11. Relation to Existing Design

Builds on [2026-04-17-trading-system-design.md](./2026-04-17-trading-system-design.md). Replaces implicit single-tenant assumptions with per-user isolation. `PortfolioSnapshot` in `base.py` aligns with position filtering already used in backtests.
