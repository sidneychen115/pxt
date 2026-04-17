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

  // liveSignals is maintained for future real-time rendering
  void liveSignals

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
