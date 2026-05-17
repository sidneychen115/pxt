import type { Strategy } from '../types'
import { parseParametersJson } from './backtestFormConfig'
import { parametersWithoutPositionPct } from './backtestPositionSizing'
import {
  STRATEGY_TIMEFRAME_ORDER,
  anchorTimeframeFromList,
  type StrategyTimeframe,
} from './strategyTimeframes'

export const DEFAULT_BACKTEST_TIMEFRAME = '1d'

export const INTRADAY_BACKTEST_TIMEFRAMES = new Set<string>([
  '1m',
  '5m',
  '15m',
  '30m',
  '1h',
  '4h',
])

/** yfinance 1h/4h history cap used by the backtest API (~730 days). */
export const INTRADAY_BACKTEST_MAX_SPAN_DAYS = 728

export const SHORT_INTRADAY_BACKTEST_MAX_SPAN_DAYS = 60

/** Inset from Yahoo's 60d edge — same calendar day often returns zero 15m bars. */
export const SHORT_INTRADAY_USABLE_BUFFER_DAYS = 1

export const DEFAULT_INTRADAY_WARMUP_MONTHS = 6
export const DEFAULT_SHORT_INTRADAY_WARMUP_MONTHS = 0
export const DEFAULT_DAILY_WARMUP_MONTHS = 24

const SHORT_INTRADAY_TIMEFRAMES = new Set(['5m', '15m', '30m'])

export function yfinanceMaxDaysForTimeframe(tf: string): number {
  if (tf === '1m') return 7
  if (SHORT_INTRADAY_TIMEFRAMES.has(tf)) return SHORT_INTRADAY_BACKTEST_MAX_SPAN_DAYS
  if (tf === '1h' || tf === '4h') return INTRADAY_BACKTEST_MAX_SPAN_DAYS
  return INTRADAY_BACKTEST_MAX_SPAN_DAYS
}

export function defaultWarmupMonthsForTimeframe(tf: string): number {
  if (!isIntradayBacktestTimeframe(tf)) return DEFAULT_DAILY_WARMUP_MONTHS
  if (tf === '1m' || SHORT_INTRADAY_TIMEFRAMES.has(tf)) return DEFAULT_SHORT_INTRADAY_WARMUP_MONTHS
  return DEFAULT_INTRADAY_WARMUP_MONTHS
}

export function isIntradayBacktestTimeframe(tf: string): boolean {
  return INTRADAY_BACKTEST_TIMEFRAMES.has(tf)
}

export function isKnownTimeframe(tf: string): tf is StrategyTimeframe {
  return (STRATEGY_TIMEFRAME_ORDER as readonly string[]).includes(tf)
}

/** All K-line periods available for backtests (not limited by strategy live config). */
export function backtestTimeframeOptions(): StrategyTimeframe[] {
  return [...STRATEGY_TIMEFRAME_ORDER]
}

/** Live-run timeframe list on a strategy row (scheduler / data collection). */
export function timeframeOptionsForStrategy(strategy?: Strategy | null): StrategyTimeframe[] {
  if (!strategy?.timeframes?.length) {
    return backtestTimeframeOptions()
  }
  const allowed = new Set(strategy.timeframes)
  return STRATEGY_TIMEFRAME_ORDER.filter(tf => allowed.has(tf))
}

/** True when the strategy's configured live timeframes do not include the backtest choice. */
export function isTimeframeOutsideStrategyConfig(
  timeframe: string,
  strategy?: Strategy | null,
): boolean {
  const tfs = strategy?.timeframes
  if (!tfs?.length) return false
  return !tfs.includes(timeframe)
}

export function defaultBacktestTimeframe(strategy?: Strategy | null): string {
  if (strategy?.timeframes?.length) {
    return anchorTimeframeFromList(strategy.timeframes)
  }
  return DEFAULT_BACKTEST_TIMEFRAME
}

export function extractBacktestTimeframe(
  params: Record<string, unknown> | undefined,
  strategy?: Strategy | null,
): string {
  const tf = params?.timeframe
  if (typeof tf === 'string' && tf.trim()) {
    const t = tf.trim()
    return isKnownTimeframe(t) ? t : defaultBacktestTimeframe(strategy)
  }
  return defaultBacktestTimeframe(strategy)
}

export function parametersWithoutTimeframe(params: Record<string, unknown>): Record<string, unknown> {
  const { timeframe: _tf, ...rest } = params
  return rest
}

export function stringifyBacktestParametersJson(params: Record<string, unknown> | undefined): string {
  const clean = parametersWithoutPositionPct(parametersWithoutTimeframe(params ?? {}))
  if (Object.keys(clean).length === 0) return '{}'
  return JSON.stringify(clean, null, 2)
}

/** @deprecated Use mergeBacktestRunParameters from backtestPositionSizing */
export function mergeBacktestParameters(
  parametersJson: string,
  timeframe: string,
): Record<string, unknown> {
  const parsed = parseParametersJson(parametersJson)
  return { ...parsed, timeframe }
}

export function backtestSpanDays(startDate: string, endDate: string): number {
  const a = Date.parse(startDate)
  const b = Date.parse(endDate)
  if (Number.isNaN(a) || Number.isNaN(b)) return 0
  return Math.max(0, Math.ceil((b - a) / 86_400_000))
}

/** Approximate calendar span including warmup months (matches backend relativedelta). */
export function intradayFetchSpanDays(
  startDate: string,
  endDate: string,
  warmupMonths: number,
): number {
  const start = new Date(`${startDate}T00:00:00Z`)
  const end = new Date(`${endDate}T00:00:00Z`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  const fetchStart = new Date(start)
  fetchStart.setUTCMonth(fetchStart.getUTCMonth() - warmupMonths)
  const simEnd = new Date(end)
  simEnd.setUTCDate(simEnd.getUTCDate() + 1)
  return Math.max(0, Math.ceil((simEnd.getTime() - fetchStart.getTime()) / 86_400_000))
}

/** Earliest start/end date for yfinance (rolling window from today). */
export function intradayYfinanceEarliestDate(
  from: Date = new Date(),
  timeframe: string = '1h',
): string {
  const d = new Date(from)
  let days = yfinanceMaxDaysForTimeframe(timeframe)
  if (timeframe === '1m' || SHORT_INTRADAY_TIMEFRAMES.has(timeframe)) {
    days = Math.max(1, days - SHORT_INTRADAY_USABLE_BUFFER_DAYS)
  }
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

export function isBacktestRangeTooOldForIntraday(
  endDate: string,
  timeframe: string,
): boolean {
  if (!endDate || endDate.length < 10) return false
  return endDate.slice(0, 10) < intradayYfinanceEarliestDate(new Date(), timeframe)
}

export function parseWarmupMonthsFromParameters(
  parametersJson: string,
  timeframe: string,
): number {
  let params: Record<string, unknown> = {}
  try {
    const t = parametersJson.trim()
    if (t) {
      const o = JSON.parse(t) as unknown
      if (o && typeof o === 'object' && !Array.isArray(o)) params = o as Record<string, unknown>
    }
  } catch {
    /* use defaults */
  }
  const defaultM = defaultWarmupMonthsForTimeframe(timeframe)
  const raw = params.backtest_warmup_months
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' ? parseInt(raw, 10) : defaultM
  if (!Number.isFinite(n)) return defaultM
  return Math.max(0, Math.min(120, n))
}
