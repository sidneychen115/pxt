/**
 * Backtest configuration presets — stored in PostgreSQL via /api/backtest-presets.
 * Helpers for matching, snapshots, and DTO mapping.
 */
import type { Backtest } from '../types'
import type { BacktestPresetDto } from '../api/backtestPresetsApi'
import type { BacktestPresetCreateBody } from '../api/backtestPresetsApi'
import {
  EMPTY_EXIT_FORM,
  exitPolicyToForm,
  parseParametersJson,
  type ExitFormState,
  sliceIsoDate,
} from './backtestFormConfig'

export interface BacktestPreset {
  id: string
  name: string
  createdAt: string
  /** 旧数据可能绑定策略；新预设为 null，加载后需在回测页自选策略 */
  strategy_id: string | null
  start_date: string
  end_date: string
  /** Comma-separated symbols, same as form input */
  symbols: string
  initial_capital: number
  parametersJson: string
  exitPolicy: ExitFormState
}

export interface BacktestFormSnapshot {
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string
  initial_capital: number
  parametersJson: string
  exitPolicy: ExitFormState
}

function mergeExitPolicy(raw: unknown): ExitFormState {
  if (!raw || typeof raw !== 'object') return { ...EMPTY_EXIT_FORM }
  const o = raw as Record<string, unknown>
  const merged = { ...EMPTY_EXIT_FORM, ...(raw as Partial<ExitFormState>) }
  if (!('exit_price_check_mode' in o) && typeof o.price_check_mode === 'string') {
    merged.exit_price_check_mode = o.price_check_mode === 'ohlc' ? 'ohlc' : 'close'
  }
  return merged
}

/** Map API row to UI model (parameters kept as JSON string for forms). */
export function dtoToPreset(d: BacktestPresetDto): BacktestPreset {
  return {
    id: d.id,
    name: d.name,
    createdAt: d.created_at,
    strategy_id: d.strategy_id ?? null,
    start_date: d.start_date,
    end_date: d.end_date,
    symbols: d.symbols,
    initial_capital: d.initial_capital,
    parametersJson: JSON.stringify(d.parameters ?? {}, null, 2),
    exitPolicy: mergeExitPolicy(d.exit_policy_form),
  }
}

export function applyPreset(p: BacktestPreset): BacktestFormSnapshot {
  return {
    strategy_id: '',
    start_date: p.start_date,
    end_date: p.end_date,
    symbols: p.symbols,
    initial_capital: p.initial_capital,
    parametersJson: p.parametersJson,
    exitPolicy: mergeExitPolicy(p.exitPolicy),
  }
}

export function snapshotFromCurrentForm(
  form: { strategy_id: string; start_date: string; end_date: string; symbols: string; initial_capital: number },
  exitPolicy: ExitFormState,
  parametersJson: string,
): Omit<BacktestPreset, 'id' | 'name' | 'createdAt'> {
  return {
    strategy_id: form.strategy_id,
    start_date: form.start_date,
    end_date: form.end_date,
    symbols: form.symbols,
    initial_capital: form.initial_capital,
    parametersJson,
    exitPolicy: { ...exitPolicy },
  }
}

export function snapshotFromBacktest(bt: Backtest): Omit<BacktestPreset, 'id' | 'name' | 'createdAt'> {
  return {
    strategy_id: bt.strategy_id,
    start_date: sliceIsoDate(bt.start_date),
    end_date: sliceIsoDate(bt.end_date),
    symbols: bt.symbols.join(', '),
    initial_capital: bt.initial_capital,
    parametersJson: JSON.stringify(bt.parameters ?? {}, null, 2),
    exitPolicy: exitPolicyToForm(bt.exit_policy),
  }
}

function normalizeSymbolCsv(s: string): string {
  return s
    .split(',')
    .map(x => x.trim().toUpperCase())
    .filter(Boolean)
    .sort()
    .join(',')
}

function sortKeysDeep(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) return obj.map(sortKeysDeep)
  const o = obj as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(o).sort()) {
    const v = o[k]
    if (v === undefined) continue
    out[k] = sortKeysDeep(v)
  }
  return out
}

function jsonComparable(obj: unknown): string {
  return JSON.stringify(sortKeysDeep(obj))
}

function sameInitialCapital(a: number, b: number): boolean {
  const da = Number(a)
  const db = Number(b)
  if (!Number.isFinite(da) || !Number.isFinite(db)) return false
  return Math.abs(da - db) < 1e-4
}

/** Match preset name if this backtest config equals a saved preset. */
export function findMatchingPresetName(bt: Backtest, presets: BacktestPreset[]): string | null {
  const snap = snapshotFromBacktest(bt)
  const symSnap = normalizeSymbolCsv(snap.symbols)
  const paramCmp = jsonComparable(bt.parameters ?? {})
  const exitCmp = jsonComparable(snap.exitPolicy)

  for (const p of presets) {
    if (p.strategy_id != null && p.strategy_id !== '' && p.strategy_id !== snap.strategy_id) continue
    if (p.start_date !== snap.start_date) continue
    if (p.end_date !== snap.end_date) continue
    if (normalizeSymbolCsv(p.symbols) !== symSnap) continue
    if (!sameInitialCapital(snap.initial_capital, p.initial_capital)) continue
    let presetParams: unknown
    try {
      presetParams = JSON.parse(p.parametersJson || '{}')
    } catch {
      continue
    }
    if (jsonComparable(presetParams) !== paramCmp) continue
    if (jsonComparable(p.exitPolicy) !== exitCmp) continue
    return p.name
  }
  return null
}

/** Build API create/update body from form snapshot + name (parse parameters JSON). */
export function presetBodyFromSnapshot(
  snap: Omit<BacktestPreset, 'id' | 'name' | 'createdAt'>,
  name: string,
): BacktestPresetCreateBody {
  const parameters = parseParametersJson(snap.parametersJson)
  return {
    name: name.trim().slice(0, 80),
    strategy_id: null,
    start_date: snap.start_date,
    end_date: snap.end_date,
    symbols: snap.symbols,
    initial_capital: snap.initial_capital,
    parameters,
    exit_policy_form: { ...snap.exitPolicy } as Record<string, unknown>,
  }
}
