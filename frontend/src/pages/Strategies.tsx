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
          <label htmlFor="symbols-input" className="text-xs text-gray-400">Symbols (comma separated)</label>
          <input id="symbols-input" value={symbols} onChange={e => setSymbols(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1" />
        </div>
        <div>
          <label htmlFor="frequency-input" className="text-xs text-gray-400">Cron Schedule</label>
          <input id="frequency-input" value={frequency} onChange={e => setFrequency(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1 font-mono" />
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
      </div>
    </div>
  )
}
