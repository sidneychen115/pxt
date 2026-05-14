import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchStrategies, updateStrategy } from '../api/strategies'
import type { Strategy } from '../types'
import {
  STRATEGY_TIMEFRAME_ORDER,
  describeLiveSchedule,
  timeframeLabel,
} from '../lib/strategyTimeframes'

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
                <div className="text-xs text-gray-500 mt-1 space-y-0.5">
                  <div>
                    跟踪周期：
                    {s.timeframes.length ? s.timeframes.map(tf => timeframeLabel(tf)).join('、') : '—'}
                  </div>
                  <div>
                    {describeLiveSchedule(s.run_interval_minutes, s.run_anchor_timeframe, s.timeframes)}
                  </div>
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
      {editing && (
        <StrategyEditModal
          strategy={editing}
          onClose={() => {
            setEditing(null)
            qc.invalidateQueries({ queryKey: ['strategies'] })
          }}
        />
      )}
    </div>
  )
}

function StrategyEditModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [symbols, setSymbols] = useState(strategy.symbols.join(', '))
  const [selectedTf, setSelectedTf] = useState<Set<string>>(() => new Set(strategy.timeframes))
  const mutation = useMutation({
    mutationFn: () => {
      const ordered = STRATEGY_TIMEFRAME_ORDER.filter(tf => selectedTf.has(tf))
      if (ordered.length === 0) {
        throw new Error('请至少选择一个 K 线周期')
      }
      return updateStrategy(strategy.id, {
        symbols: symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean),
        timeframes: ordered,
      })
    },
    onSuccess: onClose,
  })
  const toggleTf = (tf: string) => {
    setSelectedTf(prev => {
      const next = new Set(prev)
      if (next.has(tf)) next.delete(tf)
      else next.add(tf)
      return next
    })
  }
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl p-6 w-full max-w-md border border-gray-700 space-y-4">
        <h2 className="text-lg font-bold">编辑：{strategy.name}</h2>
        <div>
          <label htmlFor="symbols-input" className="text-xs text-gray-400">跟踪标的（英文逗号分隔）</label>
          <input id="symbols-input" value={symbols} onChange={e => setSymbols(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
        </div>
        <div>
          <span className="text-xs text-gray-400">K 线周期（可多选）</span>
          <p className="text-[11px] text-gray-500 mt-1 mb-2">
            启用后按所选周期中最短 K 线同步数据并执行策略，无需填写 Cron。
          </p>
          <div className="flex flex-wrap gap-2">
            {STRATEGY_TIMEFRAME_ORDER.map(tf => (
              <label
                key={tf}
                className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border cursor-pointer ${
                  selectedTf.has(tf)
                    ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                    : 'border-gray-700 bg-gray-800/60 text-gray-400'
                }`}
              >
                <input
                  type="checkbox"
                  className="rounded border-gray-600"
                  checked={selectedTf.has(tf)}
                  onChange={() => toggleTf(tf)}
                />
                {timeframeLabel(tf)}
              </label>
            ))}
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">Cancel</button>
          <button
            onClick={() => mutation.mutate()}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded font-semibold"
          >
            {mutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 text-xs">
            {mutation.error instanceof Error ? mutation.error.message : '保存失败'}
          </p>
        )}
      </div>
    </div>
  )
}
