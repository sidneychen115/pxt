/** Turn 5-field cron (America/Chicago) into short Chinese text for the Strategies UI. */

const TZ_SUFFIX = '美中 CT'

const DOW_LABELS: Record<string, string> = {
  '*': '每天',
  '?': '每天',
  'mon-fri': '每个工作日',
  '1-5': '每个工作日',
  '2-6': '每个工作日',
  'mon': '每周一',
  'tue': '每周二',
  'wed': '每周三',
  'thu': '每周四',
  'fri': '每周五',
  'sat': '每周六',
  'sun': '每周日',
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function formatClock(hour: number, minute: number): string {
  return `${pad2(hour)}:${pad2(minute)}`
}

type FieldParse =
  | { kind: 'any' }
  | { kind: 'step'; step: number }
  | { kind: 'list'; values: number[] }

function parseCronField(field: string): FieldParse | null {
  const f = field.trim().toLowerCase()
  if (f === '*' || f === '?') return { kind: 'any' }
  const stepMatch = /^\*\/(\d+)$/.exec(f)
  if (stepMatch) {
    const step = Number(stepMatch[1])
    if (step > 0) return { kind: 'step', step }
  }
  if (/^\d+$/.test(f)) return { kind: 'list', values: [Number(f)] }
  if (/^[\d,\s]+$/.test(f)) {
    const values = f
      .split(',')
      .map(s => Number(s.trim()))
      .filter(n => Number.isFinite(n))
    if (values.length) return { kind: 'list', values }
  }
  return null
}

function humanizeDayOfWeek(dow: string): string {
  const key = dow.trim().toLowerCase()
  return DOW_LABELS[key] ?? `每周（${dow}）`
}

function humanizeTimes(minuteField: string, hourField: string): string {
  const minute = parseCronField(minuteField)
  const hour = parseCronField(hourField)
  if (!minute || !hour) return `${minuteField} ${hourField}`.trim()

  if (minute.kind === 'step' && hour.kind === 'any') {
    return `每 ${minute.step} 分钟`
  }
  if (minute.kind === 'any' && hour.kind === 'step') {
    return `每 ${hour.step} 小时`
  }
  if (minute.kind === 'any' && hour.kind === 'any') {
    return '每分钟'
  }

  const minutes =
    minute.kind === 'list' ? minute.values : minute.kind === 'step' ? [0] : [0]
  const hours = hour.kind === 'list' ? hour.values : hour.kind === 'any' ? [0] : [0]

  const clocks: string[] = []
  for (const h of hours) {
    for (const m of minutes) {
      clocks.push(formatClock(h, m))
    }
  }
  const unique = [...new Set(clocks)]
  unique.sort()
  if (unique.length === 1) return unique[0]
  if (unique.length <= 4) return unique.join('、')
  return `${unique[0]} 等 ${unique.length} 个时刻`
}

/** Returns null if `expr` is not a valid 5-field cron string. */
export function humanizeCronExpression(expr: string): string | null {
  const trimmed = (expr || '').trim()
  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5) return null

  const [minute, hour, , , dow] = parts
  const when = humanizeDayOfWeek(dow)
  const times = humanizeTimes(minute, hour)

  if (times === '每分钟' || times.startsWith('每 ')) {
    return `${when}${times}（${TZ_SUFFIX}）`
  }
  return `${when} ${times}（${TZ_SUFFIX}）`
}
