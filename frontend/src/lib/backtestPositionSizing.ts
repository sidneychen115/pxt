import { parseParametersJson } from './backtestFormConfig'
import { parametersWithoutTimeframe } from './backtestTimeframe'

export const DEFAULT_BACKTEST_POSITION_PCT = 0.1

export function positionPctFromPercentInput(percent: number): number {
  if (!Number.isFinite(percent)) return DEFAULT_BACKTEST_POSITION_PCT
  return Math.max(0, Math.min(100, percent)) / 100
}

export function percentFromPositionPct(pct: number): number {
  if (!Number.isFinite(pct)) return DEFAULT_BACKTEST_POSITION_PCT * 100
  const p = pct > 1 ? pct : pct * 100
  return Math.round(p * 100) / 100
}

export function extractPositionPctPercent(
  params: Record<string, unknown> | undefined,
): number {
  const raw = params?.backtest_position_pct
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return percentFromPositionPct(raw)
  }
  if (typeof raw === 'string' && raw.trim() !== '') {
    const n = Number(raw)
    if (Number.isFinite(n)) return percentFromPositionPct(n)
  }
  return DEFAULT_BACKTEST_POSITION_PCT * 100
}

export function parametersWithoutPositionPct(
  params: Record<string, unknown>,
): Record<string, unknown> {
  const { backtest_position_pct: _p, ...rest } = params
  return rest
}

export function stringifyBacktestParametersJson(
  params: Record<string, unknown> | undefined,
): string {
  const clean = parametersWithoutPositionPct(params ?? {})
  if (Object.keys(clean).length === 0) return '{}'
  return JSON.stringify(clean, null, 2)
}

export function mergeBacktestRunParameters(
  parametersJson: string,
  timeframe: string,
  positionPctPercent: number,
): Record<string, unknown> {
  const parsed = parseParametersJson(parametersJson)
  const rest = parametersWithoutPositionPct(parametersWithoutTimeframe(parsed))
  return {
    ...rest,
    timeframe,
    backtest_position_pct: positionPctFromPercentInput(positionPctPercent),
  }
}
