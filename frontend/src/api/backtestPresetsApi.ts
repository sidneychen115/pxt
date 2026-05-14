import client from './client'

export interface BacktestPresetDto {
  id: string
  name: string
  created_at: string
  strategy_id: string | null
  start_date: string
  end_date: string
  symbols: string
  initial_capital: number
  parameters: Record<string, unknown>
  exit_policy_form: Record<string, unknown>
}

export interface BacktestPresetCreateBody {
  name: string
  strategy_id?: string | null
  start_date: string
  end_date: string
  symbols: string
  initial_capital: number
  parameters: Record<string, unknown>
  exit_policy_form: Record<string, unknown>
}

export async function fetchBacktestPresets(): Promise<BacktestPresetDto[]> {
  const { data } = await client.get<BacktestPresetDto[]>('/backtest-presets/')
  return data
}

export async function createBacktestPreset(body: BacktestPresetCreateBody): Promise<BacktestPresetDto> {
  const { data } = await client.post<BacktestPresetDto>('/backtest-presets/', body)
  return data
}

export async function updateBacktestPreset(
  id: string,
  patch: Partial<BacktestPresetCreateBody>,
): Promise<BacktestPresetDto> {
  const { data } = await client.patch<BacktestPresetDto>(`/backtest-presets/${id}`, patch)
  return data
}

export async function removeBacktestPreset(id: string): Promise<void> {
  await client.delete(`/backtest-presets/${id}`)
}
