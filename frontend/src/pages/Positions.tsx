import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchPositions } from '../api/positions'
import ManualPositionModal from '../components/ManualPositionModal'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

export default function Positions() {
  const positionsKey = useAuthQueryKey('positions')
  const [manualOpen, setManualOpen] = useState(false)
  const { data: positions, isLoading } = useQuery({
    queryKey: positionsKey,
    queryFn: fetchPositions,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Positions</h1>
          <p className="text-xs text-gray-500 mt-1">
            持仓一览。可手动录入已有仓位，或通过{' '}
            <Link to="/signals" className="text-blue-400 hover:underline">
              Signals
            </Link>{' '}
            执行信号开平仓。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setManualOpen(true)}
          className="shrink-0 px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-500"
        >
          手动开仓
        </button>
      </div>
      {isLoading && <p className="text-gray-400 text-sm">Loading…</p>}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-xs">
              <th className="px-4 py-3 text-left">Symbol</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Avg cost</th>
              <th className="px-4 py-3 text-right">Mark</th>
              <th className="px-4 py-3 text-right">Value</th>
            </tr>
          </thead>
          <tbody>
            {positions?.map(p => (
              <tr key={p.symbol} className="border-b border-gray-800/50">
                <td className="px-4 py-3 font-mono font-semibold">{p.symbol}</td>
                <td className="px-4 py-3 text-right">{p.quantity}</td>
                <td className="px-4 py-3 text-right">${p.avg_cost.toFixed(2)}</td>
                <td className="px-4 py-3 text-right">
                  {p.mark_price != null ? `$${p.mark_price.toFixed(2)}` : '—'}
                </td>
                <td className="px-4 py-3 text-right">${p.market_value.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && !positions?.length && (
          <p className="text-gray-500 text-sm text-center py-8">No open positions.</p>
        )}
      </div>
      {manualOpen && <ManualPositionModal onClose={() => setManualOpen(false)} />}
    </div>
  )
}
