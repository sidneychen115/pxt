export interface Strategy {
  id: string
  name: string
  description: string | null
  is_active: boolean
  symbols: string[]
  timeframes: string[]
  run_frequency: string
  parameters: Record<string, unknown>
  max_symbols: number
}

export interface Signal {
  id: number
  strategy_id: string
  stock_id: number | null
  option_id: number | null
  signal_time: string
  direction: 'buy' | 'sell' | 'hold'
  quantity: number | null
  order_type: string
  limit_price: number | null
  stop_price: number | null
  confidence: number | null
  reasoning: string | null
  status: string
  created_at: string
}

export interface Backtest {
  id: number
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  status: 'running' | 'completed' | 'failed'
  total_return: number | null
  annualized_return: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  win_rate: number | null
  profit_factor: number | null
  total_trades: number | null
  avg_hold_days: number | null
  llm_evaluation: string | null
  llm_model: string | null
  created_at: string
  completed_at: string | null
}

export interface BacktestTrade {
  id: number
  symbol: string
  direction: string
  quantity: number
  entry_time: string
  entry_price: number
  exit_time: string | null
  exit_price: number | null
  pnl: number | null
  pnl_pct: number | null
  hold_days: number | null
  exit_reason: string | null
  entry_signal: Record<string, unknown> | null
}

export interface EquityPoint {
  ts: string
  equity: number
  cash: number
  drawdown: number | null
}

export interface SystemEvent {
  id: number
  event_type: string
  level: 'info' | 'warning' | 'error'
  message: string
  details: Record<string, unknown> | null
  created_at: string
}
