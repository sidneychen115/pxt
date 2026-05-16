import client from './client'

export type PositionSummary = {
  open_symbols: number
  total_shares: number
  position_value: number
}

export type PositionRow = {
  symbol: string
  quantity: number
  avg_cost: number
  mark_price: number | null
  market_value: number
  updated_at: string | null
}

export const fetchPositionSummary = () =>
  client.get<PositionSummary>('/me/positions/summary').then((r) => r.data)

export const fetchPositions = () =>
  client.get<PositionRow[]>('/me/positions/').then((r) => r.data)

export type ManualFillBody = {
  symbol: string
  quantity: number
  fill_price: number
  side?: 'buy' | 'sell'
}

export type ManualFillResult = {
  ok: boolean
  symbol: string
  quantity: number
  avg_cost: number
}

export const createManualFill = (body: ManualFillBody) =>
  client.post<ManualFillResult>('/me/positions/fills', body).then((r) => r.data)
