/** K 线周期选项（与后端 `TIMEFRAME_MINUTES` / 数据采集一致） */
export const STRATEGY_TIMEFRAME_ORDER = [
  '1m',
  '5m',
  '15m',
  '30m',
  '1h',
  '4h',
  '1d',
  '1wk',
  '1mo',
] as const

export type StrategyTimeframe = (typeof STRATEGY_TIMEFRAME_ORDER)[number]

const TF_LABEL: Record<string, string> = {
  '1m': '1 分钟',
  '5m': '5 分钟',
  '15m': '15 分钟',
  '30m': '30 分钟',
  '1h': '1 小时',
  '4h': '4 小时',
  '1d': '日线',
  '1wk': '周线',
  '1mo': '月线',
}

const TF_MIN: Record<string, number> = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '1h': 60,
  '4h': 240,
  '1d': 1440,
  '1wk': 10080,
  '1mo': 43200,
}

export function timeframeLabel(tf: string): string {
  return TF_LABEL[tf] ?? tf
}

/** 与后端 min_interval_minutes 一致：取所选周期中最短 K 线对应的分钟数 */
export function minIntervalMinutesFromTimeframes(timeframes: string[]): number {
  if (!timeframes.length) return 1440
  return Math.max(1, Math.min(...timeframes.map(tf => TF_MIN[tf] ?? 1440)))
}

export function anchorTimeframeFromList(timeframes: string[]): string {
  if (!timeframes.length) return '1d'
  let best = timeframes[0]
  let bestM = TF_MIN[best] ?? 1440
  for (let i = 1; i < timeframes.length; i++) {
    const tf = timeframes[i]
    const m = TF_MIN[tf] ?? 1440
    if (m < bestM) {
      bestM = m
      best = tf
    }
  }
  return best
}

/** 启用实盘调度时的说明文案（不使用 Cron） */
export function describeLiveSchedule(
  runIntervalMinutes: number | undefined,
  runAnchorTimeframe: string | undefined,
  timeframes: string[],
): string {
  const mins = runIntervalMinutes ?? minIntervalMinutesFromTimeframes(timeframes)
  const anchor = runAnchorTimeframe ?? anchorTimeframeFromList(timeframes)
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
