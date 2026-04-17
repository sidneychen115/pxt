import client from './client'
import type { Signal } from '../types'

export const fetchSignals = (params?: { strategy_id?: string; status?: string; limit?: number }) =>
  client.get<Signal[]>('/signals', { params }).then(r => r.data)

export const fetchSignal = (id: number) =>
  client.get<Signal>(`/signals/${id}`).then(r => r.data)
