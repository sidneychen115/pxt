/**
 * Structured strategy guides for the Strategies page (display-only).
 * Format: purpose → logic → inputs → outputs → schedule → parameters.
 */

export interface StrategyGuide {
  purpose: string
  logic: string
  inputs: string
  outputs: string
  schedule?: string
  parameters?: string
}

const GUIDES: Record<string, StrategyGuide> = {
  ha_month_week_band: {
    purpose:
      '以当月 Heikin-Ashi（HA）开盘价为中期基准，用当周 HA 收盘价相对对称死区的突破捕捉趋势切换，适合日线节奏的中短期波段。',
    logic:
      '计算当月 HA open 作为 benchmark，上下轨为 benchmark ± (|benchmark|×band_pct + band_abs)。比较「上一交易日」与「当前」的当周 HA close 是否分别上穿上轨或下穿下轨；仅在发生穿越时发信号，持续在带内或带外不重复触发。置信度随突破幅度在 floor～cap 之间缩放。',
    inputs:
      '各标的日线 OHLC（实盘到点可用市价作当日 close，不落库）；策略参数 band_pct、band_abs、confidence_* 等。',
    outputs:
      'TradeSignal：buy / sell / hold；direction 为 market；含 confidence 与 reasoning（含 benchmark、轨道与 HA 数值）。',
    schedule:
      '默认定时 Cron（工作日 14:00 美中 CT）：到点拉取行情，用市价补全当日 close 后计算 HA 与信号。',
    parameters:
      'band_pct / band_abs 控制死区宽度；confidence_floor、confidence_cap、confidence_excess_scale 控制信号强度映射。',
  },
  ma_crossover: {
    purpose:
      '经典双均线趋势跟踪：在快慢 EMA 金叉时做多、死叉时平仓或做空，用于验证框架与简单趋势行情。',
    logic:
      '对每标的拉取 K 线，计算 fast / slow 两条 EMA；若前一根 K 线 fast≤slow 且当前 fast>slow 则 buy，反之为 sell。数据不足或均线未就绪时跳过。',
    inputs:
      'symbols 列表；parameters：fast、slow、timeframe（默认日线）；DataContext.get_bars。',
    outputs:
      'TradeSignal 列表（market 单，confidence≈0.75，reasoning 含 EMA 数值与交叉说明）。',
    schedule:
      '默认定时 Cron（工作日 16:00 美中 CT）或按所选 K 线周期最短间隔轮询。',
    parameters:
      'fast（默认 10）、slow（默认 30）、timeframe（默认 1d）。',
  },
  pivot_supertrend: {
    purpose:
      '以枢轴点中心线构造 SuperTrend 通道，在趋势翻转时进出场，并可选大盘过滤、波动率体制过滤与 Turtle 式仓位管理。',
    logic:
      '计算 Pivot SuperTrend 方向；多头翻转且（可选）基准标的收盘价高于其长期均线时 buy，空头翻转时 sell。可启用 ATR 体制过滤（过低/过高波动跳过）、成交量确认、ATR 风险定仓，以及将 SuperTrend 轨道作为初始 stop_price。',
    inputs:
      '各交易标的与（若启用过滤）benchmark_symbol 的 K 线；parameters 含 pivot_period、atr_factor、过滤与 sizing 开关。',
    outputs:
      'TradeSignal（含可选 quantity、stop_price、confidence）；reasoning 描述翻转与过滤结果。',
    schedule:
      '默认定时 Cron（工作日 16:00 美中 CT）；使用库内 K 线，不注入市价。',
    parameters:
      'pivot_period、atr_factor、atr_period；use_benchmark_long_filter、use_atr_regime_filter、volume_confirm_mult、dollar_risk_pct 等。',
  },
  adaptive_turtle: {
    purpose:
      '自适应 Turtle / Donchian 突破：价格突破入场通道做多，跌破出场通道平仓，并用基准指数趋势过滤系统性空头环境。',
    logic:
      '入场：收盘价突破前一根 K 线对应的 N 日最高价（fast_period），且基准（默认 SPY）收盘高于其 M 日均线。出场：收盘跌破前一根对应的 M 日最低价（slow_period）。可选按 equity×dollar_risk_pct/ATR 计算买入数量。',
    inputs:
      'symbols（使用基准过滤时需包含 benchmark_symbol）；日线 bars；portfolio 或 parameters 中的 account_equity / account_cash。',
    outputs:
      'TradeSignal buy/sell；买入可带 quantity；reasoning 含通道价、基准过滤与 ATR 定仓信息。',
    schedule:
      '默认定时 Cron（工作日 16:00 美中 CT）。',
    parameters:
      'fast_period（入场通道）、slow_period（出场通道）、benchmark_symbol、benchmark_ma_period、atr_period、dollar_risk_pct。',
  },
}

const SECTION_LABELS: (keyof StrategyGuide)[] = [
  'purpose',
  'logic',
  'inputs',
  'outputs',
  'schedule',
  'parameters',
]

const SECTION_TITLES: Record<keyof StrategyGuide, string> = {
  purpose: '目的',
  logic: '运行逻辑',
  inputs: '输入',
  outputs: '输出',
  schedule: '调度说明',
  parameters: '主要参数',
}

export function getStrategyGuide(strategyId: string): StrategyGuide | null {
  return GUIDES[strategyId] ?? null
}

/** Multi-line text for list card (one section per line). */
export function formatStrategyGuide(guide: StrategyGuide): string {
  const lines: string[] = []
  for (const key of SECTION_LABELS) {
    const body = guide[key]
    if (body) lines.push(`【${SECTION_TITLES[key]}】${body}`)
  }
  return lines.join('\n')
}

/** Fallback when no structured guide exists. */
export function formatStrategyGuideFromDescription(
  strategyId: string,
  name: string,
  description: string | null,
): string {
  const guide = getStrategyGuide(strategyId)
  if (guide) return formatStrategyGuide(guide)
  const summary = (description || '').trim() || '暂无详细说明。'
  return `【目的】${name}\n【说明】${summary}`
}
