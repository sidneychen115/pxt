import type { Backtest, ExitPolicy } from '../types'

export const EMPTY_EXIT_FORM = {
  stop_loss_pct: '',
  stop_loss_abs: '',
  take_profit_pct: '',
  take_profit_abs: '',
  trailing_stop_pct: '',
  trailing_activate_pct: '',
  entry_price_check_mode: 'close' as 'close' | 'ohlc',
  exit_price_check_mode: 'ohlc' as 'close' | 'ohlc',
  disable_sell_signal: false,
}

export type ExitFormState = typeof EMPTY_EXIT_FORM

export function exitPolicyFromForm(exitPolicy: ExitFormState): ExitPolicy | null {
  const ep = {
    stop_loss_pct: exitPolicy.stop_loss_pct !== '' ? parseFloat(exitPolicy.stop_loss_pct) / 100 : null,
    stop_loss_abs: exitPolicy.stop_loss_abs !== '' ? parseFloat(exitPolicy.stop_loss_abs) : null,
    take_profit_pct: exitPolicy.take_profit_pct !== '' ? parseFloat(exitPolicy.take_profit_pct) / 100 : null,
    take_profit_abs: exitPolicy.take_profit_abs !== '' ? parseFloat(exitPolicy.take_profit_abs) : null,
    trailing_stop_pct: exitPolicy.trailing_stop_pct !== '' ? parseFloat(exitPolicy.trailing_stop_pct) / 100 : null,
    trailing_activate_pct: exitPolicy.trailing_activate_pct !== '' ? parseFloat(exitPolicy.trailing_activate_pct) / 100 : null,
    entry_price_check_mode: exitPolicy.entry_price_check_mode,
    exit_price_check_mode: exitPolicy.exit_price_check_mode,
    disable_sell_signal: exitPolicy.disable_sell_signal,
  }
  const hasNumeric = !!(
    ep.stop_loss_pct || ep.stop_loss_abs || ep.take_profit_pct || ep.take_profit_abs
    || ep.trailing_stop_pct || ep.trailing_activate_pct
  )
  if (!hasNumeric && !ep.disable_sell_signal) return null
  return ep
}

export function exitPolicyToForm(ep: ExitPolicy | null | undefined): ExitFormState {
  if (!ep) return { ...EMPTY_EXIT_FORM }
  const pctStr = (v: number | null | undefined) =>
    v != null && Number.isFinite(v) ? String(Number((v * 100).toPrecision(12))) : ''
  const absStr = (v: number | null | undefined) =>
    v != null && Number.isFinite(v) ? String(v) : ''
  return {
    stop_loss_pct: pctStr(ep.stop_loss_pct),
    stop_loss_abs: absStr(ep.stop_loss_abs),
    take_profit_pct: pctStr(ep.take_profit_pct),
    take_profit_abs: absStr(ep.take_profit_abs),
    trailing_stop_pct: pctStr(ep.trailing_stop_pct),
    trailing_activate_pct: pctStr(ep.trailing_activate_pct),
    entry_price_check_mode:
      ep.entry_price_check_mode === 'ohlc' ? 'ohlc' : 'close',
    exit_price_check_mode: (() => {
      const v = ep.exit_price_check_mode ?? ep.price_check_mode
      return v === 'close' ? 'close' : 'ohlc'
    })(),
    disable_sell_signal: ep.disable_sell_signal ?? false,
  }
}

export function exitPolicyForRerun(ep: ExitPolicy | null | undefined): ExitPolicy | null {
  if (!ep) return null
  const hasNumeric = !!(
    ep.stop_loss_pct || ep.stop_loss_abs || ep.take_profit_pct || ep.take_profit_abs
    || ep.trailing_stop_pct || ep.trailing_activate_pct
  )
  if (!hasNumeric && !ep.disable_sell_signal) return null
  return {
    stop_loss_pct: ep.stop_loss_pct ?? null,
    stop_loss_abs: ep.stop_loss_abs ?? null,
    take_profit_pct: ep.take_profit_pct ?? null,
    take_profit_abs: ep.take_profit_abs ?? null,
    trailing_stop_pct: ep.trailing_stop_pct ?? null,
    trailing_activate_pct: ep.trailing_activate_pct ?? null,
    entry_price_check_mode: ep.entry_price_check_mode ?? 'close',
    exit_price_check_mode:
      ep.exit_price_check_mode ?? ep.price_check_mode ?? 'ohlc',
    disable_sell_signal: ep.disable_sell_signal ?? false,
  }
}

export function parseParametersJson(raw: string): Record<string, unknown> {
  const t = raw.trim()
  if (!t) return {}
  const o = JSON.parse(t) as unknown
  if (o === null || typeof o !== 'object' || Array.isArray(o)) {
    throw new Error('Parameters must be a JSON object')
  }
  return o as Record<string, unknown>
}

export function sliceIsoDate(d: string): string {
  return d.length >= 10 ? d.slice(0, 10) : d
}

export function buildRerunPayload(bt: Backtest) {
  return {
    strategy_id: bt.strategy_id,
    start_date: sliceIsoDate(bt.start_date),
    end_date: sliceIsoDate(bt.end_date),
    symbols: [...bt.symbols],
    initial_capital: bt.initial_capital,
    parameters: { ...(bt.parameters ?? {}) },
    exit_policy: exitPolicyForRerun(bt.exit_policy),
  }
}
