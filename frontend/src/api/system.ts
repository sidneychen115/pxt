import client from './client'
import type { SystemEvent } from '../types'

// No trailing slash on /health or /events: `/…/` can 307; Location may omit :port behind nginx.
export const fetchHealth = () =>
  client.get<{ status: string }>('/system/health').then(r => r.data)

export const fetchEvents = (params?: { level?: string; event_type?: string; limit?: number }) =>
  client.get<SystemEvent[]>('/system/events', { params }).then(r => r.data)
