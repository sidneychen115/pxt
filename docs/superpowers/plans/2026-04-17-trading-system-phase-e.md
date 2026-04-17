# PXT Trading System — Phase E: React Frontend + Docker

> **For agentic workers:** Complete Phase D before starting. REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Build the React frontend (5 pages) with TradingView charts, real-time WebSocket updates, and Docker deployment configuration.

**Tech Stack:** React 18, Vite, TypeScript, React Router, TanStack Query, Axios, TradingView Lightweight Charts, Tailwind CSS

---

## File Map

| File | Purpose |
|---|---|
| `frontend/package.json` | Frontend dependencies |
| `frontend/vite.config.ts` | Vite config with API proxy |
| `frontend/src/types/index.ts` | TypeScript interfaces |
| `frontend/src/api/client.ts` | Axios instance |
| `frontend/src/api/strategies.ts` | Strategy API calls |
| `frontend/src/api/signals.ts` | Signal API calls |
| `frontend/src/api/backtests.ts` | Backtest API calls |
| `frontend/src/api/system.ts` | System API calls |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket hook |
| `frontend/src/components/Layout.tsx` | Nav + page wrapper |
| `frontend/src/components/MetricCard.tsx` | Reusable metric display |
| `frontend/src/components/SignalBadge.tsx` | Buy/sell/hold badge |
| `frontend/src/components/EquityChart.tsx` | TradingView chart |
| `frontend/src/pages/Dashboard.tsx` | Overview page |
| `frontend/src/pages/Strategies.tsx` | Strategy list + config |
| `frontend/src/pages/Signals.tsx` | Signal list + detail |
| `frontend/src/pages/Backtests.tsx` | Backtest list + drill-down |
| `frontend/src/pages/System.tsx` | System logs + health |
| `frontend/src/App.tsx` | Router setup |
| `frontend/src/main.tsx` | Entry point |
| `docker/Dockerfile.backend` | Backend image |
| `docker/Dockerfile.frontend` | Frontend image |
| `docker/docker-compose.yml` | Full stack compose |

---

## Task 16: Frontend Setup + API Layer

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "pxt-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "@tanstack/react-query": "^5.62.0",
    "axios": "^1.7.9",
    "lightweight-charts": "^4.2.0",
    "lucide-react": "^0.469.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.14",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.7.2",
    "vite": "^6.0.5",
    "tailwindcss": "^3.4.17",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49"
  }
}
```

- [ ] **Step 2: Install dependencies**

```bash
cd /home/imxichen/projects/pxt/frontend
npm install
```

- [ ] **Step 3: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 4: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Create `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 6: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}
```

- [ ] **Step 7: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PXT Trading</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Create `frontend/src/types/index.ts`**

```typescript
export interface Strategy {
  id: string
  name: string
  description: string | null
  is_active: boolean
  symbols: string[]
  timeframes: string[]
  run_frequency: string
  parameters: Record<string, unknown>
  max_symbols: number
}

export interface Signal {
  id: number
  strategy_id: string
  stock_id: number | null
  option_id: number | null
  signal_time: string
  direction: 'buy' | 'sell' | 'hold'
  quantity: number | null
  order_type: string
  limit_price: number | null
  stop_price: number | null
  confidence: number | null
  reasoning: string | null
  status: string
  created_at: string
}

export interface Backtest {
  id: number
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  status: 'running' | 'completed' | 'failed'
  total_return: number | null
  annualized_return: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  win_rate: number | null
  profit_factor: number | null
  total_trades: number | null
  avg_hold_days: number | null
  llm_evaluation: string | null
  llm_model: string | null
  created_at: string
  completed_at: string | null
}

export interface BacktestTrade {
  id: number
  symbol: string
  direction: string
  quantity: number
  entry_time: string
  entry_price: number
  exit_time: string | null
  exit_price: number | null
  pnl: number | null
  pnl_pct: number | null
  hold_days: number | null
  exit_reason: string | null
  entry_signal: Record<string, unknown> | null
}

export interface EquityPoint {
  ts: string
  equity: number
  cash: number
  drawdown: number | null
}

export interface SystemEvent {
  id: number
  event_type: string
  level: 'info' | 'warning' | 'error'
  message: string
  details: Record<string, unknown>
  created_at: string
}
```

- [ ] **Step 9: Create `frontend/src/api/client.ts`**

```typescript
import axios from 'axios'

const client = axios.create({ baseURL: '/api' })
export default client
```

- [ ] **Step 10: Create `frontend/src/api/strategies.ts`**

```typescript
import client from './client'
import type { Strategy } from '../types'

export const fetchStrategies = () =>
  client.get<Strategy[]>('/strategies').then(r => r.data)

export const fetchStrategy = (id: string) =>
  client.get<Strategy>(`/strategies/${id}`).then(r => r.data)

export const updateStrategy = (id: string, data: Partial<Strategy>) =>
  client.put<{ ok: boolean }>(`/strategies/${id}`, data).then(r => r.data)
```

- [ ] **Step 11: Create `frontend/src/api/signals.ts`**

```typescript
import client from './client'
import type { Signal } from '../types'

export const fetchSignals = (params?: { strategy_id?: string; status?: string; limit?: number }) =>
  client.get<Signal[]>('/signals', { params }).then(r => r.data)

export const fetchSignal = (id: number) =>
  client.get<Signal>(`/signals/${id}`).then(r => r.data)
```

- [ ] **Step 12: Create `frontend/src/api/backtests.ts`**

```typescript
import client from './client'
import type { Backtest, BacktestTrade, EquityPoint } from '../types'

export const fetchBacktests = (strategy_id?: string) =>
  client.get<Backtest[]>('/backtests', { params: { strategy_id } }).then(r => r.data)

export const fetchBacktest = (id: number) =>
  client.get<Backtest>(`/backtests/${id}`).then(r => r.data)

export const triggerBacktest = (data: {
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  parameters: Record<string, unknown>
}) => client.post<{ id: number; status: string }>('/backtests', data).then(r => r.data)

export const fetchBacktestTrades = (id: number, sort_by = 'entry_time', order = 'asc') =>
  client.get<BacktestTrade[]>(`/backtests/${id}/trades`, { params: { sort_by, order } }).then(r => r.data)

export const fetchEquityCurve = (id: number) =>
  client.get<EquityPoint[]>(`/backtests/${id}/equity`).then(r => r.data)
```

- [ ] **Step 13: Create `frontend/src/api/system.ts`**

```typescript
import client from './client'
import type { SystemEvent } from '../types'

export const fetchHealth = () =>
  client.get<{ status: string }>('/system/health').then(r => r.data)

export const fetchEvents = (params?: { level?: string; event_type?: string; limit?: number }) =>
  client.get<SystemEvent[]>('/system/events', { params }).then(r => r.data)
```

- [ ] **Step 14: Create `frontend/src/hooks/useWebSocket.ts`**

```typescript
import { useEffect, useRef, useCallback } from 'react'

type MessageHandler = (channel: string, data: unknown) => void

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const { channel, data } = JSON.parse(event.data)
        onMessage(channel, data)
      } catch {}
    }

    ws.onclose = () => {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [onMessage])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connect])
}
```

- [ ] **Step 15: Commit**

```bash
cd /home/imxichen/projects/pxt
git add frontend/
git commit -m "feat: frontend setup — Vite, types, API client, WebSocket hook"
```

---

## Task 17: Layout + Core Components

- [ ] **Step 1: Create `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
)
```

- [ ] **Step 2: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Create `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Signals from './pages/Signals'
import Backtests from './pages/Backtests'
import System from './pages/System'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/backtests/:id" element={<Backtests />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/Layout.tsx`**

```tsx
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Bell, BarChart2, Activity } from 'lucide-react'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/strategies', icon: TrendingUp, label: 'Strategies' },
  { to: '/signals', icon: Bell, label: 'Signals' },
  { to: '/backtests', icon: BarChart2, label: 'Backtests' },
  { to: '/system', icon: Activity, label: 'System' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <nav className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col p-4 gap-1">
        <div className="text-xl font-bold text-white mb-6 px-2">PXT Trading</div>
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  )
}
```

- [ ] **Step 5: Create `frontend/src/components/MetricCard.tsx`**

```tsx
interface MetricCardProps {
  label: string
  value: string | number | null
  sub?: string
  color?: 'green' | 'red' | 'blue' | 'gray'
}

export default function MetricCard({ label, value, sub, color = 'gray' }: MetricCardProps) {
  const colors = {
    green: 'text-green-400',
    red: 'text-red-400',
    blue: 'text-blue-400',
    gray: 'text-gray-100',
  }
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colors[color]}`}>
        {value ?? '—'}
      </div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  )
}
```

- [ ] **Step 6: Create `frontend/src/components/SignalBadge.tsx`**

```tsx
export default function SignalBadge({ direction }: { direction: string }) {
  const styles: Record<string, string> = {
    buy: 'bg-green-900 text-green-300 border border-green-700',
    sell: 'bg-red-900 text-red-300 border border-red-700',
    hold: 'bg-gray-800 text-gray-400 border border-gray-700',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${styles[direction] ?? styles.hold}`}>
      {direction}
    </span>
  )
}
```

- [ ] **Step 7: Create `frontend/src/components/EquityChart.tsx`**

```tsx
import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineStyle } from 'lightweight-charts'
import type { EquityPoint } from '../types'

interface EquityChartProps {
  data: EquityPoint[]
  initialCapital: number
}

export default function EquityChart({ data, initialCapital }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#111827' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1F2937' }, horzLines: { color: '#1F2937' } },
      width: containerRef.current.clientWidth,
      height: 300,
    })

    const equitySeries = chart.addLineSeries({
      color: '#3B82F6',
      lineWidth: 2,
      title: 'Portfolio Equity',
    })

    const baselineSeries = chart.addLineSeries({
      color: '#6B7280',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Initial Capital',
    })

    const chartData = data.map(p => ({
      time: p.ts.split('T')[0] as `${number}-${number}-${number}`,
      value: p.equity,
    }))

    equitySeries.setData(chartData)
    baselineSeries.setData(
      chartData.map(p => ({ time: p.time, value: initialCapital }))
    )

    chart.timeScale().fitContent()

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current!.clientWidth })
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data, initialCapital])

  return <div ref={containerRef} className="w-full" />
}
```

- [ ] **Step 8: Commit**

```bash
cd /home/imxichen/projects/pxt
git add frontend/src/
git commit -m "feat: layout, shared components, App router"
```

---

## Task 18: All Five Pages

- [ ] **Step 1: Create `frontend/src/pages/Dashboard.tsx`**

```tsx
import { useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { fetchHealth } from '../api/system'
import { fetchStrategies } from '../api/strategies'
import { fetchSignals } from '../api/signals'
import { useWebSocket } from '../hooks/useWebSocket'
import MetricCard from '../components/MetricCard'
import SignalBadge from '../components/SignalBadge'

export default function Dashboard() {
  const [liveSignals, setLiveSignals] = useState<unknown[]>([])
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 30_000 })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const { data: signals } = useQuery({ queryKey: ['signals', 'today'], queryFn: () => fetchSignals({ limit: 10 }) })

  const handleWsMessage = useCallback((channel: string, data: unknown) => {
    if (channel === 'signals') setLiveSignals(prev => [data, ...prev].slice(0, 5))
  }, [])
  useWebSocket(handleWsMessage)

  const activeCount = strategies?.filter(s => s.is_active).length ?? 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-3 gap-4">
        <MetricCard label="System Status" value={health?.status === 'ok' ? 'Online' : 'Offline'}
          color={health?.status === 'ok' ? 'green' : 'red'} />
        <MetricCard label="Active Strategies" value={activeCount} color="blue" />
        <MetricCard label="Today's Signals" value={signals?.length ?? 0} />
      </div>
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Recent Signals</h2>
        {signals?.length === 0 && <p className="text-gray-500 text-sm">No signals yet.</p>}
        <div className="space-y-2">
          {signals?.map(s => (
            <div key={s.id} className="flex items-center gap-3 text-sm">
              <SignalBadge direction={s.direction} />
              <span className="text-gray-200 font-mono">{s.strategy_id}</span>
              <span className="text-gray-400 text-xs ml-auto">
                {new Date(s.created_at).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/pages/Strategies.tsx`**

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchStrategies, updateStrategy } from '../api/strategies'
import type { Strategy } from '../types'

export default function Strategies() {
  const qc = useQueryClient()
  const { data: strategies, isLoading } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const [editing, setEditing] = useState<Strategy | null>(null)

  const toggleMutation = useMutation({
    mutationFn: (s: Strategy) => updateStrategy(s.id, { is_active: !s.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Strategies</h1>
      <div className="space-y-3">
        {strategies?.map(s => (
          <div key={s.id} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold text-gray-100">{s.name}</div>
                <div className="text-xs text-gray-400 mt-0.5">{s.description}</div>
                <div className="flex gap-2 mt-2 flex-wrap">
                  {s.symbols.map(sym => (
                    <span key={sym} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded">{sym}</span>
                  ))}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Schedule: <code className="text-gray-300">{s.run_frequency}</code> |
                  Timeframes: {s.timeframes.join(', ')}
                </div>
              </div>
              <div className="flex gap-2 items-center">
                <button
                  onClick={() => setEditing(s)}
                  className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded border border-gray-700"
                >
                  Edit
                </button>
                <button
                  onClick={() => toggleMutation.mutate(s)}
                  className={`text-xs px-3 py-1 rounded font-semibold ${
                    s.is_active ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {s.is_active ? 'Active' : 'Inactive'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {editing && <StrategyEditModal strategy={editing} onClose={() => { setEditing(null); qc.invalidateQueries({ queryKey: ['strategies'] }) }} />}
    </div>
  )
}

function StrategyEditModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [symbols, setSymbols] = useState(strategy.symbols.join(', '))
  const [frequency, setFrequency] = useState(strategy.run_frequency)
  const mutation = useMutation({
    mutationFn: () => updateStrategy(strategy.id, {
      symbols: symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean),
      run_frequency: frequency,
    }),
    onSuccess: onClose,
  })
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl p-6 w-full max-w-md border border-gray-700 space-y-4">
        <h2 className="text-lg font-bold">Edit: {strategy.name}</h2>
        <div>
          <label className="text-xs text-gray-400">Symbols (comma separated)</label>
          <input value={symbols} onChange={e => setSymbols(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
        </div>
        <div>
          <label className="text-xs text-gray-400">Cron Schedule</label>
          <input value={frequency} onChange={e => setFrequency(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1 font-mono" />
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">Cancel</button>
          <button onClick={() => mutation.mutate()}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded font-semibold">
            {mutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create `frontend/src/pages/Signals.tsx`**

```tsx
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSignals } from '../api/signals'
import SignalBadge from '../components/SignalBadge'

export default function Signals() {
  const [status, setStatus] = useState('')
  const { data: signals, isLoading } = useQuery({
    queryKey: ['signals', status],
    queryFn: () => fetchSignals({ status: status || undefined, limit: 100 }),
    refetchInterval: 60_000,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Signals</h1>
        <select value={status} onChange={e => setStatus(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm">
          <option value="">All Status</option>
          <option value="pending">Pending</option>
          <option value="notified">Notified</option>
          <option value="executed">Executed</option>
        </select>
      </div>
      {isLoading && <div className="text-gray-400">Loading...</div>}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-xs">
              <th className="px-4 py-3 text-left">Signal</th>
              <th className="px-4 py-3 text-left">Strategy</th>
              <th className="px-4 py-3 text-left">Order</th>
              <th className="px-4 py-3 text-right">Confidence</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Time</th>
            </tr>
          </thead>
          <tbody>
            {signals?.map(s => (
              <tr key={s.id} className="border-b border-gray-800/50 hover:bg-gray-800/40">
                <td className="px-4 py-3"><SignalBadge direction={s.direction} /></td>
                <td className="px-4 py-3 text-gray-300 font-mono text-xs">{s.strategy_id}</td>
                <td className="px-4 py-3 text-gray-400">{s.order_type}</td>
                <td className="px-4 py-3 text-right text-gray-300">
                  {s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-gray-400">{s.status}</span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {new Date(s.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {signals?.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">No signals found.</div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/pages/System.tsx`**

```tsx
import { useQuery } from '@tanstack/react-query'
import { fetchHealth, fetchEvents } from '../api/system'

const levelColors: Record<string, string> = {
  info: 'text-blue-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
}

export default function System() {
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 10_000 })
  const { data: events } = useQuery({ queryKey: ['events'], queryFn: () => fetchEvents({ limit: 200 }), refetchInterval: 15_000 })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System</h1>
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${health?.status === 'ok' ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-sm font-medium">Backend: {health?.status ?? 'unknown'}</span>
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-gray-300">Event Log</div>
        <div className="max-h-[600px] overflow-y-auto font-mono text-xs">
          {events?.map(e => (
            <div key={e.id} className="px-4 py-2 border-b border-gray-800/40 flex gap-3 hover:bg-gray-800/30">
              <span className="text-gray-500 shrink-0">{new Date(e.created_at).toLocaleTimeString()}</span>
              <span className={`shrink-0 w-16 ${levelColors[e.level] ?? 'text-gray-400'}`}>{e.level.toUpperCase()}</span>
              <span className="text-gray-400 shrink-0">[{e.event_type}]</span>
              <span className="text-gray-200 break-all">{e.message}</span>
            </div>
          ))}
          {events?.length === 0 && <div className="text-gray-500 text-center py-8">No events.</div>}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create `frontend/src/pages/Backtests.tsx`**

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchBacktests, fetchBacktest, triggerBacktest, fetchBacktestTrades, fetchEquityCurve } from '../api/backtests'
import { fetchStrategies } from '../api/strategies'
import MetricCard from '../components/MetricCard'
import EquityChart from '../components/EquityChart'
import SignalBadge from '../components/SignalBadge'

export default function Backtests() {
  const { id } = useParams<{ id?: string }>()
  return id ? <BacktestDetail id={parseInt(id)} /> : <BacktestList />
}

function BacktestList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: backtests, isLoading } = useQuery({ queryKey: ['backtests'], queryFn: () => fetchBacktests() })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ strategy_id: '', start_date: '2023-01-01', end_date: '2024-01-01', symbols: '', initial_capital: 100000 })

  const triggerMutation = useMutation({
    mutationFn: () => triggerBacktest({
      strategy_id: form.strategy_id,
      start_date: form.start_date,
      end_date: form.end_date,
      symbols: form.symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean),
      initial_capital: form.initial_capital,
      parameters: {},
    }),
    onSuccess: (data) => {
      setShowForm(false)
      qc.invalidateQueries({ queryKey: ['backtests'] })
      navigate(`/backtests/${data.id}`)
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Backtests</h1>
        <button onClick={() => setShowForm(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold">
          + New Backtest
        </button>
      </div>
      {showForm && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-700 space-y-4">
          <h2 className="font-semibold">Configure Backtest</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400">Strategy</label>
              <select value={form.strategy_id} onChange={e => setForm(f => ({ ...f, strategy_id: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1">
                <option value="">Select...</option>
                {strategies?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Symbols (comma separated)</label>
              <input value={form.symbols} onChange={e => setForm(f => ({ ...f, symbols: e.target.value }))}
                placeholder="AAPL, SPY, MSFT"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Start Date</label>
              <input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
            </div>
            <div>
              <label className="text-xs text-gray-400">End Date</label>
              <input type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Initial Capital ($)</label>
              <input type="number" value={form.initial_capital} onChange={e => setForm(f => ({ ...f, initial_capital: +e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">Cancel</button>
            <button onClick={() => triggerMutation.mutate()}
              disabled={!form.strategy_id || !form.symbols}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold disabled:opacity-50">
              {triggerMutation.isPending ? 'Starting...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      )}
      {isLoading && <div className="text-gray-400">Loading...</div>}
      <div className="space-y-3">
        {backtests?.map(bt => (
          <div key={bt.id} onClick={() => navigate(`/backtests/${bt.id}`)}
            className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-gray-600 cursor-pointer">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-gray-100">{bt.strategy_id}</div>
                <div className="text-xs text-gray-400 mt-0.5">{bt.start_date} → {bt.end_date} | {bt.symbols.join(', ')}</div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                {bt.status === 'completed' && (
                  <>
                    <span className={bt.total_return != null && bt.total_return >= 0 ? 'text-green-400' : 'text-red-400'}>
                      {bt.total_return != null ? `${(bt.total_return * 100).toFixed(2)}%` : '—'}
                    </span>
                    <span className="text-gray-400">Sharpe: {bt.sharpe_ratio?.toFixed(2) ?? '—'}</span>
                  </>
                )}
                <span className={`text-xs px-2 py-0.5 rounded ${
                  bt.status === 'completed' ? 'bg-green-900 text-green-300' :
                  bt.status === 'failed' ? 'bg-red-900 text-red-300' :
                  'bg-yellow-900 text-yellow-300'
                }`}>{bt.status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BacktestDetail({ id }: { id: number }) {
  const navigate = useNavigate()
  const [sortBy, setSortBy] = useState('entry_time')
  const [sortOrder, setSortOrder] = useState('asc')
  const { data: bt, isLoading } = useQuery({ queryKey: ['backtest', id], queryFn: () => fetchBacktest(id), refetchInterval: (q) => q.state.data?.status === 'running' ? 3000 : false })
  const { data: trades } = useQuery({ queryKey: ['bt-trades', id, sortBy, sortOrder], queryFn: () => fetchBacktestTrades(id, sortBy, sortOrder), enabled: bt?.status === 'completed' })
  const { data: equity } = useQuery({ queryKey: ['bt-equity', id], queryFn: () => fetchEquityCurve(id), enabled: bt?.status === 'completed' })

  if (isLoading) return <div className="text-gray-400">Loading...</div>
  if (!bt) return <div className="text-gray-400">Not found.</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/backtests')} className="text-gray-400 hover:text-gray-200">← Back</button>
        <h1 className="text-2xl font-bold">{bt.strategy_id}</h1>
        <span className={`text-xs px-2 py-1 rounded font-semibold ${bt.status === 'completed' ? 'bg-green-900 text-green-300' : bt.status === 'failed' ? 'bg-red-900 text-red-300' : 'bg-yellow-900 text-yellow-300'}`}>
          {bt.status}
        </span>
      </div>
      {bt.status === 'running' && <div className="text-yellow-400 text-sm">Backtest is running...</div>}
      {bt.status === 'completed' && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <MetricCard label="Total Return" value={bt.total_return != null ? `${(bt.total_return * 100).toFixed(2)}%` : '—'} color={bt.total_return != null && bt.total_return >= 0 ? 'green' : 'red'} />
            <MetricCard label="Sharpe Ratio" value={bt.sharpe_ratio?.toFixed(2) ?? '—'} color={bt.sharpe_ratio != null && bt.sharpe_ratio >= 1 ? 'green' : 'gray'} />
            <MetricCard label="Max Drawdown" value={bt.max_drawdown != null ? `${(bt.max_drawdown * 100).toFixed(2)}%` : '—'} color="red" />
            <MetricCard label="Win Rate" value={bt.win_rate != null ? `${(bt.win_rate * 100).toFixed(1)}%` : '—'} />
            <MetricCard label="Profit Factor" value={bt.profit_factor?.toFixed(2) ?? '—'} />
            <MetricCard label="Total Trades" value={bt.total_trades ?? '—'} />
            <MetricCard label="Avg Hold Days" value={bt.avg_hold_days?.toFixed(1) ?? '—'} />
            <MetricCard label="Annualized Return" value={bt.annualized_return != null ? `${(bt.annualized_return * 100).toFixed(2)}%` : '—'} />
          </div>
          {equity && equity.length > 0 && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">Equity Curve</h2>
              <EquityChart data={equity} initialCapital={bt.initial_capital} />
            </div>
          )}
          {bt.llm_evaluation && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">AI Evaluation ({bt.llm_model})</h2>
              <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans">{bt.llm_evaluation}</pre>
            </div>
          )}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-4">
              <h2 className="text-sm font-semibold text-gray-300">Trade Log</h2>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs ml-auto">
                <option value="entry_time">Entry Time</option>
                <option value="pnl">P&L</option>
                <option value="hold_days">Hold Days</option>
                <option value="pnl_pct">Return %</option>
              </select>
              <select value={sortOrder} onChange={e => setSortOrder(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs">
                <option value="asc">Asc</option>
                <option value="desc">Desc</option>
              </select>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs">
                  <th className="px-4 py-2 text-left">Symbol</th>
                  <th className="px-4 py-2 text-left">Dir</th>
                  <th className="px-4 py-2 text-right">Qty</th>
                  <th className="px-4 py-2 text-right">Entry</th>
                  <th className="px-4 py-2 text-right">Exit</th>
                  <th className="px-4 py-2 text-right">P&L</th>
                  <th className="px-4 py-2 text-right">Return</th>
                  <th className="px-4 py-2 text-right">Days</th>
                  <th className="px-4 py-2 text-left">Reason</th>
                </tr>
              </thead>
              <tbody>
                {trades?.map(t => (
                  <tr key={t.id} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                    <td className="px-4 py-2 font-mono font-semibold text-gray-200">{t.symbol}</td>
                    <td className="px-4 py-2"><SignalBadge direction={t.direction} /></td>
                    <td className="px-4 py-2 text-right text-gray-300">{t.quantity}</td>
                    <td className="px-4 py-2 text-right text-gray-300">${t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right text-gray-300">{t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : '—'}</td>
                    <td className={`px-4 py-2 text-right font-semibold ${t.pnl != null && t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-4 py-2 text-right ${t.pnl_pct != null && t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl_pct != null ? `${(t.pnl_pct * 100).toFixed(2)}%` : '—'}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-400">{t.hold_days?.toFixed(0) ?? '—'}</td>
                    <td className="px-4 py-2 text-xs text-gray-500">{t.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {trades?.length === 0 && <div className="text-gray-500 text-center py-6 text-sm">No trades.</div>}
          </div>
        </>
      )}
      {bt.status === 'failed' && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          Error: {bt.llm_evaluation ?? 'Unknown error'}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Start dev server and verify all pages load**

```bash
cd /home/imxichen/projects/pxt/frontend
npm run dev
```

Visit `http://localhost:3000` and check each page loads without console errors.

- [ ] **Step 7: Commit**

```bash
cd /home/imxichen/projects/pxt
git add frontend/src/pages/ frontend/src/components/ frontend/src/main.tsx frontend/src/App.tsx frontend/src/index.css
git commit -m "feat: all 5 React pages — Dashboard, Strategies, Signals, Backtests, System"
```

---

## Task 19: Docker Setup

- [ ] **Step 1: Create `docker/Dockerfile.backend`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev
COPY backend/src ./src
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `docker/Dockerfile.frontend`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 3: Create `docker/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Create `docker/docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: pxt
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/pxt
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - ../schwab_token.json:/app/schwab_token.json:ro

  frontend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

- [ ] **Step 5: Test Docker build**

```bash
cd /home/imxichen/projects/pxt
docker compose -f docker/docker-compose.yml build
```

Expected: Both images build without error.

- [ ] **Step 6: Commit**

```bash
cd /home/imxichen/projects/pxt
git add docker/
git commit -m "feat: Docker setup — backend, frontend, compose"
```

---

**All phases complete.**

## Self-Review

**Spec coverage:**
- Data collection (Schwab + yfinance, multi-timeframe): ✅ Phase B
- Strategy library (unified interface, indicators, registry): ✅ Phase C
- Scheduler (multi-strategy, configurable frequency): ✅ Phase C Task 11
- Signal processing (email phase 1): ✅ Phase D Task 14
- Backtesting (look-ahead prevention, drill-down, LLM eval): ✅ Phase D Tasks 12–13
- Web dashboard (all 5 pages): ✅ Phase E
- Docker deployment: ✅ Phase E Task 19

**Type consistency:** All types defined in `base.py` (TradeSignal, DataContext, BaseStrategy) used consistently throughout. `BacktestMetrics` defined in `metrics.py` and consumed in `engine.py` and `evaluator.py`. Frontend TypeScript interfaces in `types/index.ts` match API response shapes.

**No placeholders detected.**

---

**Plan complete and saved to:**
- `docs/superpowers/plans/2026-04-17-trading-system-phase-a.md` (Foundation)
- `docs/superpowers/plans/2026-04-17-trading-system-phase-b.md` (Data Layer)
- `docs/superpowers/plans/2026-04-17-trading-system-phase-c.md` (Strategy + Scheduler)
- `docs/superpowers/plans/2026-04-17-trading-system-phase-d.md` (Backtest + API)
- `docs/superpowers/plans/2026-04-17-trading-system-phase-e.md` (Frontend + Docker)

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration. Invoke `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks in this session with checkpoints. Invoke `superpowers:executing-plans`.

Which approach?
