import { useEffect, useMemo, useRef } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { Strategy } from '../types'
import type { ExitFormState } from '../lib/backtestFormConfig'
import {
  backtestTimeframeOptions,
  defaultWarmupMonthsForTimeframe,
  intradayFetchSpanDays,
  intradayYfinanceEarliestDate,
  isBacktestRangeTooOldForIntraday,
  isIntradayBacktestTimeframe,
  isTimeframeOutsideStrategyConfig,
  parseWarmupMonthsFromParameters,
  yfinanceMaxDaysForTimeframe,
} from '../lib/backtestTimeframe'
import {
  anchorTimeframeFromList,
  STRATEGY_TIMEFRAME_ORDER,
  timeframeLabel,
} from '../lib/strategyTimeframes'

export type BacktestFormFields = {
  strategy_id: string
  timeframe: string
  /** Percent of available cash per new buy (engine default sizing). */
  position_pct_percent: number
  start_date: string
  end_date: string
  symbols: string
  initial_capital: number
}

type Props = {
  form: BacktestFormFields
  setForm: Dispatch<SetStateAction<BacktestFormFields>>
  exitPolicy: ExitFormState
  setExitPolicy: Dispatch<SetStateAction<ExitFormState>>
  parametersJson: string
  setParametersJson: (v: string) => void
  strategies: Strategy[] | undefined
  /** 预设保存不含策略：在预设管理里隐藏策略下拉，仅在回测页选择 */
  showStrategySelect?: boolean
}

/**
 * Shared strategy / symbols / dates / parameters / exit rules block for new backtest and preset editor.
 */
export default function BacktestConfigForm({
  form,
  setForm,
  exitPolicy,
  setExitPolicy,
  parametersJson,
  setParametersJson,
  strategies,
  showStrategySelect = true,
}: Props) {
  const selectedStrategy = useMemo(
    () => strategies?.find(s => s.id === form.strategy_id),
    [strategies, form.strategy_id],
  )
  const prevStrategyIdRef = useRef(form.strategy_id)
  useEffect(() => {
    if (!form.strategy_id || form.strategy_id === prevStrategyIdRef.current) return
    prevStrategyIdRef.current = form.strategy_id
    const tfs = selectedStrategy?.timeframes
    if (!tfs?.length) return
    const anchor = anchorTimeframeFromList(tfs)
    setForm(f => (f.timeframe === anchor ? f : { ...f, timeframe: anchor }))
  }, [form.strategy_id, selectedStrategy, setForm])

  const timeframeOptions = backtestTimeframeOptions()
  const timeframeOutsideStrategy = isTimeframeOutsideStrategyConfig(
    form.timeframe,
    selectedStrategy,
  )
  const timeframeValueInOptions = (STRATEGY_TIMEFRAME_ORDER as readonly string[]).includes(
    form.timeframe,
  )

  const warmupMonths = useMemo(
    () => parseWarmupMonthsFromParameters(parametersJson, form.timeframe),
    [parametersJson, form.timeframe],
  )
  const intradayFetchSpan = useMemo(
    () =>
      isIntradayBacktestTimeframe(form.timeframe)
        ? intradayFetchSpanDays(form.start_date, form.end_date, warmupMonths)
        : 0,
    [form.start_date, form.end_date, form.timeframe, warmupMonths],
  )
  const yfMaxDays = yfinanceMaxDaysForTimeframe(form.timeframe)
  const defaultWarmup = defaultWarmupMonthsForTimeframe(form.timeframe)
  const intradaySpanWarning =
    isIntradayBacktestTimeframe(form.timeframe) && intradayFetchSpan > yfMaxDays
  const intradayTooOld =
    isIntradayBacktestTimeframe(form.timeframe) &&
    isBacktestRangeTooOldForIntraday(form.end_date, form.timeframe)

  return (
    <>
      <div className="grid grid-cols-2 gap-4">
        {showStrategySelect ? (
          <div>
            <label className="text-xs text-gray-400">Strategy</label>
            <select
              value={form.strategy_id}
              onChange={e => setForm(f => ({ ...f, strategy_id: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            >
              <option value="">Select...</option>
              {strategies?.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="col-span-2 rounded border border-dashed border-gray-700 bg-gray-800/30 px-3 py-2">
            <p className="text-xs text-gray-500 leading-relaxed">
              预设不保存策略。保存后在「新建回测」中加载预设，再自行选择要运行的策略。
            </p>
          </div>
        )}
        <div>
          <label className="text-xs text-gray-400">K 线周期</label>
          <select
            value={form.timeframe}
            onChange={e => setForm(f => ({ ...f, timeframe: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          >
            {timeframeOptions.map(tf => (
              <option key={tf} value={tf}>
                {timeframeLabel(tf)}
              </option>
            ))}
            {!timeframeValueInOptions && form.timeframe ? (
              <option value={form.timeframe}>{form.timeframe}</option>
            ) : null}
          </select>
          {isIntradayBacktestTimeframe(form.timeframe) && (
            <p className="text-[11px] text-amber-200/80 mt-1 leading-snug">
              日内周期：yfinance {form.timeframe} 约最近 {yfMaxDays} 天；可靠起始日建议 ≥{' '}
              {intradayYfinanceEarliestDate(new Date(), form.timeframe)}（滚动窗口边界当天常无数据）。
              默认预热{' '}
              {defaultWarmup} 月
              {warmupMonths !== defaultWarmup ? `（当前参数 ${warmupMonths} 月）` : ''}；可设{' '}
              <span className="font-mono">backtest_warmup_months</span>。15m/5m 预热过大易导致拉数失败。
            </p>
          )}
          {intradayTooOld && (
            <p className="text-[11px] text-red-300/90 mt-1 leading-snug">
              结束日期 {form.end_date} 早于 yfinance {form.timeframe} 可用范围（约{' '}
              {intradayYfinanceEarliestDate(new Date(), form.timeframe)} 之后）。请改选最近日期，或改用日线。
            </p>
          )}
          {intradaySpanWarning && (
            <p className="text-[11px] text-red-300/90 mt-1 leading-snug">
              预热+回测约 {intradayFetchSpan} 天（预热 {warmupMonths} 月），超过约 {yfMaxDays} 天限制；请缩短日期或降低{' '}
              <span className="font-mono">backtest_warmup_months</span>。服务端会自动下调预热，但回测窗口过长仍会失败。
            </p>
          )}
          {timeframeOutsideStrategy && (
            <p className="text-[11px] text-amber-200/80 mt-1 leading-snug">
              该策略实盘配置为{' '}
              {selectedStrategy!.timeframes.map(tf => timeframeLabel(tf)).join('、')}
              ；当前周期回测可能无信号或不符合策略设计（如 HA 月/日类策略请用日线）。
            </p>
          )}
        </div>
        <div>
          <label className="text-xs text-gray-400">Symbols (comma separated)</label>
          <input
            value={form.symbols}
            onChange={e => setForm(f => ({ ...f, symbols: e.target.value }))}
            placeholder="AAPL, SPY, MSFT"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400">Start Date</label>
          <input
            type="date"
            value={form.start_date}
            onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400">End Date</label>
          <input
            type="date"
            value={form.end_date}
            onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400">开仓资金比例 (%)</label>
          <input
            type="number"
            min={0}
            max={100}
            step={1}
            value={form.position_pct_percent}
            onChange={e =>
              setForm(f => ({
                ...f,
                position_pct_percent: Math.max(0, Math.min(100, Number(e.target.value) || 0)),
              }))
            }
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          />
          <p className="text-[11px] text-gray-500 mt-1 leading-snug">
            每笔买入最多使用当时可用现金的该比例。策略已指定股数时取较小值；HA 分槽等自算仓位仍以策略为准。
          </p>
        </div>
        <div>
          <label className="text-xs text-gray-400">Initial Capital ($)</label>
          <input
            type="number"
            value={form.initial_capital}
            onChange={e => setForm(f => ({ ...f, initial_capital: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
          />
        </div>
      </div>
      <details className="border border-gray-700 rounded p-3">
        <summary className="text-sm text-gray-400 cursor-pointer select-none">策略参数 (JSON，可选)</summary>
        <p className="text-[11px] text-gray-500 mt-2 leading-snug">
          K 线周期、开仓比例由上方控件写入{' '}
          <span className="font-mono">parameters.timeframe</span> /{' '}
          <span className="font-mono">backtest_position_pct</span>（比例为 0–1，如 0.2 表示 20%）；此处无需重复填写。
        </p>
        <textarea
          value={parametersJson}
          onChange={e => setParametersJson(e.target.value)}
          spellCheck={false}
          placeholder="{}"
          className="w-full mt-2 min-h-[88px] font-mono text-xs bg-gray-800 border border-gray-700 rounded px-3 py-2"
        />
      </details>
      <details className="border border-gray-700 rounded p-3">
        <summary className="text-sm text-gray-400 cursor-pointer select-none">Exit Rules (optional)</summary>
        <div className="grid grid-cols-2 gap-4 mt-3">
          <div>
            <label className="text-xs text-gray-400">Stop Loss %</label>
            <input
              type="number"
              min="0"
              step="0.1"
              placeholder="e.g. 5 for 5%"
              value={exitPolicy.stop_loss_pct}
              onChange={e => setExitPolicy(p => ({ ...p, stop_loss_pct: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Stop Loss $ (absolute)</label>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="e.g. 500 for $500 loss"
              value={exitPolicy.stop_loss_abs}
              onChange={e => setExitPolicy(p => ({ ...p, stop_loss_abs: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Take Profit %</label>
            <input
              type="number"
              min="0"
              step="0.1"
              placeholder="e.g. 15 for 15%"
              value={exitPolicy.take_profit_pct}
              onChange={e => setExitPolicy(p => ({ ...p, take_profit_pct: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Take Profit $ (absolute)</label>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="e.g. 2000 for $2000 gain"
              value={exitPolicy.take_profit_abs}
              onChange={e => setExitPolicy(p => ({ ...p, take_profit_abs: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Trailing Stop %</label>
            <input
              type="number"
              min="0"
              step="0.1"
              placeholder="e.g. 5 for 5%"
              value={exitPolicy.trailing_stop_pct}
              onChange={e => setExitPolicy(p => ({ ...p, trailing_stop_pct: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Trailing Activate % (optional)</label>
            <input
              type="number"
              min="0"
              step="0.1"
              placeholder="e.g. 10 to activate after 10% gain"
              value={exitPolicy.trailing_activate_pct}
              onChange={e => setExitPolicy(p => ({ ...p, trailing_activate_pct: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">开仓 / 信号 (Entry)</label>
            <select
              value={exitPolicy.entry_price_check_mode}
              onChange={e =>
                setExitPolicy(p => ({
                  ...p,
                  entry_price_check_mode: e.target.value as 'close' | 'ohlc',
                }))
              }
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            >
              <option value="close">Close（策略按收盘价生成信号）</option>
              <option value="ohlc">OHLC（与当根 high/low 相关的入场语义）</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">平仓 / 止损止盈 (Exit)</label>
            <select
              value={exitPolicy.exit_price_check_mode}
              onChange={e =>
                setExitPolicy(p => ({
                  ...p,
                  exit_price_check_mode: e.target.value as 'close' | 'ohlc',
                }))
              }
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
            >
              <option value="ohlc">OHLC（用当根 low/high 判定止损/止盈/移动止损）</option>
              <option value="close">Close（仅收盘价触发；触发后多在下一根开盘价成交）</option>
            </select>
          </div>
          <div className="col-span-2">
            <p className="text-[11px] text-gray-500 leading-snug">
              实际成交价由策略参数里的{' '}
              <span className="font-mono text-gray-400">backtest_fill_mode</span> 或策略类默认值决定：{' '}
              <span className="font-mono text-gray-400">same_close</span> 为当根收盘价成交；{' '}
              <span className="font-mono text-gray-400">next_open</span> 为下一根开盘价成交。可在「策略参数 (JSON)」中覆盖。
            </p>
          </div>
          <div className="col-span-2 flex items-start gap-2 pt-1">
            <input
              type="checkbox"
              id="disable_sell_signal_form"
              checked={exitPolicy.disable_sell_signal}
              onChange={e => setExitPolicy(p => ({ ...p, disable_sell_signal: e.target.checked }))}
              className="mt-1 rounded border-gray-600"
            />
            <label
              htmlFor="disable_sell_signal_form"
              className="text-sm text-gray-300 cursor-pointer select-none leading-snug"
            >
              禁用卖出信号（忽略策略 SELL，仅通过止损/止盈/移动止损或回测结束平仓）
            </label>
          </div>
        </div>
      </details>
    </>
  )
}
