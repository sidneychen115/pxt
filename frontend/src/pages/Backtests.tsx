import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom'
import {
  fetchBacktests, fetchBacktest, triggerBacktest,
  fetchBacktestTrades, fetchEquityCurve, fetchBacktestOhlc,
} from '../api/backtests'
import { createBacktestPreset, fetchBacktestPresets } from '../api/backtestPresetsApi'
import { fetchStrategies } from '../api/strategies'
import MetricCard from '../components/MetricCard'
import EquityChart from '../components/EquityChart'
import BacktestCandlestickChart from '../components/BacktestCandlestickChart'
import SignalBadge from '../components/SignalBadge'
import BacktestConfigForm from '../components/BacktestConfigForm'
import type { Backtest, BacktestProgressPhase, BacktestTrade } from '../types'
import { isBacktestInProgress } from '../lib/backtestStatus'
import {
  EMPTY_EXIT_FORM,
  exitPolicyFromForm,
  exitPolicyToForm,
  buildRerunPayload,
  sliceIsoDate,
  type ExitFormState,
} from '../lib/backtestFormConfig'
import {
  applyPreset,
  dtoToPreset,
  findMatchingPresetName,
  presetBodyFromSnapshot,
  snapshotFromCurrentForm,
} from '../lib/backtestPresets'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'
import { formatAppDateOnly, formatAppDateTime, formatDurationSeconds } from '../lib/formatTime'
import {
  DEFAULT_BACKTEST_TIMEFRAME,
  extractBacktestTimeframe,
  stringifyBacktestParametersJson,
} from '../lib/backtestTimeframe'
import {
  DEFAULT_BACKTEST_POSITION_PCT,
  extractPositionPctPercent,
  mergeBacktestRunParameters,
} from '../lib/backtestPositionSizing'
import { timeframeLabel } from '../lib/strategyTimeframes'

function formatIsoDateShort(iso: string | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const s = iso.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : iso
}

function fmtPct01(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(2)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

type BacktestSortKey =
  | 'id'
  | 'strategy'
  | 'preset'
  | 'total_return'
  | 'alpha'
  | 'annualized_return'
  | 'sharpe_ratio'
  | 'max_drawdown'
  | 'win_rate'
  | 'profit_factor'
  | 'total_trades'
  | 'avg_hold_days'
  | 'created_at'
  | 'duration_seconds'
  | 'start_date'
  | 'end_date'
  | 'status'

type SortDirection = 'desc' | 'asc'

type SortRule = { key: BacktestSortKey; direction: SortDirection }

/** Normalize metrics for stable numeric sort (avoids string vs number mixed cmp). */
function sortableNumber(v: number | null | undefined): number | null {
  if (v == null) return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function compareSortValues(a: string | number | null, b: string | number | null): number {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'zh-CN', { sensitivity: 'base' })
}

type TradeSortKey =
  | 'symbol'
  | 'direction'
  | 'quantity'
  | 'entry_time'
  | 'entry_price'
  | 'exit_time'
  | 'exit_price'
  | 'pnl'
  | 'pnl_pct'
  | 'hold_days'
  | 'exit_reason'

type TradeSortRule = { key: TradeSortKey; direction: SortDirection }

function isTradeNumericColumn(key: TradeSortKey): boolean {
  return (
    key === 'quantity' ||
    key === 'entry_price' ||
    key === 'exit_price' ||
    key === 'pnl' ||
    key === 'pnl_pct' ||
    key === 'hold_days'
  )
}

const PROGRESS_STEPS: { phase: BacktestProgressPhase; label: string }[] = [
  { phase: 'fetching_data', label: '数据拉取' },
  { phase: 'engine', label: '回测引擎' },
  { phase: 'llm_eval', label: 'LLM 评估' },
]

const PHASE_ORDER: BacktestProgressPhase[] = [
  'queued',
  'worker',
  'fetching_data',
  'engine',
  'llm_eval',
]

function phaseRank(p: BacktestProgressPhase | null | undefined): number {
  if (p == null) return -1
  const i = PHASE_ORDER.indexOf(p)
  return i >= 0 ? i : -1
}

function formatRelativeUpdate(iso: string | null | undefined): string {
  if (iso == null || iso === '') return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (sec < 60) return `${sec} 秒前更新`
  const min = Math.floor(sec / 60)
  if (min < 120) return `${min} 分钟前更新`
  const hr = Math.floor(min / 60)
  return `${hr} 小时前更新`
}

/** Stale HTTP poll must not overwrite newer WebSocket progress while status is running. */
function mergeRunningBacktestProgress(prev: Backtest | undefined, next: Backtest): Backtest {
  if (!prev || prev.id !== next.id) return next
  if (!isBacktestInProgress(prev.status) || !isBacktestInProgress(next.status)) return next
  const pr = phaseRank(prev.progress_phase)
  const nr = phaseRank(next.progress_phase)
  const prevTs = prev.progress_updated_at ? Date.parse(prev.progress_updated_at) : 0
  const nextTs = next.progress_updated_at ? Date.parse(next.progress_updated_at) : 0
  if (pr > nr) {
    return {
      ...next,
      progress_phase: prev.progress_phase,
      progress_message: prev.progress_message ?? next.progress_message,
      progress_updated_at:
        prevTs >= nextTs ? prev.progress_updated_at : next.progress_updated_at,
    }
  }
  if (prevTs > nextTs) {
    return {
      ...next,
      progress_message: prev.progress_message ?? next.progress_message,
      progress_updated_at: prev.progress_updated_at,
    }
  }
  return next
}

function BacktestProgressPanel({ bt }: { bt: Backtest }) {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 5000)
    return () => window.clearInterval(id)
  }, [bt.progress_updated_at])

  const relativeFreshness = useMemo(
    () => formatRelativeUpdate(bt.progress_updated_at),
    [bt.progress_updated_at, tick],
  )

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
        {bt.progress_message ?? (isBacktestInProgress(bt.status) ? '正在启动…' : '')}
      </div>
      {isBacktestInProgress(bt.status) && (
        <div className="text-xs text-gray-500">
          {relativeFreshness || '等待首次进度上报…'}
          <span className="text-gray-600"> · </span>
          若长时间无更新且非 LLM 评估阶段，可能已卡死或进程已退出；超时后系统会自动标为失败。
        </div>
      )}
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
  const backtestsKey = useAuthQueryKey('backtests')
  const presetsKey = useAuthQueryKey('backtest-presets')
  const {
    data: backtests,
    isPending: backtestsPending,
    isError: backtestsError,
    error: backtestsErrorObj,
    refetch: refetchBacktests,
  } = useQuery({
    queryKey: backtestsKey,
    queryFn: () => fetchBacktests(),
  })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const { data: presetDtos } = useQuery({ queryKey: presetsKey, queryFn: fetchBacktestPresets })
  const presets = useMemo(() => (presetDtos ?? []).map(dtoToPreset), [presetDtos])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    strategy_id: '',
    timeframe: DEFAULT_BACKTEST_TIMEFRAME,
    position_pct_percent: DEFAULT_BACKTEST_POSITION_PCT * 100,
    start_date: '2023-01-01',
    end_date: '2024-01-01',
    symbols: '',
    initial_capital: 100000,
  })
  const [exitPolicy, setExitPolicy] = useState<ExitFormState>(() => ({ ...EMPTY_EXIT_FORM }))
  const [parametersJson, setParametersJson] = useState('{}')
  const [loadPresetSelect, setLoadPresetSelect] = useState('')
  const [savePresetName, setSavePresetName] = useState('')
  const [sortRules, setSortRules] = useState<SortRule[]>([])

  const sortedRows = useMemo(() => {
    const rows = (backtests ?? []).map((bt, idx) => ({
      bt,
      strategyName: strategies?.find(s => s.id === bt.strategy_id)?.name ?? bt.strategy_id,
      presetLabel: findMatchingPresetName(bt, presets) ?? '—',
      idx,
    }))
    if (sortRules.length === 0) return rows

    const valueByKey = (row: (typeof rows)[number], key: BacktestSortKey): string | number | null => {
      const { bt, strategyName, presetLabel } = row
      switch (key) {
        case 'id':
          return bt.id
        case 'strategy':
          return strategyName
        case 'preset':
          return presetLabel
        case 'total_return':
          return sortableNumber(bt.total_return)
        case 'alpha':
          return sortableNumber(bt.alpha_vs_benchmark)
        case 'annualized_return':
          return sortableNumber(bt.annualized_return)
        case 'sharpe_ratio':
          return sortableNumber(bt.sharpe_ratio)
        case 'max_drawdown':
          return sortableNumber(bt.max_drawdown)
        case 'win_rate':
          return sortableNumber(bt.win_rate)
        case 'profit_factor':
          return sortableNumber(bt.profit_factor)
        case 'total_trades':
          return sortableNumber(bt.total_trades)
        case 'avg_hold_days':
          return sortableNumber(bt.avg_hold_days)
        case 'created_at':
          return new Date(bt.created_at).getTime()
        case 'duration_seconds':
          return sortableNumber(bt.duration_seconds)
        case 'start_date':
          return new Date(bt.start_date).getTime()
        case 'end_date':
          return new Date(bt.end_date).getTime()
        case 'status':
          return bt.status
      }
    }

    return [...rows].sort((a, b) => {
      for (const rule of sortRules) {
        const base = compareSortValues(valueByKey(a, rule.key), valueByKey(b, rule.key))
        if (base !== 0) return rule.direction === 'desc' ? -base : base
      }
      return a.idx - b.idx
    })
  }, [backtests, strategies, presets, sortRules])

  const toggleSort = (key: BacktestSortKey, shiftKey: boolean) => {
    setSortRules(prev => {
      const existing = prev.find(r => r.key === key)
      if (shiftKey) {
        if (!existing) return [...prev, { key, direction: 'desc' }]
        if (existing.direction === 'desc') {
          return prev.map(r => (r.key === key ? { ...r, direction: 'asc' } : r))
        }
        return prev.filter(r => r.key !== key)
      }
      const onlyThis = prev.length === 1 && prev[0].key === key
      if (onlyThis) {
        if (prev[0].direction === 'desc') return [{ key, direction: 'asc' }]
        return []
      }
      return [{ key, direction: 'desc' }]
    })
  }

  const sortBadge = (key: BacktestSortKey): string => {
    const idx = sortRules.findIndex(r => r.key === key)
    if (idx < 0) return ''
    const dir = sortRules[idx].direction === 'desc' ? '▼' : '▲'
    return `${dir}${idx + 1}`
  }

  useEffect(() => {
    const raw = (location.state as { prefillFromBacktest?: Backtest } | null)?.prefillFromBacktest
    if (!raw) return
    const params = raw.parameters ?? {}
    setForm({
      strategy_id: raw.strategy_id,
      timeframe: extractBacktestTimeframe(params),
      position_pct_percent: extractPositionPctPercent(params),
      start_date: sliceIsoDate(raw.start_date),
      end_date: sliceIsoDate(raw.end_date),
      symbols: raw.symbols.join(', '),
      initial_capital: raw.initial_capital,
    })
    setExitPolicy(exitPolicyToForm(raw.exit_policy))
    setParametersJson(stringifyBacktestParametersJson(params))
    setShowForm(true)
    navigate('/backtests', { replace: true, state: {} })
  }, [location.state, navigate])

  const savePresetMutation = useMutation({
    mutationFn: async () => {
      const name = savePresetName.trim()
      if (!name) throw new Error('请填写预设名称')
      const snap = snapshotFromCurrentForm(form, exitPolicy, parametersJson)
      return createBacktestPreset(presetBodyFromSnapshot(snap, name))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: presetsKey })
      setSavePresetName('')
    },
  })

  const triggerMutation = useMutation({
    mutationFn: () => {
      let parameters: Record<string, unknown>
      try {
        parameters = mergeBacktestRunParameters(
          parametersJson,
          form.timeframe,
          form.position_pct_percent,
        )
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
      qc.invalidateQueries({ queryKey: backtestsKey })
      navigate(`/backtests/${data.id}`)
    },
  })

  const applyLoadedPreset = (id: string) => {
    const p = presets.find(x => x.id === id)
    if (!p) return
    const snap = applyPreset(p)
    setForm({
      strategy_id: snap.strategy_id,
      timeframe: snap.timeframe,
      position_pct_percent: snap.position_pct_percent,
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
          <Link
            to="/backtests/presets"
            className="px-3 py-2 text-sm rounded border border-gray-700 bg-gray-800/80 text-gray-200 hover:bg-gray-800"
          >
            预设管理
          </Link>
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
          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
            <p className="text-xs text-gray-500 mb-2">
              预设保存在服务器数据库。完整增删改请到
              <Link to="/backtests/presets" className="text-blue-400 hover:underline mx-1">
                预设管理
              </Link>
              。
            </p>
            <div className="flex flex-wrap items-end gap-3">
              {presets.length > 0 && (
                <div>
                  <label className="text-xs text-gray-400 block">加载预设</label>
                  <select
                    value={loadPresetSelect}
                    onChange={(e) => {
                      const id = e.target.value
                      setLoadPresetSelect('')
                      if (!id) return
                      applyLoadedPreset(id)
                    }}
                    className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1 min-w-[180px]"
                  >
                    <option value="">选择预设…</option>
                    {presets.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex-1 min-w-[140px] max-w-xs">
                <label className="text-xs text-gray-400 block">保存为预设</label>
                <input
                  type="text"
                  value={savePresetName}
                  onChange={e => setSavePresetName(e.target.value)}
                  placeholder="新预设名称"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  savePresetMutation.mutate(undefined, {
                    onError: err => {
                      window.alert(err instanceof Error ? err.message : '保存失败')
                    },
                  })
                }}
                disabled={savePresetMutation.isPending}
                className="px-3 py-2 bg-emerald-700 hover:bg-emerald-600 rounded text-sm font-semibold disabled:opacity-50"
              >
                {savePresetMutation.isPending ? '保存中…' : '保存预设'}
              </button>
            </div>
          </div>
          <BacktestConfigForm
            form={form}
            setForm={setForm}
            exitPolicy={exitPolicy}
            setExitPolicy={setExitPolicy}
            parametersJson={parametersJson}
            setParametersJson={setParametersJson}
            strategies={strategies}
          />
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
      {backtestsError && (
        <div className="rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-200 space-y-2">
          <p>
            无法加载回测列表：
            {backtestsErrorObj instanceof Error ? backtestsErrorObj.message : '请求失败'}
          </p>
          <p className="text-xs text-red-300/90">
            常见原因：浏览器访问的站点与后端 API 不通、数据库未就绪、或回测接口超时。请打开开发者工具 → Network
            查看 <code className="text-red-100">/api/backtests/</code> 是否失败或挂起。
          </p>
          <button
            type="button"
            onClick={() => refetchBacktests()}
            className="px-3 py-1.5 rounded bg-red-900/80 hover:bg-red-800 text-red-100 text-xs font-medium"
          >
            重试
          </button>
        </div>
      )}
      {backtestsPending && !backtestsError && <div className="text-gray-400">Loading...</div>}
      {sortRules.length > 1 && (
        <p className="text-xs text-gray-500 mb-2 px-1">
          多列排序按优先级：仅当左侧列的值并列时，才按下一列排序；两列数值都不同则顺序只由左侧列决定。
        </p>
      )}
      <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/80">
        <table className="min-w-[1280px] w-full text-sm text-left">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wide">
              {([
                ['id', 'ID'],
                ['strategy', '策略'],
                ['preset', '预设'],
                ['total_return', '总收益'],
                ['alpha', 'Alpha'],
                ['annualized_return', '年化'],
                ['sharpe_ratio', '夏普'],
                ['max_drawdown', '最大回撤'],
                ['win_rate', '胜率'],
                ['profit_factor', '盈利因子'],
                ['total_trades', '交易数'],
                ['avg_hold_days', '均持仓'],
                ['created_at', '创建时间'],
                ['duration_seconds', '耗时'],
                ['start_date', '区间起'],
                ['end_date', '区间止'],
                ['status', '状态'],
              ] as [BacktestSortKey, string][]).map(([key, label]) => (
                <th
                  key={key}
                  className={`px-3 py-2.5 font-medium whitespace-nowrap ${key === 'preset' ? 'min-w-[100px]' : ''} ${
                    key === 'created_at' ? 'min-w-[130px]' : ''
                  }`}
                >
                  <button
                    type="button"
                    onClick={e => toggleSort(key, e.shiftKey)}
                    className="inline-flex items-center gap-1 hover:text-gray-300"
                    title="单击：单列排序（降序→升序→取消）；Shift+单击：追加为多列排序（下一列仅在上一列并列时生效）"
                  >
                    <span>{label}</span>
                    <span className="text-[10px] text-gray-400 min-w-[20px] text-left">{sortBadge(key)}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {backtests?.length === 0 && (
              <tr>
                <td colSpan={17} className="px-3 py-8 text-center text-gray-500">
                  暂无回测记录。点击「New Backtest」开始。
                </td>
              </tr>
            )}
            {sortedRows.map(({ bt, strategyName, presetLabel }, idx) => {
              return (
                <tr
                  key={bt.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/backtests/${bt.id}`)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') navigate(`/backtests/${bt.id}`)
                  }}
                  className={`border-b border-gray-800/80 hover:bg-gray-800/60 cursor-pointer ${
                    idx % 2 === 0 ? 'bg-gray-900/40' : 'bg-gray-900/20'
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-gray-400 whitespace-nowrap">{bt.id}</td>
                  <td className="px-3 py-2 text-gray-100 font-medium whitespace-nowrap max-w-[160px] truncate" title={strategyName}>
                    {strategyName}
                  </td>
                  <td className="px-3 py-2 text-gray-300 max-w-[140px] truncate" title={presetLabel === '—' ? undefined : presetLabel}>
                    {presetLabel}
                  </td>
                  <td
                    className={`px-3 py-2 whitespace-nowrap ${
                      bt.total_return != null
                        ? bt.total_return >= 0
                          ? 'text-green-400'
                          : 'text-red-400'
                        : 'text-gray-500'
                    }`}
                  >
                    {fmtPct01(bt.total_return)}
                  </td>
                  <td
                    className={`px-3 py-2 whitespace-nowrap ${
                      bt.alpha_vs_benchmark != null
                        ? bt.alpha_vs_benchmark >= 0
                          ? 'text-green-400'
                          : 'text-red-400'
                        : 'text-gray-500'
                    }`}
                  >
                    {fmtPct01(bt.alpha_vs_benchmark)}
                  </td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtPct01(bt.annualized_return)}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtNum(bt.sharpe_ratio)}</td>
                  <td className="px-3 py-2 text-red-300/90 whitespace-nowrap">{fmtPct01(bt.max_drawdown)}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtPct01(bt.win_rate)}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtNum(bt.profit_factor)}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap tabular-nums">
                    {bt.total_trades != null ? String(bt.total_trades) : '—'}
                  </td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtNum(bt.avg_hold_days, 1)}</td>
                  <td className="px-3 py-2 text-gray-400 text-xs whitespace-nowrap">{formatAppDateTime(bt.created_at)}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap tabular-nums">
                    {formatDurationSeconds(bt.duration_seconds)}
                    {isBacktestInProgress(bt.status) && bt.duration_seconds != null && (
                      <span className="text-gray-500 text-[10px] ml-1">进行中</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{formatIsoDateShort(bt.start_date)}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{formatIsoDateShort(bt.end_date)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        bt.status === 'completed'
                          ? 'bg-green-900/80 text-green-300'
                          : bt.status === 'failed'
                            ? 'bg-red-900/80 text-red-300'
                            : 'bg-yellow-900/80 text-yellow-300'
                      }`}
                    >
                      {bt.status}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BacktestDetail({ id }: { id: number }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const backtestKey = useAuthQueryKey('backtest', id)
  const backtestsKey = useAuthQueryKey('backtests')
  const btTradesKey = useAuthQueryKey('bt-trades', id)
  const btEquityKey = useAuthQueryKey('bt-equity', id)
  const [tradeSortRules, setTradeSortRules] = useState<TradeSortRule[]>([])
  const [chartSymbol, setChartSymbol] = useState<string | null>(null)
  const btOhlcKey = useAuthQueryKey('bt-ohlc', id, chartSymbol)
  const [chartFocusTradeId, setChartFocusTradeId] = useState<number | null>(null)
  const { data: bt, isLoading } = useQuery({
    queryKey: backtestKey,
    queryFn: async () => {
      const next = await fetchBacktest(id)
      return mergeRunningBacktestProgress(qc.getQueryData<Backtest>(backtestKey), next)
    },
    refetchInterval: (q) => (isBacktestInProgress(q.state.data?.status) ? 2500 : false),
  })

  useEffect(() => {
    if (!isBacktestInProgress(bt?.status)) return
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
            progress_updated_at?: string | null
          }
        }
        if (msg.channel !== 'backtest_progress' || msg.data.backtest_id !== id) return
        if (msg.data.status === 'completed' || msg.data.status === 'failed') {
          qc.invalidateQueries({ queryKey: backtestKey })
          qc.invalidateQueries({ queryKey: backtestsKey })
          qc.invalidateQueries({ queryKey: btOhlcKey })
          qc.invalidateQueries({ queryKey: btTradesKey })
          qc.invalidateQueries({ queryKey: btEquityKey })
          return
        }
        qc.setQueryData(backtestKey, (prev: Backtest | undefined) => {
          if (!prev) return prev
          const ph = msg.data.phase
          return {
            ...prev,
            progress_phase:
              ph === 'fetching_data' || ph === 'engine' || ph === 'llm_eval'
                ? ph
                : prev.progress_phase,
            progress_message: msg.data.message ?? prev.progress_message,
            progress_updated_at: msg.data.progress_updated_at ?? prev.progress_updated_at,
          }
        })
      } catch {
        /* malformed message */
      }
    }
    return () => {
      ws.close()
    }
  }, [id, bt?.status, qc, backtestKey, backtestsKey, btOhlcKey, btTradesKey, btEquityKey])

  useEffect(() => {
    if (!bt?.symbols?.length) return
    setChartSymbol(prev => (prev && bt.symbols.includes(prev) ? prev : bt.symbols[0]))
  }, [bt?.id, bt?.symbols])

  useEffect(() => {
    setChartFocusTradeId(null)
  }, [bt?.id])

  const chartSym =
    chartSymbol && bt?.symbols?.includes(chartSymbol) ? chartSymbol : (bt?.symbols?.[0] ?? '')

  const { data: trades } = useQuery({
    queryKey: btTradesKey,
    queryFn: () => fetchBacktestTrades(id),
    enabled: bt?.status === 'completed',
  })

  const sortedTradeRows = useMemo(() => {
    const raw = trades ?? []
    const rows = raw.map((t, idx) => ({ t, idx }))
    if (tradeSortRules.length === 0) return rows

    const valueByKey = (row: { t: BacktestTrade; idx: number }, key: TradeSortKey): string | number | null => {
      const { t } = row
      switch (key) {
        case 'symbol':
          return t.symbol
        case 'direction':
          return t.direction
        case 'quantity':
          return sortableNumber(t.quantity)
        case 'entry_time':
          return new Date(t.entry_time).getTime()
        case 'entry_price':
          return sortableNumber(t.entry_price)
        case 'exit_time':
          return t.exit_time ? new Date(t.exit_time).getTime() : null
        case 'exit_price':
          return sortableNumber(t.exit_price)
        case 'pnl':
          return sortableNumber(t.pnl)
        case 'pnl_pct':
          return sortableNumber(t.pnl_pct)
        case 'hold_days':
          return sortableNumber(t.hold_days)
        case 'exit_reason':
          return t.exit_reason ?? null
      }
    }

    return [...rows].sort((a, b) => {
      for (const rule of tradeSortRules) {
        const base = compareSortValues(valueByKey(a, rule.key), valueByKey(b, rule.key))
        if (base !== 0) return rule.direction === 'desc' ? -base : base
      }
      return a.idx - b.idx
    })
  }, [trades, tradeSortRules])

  const toggleTradeSort = (key: TradeSortKey, shiftKey: boolean) => {
    setTradeSortRules(prev => {
      const existing = prev.find(r => r.key === key)
      if (shiftKey) {
        if (!existing) return [...prev, { key, direction: 'desc' }]
        if (existing.direction === 'desc') {
          return prev.map(r => (r.key === key ? { ...r, direction: 'asc' } : r))
        }
        return prev.filter(r => r.key !== key)
      }
      const onlyThis = prev.length === 1 && prev[0].key === key
      if (onlyThis) {
        if (prev[0].direction === 'desc') return [{ key, direction: 'asc' }]
        return []
      }
      return [{ key, direction: 'desc' }]
    })
  }

  const tradeSortBadge = (key: TradeSortKey): string => {
    const idx = tradeSortRules.findIndex(r => r.key === key)
    if (idx < 0) return ''
    const dir = tradeSortRules[idx].direction === 'desc' ? '▼' : '▲'
    return `${dir}${idx + 1}`
  }
  const { data: equity } = useQuery({
    queryKey: btEquityKey,
    queryFn: () => fetchEquityCurve(id),
    enabled: bt?.status === 'completed',
  })

  const {
    data: ohlc,
    isPending: ohlcPending,
    isError: ohlcError,
    error: ohlcErrorObj,
  } = useQuery({
    queryKey: btOhlcKey,
    queryFn: () => fetchBacktestOhlc(id, { symbol: chartSym }),
    enabled: bt?.status === 'completed' && chartSym.length > 0,
  })

  const rerunMutation = useMutation({
    mutationFn: (payload: Parameters<typeof triggerBacktest>[0]) => triggerBacktest(payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: backtestsKey })
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
          <span className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-300">
            {timeframeLabel(extractBacktestTimeframe(bt.parameters ?? {}))}
          </span>
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
      {isBacktestInProgress(bt.status) && <BacktestProgressPanel bt={bt} />}
      {bt.status === 'failed' && bt.error_message && (
        <div className="rounded-xl border border-red-800/60 bg-red-950/30 px-4 py-3 text-sm text-red-200">
          <p className="font-semibold text-red-300 mb-1">失败原因</p>
          <p className="whitespace-pre-wrap break-words">{bt.error_message}</p>
        </div>
      )}
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
            <MetricCard
              label={`${String(bt.parameters?.benchmark_symbol ?? 'SPY')} buy-hold`}
              value={
                bt.benchmark_total_return != null
                  ? `${(bt.benchmark_total_return * 100).toFixed(2)}%`
                  : '—'
              }
              color="gray"
            />
            <MetricCard
              label="Alpha vs benchmark"
              value={
                bt.alpha_vs_benchmark != null
                  ? `${(bt.alpha_vs_benchmark * 100).toFixed(2)}%`
                  : '—'
              }
              color={
                bt.alpha_vs_benchmark != null && bt.alpha_vs_benchmark >= 0 ? 'green' : 'red'
              }
            />
          </div>
          {bt.pnl_by_symbol != null && bt.pnl_by_symbol.length > 0 && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">按标的汇总</h2>
              <p className="text-xs text-gray-500 mb-3">
                由成交明细合并：每个标的的已实现总 P&amp;L（<code className="text-gray-400">sum(pnl)</code>）与平仓笔数（明细行数）。
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm max-w-xl">
                  <thead>
                    <tr className="text-gray-400 text-xs border-b border-gray-800">
                      <th className="py-2 pr-4 font-medium text-left">标的</th>
                      <th className="py-2 pr-4 font-medium text-right">交易次数</th>
                      <th className="py-2 font-medium text-right">总 P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...bt.pnl_by_symbol].sort((a, b) => b.total_pnl - a.total_pnl).map(row => (
                      <tr key={row.symbol} className="border-b border-gray-800/60">
                        <td className="py-2 pr-4 text-gray-200">{row.symbol}</td>
                        <td className="py-2 pr-4 text-right text-gray-300 tabular-nums">{row.trade_count}</td>
                        <td
                          className={`py-2 text-right font-medium tabular-nums ${
                            row.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}
                        >
                          ${row.total_pnl.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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
          {chartSym && (
            <div
              id="backtest-ohlc-panel"
              className="bg-gray-900 rounded-xl p-4 border border-gray-800 scroll-mt-4 min-h-[480px]"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h2 className="text-sm font-semibold text-gray-400">行情与买卖点</h2>
                {bt.symbols.length > 1 && (
                  <label className="text-xs text-gray-500 flex items-center gap-2">
                    <span>标的</span>
                    <select
                      value={chartSym}
                      onChange={e => {
                        setChartSymbol(e.target.value)
                        setChartFocusTradeId(null)
                      }}
                      className="bg-gray-950 border border-gray-700 rounded px-2 py-1 text-gray-200"
                    >
                      {bt.symbols.map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {ohlcPending && <div className="text-gray-400 text-sm">加载 K 线…</div>}
              {ohlcError && (
                <p className="text-red-400 text-sm">
                  无法加载 K 线：
                  {ohlcErrorObj instanceof Error ? ohlcErrorObj.message : '请求失败'}
                </p>
              )}
              {ohlc && ohlc.bars.length === 0 && !ohlcPending && !ohlcError && (
                <p className="text-gray-500 text-sm">该窗口无可用 K 线数据。</p>
              )}
              {ohlc && ohlc.bars.length > 0 && trades && (
                <div className="w-full min-h-[560px]">
                  <BacktestCandlestickChart
                    ohlc={ohlc}
                    trades={trades.filter(t => t.symbol === chartSym)}
                    focusTradeId={chartFocusTradeId}
                  />
                </div>
              )}
              {ohlc && ohlc.bars.length > 0 && (
                <p className="text-xs text-gray-500 mt-2">周期：{ohlc.timeframe}</p>
              )}
            </div>
          )}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h2 className="text-sm font-semibold text-gray-300">成交明细</h2>
              <p className="text-xs text-gray-500 mt-1">
                表头可排序：单击单列（降序→升序→取消）；Shift+单击追加多列排序。
                {tradeSortRules.length > 1 && ' 多列时仅当左侧列并列时才用下一列。'}
                {' '}
                单击某一行可跳转到上方 K 线并缩放到该笔买卖点附近。
              </p>
            </div>
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[960px]">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs">
                  {([
                    ['symbol', '标的'],
                    ['direction', '方向'],
                    ['quantity', '数量'],
                    ['entry_time', '买入时间'],
                    ['entry_price', '买入价'],
                    ['exit_time', '卖出时间'],
                    ['exit_price', '卖出价'],
                    ['pnl', 'P&L'],
                    ['pnl_pct', '收益率'],
                    ['hold_days', '天数'],
                    ['exit_reason', '原因'],
                  ] as [TradeSortKey, string][]).map(([key, label]) => (
                    <th
                      key={key}
                      className={`px-4 py-2 whitespace-nowrap font-medium ${isTradeNumericColumn(key) ? 'text-right' : 'text-left'}`}
                    >
                      <button
                        type="button"
                        onClick={e => toggleTradeSort(key, e.shiftKey)}
                        className={`inline-flex items-center gap-1 hover:text-gray-300 ${
                          isTradeNumericColumn(key) ? 'justify-end w-full' : ''
                        }`}
                        title="单击：单列排序（降序→升序→取消）；Shift+单击：追加为多列排序"
                      >
                        <span>{label}</span>
                        <span className="text-[10px] text-gray-400 min-w-[20px] text-left">{tradeSortBadge(key)}</span>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedTradeRows.map(({ t }) => (
                  <tr
                    key={t.id}
                    role="button"
                    tabIndex={0}
                    title="跳转到 K 线与买卖点"
                    onClick={() => {
                      setChartSymbol(t.symbol)
                      setChartFocusTradeId(t.id)
                      requestAnimationFrame(() => {
                        document.getElementById('backtest-ohlc-panel')?.scrollIntoView({
                          behavior: 'smooth',
                          block: 'start',
                        })
                      })
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setChartSymbol(t.symbol)
                        setChartFocusTradeId(t.id)
                        requestAnimationFrame(() => {
                          document.getElementById('backtest-ohlc-panel')?.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start',
                          })
                        })
                      }
                    }}
                    className={`border-b border-gray-800/40 hover:bg-gray-800/30 cursor-pointer ${
                      chartFocusTradeId === t.id ? 'bg-slate-800/50 ring-1 ring-inset ring-blue-500/40' : ''
                    }`}
                  >
                    <td className="px-4 py-2 font-mono font-semibold text-gray-200">{t.symbol}</td>
                    <td className="px-4 py-2"><SignalBadge direction={t.direction} /></td>
                    <td className="px-4 py-2 text-right text-gray-300">{t.quantity}</td>
                    <td className="px-4 py-2 text-left text-gray-300 whitespace-nowrap tabular-nums">
                      {formatAppDateOnly(t.entry_time)}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-300 tabular-nums">${t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2 text-left text-gray-300 whitespace-nowrap tabular-nums">
                      {formatAppDateOnly(t.exit_time)}
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
            {(trades?.length ?? 0) === 0 && (
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
