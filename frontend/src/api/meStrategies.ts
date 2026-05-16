import client from './client'
import type { Strategy } from '../types'

export type UserStrategy = Strategy & {
  row_id: number
  user_id: number
  updated_at?: string | null
}

export const fetchMyStrategies = () =>
  client.get<UserStrategy[]>('/me/strategies/').then((r) => r.data)

export const fetchStrategyPool = () =>
  client.get<Strategy[]>('/me/strategies/pool').then((r) => r.data)

export const addMyStrategy = (strategy_id: string) =>
  client.post<UserStrategy>('/me/strategies/', { strategy_id }).then((r) => r.data)

export const updateMyStrategy = (rowId: number, data: Partial<Strategy>) =>
  client.put<UserStrategy>(`/me/strategies/${rowId}`, data).then((r) => r.data)

export const removeMyStrategy = (rowId: number) =>
  client.delete<{ ok: boolean }>(`/me/strategies/${rowId}`).then((r) => r.data)
