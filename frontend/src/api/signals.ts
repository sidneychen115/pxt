import client from './client'
import type { Signal, SignalRun } from '../types'

export const fetchSignalRuns = (params?: { strategy_id?: string; limit?: number }) =>
  client.get<SignalRun[]>('/signals/runs', { params }).then(r => r.data)

export const fetchSignals = (params?: {
  strategy_id?: string
  status?: string
  signal_time?: string
  limit?: number
}) => client.get<Signal[]>('/signals/', { params }).then(r => r.data)

export const fetchSignal = (id: number) =>
  client.get<Signal>(`/signals/${id}`).then(r => r.data)

export const executeSignal = (id: number, body: { quantity: number; fill_price: number }) =>
  client.post<{ ok: boolean }>(`/signals/${id}/execute`, body).then(r => r.data)
