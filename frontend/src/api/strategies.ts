import client from './client'
import type { Strategy } from '../types'

export const fetchStrategies = () =>
  client.get<Strategy[]>('/strategies/').then(r => r.data)

export const fetchStrategy = (id: string) =>
  client.get<Strategy>(`/strategies/${id}`).then(r => r.data)

export const updateStrategy = (id: string, data: Partial<Strategy>) =>
  client.put<{ ok: boolean }>(`/strategies/${id}`, data).then(r => r.data)
