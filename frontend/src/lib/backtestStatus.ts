export type BacktestStatus = 'queued' | 'running' | 'completed' | 'failed'

export function isBacktestInProgress(status: string | undefined | null): boolean {
  return status === 'queued' || status === 'running'
}

export function backtestStatusLabel(status: string): string {
  if (status === 'queued') return 'queued'
  return status
}
