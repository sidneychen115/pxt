import { useQuery } from '@tanstack/react-query'
import { fetchHealth, fetchEvents } from '../api/system'
import type { SystemEvent } from '../types'

const levelColors: Record<string, string> = {
  info: 'text-blue-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
}

const phaseLabels: Record<string, string> = {
  start: 'START',
  step: 'STEP',
  complete: 'DONE',
  fail: 'FAIL',
}

const phaseColors: Record<string, string> = {
  start: 'text-cyan-400 bg-cyan-950/50',
  step: 'text-gray-400 bg-gray-800/60',
  complete: 'text-green-400 bg-green-950/50',
  fail: 'text-red-400 bg-red-950/50',
}

function strategyPhase(e: SystemEvent): string | null {
  if (e.event_type !== 'strategy_run') return null
  const phase = e.details?.phase
  return typeof phase === 'string' ? phase : null
}

function formatDetailsLine(details: Record<string, unknown> | null): string | null {
  if (!details) return null
  const skip = new Set(['phase', 'run_id', 'strategy_id'])
  const parts: string[] = []
  for (const [k, v] of Object.entries(details)) {
    if (skip.has(k) || v == null || v === '') continue
    if (typeof v === 'object') continue
    parts.push(`${k}=${v}`)
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

function EventRow({ event, indent }: { event: SystemEvent; indent: boolean }) {
  const phase = strategyPhase(event)
  const detailsLine = formatDetailsLine(event.details)
  const runId =
    event.details && typeof event.details.run_id === 'string'
      ? event.details.run_id
      : null

  return (
    <div
      className={`px-4 py-2 border-b border-gray-800/40 flex gap-3 hover:bg-gray-800/30 ${
        indent ? 'pl-10 border-l-2 border-l-gray-700/80 ml-4' : ''
      }`}
    >
      <span className="text-gray-500 shrink-0 w-[4.5rem]">
        {new Date(event.created_at).toLocaleTimeString()}
      </span>
      <span className={`shrink-0 w-16 ${levelColors[event.level] ?? 'text-gray-400'}`}>
        {event.level.toUpperCase()}
      </span>
      {phase ? (
        <span
          className={`shrink-0 w-12 text-center rounded px-1 text-[10px] font-semibold ${
            phaseColors[phase] ?? 'text-gray-400 bg-gray-800/60'
          }`}
        >
          {phaseLabels[phase] ?? phase.toUpperCase()}
        </span>
      ) : (
        <span className="text-gray-400 shrink-0 w-12 text-center">—</span>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap gap-x-2 items-baseline">
          <span className="text-gray-400 shrink-0">[{event.event_type}]</span>
          <span className="text-gray-200 break-all">{event.message}</span>
        </div>
        {(detailsLine || runId) && (
          <div className="text-gray-500 mt-0.5 break-all">
            {runId && <span className="text-gray-600">run {runId}</span>}
            {runId && detailsLine && <span className="mx-1.5">·</span>}
            {detailsLine}
          </div>
        )}
      </div>
    </div>
  )
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
            <EventRow
              key={e.id}
              event={e}
              indent={strategyPhase(e) === 'step'}
            />
          ))}
          {events?.length === 0 && <div className="text-gray-500 text-center py-8">No events.</div>}
        </div>
      </div>
    </div>
  )
}