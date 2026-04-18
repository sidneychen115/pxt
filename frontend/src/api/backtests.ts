import client from './client'
import type { Backtest, BacktestTrade, EquityPoint, ExitPolicy } from '../types'

export const fetchBacktests = (strategy_id?: string) =>
  client.get<Backtest[]>('/backtests/', { params: { strategy_id } }).then(r => r.data)

export const fetchBacktest = (id: number) =>
  client.get<Backtest>(`/backtests/${id}`).then(r => r.data)

export const triggerBacktest = (data: {
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  parameters: Record<string, unknown>
  exit_policy?: ExitPolicy | null
}) => client.post<{ id: number; status: string }>('/backtests/', data).then(r => r.data)

export const fetchBacktestTrades = (id: number, sort_by = 'entry_time', order = 'asc') =>
  client.get<BacktestTrade[]>(`/backtests/${id}/trades`, { params: { sort_by, order } }).then(r => r.data)

export const fetchEquityCurve = (id: number) =>
  client.get<EquityPoint[]>(`/backtests/${id}/equity`).then(r => r.data)
