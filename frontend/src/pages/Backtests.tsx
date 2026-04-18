import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  fetchBacktests, fetchBacktest, triggerBacktest,
  fetchBacktestTrades, fetchEquityCurve,
} from '../api/backtests'
import { fetchStrategies } from '../api/strategies'
import MetricCard from '../components/MetricCard'
import EquityChart from '../components/EquityChart'
import SignalBadge from '../components/SignalBadge'

export default function Backtests() {
  const { id } = useParams<{ id?: string }>()
  const numId = id ? parseInt(id, 10) : NaN
  return !isNaN(numId) ? <BacktestDetail id={numId} /> : <BacktestList />
}

function BacktestList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: backtests, isLoading } = useQuery({
    queryKey: ['backtests'],
    queryFn: () => fetchBacktests(),
  })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    strategy_id: '',
    start_date: '2023-01-01',
    end_date: '2024-01-01',
    symbols: '',
    initial_capital: 100000,
  })
  const [exitPolicy, setExitPolicy] = useState({
    stop_loss_pct: '',
    stop_loss_abs: '',
    take_profit_pct: '',
    take_profit_abs: '',
    trailing_stop_pct: '',
    trailing_activate_pct: '',
    price_check_mode: 'close' as 'close' | 'ohlc',
  })

  const triggerMutation = useMutation({
    mutationFn: () => triggerBacktest({
      strategy_id: form.strategy_id,
      start_date: form.start_date,
      end_date: form.end_date,
      symbols: form.symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean),
      initial_capital: form.initial_capital,
      parameters: {},
      exit_policy: (() => {
        const ep = {
          stop_loss_pct: exitPolicy.stop_loss_pct !== '' ? parseFloat(exitPolicy.stop_loss_pct) / 100 : null,
          stop_loss_abs: exitPolicy.stop_loss_abs !== '' ? parseFloat(exitPolicy.stop_loss_abs) : null,
          take_profit_pct: exitPolicy.take_profit_pct !== '' ? parseFloat(exitPolicy.take_profit_pct) / 100 : null,
          take_profit_abs: exitPolicy.take_profit_abs !== '' ? parseFloat(exitPolicy.take_profit_abs) : null,
          trailing_stop_pct: exitPolicy.trailing_stop_pct !== '' ? parseFloat(exitPolicy.trailing_stop_pct) / 100 : null,
          trailing_activate_pct: exitPolicy.trailing_activate_pct !== '' ? parseFloat(exitPolicy.trailing_activate_pct) / 100 : null,
          price_check_mode: exitPolicy.price_check_mode,
        }
        return (ep.stop_loss_pct || ep.stop_loss_abs || ep.take_profit_pct || ep.take_profit_abs || ep.trailing_stop_pct || ep.trailing_activate_pct) ? ep : null
      })(),
    }),
    onSuccess: (data) => {
      setShowForm(false)
      qc.invalidateQueries({ queryKey: ['backtests'] })
      navigate(`/backtests/${data.id}`)
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Backtests</h1>
        <button
          onClick={() => setShowForm(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold"
        >
          + New Backtest
        </button>
      </div>
      {showForm && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-700 space-y-4">
          <h2 className="font-semibold">Configure Backtest</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400">Strategy</label>
              <select
                value={form.strategy_id}
                onChange={e => setForm(f => ({ ...f, strategy_id: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
              >
                <option value="">Select...</option>
                {strategies?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
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
                <label className="text-xs text-gray-400">Price Check Mode</label>
                <select
                  value={exitPolicy.price_check_mode}
                  onChange={e => setExitPolicy(p => ({ ...p, price_check_mode: e.target.value as 'close' | 'ohlc' }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                >
                  <option value="close">Close (fill at next open)</option>
                  <option value="ohlc">OHLC (intrabar fill at trigger price)</option>
                </select>
              </div>
            </div>
          </details>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">
              Cancel
            </button>
            <button
              onClick={() => triggerMutation.mutate()}
              disabled={!form.strategy_id || !form.symbols || triggerMutation.isPending}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold disabled:opacity-50"
            >
              {triggerMutation.isPending ? 'Starting...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      )}
      {isLoading && <div className="text-gray-400">Loading...</div>}
      <div className="space-y-3">
        {backtests?.map(bt => (
          <div
            key={bt.id}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/backtests/${bt.id}`)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') navigate(`/backtests/${bt.id}`) }}
            className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-gray-600 cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-gray-100">{bt.strategy_id}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {bt.start_date} → {bt.end_date} | {bt.symbols.join(', ')}
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                {bt.status === 'completed' && (
                  <>
                    <span className={bt.total_return != null && bt.total_return >= 0 ? 'text-green-400' : 'text-red-400'}>
                      {bt.total_return != null ? `${(bt.total_return * 100).toFixed(2)}%` : '—'}
                    </span>
                    <span className="text-gray-400">Sharpe: {bt.sharpe_ratio?.toFixed(2) ?? '—'}</span>
                  </>
                )}
                <span className={`text-xs px-2 py-0.5 rounded ${
                  bt.status === 'completed' ? 'bg-green-900 text-green-300' :
                  bt.status === 'failed' ? 'bg-red-900 text-red-300' :
                  'bg-yellow-900 text-yellow-300'
                }`}>{bt.status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BacktestDetail({ id }: { id: number }) {
  const navigate = useNavigate()
  const [sortBy, setSortBy] = useState('entry_time')
  const [sortOrder, setSortOrder] = useState('asc')
  const { data: bt, isLoading } = useQuery({
    queryKey: ['backtest', id],
    queryFn: () => fetchBacktest(id),
    refetchInterval: (q) => q.state.data?.status === 'running' ? 3000 : false,
  })
  const { data: trades } = useQuery({
    queryKey: ['bt-trades', id, sortBy, sortOrder],
    queryFn: () => fetchBacktestTrades(id, sortBy, sortOrder),
    enabled: bt?.status === 'completed',
  })
  const { data: equity } = useQuery({
    queryKey: ['bt-equity', id],
    queryFn: () => fetchEquityCurve(id),
    enabled: bt?.status === 'completed',
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>
  if (!bt) return <div className="text-gray-400">Not found.</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/backtests')} className="text-gray-400 hover:text-gray-200">← Back</button>
        <h1 className="text-2xl font-bold">{bt.strategy_id}</h1>
        <span className={`text-xs px-2 py-1 rounded font-semibold ${
          bt.status === 'completed' ? 'bg-green-900 text-green-300' :
          bt.status === 'failed' ? 'bg-red-900 text-red-300' :
          'bg-yellow-900 text-yellow-300'
        }`}>
          {bt.status}
        </span>
      </div>
      {bt.status === 'running' && <div className="text-yellow-400 text-sm">Backtest is running...</div>}
      {bt.status === 'completed' && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <MetricCard
              label="Total Return"
              value={bt.total_return != null ? `${(bt.total_return * 100).toFixed(2)}%` : '—'}
              color={bt.total_return != null && bt.total_return >= 0 ? 'green' : 'red'}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={bt.sharpe_ratio?.toFixed(2) ?? '—'}
              color={bt.sharpe_ratio != null && bt.sharpe_ratio >= 1 ? 'green' : 'gray'}
            />
            <MetricCard
              label="Max Drawdown"
              value={bt.max_drawdown != null ? `${(bt.max_drawdown * 100).toFixed(2)}%` : '—'}
              color="red"
            />
            <MetricCard label="Win Rate" value={bt.win_rate != null ? `${(bt.win_rate * 100).toFixed(1)}%` : '—'} />
            <MetricCard label="Profit Factor" value={bt.profit_factor?.toFixed(2) ?? '—'} />
            <MetricCard label="Total Trades" value={bt.total_trades ?? '—'} />
            <MetricCard label="Avg Hold Days" value={bt.avg_hold_days?.toFixed(1) ?? '—'} />
            <MetricCard
              label="Annualized Return"
              value={bt.annualized_return != null ? `${(bt.annualized_return * 100).toFixed(2)}%` : '—'}
            />
          </div>
          {equity && equity.length > 0 && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">Equity Curve</h2>
              <EquityChart data={equity} initialCapital={bt.initial_capital} />
            </div>
          )}
          {bt.llm_evaluation && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <h2 className="text-sm font-semibold text-gray-400 mb-3">AI Evaluation ({bt.llm_model})</h2>
              <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans">{bt.llm_evaluation}</pre>
            </div>
          )}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-4">
              <h2 className="text-sm font-semibold text-gray-300">Trade Log</h2>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs ml-auto"
              >
                <option value="entry_time">Entry Time</option>
                <option value="pnl">P&amp;L</option>
                <option value="hold_days">Hold Days</option>
                <option value="pnl_pct">Return %</option>
              </select>
              <select
                value={sortOrder}
                onChange={e => setSortOrder(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
              >
                <option value="asc">Asc</option>
                <option value="desc">Desc</option>
              </select>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs">
                  <th className="px-4 py-2 text-left">Symbol</th>
                  <th className="px-4 py-2 text-left">Dir</th>
                  <th className="px-4 py-2 text-right">Qty</th>
                  <th className="px-4 py-2 text-right">Entry</th>
                  <th className="px-4 py-2 text-right">Exit</th>
                  <th className="px-4 py-2 text-right">P&amp;L</th>
                  <th className="px-4 py-2 text-right">Return</th>
                  <th className="px-4 py-2 text-right">Days</th>
                  <th className="px-4 py-2 text-left">Reason</th>
                </tr>
              </thead>
              <tbody>
                {trades?.map(t => (
                  <tr key={t.id} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                    <td className="px-4 py-2 font-mono font-semibold text-gray-200">{t.symbol}</td>
                    <td className="px-4 py-2"><SignalBadge direction={t.direction} /></td>
                    <td className="px-4 py-2 text-right text-gray-300">{t.quantity}</td>
                    <td className="px-4 py-2 text-right text-gray-300">${t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right text-gray-300">
                      {t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-4 py-2 text-right font-semibold ${
                      t.pnl != null && t.pnl >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className={`px-4 py-2 text-right ${
                      t.pnl_pct != null && t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {t.pnl_pct != null ? `${(t.pnl_pct * 100).toFixed(2)}%` : '—'}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-400">{t.hold_days?.toFixed(0) ?? '—'}</td>
                    <td className="px-4 py-2 text-xs text-gray-500">{t.exit_reason ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {trades?.length === 0 && (
              <div className="text-gray-500 text-center py-6 text-sm">No trades.</div>
            )}
          </div>
        </>
      )}
      {bt.status === 'failed' && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          Backtest failed. Check system logs for details.
        </div>
      )}
    </div>
  )
}
