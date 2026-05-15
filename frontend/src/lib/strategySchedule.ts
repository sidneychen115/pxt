/** Cron / interval scheduling for live strategies (America/Chicago). */

export type ScheduleMode = 'interval' | 'cron'

const CRON_RE = /^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$/
const INTERVAL_RE = /^(\d+)m$/i

/** Default cron for HA band strategy (weekdays 14:00 CT). */
export const HA_MONTH_WEEK_BAND_DEFAULT_CRON = '0 14 * * mon-fri'

export function scheduleModeFromFrequency(runFrequency: string): ScheduleMode {
  return CRON_RE.test((runFrequency || '').trim()) ? 'cron' : 'interval'
}

export function isValidCronExpression(expr: string): boolean {
  return CRON_RE.test((expr || '').trim())
}

export function isIntervalFrequency(runFrequency: string): boolean {
  return INTERVAL_RE.test((runFrequency || '').trim())
}

/** Initial cron field when opening the editor. */
export function defaultCronForStrategy(strategyId: string, runFrequency: string): string {
  const trimmed = (runFrequency || '').trim()
  if (isValidCronExpression(trimmed)) {
    return trimmed
  }
  if (strategyId === 'ha_month_week_band') {
    return HA_MONTH_WEEK_BAND_DEFAULT_CRON
  }
  return '0 16 * * mon-fri'
}

/** Timeframes to persist when saving in cron mode (no UI). */
export function timeframesForCronSave(strategyId: string, existing: string[]): string[] {
  if (strategyId === 'ha_month_week_band') {
    return ['1d']
  }
  if (existing.length > 0) {
    return existing
  }
  return ['1d']
}

/** Human-readable live schedule line for Strategies list. */
export function describeLiveSchedule(
  runFrequency: string,
  runIntervalMinutes: number | undefined,
  runAnchorTimeframe: string | undefined,
  timeframes: string[],
  timeframeLabel: (tf: string) => string,
  minIntervalFromTfs: (tfs: string[]) => number,
  anchorFromTfs: (tfs: string[]) => string,
  strategyId?: string,
): string {
  const freq = (runFrequency || '').trim()
  if (isValidCronExpression(freq)) {
    const haNote =
      strategyId === 'ha_month_week_band'
        ? '；到点用市价作日线 close 算信号（不落库）'
        : ''
    return `启用后按 Cron（America/Chicago）：${freq}${haNote}`
  }
  const mins = runIntervalMinutes ?? minIntervalFromTfs(timeframes)
  const anchor = runAnchorTimeframe ?? anchorFromTfs(timeframes)
  if (mins < 60) {
    return `启用后约每 ${mins} 分钟同步数据并跑策略（最短周期 ${timeframeLabel(anchor)}）`
  }
  if (mins < 1440) {
    return `启用后约每 ${mins} 分钟同步数据并跑策略（最短周期 ${timeframeLabel(anchor)}）`
  }
  if (mins === 1440) {
    return `启用后约每 24 小时同步并跑策略（最短周期 ${timeframeLabel(anchor)}）`
  }
  const days = Math.max(1, Math.round(mins / 1440))
  return `启用后约每 ${days} 日同步并跑策略（最短周期 ${timeframeLabel(anchor)}）`
}
