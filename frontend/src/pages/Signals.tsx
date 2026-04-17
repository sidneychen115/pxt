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
