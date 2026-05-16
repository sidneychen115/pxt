import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchSignalRuns, fetchSignals } from '../api/signals'
import type { SignalRun } from '../types'
import ExecuteSignalModal from '../components/ExecuteSignalModal'
import SignalBadge from '../components/SignalBadge'
import { formatChicagoDateTime } from '../lib/formatTime'
import type { Signal } from '../types'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

type SortKey =
  | 'direction'
  | 'symbol'
  | 'strategy_id'
  | 'order_type'
  | 'confidence'
  | 'status'
  | 'signal_time'

type SortDir = 'asc' | 'desc'

function compareSignals(a: Signal, b: Signal, key: SortKey, dir: SortDir): number {
  const mul = dir === 'asc' ? 1 : -1
  const str = (x: string | null | undefined) => (x ?? '').toLowerCase()
  switch (key) {
    case 'direction':
      return mul * str(a.direction).localeCompare(str(b.direction))
    case 'symbol':
      return mul * str(a.symbol).localeCompare(str(b.symbol))
    case 'strategy_id':
      return mul * str(a.strategy_id).localeCompare(str(b.strategy_id))
    case 'order_type':
      return mul * str(a.order_type).localeCompare(str(b.order_type))
    case 'confidence': {
      const av = a.confidence ?? -1
      const bv = b.confidence ?? -1
      return mul * (av - bv)
    }
    case 'status':
      return mul * str(a.status).localeCompare(str(b.status))
    case 'signal_time':
      return mul * (new Date(a.signal_time).getTime() - new Date(b.signal_time).getTime())
    default:
      return 0
  }
}

function SortableTh({
  label,
  column,
  sortKey,
  sortDir,
  onSort,
  align = 'left',
}: {
  label: string
  column: SortKey
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  align?: 'left' | 'right'
}) {
  const active = sortKey === column
  return (
    <th className={`px-4 py-3 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-1 text-xs font-medium hover:text-gray-200 ${
          active ? 'text-gray-200' : 'text-gray-400'
        }`}
      >
        {label}
        <span className="text-[10px] text-gray-500" aria-hidden>
          {active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}

function runOptionLabel(run: SignalRun): string {
  return `${formatChicagoDateTime(run.signal_time)} · ${run.strategy_id} (${run.signal_count})`
}

export default function Signals() {
  const [status, setStatus] = useState('')
  const [selectedRunTime, setSelectedRunTime] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [executeSignal, setExecuteSignal] = useState<Signal | null>(null)
  const runsKey = useAuthQueryKey('signal-runs')

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: runsKey,
    queryFn: () => fetchSignalRuns({ limit: 100 }),
    refetchInterval: 60_000,
  })

  const activeRunTime = selectedRunTime || runs?.[0]?.signal_time
  const signalsKey = useAuthQueryKey('signals', status, activeRunTime)

  const { data: signals, isLoading: signalsLoading } = useQuery({
    queryKey: signalsKey,
    queryFn: () =>
      fetchSignals({
        status: status || undefined,
        signal_time: activeRunTime,
        limit: 500,
      }),
    enabled: Boolean(activeRunTime),
    refetchInterval: 60_000,
  })

  const isLoading = runsLoading || signalsLoading
  const selectedRun = runs?.find(r => r.signal_time === activeRunTime)

  const sortedSignals = useMemo(() => {
    if (!signals?.length) return []
    return [...signals].sort((a, b) => compareSignals(a, b, sortKey, sortDir))
  }, [signals, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'signal_time' || key === 'confidence' ? 'desc' : 'asc')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Signals</h1>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={activeRunTime ?? ''}
            onChange={e => setSelectedRunTime(e.target.value)}
            disabled={!runs?.length}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm max-w-md"
            aria-label="Strategy run"
          >
            {runs?.map(run => (
              <option key={`${run.strategy_id}-${run.signal_time}`} value={run.signal_time}>
                {runOptionLabel(run)}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="notified">Notified</option>
            <option value="executed">Executed</option>
          </select>
        </div>
      </div>
      <p className="text-xs text-gray-500 -mt-2">
        信号供人工或自动下单参考；请根据 Symbol 与 Reasoning 自行判断，未必已成交。Confidence
        表示突破 band 的强度（非模型概率）。时间列为策略产生时刻（America/Chicago）。通过上方下拉选择某次策略运行产生的整批信号。
        {selectedRun && (
          <span className="text-gray-400">
            {' '}
            当前批次：{selectedRun.signal_count} 条 · {selectedRun.strategy_id}
          </span>
        )}
      </p>
      {isLoading && <div className="text-gray-400">Loading...</div>}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="border-b border-gray-800">
                <SortableTh
                  label="Signal"
                  column="direction"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Symbol"
                  column="symbol"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Strategy"
                  column="strategy_id"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <th className="px-4 py-3 text-left text-xs text-gray-400 font-medium">Reasoning</th>
                <SortableTh
                  label="Order"
                  column="order_type"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Confidence"
                  column="confidence"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                  align="right"
                />
                <SortableTh
                  label="Status"
                  column="status"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <SortableTh
                  label="Signal time (CT)"
                  column="signal_time"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
                <th className="px-4 py-3 text-right text-xs text-gray-400 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedSignals.map(s => (
                <tr key={s.id} className="border-b border-gray-800/50 hover:bg-gray-800/40 align-top">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <SignalBadge direction={s.direction} />
                  </td>
                  <td className="px-4 py-3 font-mono font-semibold text-gray-100 whitespace-nowrap">
                    {s.symbol ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs whitespace-nowrap">
                    {s.strategy_id}
                  </td>
                  <td className="px-4 py-3 text-gray-300 text-xs max-w-md">
                    {s.reasoning ? (
                      <span className="block leading-relaxed break-words" title={s.reasoning}>
                        {s.reasoning}
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{s.order_type}</td>
                  <td className="px-4 py-3 text-right text-gray-300 whitespace-nowrap">
                    {s.confidence != null ? `${(s.confidence * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-xs text-gray-400">{s.status}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatChicagoDateTime(s.signal_time)}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {(s.status === 'pending' || s.status === 'notified') &&
                      (s.direction === 'buy' || s.direction === 'sell') && (
                        <button
                          type="button"
                          onClick={() => setExecuteSignal(s)}
                          className="text-xs px-2 py-1 rounded border border-blue-700 text-blue-400 hover:bg-blue-900/40"
                        >
                          {s.direction === 'buy' ? '开仓' : '平仓'}
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!isLoading && !runs?.length && (
          <div className="text-gray-500 text-sm text-center py-8">尚无策略运行产生的信号。</div>
        )}
        {!isLoading && runs?.length && sortedSignals.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">该批次下没有符合筛选条件的信号。</div>
        )}
      </div>
      {executeSignal && (
        <ExecuteSignalModal signal={executeSignal} onClose={() => setExecuteSignal(null)} />
      )}
    </div>
  )
}
