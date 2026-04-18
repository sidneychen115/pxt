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

export interface ExitPolicy {
  stop_loss_pct?: number | null
  stop_loss_abs?: number | null
  take_profit_pct?: number | null
  take_profit_abs?: number | null
  trailing_stop_pct?: number | null
  trailing_activate_pct?: number | null
  price_check_mode?: 'close' | 'ohlc'
  /** When true, ignore strategy SELL signals (exits only via exit rules or end of test). */
  disable_sell_signal?: boolean
}

/** Backtest pipeline step; null when idle or after completion. */
export type BacktestProgressPhase = 'fetching_data' | 'engine' | 'llm_eval'

export interface Backtest {
  id: number
  strategy_id: string
  start_date: string
  end_date: string
  symbols: string[]
  initial_capital: number
  status: 'running' | 'completed' | 'failed'
  /** Current pipeline step while status is running */
  progress_phase?: BacktestProgressPhase | null
  /** Human-readable detail, e.g. symbol (2/5) */
  progress_message?: string | null
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
  /** Strategy parameters snapshot from when the backtest was created */
  parameters?: Record<string, unknown>
  exit_policy?: ExitPolicy | null
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
