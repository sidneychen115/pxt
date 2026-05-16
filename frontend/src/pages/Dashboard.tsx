import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchHealth } from '../api/system'
import { fetchMyStrategies } from '../api/meStrategies'
import { fetchSignals } from '../api/signals'
import { fetchPositionSummary } from '../api/positions'
import type { Signal } from '../types'
import MetricCard from '../components/MetricCard'
import SignalBadge from '../components/SignalBadge'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

export default function Dashboard() {
  const strategiesKey = useAuthQueryKey('my-strategies')
  const summaryKey = useAuthQueryKey('position-summary')
  const signalsKey = useAuthQueryKey('signals', 'dashboard')

  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 30_000 })
  const { data: strategies } = useQuery({ queryKey: strategiesKey, queryFn: fetchMyStrategies })
  const { data: summary } = useQuery({ queryKey: summaryKey, queryFn: fetchPositionSummary })
  const { data: signals } = useQuery({
    queryKey: signalsKey,
    queryFn: () => fetchSignals({ limit: 3 }),
  })

  const activeCount = strategies?.filter(s => s.is_active).length ?? 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard
          label="System"
          value={health?.status === 'ok' ? 'Online' : 'Offline'}
          color={health?.status === 'ok' ? 'green' : 'red'}
        />
        <MetricCard label="Active Strategies" value={activeCount} color="blue" />
        <MetricCard label="Open Symbols" value={summary?.open_symbols ?? 0} />
        <MetricCard label="Total Shares" value={summary?.total_shares ?? 0} />
        <MetricCard
          label="Position Value"
          value={
            summary?.position_value != null
              ? `$${summary.position_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
              : '—'
          }
        />
        <MetricCard label="Recent Signals" value={signals?.length ?? 0} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-400">Recent Signals</h2>
            <Link to="/signals" className="text-xs text-blue-400 hover:underline">
              View all
            </Link>
          </div>
          {signals?.length === 0 && <p className="text-gray-500 text-sm">No signals yet.</p>}
          <div className="space-y-2">
            {signals?.map((s: Signal) => (
              <div key={s.id} className="flex items-center gap-2 text-sm flex-wrap">
                <SignalBadge direction={s.direction} />
                <span className="font-mono font-semibold">{s.symbol ?? '—'}</span>
                <span className="text-gray-500 text-xs">{s.strategy_id}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 min-h-[120px]">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-400">Positions</h2>
            <Link to="/positions" className="text-xs text-blue-400 hover:underline">
              Details
            </Link>
          </div>
          <p className="text-gray-500 text-sm">
            {summary?.open_symbols
              ? `${summary.open_symbols} symbol(s), ${summary.total_shares} shares`
              : 'No open positions'}
          </p>
        </div>
      </div>
    </div>
  )
}
