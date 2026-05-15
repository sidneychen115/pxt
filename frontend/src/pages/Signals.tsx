import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchSignals } from '../api/signals'
import SignalBadge from '../components/SignalBadge'
import type { Signal } from '../types'

type SortKey =
  | 'direction'
  | 'symbol'
  | 'strategy_id'
  | 'order_type'
  | 'confidence'
  | 'status'
  | 'created_at'

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
    case 'created_at':
      return mul * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
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

export default function Signals() {
  const [status, setStatus] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: signals, isLoading } = useQuery({
    queryKey: ['signals', status],
    queryFn: () => fetchSignals({ status: status || undefined, limit: 100 }),
    refetchInterval: 60_000,
  })

  const sortedSignals = useMemo(() => {
    if (!signals?.length) return []
    return [...signals].sort((a, b) => compareSignals(a, b, sortKey, sortDir))
  }, [signals, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'created_at' || key === 'confidence' ? 'desc' : 'asc')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Signals</h1>
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
      <p className="text-xs text-gray-500 -mt-4">
        信号供人工或自动下单参考；请根据 Symbol 与 Reasoning 自行判断，未必已成交。Confidence
        表示突破 band 的强度（非模型概率）。点击表头可排序。
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
                  label="Time"
                  column="created_at"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                />
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
                    {new Date(s.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!isLoading && sortedSignals.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">No signals found.</div>
        )}
      </div>
    </div>
  )
}
