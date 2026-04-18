/**
 * Saved backtest configuration presets (browser localStorage).
 * No server DB — remind users configs are per-browser.
 */
import type { Backtest } from '../types'
import {
  EMPTY_EXIT_FORM,
  exitPolicyToForm,
  type ExitFormState,
  sliceIsoDate,
} from './backtestFormConfig'

const STORAGE_KEY = 'pxt.backtestPresets.v1'
const MAX_PRESETS = 50

export interface BacktestPreset {
  id: string
  name: string
  createdAt: string
  strategy_id: string
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
  return { ...EMPTY_EXIT_FORM, ...(raw as Partial<ExitFormState>) }
}

function readRaw(): BacktestPreset[] {
  try {
    const s = localStorage.getItem(STORAGE_KEY)
    if (!s) return []
    const a = JSON.parse(s) as unknown
    if (!Array.isArray(a)) return []
    const out: BacktestPreset[] = []
    for (const x of a) {
      const p = normalizePreset(x)
      if (p) out.push(p)
    }
    return out
  } catch {
    return []
  }
}

function normalizePreset(x: unknown): BacktestPreset | null {
  if (!x || typeof x !== 'object') return null
  const o = x as Record<string, unknown>
  if (typeof o.id !== 'string' || typeof o.name !== 'string') return null
  if (typeof o.strategy_id !== 'string' || typeof o.start_date !== 'string' || typeof o.end_date !== 'string') {
    return null
  }
  if (typeof o.symbols !== 'string' || typeof o.initial_capital !== 'number') return null
  if (typeof o.parametersJson !== 'string') return null
  const createdAt = typeof o.createdAt === 'string' ? o.createdAt : new Date().toISOString()
  return {
    id: o.id,
    name: o.name,
    createdAt,
    strategy_id: o.strategy_id,
    start_date: o.start_date,
    end_date: o.end_date,
    symbols: o.symbols,
    initial_capital: o.initial_capital,
    parametersJson: o.parametersJson,
    exitPolicy: mergeExitPolicy(o.exitPolicy),
  }
}

function writeRaw(presets: BacktestPreset[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets))
}

export function listPresets(): BacktestPreset[] {
  return readRaw().sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}

export function getPreset(id: string): BacktestPreset | undefined {
  return readRaw().find(p => p.id === id)
}

export function applyPreset(p: BacktestPreset): BacktestFormSnapshot {
  return {
    strategy_id: p.strategy_id,
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

export function saveNewPreset(name: string, snapshot: Omit<BacktestPreset, 'id' | 'name' | 'createdAt'>): BacktestPreset {
  const trimmed = name.trim()
  if (!trimmed) {
    throw new Error('预设名称不能为空')
  }
  const presets = readRaw()
  if (presets.length >= MAX_PRESETS) {
    throw new Error(`最多保存 ${MAX_PRESETS} 条预设，请先删除旧配置`)
  }
  const preset: BacktestPreset = {
    id: crypto.randomUUID(),
    name: trimmed.slice(0, 80),
    createdAt: new Date().toISOString(),
    ...snapshot,
  }
  writeRaw([preset, ...presets])
  return preset
}

export function deletePreset(id: string): void {
  writeRaw(readRaw().filter(p => p.id !== id))
}
