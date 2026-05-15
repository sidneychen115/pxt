import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchStrategies, updateStrategy } from '../api/strategies'
import type { Strategy } from '../types'
import {
  STRATEGY_TIMEFRAME_ORDER,
  anchorTimeframeFromList,
  minIntervalMinutesFromTimeframes,
  timeframeLabel,
} from '../lib/strategyTimeframes'
import {
  defaultCronForStrategy,
  describeLiveSchedule,
  isValidCronExpression,
  scheduleModeFromFrequency,
  timeframesForCronSave,
  type ScheduleMode,
} from '../lib/strategySchedule'
import { parseSymbolList } from '../lib/parseSymbols'
import { apiErrorMessage } from '../lib/apiError'
import { parseParametersJson } from '../lib/backtestFormConfig'

function parametersJsonString(params: Record<string, unknown> | undefined): string {
  return JSON.stringify(params ?? {}, null, 2)
}

export default function Strategies() {
  const qc = useQueryClient()
  const { data: strategies, isLoading } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const [editing, setEditing] = useState<Strategy | null>(null)

  const toggleMutation = useMutation({
    mutationFn: (s: Strategy) => updateStrategy(s.id, { is_active: !s.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Strategies</h1>
      <div className="space-y-3">
        {strategies?.map(s => (
          <div key={s.id} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold text-gray-100">{s.name}</div>
                <div className="text-xs text-gray-400 mt-0.5">{s.description}</div>
                <div className="flex gap-2 mt-2 flex-wrap">
                  {s.symbols.map(sym => (
                    <span key={sym} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded">{sym}</span>
                  ))}
                </div>
                <div className="text-xs text-gray-500 mt-1 space-y-0.5">
                  {scheduleModeFromFrequency(s.run_frequency) === 'interval' && (
                    <div>
                      跟踪周期：
                      {s.timeframes.length ? s.timeframes.map(tf => timeframeLabel(tf)).join('、') : '—'}
                    </div>
                  )}
                  <div>
                    {describeLiveSchedule(
                      s.run_frequency,
                      s.run_interval_minutes,
                      s.run_anchor_timeframe,
                      s.timeframes,
                      timeframeLabel,
                      minIntervalMinutesFromTimeframes,
                      anchorTimeframeFromList,
                      s.id,
                    )}
                  </div>
                  {Object.keys(s.parameters ?? {}).length > 0 && (
                    <div
                      className="text-[11px] text-gray-500 font-mono truncate max-w-md"
                      title={parametersJsonString(s.parameters)}
                    >
                      参数：{parametersJsonString(s.parameters)}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex gap-2 items-center">
                <button
                  onClick={() => setEditing(s)}
                  className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded border border-gray-700"
                >
                  Edit
                </button>
                <button
                  onClick={() => toggleMutation.mutate(s)}
                  className={`text-xs px-3 py-1 rounded font-semibold ${
                    s.is_active ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {s.is_active ? 'Active' : 'Inactive'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {editing && (
        <StrategyEditModal
          strategy={editing}
          onClose={() => {
            setEditing(null)
            qc.invalidateQueries({ queryKey: ['strategies'] })
          }}
        />
      )}
    </div>
  )
}

function StrategyEditModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [symbols, setSymbols] = useState(strategy.symbols.join(', '))
  const parsedSymbols = parseSymbolList(symbols)
  const overMax = parsedSymbols.length > strategy.max_symbols
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>(
    () => strategy.schedule_mode ?? scheduleModeFromFrequency(strategy.run_frequency),
  )
  const [cronExpression, setCronExpression] = useState(() =>
    defaultCronForStrategy(strategy.id, strategy.run_frequency),
  )
  const [selectedTf, setSelectedTf] = useState<Set<string>>(() => new Set(strategy.timeframes))
  const [parametersJson, setParametersJson] = useState(() =>
    parametersJsonString(strategy.parameters),
  )
  const defaultParametersJson = parametersJsonString(strategy.default_parameters)

  const mutation = useMutation({
    mutationFn: () => {
      if (overMax) {
        throw new Error(
          `标的数量 ${parsedSymbols.length} 超过本策略上限 ${strategy.max_symbols}，请删减后保存`,
        )
      }
      let parameters: Record<string, unknown>
      try {
        parameters = parseParametersJson(parametersJson)
      } catch {
        throw new Error('策略参数必须是合法的 JSON 对象')
      }
      const payload: Parameters<typeof updateStrategy>[1] = {
        symbols: parsedSymbols,
        parameters,
      }

      if (scheduleMode === 'cron') {
        const cron = cronExpression.trim()
        if (!isValidCronExpression(cron)) {
          throw new Error(
            '请填写有效的 5 段 Cron（分 时 日 月 周），例如：0 14 * * mon-fri（America/Chicago）',
          )
        }
        payload.run_frequency = cron
        payload.timeframes = timeframesForCronSave(strategy.id, strategy.timeframes)
      } else {
        const ordered = STRATEGY_TIMEFRAME_ORDER.filter(tf => selectedTf.has(tf))
        if (ordered.length === 0) {
          throw new Error('请至少选择一个 K 线周期')
        }
        payload.timeframes = ordered
        const mins = minIntervalMinutesFromTimeframes(ordered)
        payload.run_frequency = `${mins}m`
      }

      return updateStrategy(strategy.id, payload)
    },
    onSuccess: onClose,
  })

  const toggleTf = (tf: string) => {
    setSelectedTf(prev => {
      const next = new Set(prev)
      if (next.has(tf)) next.delete(tf)
      else next.add(tf)
      return next
    })
  }

  const resetParametersToDefaults = () => {
    setParametersJson(defaultParametersJson)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl p-6 w-full max-w-lg border border-gray-700 space-y-4 max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold">编辑：{strategy.name}</h2>
        <div>
          <label htmlFor="symbols-input" className="text-xs text-gray-400">跟踪标的（英文逗号分隔）</label>
          <input
            id="symbols-input"
            value={symbols}
            onChange={e => setSymbols(e.target.value)}
            className={`w-full bg-gray-800 border rounded px-3 py-2 text-sm mt-1 ${
              overMax ? 'border-red-600' : 'border-gray-700'
            }`}
          />
          <p className={`text-[11px] mt-1 ${overMax ? 'text-red-400' : 'text-gray-500'}`}>
            已解析 {parsedSymbols.length} 个标的（上限 {strategy.max_symbols}）
          </p>
        </div>

        <div>
          <span className="text-xs text-gray-400">实盘调度</span>
          <div className="flex gap-4 mt-2 mb-3 text-xs">
            <label className="inline-flex items-center gap-1.5 cursor-pointer text-gray-300">
              <input
                type="radio"
                name="scheduleMode"
                checked={scheduleMode === 'cron'}
                onChange={() => setScheduleMode('cron')}
              />
              Cron 定时（美中 CT）
            </label>
            <label className="inline-flex items-center gap-1.5 cursor-pointer text-gray-300">
              <input
                type="radio"
                name="scheduleMode"
                checked={scheduleMode === 'interval'}
                onChange={() => setScheduleMode('interval')}
              />
              按 K 线周期间隔
            </label>
          </div>

          {scheduleMode === 'cron' ? (
            <div className="mb-1">
              <label htmlFor="cron-expr" className="text-xs text-gray-400">
                Cron 表达式（5 段：分 时 日 月 周）
              </label>
              <input
                id="cron-expr"
                type="text"
                value={cronExpression}
                onChange={e => setCronExpression(e.target.value)}
                placeholder="0 14 * * mon-fri"
                className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm font-mono"
                spellCheck={false}
              />
              <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
                时区为 America/Chicago。示例：工作日 14:00 →{' '}
                <code className="text-gray-400">0 14 * * mon-fri</code>
                ；每天 9:30 与 14:00 → <code className="text-gray-400">30 9,14 * * mon-fri</code>
                。HA 策略到点用市价作日线 close（不写 ohlcv_bars）。
              </p>
            </div>
          ) : (
            <>
              <p className="text-[11px] text-gray-500 mb-3">
                按所选周期中最短 K 线间隔同步并执行（使用库内 K 线，不注入市价）。
              </p>
              <div>
                <span className="text-xs text-gray-400">K 线周期（可多选）</span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {STRATEGY_TIMEFRAME_ORDER.map(tf => (
                    <label
                      key={tf}
                      className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border cursor-pointer ${
                        selectedTf.has(tf)
                          ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                          : 'border-gray-700 bg-gray-800/60 text-gray-400'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="rounded border-gray-600"
                        checked={selectedTf.has(tf)}
                        onChange={() => toggleTf(tf)}
                      />
                      {timeframeLabel(tf)}
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="strategy-params" className="text-xs text-gray-400">
              策略参数（JSON）
            </label>
            <button
              type="button"
              onClick={resetParametersToDefaults}
              className="text-[11px] text-blue-400 hover:text-blue-300"
            >
              恢复默认
            </button>
          </div>
          <div className="mt-2">
            <span className="text-[11px] text-gray-500 block mb-1">默认值（只读）</span>
            <pre className="text-[11px] text-gray-400 bg-gray-950/80 border border-gray-800 rounded px-3 py-2 overflow-x-auto font-mono leading-relaxed">
              {defaultParametersJson}
            </pre>
          </div>
          <textarea
            id="strategy-params"
            value={parametersJson}
            onChange={e => setParametersJson(e.target.value)}
            rows={8}
            spellCheck={false}
            className="w-full mt-2 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs font-mono leading-relaxed"
          />
          {strategy.id === 'ha_month_week_band' && (
            <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
              对称死区：上沿 = 月 HA open + |open|×<code className="text-gray-400">band_pct</code> +{' '}
              <code className="text-gray-400">band_abs</code>。Confidence 由突破幅度计算：{' '}
              <code className="text-gray-400">floor + confidence_excess_scale × excess</code>（上限{' '}
              <code className="text-gray-400">confidence_cap</code>）；band 为 0 时用相对 benchmark 偏离。
            </p>
          )}
        </div>

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={overMax}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {mutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 text-xs">
            {apiErrorMessage(mutation.error, '保存失败')}
          </p>
        )}
      </div>
    </div>
  )
}
