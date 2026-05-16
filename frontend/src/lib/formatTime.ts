/** Serialize / display timestamps in app timezone (`VITE_APP_TIMEZONE`, default America/Chicago). */

export const APP_TIMEZONE = import.meta.env.VITE_APP_TIMEZONE ?? 'America/Chicago'

/** Parse ISO; if no offset, assume UTC instant (legacy payloads). */
export function parseUtcIso(iso: string): Date {
  const s = iso.trim()
  if (!s) return new Date(Number.NaN)
  if (s.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(s)) {
    return new Date(s)
  }
  const normalized = s.includes('T') ? s : s.replace(' ', 'T')
  return new Date(`${normalized}Z`)
}

export function formatAppDateTime(iso: string | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    timeZone: APP_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function formatAppDateOnly(iso: string | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('zh-CN', {
    timeZone: APP_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/** YYYY-MM-DD in app TZ (for Lightweight Charts daily `time` markers, etc.). */
export function formatAppChartDay(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.trim().slice(0, 10)
  const s = new Intl.DateTimeFormat('en-CA', {
    timeZone: APP_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d)
  return s
}

/** Human label including seconds (signals / diagnostics). */
export function formatChicagoDateTime(iso: string): string {
  const d = parseUtcIso(iso)
  if (Number.isNaN(d.getTime())) return iso
  return (
    d.toLocaleString('en-US', {
      timeZone: APP_TIMEZONE,
      month: 'numeric',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }) + ` (${APP_TIMEZONE})`
  )
}

/** Human label for 5-field cron in America/Chicago (e.g. ``13 14 * * mon-fri`` → ``2:13 PM CT``). */
export function cronScheduleLabelChicago(runFrequency: string): string | null {
  const parts = runFrequency.trim().split(/\s+/)
  if (parts.length < 5) return null
  const minute = Number.parseInt(parts[0]!, 10)
  const hour = Number.parseInt(parts[1]!, 10)
  if (Number.isNaN(minute) || Number.isNaN(hour)) return null
  const h12 = hour % 12 || 12
  const ampm = hour >= 12 ? 'PM' : 'AM'
  return `${h12}:${String(minute).padStart(2, '0')} ${ampm} (${APP_TIMEZONE})`
}
