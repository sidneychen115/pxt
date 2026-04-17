import { useQuery } from '@tanstack/react-query'
import { fetchHealth, fetchEvents } from '../api/system'

const levelColors: Record<string, string> = {
  info: 'text-blue-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
}

export default function System() {
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 10_000 })
  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: () => fetchEvents({ limit: 200 }),
    refetchInterval: 15_000,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System</h1>
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${health?.status === 'ok' ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-sm font-medium">Backend: {health?.status ?? 'unknown'}</span>
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-gray-300">Event Log</div>
        <div className="max-h-[600px] overflow-y-auto font-mono text-xs">
          {events?.map(e => (
            <div key={e.id} className="px-4 py-2 border-b border-gray-800/40 flex gap-3 hover:bg-gray-800/30">
              <span className="text-gray-500 shrink-0">{new Date(e.created_at).toLocaleTimeString()}</span>
              <span className={`shrink-0 w-16 ${levelColors[e.level] ?? 'text-gray-400'}`}>{e.level.toUpperCase()}</span>
              <span className="text-gray-400 shrink-0">[{e.event_type}]</span>
              <span className="text-gray-200 break-all">{e.message}</span>
            </div>
          ))}
          {events?.length === 0 && <div className="text-gray-500 text-center py-8">No events.</div>}
        </div>
      </div>
    </div>
  )
}
