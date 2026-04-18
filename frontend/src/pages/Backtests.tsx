import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  fetchBacktests, fetchBacktest, triggerBacktest,
  fetchBacktestTrades, fetchEquityCurve,
} from '../api/backtests'
import { fetchStrategies } from '../api/strategies'
import MetricCard from '../components/MetricCard'
import EquityChart from '../components/EquityChart'
import SignalBadge from '../components/SignalBadge'
import type { Backtest, BacktestProgressPhase } from '../types'
import {
  EMPTY_EXIT_FORM,
  exitPolicyFromForm,
  exitPolicyToForm,
  parseParametersJson,
  buildRerunPayload,
  sliceIsoDate,
  type ExitFormState,
} from '../lib/backtestFormConfig'
import {
  listPresets,
  saveNewPreset,
  deletePreset,
  getPreset,
  applyPreset,
  snapshotFromCurrentForm,
  snapshotFromBacktest,
} from '../lib/backtestPresets'

function formatBacktestDateTime(iso: string | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const PROGRESS_STEPS: { phase: BacktestProgressPhase; label: string }[] = [
  { phase: 'fetching_data', label: '数据拉取' },
  { phase: 'engine', label: '回测引擎' },
  { phase: 'llm_eval', label: 'LLM 评估' },
]

function BacktestProgressPanel({ bt }: { bt: Backtest }) {
  const phaseIndex = useMemo(() => {
    if (!bt.progress_phase) return -1
    return PROGRESS_STEPS.findIndex(s => s.phase === bt.progress_phase)
  }, [bt.progress_phase])

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-yellow-800/50 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-yellow-200/90">运行进度</h2>
        <span className="text-xs text-gray-500">WebSocket + 轮询</span>
      </div>
      <div className="flex flex-wrap gap-2 md:gap-0 md:justify-between">
        {PROGRESS_STEPS.map((step, i) => {
          const done = phaseIndex > i
          const active = phaseIndex === i
          return (
            <div
              key={step.phase}
              className={`flex items-center gap-2 text-sm rounded-lg px-3 py-2 border flex-1 min-w-[140px] ${
                done
                  ? 'border-green-700/60 bg-green-950/40 text-green-300'
                  : active
                    ? 'border-yellow-600 bg-yellow-950/30 text-yellow-200 ring-1 ring-yellow-700/40'
                    : 'border-gray-700 text-gray-500'
              }`}
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  done ? 'bg-green-700 text-white' : active ? 'bg-yellow-600 text-black' : 'bg-gray-700 text-gray-400'
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span className="font-medium">{step.label}</span>
            </div>
          )
        })}
      </div>
      <div className="text-sm text-gray-300 min-h-[1.25rem]">
        {bt.progress_message ?? (bt.status === 'running' ? '正在启动…' : '')}
      </div>
      <div className="h-1 w-full bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-yellow-600 transition-all duration-500 ease-out"
          style={{
            width:
              phaseIndex < 0
                ? '8%'
                : `${Math.min(100, Math.round(((phaseIndex + 1) / PROGRESS_STEPS.length) * 100))}%`,
          }}
        />
      </div>
    </div>
  )
}

export default function Backtests() {
  const { id } = useParams<{ id?: string }>()
  const numId = id ? parseInt(id, 10) : NaN
  return !isNaN(numId) ? <BacktestDetail id={numId} /> : <BacktestList />
}

function BacktestList() {
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const { data: backtests, isLoading } = useQuery({
    queryKey: ['backtests'],
    queryFn: () => fetchBacktests(),
  })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    strategy_id: '',
    start_date: '2023-01-01',
    end_date: '2024-01-01',
    symbols: '',
    initial_capital: 100000,
  })
  const [exitPolicy, setExitPolicy] = useState<ExitFormState>(() => ({ ...EMPTY_EXIT_FORM }))
  const [parametersJson, setParametersJson] = useState('{}')
  const [presetListTick, setPresetListTick] = useState(0)
  const presets = useMemo(() => listPresets(), [presetListTick])
  const [loadPresetSelect, setLoadPresetSelect] = useState('')
  const [savePresetName, setSavePresetName] = useState('')
  const [deletePresetId, setDeletePresetId] = useState('')

  useEffect(() => {
    const raw = (location.state as { prefillFromBacktest?: Backtest } | null)?.prefillFromBacktest
    if (!raw) return
    setForm({
      strategy_id: raw.strategy_id,
      start_date: sliceIsoDate(raw.start_date),
      end_date: sliceIsoDate(raw.end_date),
      symbols: raw.symbols.join(', '),
      initial_capital: raw.initial_capital,
    })
    setExitPolicy(exitPolicyToForm(raw.exit_policy))
    setParametersJson(JSON.stringify(raw.parameters ?? {}, null, 2))
    setShowForm(true)
    navigate('/backtests', { replace: true, state: {} })
  }, [location.state, navigate])

  const triggerMutation = useMutation({
    mutationFn: () => {
      let parameters: Record<string, unknown>
      try {
        parameters = parseParametersJson(parametersJson)
      } catch (e) {
        const msg =
          e instanceof SyntaxError
            ? '策略参数 JSON 格式无效'
            : e instanceof Error
              ? e.message
              : 'Invalid parameters'
        throw new Error(msg)
      }
      return triggerBacktest({
        strategy_id: form.strategy_id,
        start_date: form.start_date,
        end_date: form.end_date,
        symbols: form.symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean),
        initial_capital: form.initial_capital,
        parameters,
        exit_policy: exitPolicyFromForm(exitPolicy),
      })
    },
    onSuccess: (data) => {
      setShowForm(false)
      qc.invalidateQueries({ queryKey: ['backtests'] })
      navigate(`/backtests/${data.id}`)
    },
  })

  const applyLoadedPreset = (id: string) => {
    const p = getPreset(id)
    if (!p) return
    const snap = applyPreset(p)
    setForm({
      strategy_id: snap.strategy_id,
      start_date: snap.start_date,
      end_date: snap.end_date,
      symbols: snap.symbols,
      initial_capital: snap.initial_capital,
    })
    setExitPolicy(snap.exitPolicy)
    setParametersJson(snap.parametersJson)
    setShowForm(true)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Backtests</h1>
        <div className="flex flex-wrap items-center gap-2">
          {presets.length > 0 && (
            <select
              value={loadPresetSelect}
              onChange={(e) => {
                const id = e.target.value
                setLoadPresetSelect('')
                if (!id) return
                applyLoadedPreset(id)
              }}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm min-w-[160px]"
            >
              <option value="">加载预设…</option>
              {presets.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold"
          >
            + New Backtest
          </button>
        </div>
      </div>
      {showForm && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-700 space-y-4">
          <h2 className="font-semibold">Configure Backtest</h2>
          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3 space-y-3">
            <div className="text-xs text-gray-500">预设保存在本机浏览器（换浏览器或清除数据会丢失）</div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1 min-w-[140px]">
                <label className="text-xs text-gray-400">保存当前表单为预设</label>
                <input
                  type="text"
                  value={savePresetName}
                  onChange={e => setSavePresetName(e.target.value)}
                  placeholder="预设名称"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  try {
                    const snap = snapshotFromCurrentForm(form, exitPolicy, parametersJson)
                    saveNewPreset(savePresetName, snap)
                    setSavePresetName('')
                    setPresetListTick(t => t + 1)
                  } catch (err) {
                    window.alert(err instanceof Error ? err.message : '保存失败')
                  }
                }}
                className="px-3 py-2 bg-emerald-700 hover:bg-emerald-600 rounded text-sm font-semibold"
              >
                保存预设
              </button>
            </div>
            {presets.length > 0 && (
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex-1 min-w-[160px]">
                  <label className="text-xs text-gray-400">删除预设</label>
                  <select
                    value={deletePresetId}
                    onChange={e => setDeletePresetId(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                  >
                    <option value="">选择…</option>
                    {presets.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  disabled={!deletePresetId}
                  onClick={() => {
                    if (!deletePresetId) return
                    deletePreset(deletePresetId)
                    setDeletePresetId('')
                    setPresetListTick(t => t + 1)
                  }}
                  className="px-3 py-2 bg-red-900/80 hover:bg-red-800 rounded text-sm font-semibold disabled:opacity-40"
                >
                  删除
                </button>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400">Strategy</label>
              <select
                value={form.strategy_id}
                onChange={e => setForm(f => ({ ...f, strategy_id: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              >
                <option value="">Select...</option>
                {strategies?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Symbols (comma separated)</label>
              <input
                value={form.symbols}
                onChange={e => setForm(f => ({ ...f, symbols: e.target.value }))}
                placeholder="AAPL, SPY, MSFT"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400">Start Date</label>
              <input
                type="date"
                value={form.start_date}
                onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400">End Date</label>
              <input
                type="date"
                value={form.end_date}
                onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400">Initial Capital ($)</label>
              <input
                type="number"
                value={form.initial_capital}
                onChange={e => setForm(f => ({ ...f, initial_capital: +e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              />
            </div>
          </div>
          <details className="border border-gray-700 rounded p-3">
            <summary className="text-sm text-gray-400 cursor-pointer select-none">策略参数 (JSON，可选)</summary>
            <textarea
              value={parametersJson}
              onChange={e => setParametersJson(e.target.value)}
              spellCheck={false}
              placeholder="{}"
              className="w-full mt-2 min-h-[88px] font-mono text-xs bg-gray-800 border border-gray-700 rounded px-3 py-2"
            />
          </details>
          <details className="border border-gray-700 rounded p-3">
            <summary className="text-sm text-gray-400 cursor-pointer select-none">Exit Rules (optional)</summary>
            <div className="grid grid-cols-2 gap-4 mt-3">
              <div>
                <label className="text-xs text-gray-400">Stop Loss %</label>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  placeholder="e.g. 5 for 5%"
                  value={exitPolicy.stop_loss_pct}
                  onChange={e => setExitPolicy(p => ({ ...p, stop_loss_pct: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Stop Loss $ (absolute)</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  placeholder="e.g. 500 for $500 loss"
                  value={exitPolicy.stop_loss_abs}
                  onChange={e => setExitPolicy(p => ({ ...p, stop_loss_abs: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Take Profit %</label>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  placeholder="e.g. 15 for 15%"
                  value={exitPolicy.take_profit_pct}
                  onChange={e => setExitPolicy(p => ({ ...p, take_profit_pct: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Take Profit $ (absolute)</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  placeholder="e.g. 2000 for $2000 gain"
                  value={exitPolicy.take_profit_abs}
                  onChange={e => setExitPolicy(p => ({ ...p, take_profit_abs: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Trailing Stop %</label>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  placeholder="e.g. 5 for 5%"
                  value={exitPolicy.trailing_stop_pct}
                  onChange={e => setExitPolicy(p => ({ ...p, trailing_stop_pct: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Trailing Activate % (optional)</label>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  placeholder="e.g. 10 to activate after 10% gain"
                  value={exitPolicy.trailing_activate_pct}
                  onChange={e => setExitPolicy(p => ({ ...p, trailing_activate_pct: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400">Price Check Mode</label>
                <select
                  value={exitPolicy.price_check_mode}
                  onChange={e => setExitPolicy(p => ({ ...p, price_check_mode: e.target.value as 'close' | 'ohlc' }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                >
                  <option value="close">Close (fill at next open)</option>
                  <option value="ohlc">OHLC (intrabar fill at trigger price)</option>
                </select>
              </div>
              <div className="col-span-2 flex items-start gap-2 pt-1">
                <input
                  type="checkbox"
                  id="disable_sell_signal"
                  checked={exitPolicy.disable_sell_signal}
                  onChange={e => setExitPolicy(p => ({ ...p, disable_sell_signal: e.target.checked }))}
                  className="mt-1 rounded border-gray-600"
                />
                <label htmlFor="disable_sell_signal" className="text-sm text-gray-300 cursor-pointer select-none leading-snug">
                  禁用卖出信号（忽略策略 SELL，仅通过止损/止盈/移动止损或回测结束平仓）
                </label>
              </div>
            </div>
          </details>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">
              Cancel
            </button>
            <button
              onClick={() => triggerMutation.mutate()}
              disabled={!form.strategy_id || !form.symbols || triggerMutation.isPending}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold disabled:opacity-50"
            >
              {triggerMutation.isPending ? 'Starting...' : 'Run Backtest'}
            </button>
          </div>
          {triggerMutation.isError && (
            <p className="text-red-400 text-sm">
              {triggerMutation.error instanceof Error ? triggerMutation.error.message : 'Failed to start backtest.'}
            </p>
          )}
        </div>
      )}
      {isLoading && <div className="text-gray-400">Loading...</div>}
      <div className="space-y-3">
        {backtests?.map(bt => (
          <div
            key={bt.id}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/backtests/${bt.id}`)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') navigate(`/backtests/${bt.id}`) }}
            className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-gray-600 cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-gray-100">{bt.strategy_id}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {bt.start_date} → {bt.end_date} | {bt.symbols.join(', ')}
                </div>
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
  const qc = useQueryClient()
  const [sortBy, setSortBy] = useState('entry_time')
  const [sortOrder, setSortOrder] = useState('asc')
  const [detailPresetName, setDetailPresetName] = useState('')
  const [detailPresetHint, setDetailPresetHint] = useState<string | null>(null)
  const { data: bt, isLoading } = useQuery({
    queryKey: ['backtest', id],
    queryFn: () => fetchBacktest(id),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1500 : false),
  })

  useEffect(() => {
    if (bt?.status !== 'running') return
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws`)
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as {
          channel: string
          data: {
            backtest_id: number
            phase: string | null
            message: string | null
            status?: string
          }
        }
        if (msg.channel !== 'backtest_progress' || msg.data.backtest_id !== id) return
        if (msg.data.status === 'completed' || msg.data.status === 'failed') {
          qc.invalidateQueries({ queryKey: ['backtest', id] })
          qc.invalidateQueries({ queryKey: ['backtests'] })
          return
        }
        qc.setQueryData(['backtest', id], (prev: Backtest | undefined) => {
          if (!prev) return prev
          const ph = msg.data.phase
          return {
            ...prev,
            progress_phase:
              ph === 'fetching_data' || ph === 'engine' || ph === 'llm_eval'
                ? ph
                : prev.progress_phase,
            progress_message: msg.data.message ?? prev.progress_message,
          }
        })
      } catch {
        /* malformed message */
      }
    }
    return () => {
      ws.close()
    }
  }, [id, bt?.status, qc])

  useEffect(() => {
    setDetailPresetHint(null)
    setDetailPresetName('')
  }, [id])

  const { data: trades } = useQuery({
    queryKey: ['bt-trades', id, sortBy, sortOrder],
    queryFn: () => fetchBacktestTrades(id, sortBy, sortOrder),
    enabled: bt?.status === 'completed',
  })
  const { data: equity } = useQuery({
    queryKey: ['bt-equity', id],
    queryFn: () => fetchEquityCurve(id),
    enabled: bt?.status === 'completed',
  })

  const rerunMutation = useMutation({
    mutationFn: (payload: Parameters<typeof triggerBacktest>[0]) => triggerBacktest(payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['backtests'] })
      navigate(`/backtests/${data.id}`)
    },
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>
  if (!bt) return <div className="text-gray-400">Not found.</div>

  const canRerun = bt.status === 'completed' || bt.status === 'failed'

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={() => navigate('/backtests')} className="text-gray-400 hover:text-gray-200">← Back</button>
          <h1 className="text-2xl font-bold">{bt.strategy_id}</h1>
          <span className={`text-xs px-2 py-1 rounded font-semibold ${
            bt.status === 'completed' ? 'bg-green-900 text-green-300' :
            bt.status === 'failed' ? 'bg-red-900 text-red-300' :
            'bg-yellow-900 text-yellow-300'
          }`}>
            {bt.status}
          </span>
        </div>
        {canRerun && (
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={() => rerunMutation.mutate(buildRerunPayload(bt))}
              disabled={rerunMutation.isPending}
              className="px-3 py-1.5 text-sm rounded font-semibold bg-slate-700 hover:bg-slate-600 border border-gray-600 text-gray-100 disabled:opacity-50"
            >
              {rerunMutation.isPending ? '启动中…' : '重新测试'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/backtests', { state: { prefillFromBacktest: bt } })}
              className="px-3 py-1.5 text-sm rounded font-semibold bg-blue-600 hover:bg-blue-500 text-white"
            >
              调整参数重测
            </button>
          </div>
        )}
      </div>
      {rerunMutation.isError && (
        <p className="text-red-400 text-sm">
          {rerunMutation.error instanceof Error ? rerunMutation.error.message : '重新测试失败'}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 bg-gray-900/60 border border-gray-800 rounded-lg px-3 py-2.5">
        <span className="text-sm text-gray-400 shrink-0">保存为配置预设</span>
        <input
          type="text"
          value={detailPresetName}
          onChange={e => setDetailPresetName(e.target.value)}
          placeholder="预设名称"
          className="flex-1 min-w-[120px] max-w-xs bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={() => {
            try {
              saveNewPreset(detailPresetName, snapshotFromBacktest(bt))
              setDetailPresetHint('已保存到本机浏览器，可在列表页「加载预设」使用')
              setDetailPresetName('')
            } catch (err) {
              window.alert(err instanceof Error ? err.message : '保存失败')
            }
          }}
          className="px-3 py-1.5 text-sm rounded font-semibold bg-emerald-800 hover:bg-emerald-700 text-white shrink-0"
        >
          保存预设
        </button>
        {detailPresetHint && (
          <span className="text-xs text-green-400 w-full sm:w-auto">{detailPresetHint}</span>
        )}
      </div>
      {bt.status === 'running' && <BacktestProgressPanel bt={bt} />}
      {bt.status === 'completed' && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <MetricCard
              label="Total Return"
              value={bt.total_return != null ? `${(bt.total_return * 100).toFixed(2)}%` : '—'}
              color={bt.total_return != null && bt.total_return >= 0 ? 'green' : 'red'}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={bt.sharpe_ratio?.toFixed(2) ?? '—'}
              color={bt.sharpe_ratio != null && bt.sharpe_ratio >= 1 ? 'green' : 'gray'}
            />
            <MetricCard
              label="Max Drawdown"
              value={bt.max_drawdown != null ? `${(bt.max_drawdown * 100).toFixed(2)}%` : '—'}
              color="red"
            />
            <MetricCard label="Win Rate" value={bt.win_rate != null ? `${(bt.win_rate * 100).toFixed(1)}%` : '—'} />
            <MetricCard label="Profit Factor" value={bt.profit_factor?.toFixed(2) ?? '—'} />
            <MetricCard label="Total Trades" value={bt.total_trades ?? '—'} />
            <MetricCard label="Avg Hold Days" value={bt.avg_hold_days?.toFixed(1) ?? '—'} />
            <MetricCard
              label="Annualized Return"
              value={bt.annualized_return != null ? `${(bt.annualized_return * 100).toFixed(2)}%` : '—'}
            />
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
            <div className="px-4 py-3 border-b border-gray-800 flex flex-wrap items-center gap-4">
              <h2 className="text-sm font-semibold text-gray-300">成交明细</h2>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs ml-auto"
              >
                <option value="entry_time">买入时间</option>
                <option value="pnl">盈亏</option>
                <option value="hold_days">持有天数</option>
                <option value="pnl_pct">收益率</option>
              </select>
              <select
                value={sortOrder}
                onChange={e => setSortOrder(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
              >
                <option value="asc">升序</option>
                <option value="desc">降序</option>
              </select>
            </div>
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[960px]">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs">
                  <th className="px-4 py-2 text-left whitespace-nowrap">标的</th>
                  <th className="px-4 py-2 text-left whitespace-nowrap">方向</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">数量</th>
                  <th className="px-4 py-2 text-left whitespace-nowrap">买入时间</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">买入价</th>
                  <th className="px-4 py-2 text-left whitespace-nowrap">卖出时间</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">卖出价</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">P&amp;L</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">收益率</th>
                  <th className="px-4 py-2 text-right whitespace-nowrap">天数</th>
                  <th className="px-4 py-2 text-left whitespace-nowrap">原因</th>
                </tr>
              </thead>
              <tbody>
                {trades?.map(t => (
                  <tr key={t.id} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                    <td className="px-4 py-2 font-mono font-semibold text-gray-200">{t.symbol}</td>
                    <td className="px-4 py-2"><SignalBadge direction={t.direction} /></td>
                    <td className="px-4 py-2 text-right text-gray-300">{t.quantity}</td>
                    <td className="px-4 py-2 text-left text-gray-300 whitespace-nowrap tabular-nums">
                      {formatBacktestDateTime(t.entry_time)}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-300 tabular-nums">${t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2 text-left text-gray-300 whitespace-nowrap tabular-nums">
                      {formatBacktestDateTime(t.exit_time)}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-300 tabular-nums">
                      {t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-4 py-2 text-right font-semibold ${
                      t.pnl != null && t.pnl >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-4 py-2 text-right ${
                      t.pnl_pct != null && t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {t.pnl_pct != null ? `${(t.pnl_pct * 100).toFixed(2)}%` : '—'}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-400">{t.hold_days?.toFixed(0) ?? '—'}</td>
                    <td className="px-4 py-2 text-xs text-gray-500">{t.exit_reason ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {trades?.length === 0 && (
              <div className="text-gray-500 text-center py-6 text-sm">暂无成交</div>
            )}
          </div>
        </>
      )}
      {bt.status === 'failed' && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          Backtest failed. Check system logs for details.
        </div>
      )}
    </div>
  )
}
