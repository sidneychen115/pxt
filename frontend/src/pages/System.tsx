import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchHealth, fetchEvents } from '../api/system'
import {
  cronScheduleLabelChicago,
  formatChicagoDateTime,
  parseUtcIso,
} from '../lib/formatTime'
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

function runStartedIso(event: SystemEvent): string | null {
  const d = event.details
  if (!d) return null
  if (typeof d.started_at === 'string') return d.started_at
  if (event.event_type === 'strategy_run' && strategyPhase(event) === 'start') {
    return event.created_at
  }
  const elapsed = d.elapsed_s
  if (typeof elapsed === 'number' && Number.isFinite(elapsed)) {
    const endMs = parseUtcIso(event.created_at).getTime()
    return new Date(endMs - elapsed * 1000).toISOString()
  }
  return null
}

function strategyRunTimingLine(event: SystemEvent): string | null {
  if (event.event_type !== 'strategy_run') return null
  const phase = strategyPhase(event)
  const started = runStartedIso(event)
  const parts: string[] = []
  if (started) {
    parts.push(`started ${formatChicagoDateTime(started)}`)
  }
  if (phase === 'complete' || phase === 'fail') {
    parts.push(`logged ${formatChicagoDateTime(event.created_at)}`)
  }
  const freq = event.details?.run_frequency
  if (typeof freq === 'string' && event.details?.schedule_mode === 'cron') {
    const label = cronScheduleLabelChicago(freq)
    if (label) parts.push(`cron ${label}`)
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

function formatDetailsLine(details: Record<string, unknown> | null): string | null {
  if (!details) return null
  const skip = new Set([
    'phase',
    'run_id',
    'strategy_id',
    'started_at',
    'run_frequency',
    'schedule_mode',
    'symbols',
    'timeframes',
    'snapshot_close',
  ])
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
  const timingLine = strategyRunTimingLine(event)
  const runId =
    event.details && typeof event.details.run_id === 'string'
      ? event.details.run_id
      : null
  const displayTime = formatChicagoDateTime(event.created_at)

  return (
    <div
      className={`px-4 py-2 border-b border-gray-800/40 flex gap-3 hover:bg-gray-800/30 ${
        indent ? 'pl-10 border-l-2 border-l-gray-700/80 ml-4' : ''
      }`}
    >
      <span
        className="text-gray-500 shrink-0 w-[12rem] leading-tight tabular-nums"
        title={event.created_at}
      >
        {displayTime}
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
        {(timingLine || detailsLine || runId) && (
          <div className="text-gray-500 mt-0.5 break-all">
            {runId && <span className="text-gray-600">run {runId}</span>}
            {runId && (timingLine || detailsLine) && <span className="mx-1.5">·</span>}
            {timingLine}
            {timingLine && detailsLine && <span className="mx-1.5">·</span>}
            {detailsLine}
          </div>
        )}
      </div>
    </div>
  )
}

export default function System() {
  const [showSteps, setShowSteps] = useState(false)
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 10_000 })
  const { data: events } = useQuery({
    queryKey: ['events', showSteps],
    queryFn: () =>
      fetchEvents({
        limit: 500,
        summary: !showSteps,
      }),
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
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-gray-300">Event Log</span>
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSteps}
              onChange={e => setShowSteps(e.target.checked)}
              className="rounded border-gray-600"
            />
            显示逐步日志（每标的 STEP）
          </label>
        </div>
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