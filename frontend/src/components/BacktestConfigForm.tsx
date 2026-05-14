import type { Dispatch, SetStateAction } from 'react'
import type { Strategy } from '../types'
import type { ExitFormState } from '../lib/backtestFormConfig'

export type BacktestFormFields = {
  strategy_id: string
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
