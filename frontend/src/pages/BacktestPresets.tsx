import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createBacktestPreset,
  fetchBacktestPresets,
  removeBacktestPreset,
  updateBacktestPreset,
} from '../api/backtestPresetsApi'
import { fetchStrategies } from '../api/strategies'
import BacktestConfigForm, { type BacktestFormFields } from '../components/BacktestConfigForm'
import {
  EMPTY_EXIT_FORM,
  parseParametersJson,
  type ExitFormState,
} from '../lib/backtestFormConfig'
import {
  applyPreset,
  dtoToPreset,
  presetBodyFromSnapshot,
  snapshotFromCurrentForm,
  type BacktestPreset,
} from '../lib/backtestPresets'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

const defaultForm = (): BacktestFormFields => ({
  strategy_id: '',
  start_date: '2023-01-01',
  end_date: '2024-01-01',
  symbols: '',
  initial_capital: 100_000,
})

export default function BacktestPresets() {
  const qc = useQueryClient()
  const presetsKey = useAuthQueryKey('backtest-presets')
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: fetchStrategies })
  const { data: presetDtos, isLoading: presetsLoading } = useQuery({
    queryKey: presetsKey,
    queryFn: fetchBacktestPresets,
  })
  const presets = useMemo(() => (presetDtos ?? []).map(dtoToPreset), [presetDtos])

  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [presetName, setPresetName] = useState('')
  const [form, setForm] = useState<BacktestFormFields>(defaultForm)
  const [exitPolicy, setExitPolicy] = useState<ExitFormState>(() => ({ ...EMPTY_EXIT_FORM }))
  const [parametersJson, setParametersJson] = useState('{}')
  const [formError, setFormError] = useState<string | null>(null)

  const saveMutation = useMutation({
    mutationFn: async () => {
      parseParametersJson(parametersJson)
      const name = presetName.trim()
      if (!name) throw new Error('请填写预设名称')
      const snap = snapshotFromCurrentForm(form, exitPolicy, parametersJson)
      const body = presetBodyFromSnapshot(snap, name)
      if (editingId) {
        return updateBacktestPreset(editingId, body)
      }
      return createBacktestPreset(body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: presetsKey })
      closeModal()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => removeBacktestPreset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: presetsKey }),
  })

  const openNew = () => {
    setEditingId(null)
    setPresetName('')
    setForm(defaultForm())
    setExitPolicy({ ...EMPTY_EXIT_FORM })
    setParametersJson('{}')
    setFormError(null)
    setModalOpen(true)
  }

  const openEdit = (p: BacktestPreset) => {
    setEditingId(p.id)
    setPresetName(p.name)
    const snap = applyPreset(p)
    setForm({
      strategy_id: snap.strategy_id,
      start_date: snap.start_date,
      end_date: snap.end_date,
      symbols: snap.symbols,
      initial_capital: snap.initial_capital,
    })
    setExitPolicy(snap.exitPolicy)
    setParametersJson(snap.parametersJson)
    setFormError(null)
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingId(null)
    setFormError(null)
  }

  const handleSaveModal = () => {
    setFormError(null)
    saveMutation.mutate(undefined, {
      onError: e => {
        setFormError(e instanceof Error ? e.message : '保存失败')
      },
    })
  }

  const handleDelete = (id: string, name: string) => {
    if (!window.confirm(`删除预设「${name}」？`)) return
    deleteMutation.mutate(id)
  }

  const fmtCreated = (iso: string) => {
    const d = new Date(iso)
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString('zh-CN', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
            <Link to="/backtests" className="hover:text-gray-200">
              ← Backtests
            </Link>
          </div>
          <h1 className="text-2xl font-bold">预设管理</h1>
          <p className="text-sm text-gray-500 mt-1">
            预设保存在服务器数据库，同一后端下的客户端共享。在
            <Link to="/backtests" className="text-blue-400 hover:underline mx-1">
              新建回测
            </Link>
            中可快速加载或保存预设。
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold shrink-0"
        >
          + 新建预设
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/80">
        <table className="min-w-[800px] w-full text-sm text-left">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wide">
              <th className="px-3 py-2.5 font-medium">名称</th>
              <th className="px-3 py-2.5 font-medium">区间</th>
              <th className="px-3 py-2.5 font-medium">标的</th>
              <th className="px-3 py-2.5 font-medium">初始资金</th>
              <th className="px-3 py-2.5 font-medium">创建时间</th>
              <th className="px-3 py-2.5 font-medium whitespace-nowrap">操作</th>
            </tr>
          </thead>
          <tbody>
            {presetsLoading && (
              <tr>
                <td colSpan={6} className="px-3 py-10 text-center text-gray-500">
                  加载中…
                </td>
              </tr>
            )}
            {!presetsLoading && presets.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-10 text-center text-gray-500">
                  暂无预设。点击「新建预设」添加。
                </td>
              </tr>
            )}
            {!presetsLoading &&
              presets.map((p, idx) => (
                <tr
                  key={p.id}
                  className={`border-b border-gray-800/80 ${idx % 2 === 0 ? 'bg-gray-900/40' : 'bg-gray-900/20'}`}
                >
                  <td className="px-3 py-2 font-medium text-gray-100">{p.name}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">
                    {p.start_date} → {p.end_date}
                  </td>
                  <td className="px-3 py-2 text-gray-400 max-w-[200px] truncate" title={p.symbols}>
                    {p.symbols}
                  </td>
                  <td className="px-3 py-2 text-gray-300 tabular-nums">
                    {p.initial_capital.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-gray-500 text-xs whitespace-nowrap">{fmtCreated(p.createdAt)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => openEdit(p)}
                      className="text-blue-400 hover:text-blue-300 text-sm mr-3"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(p.id, p.name)}
                      disabled={deleteMutation.isPending}
                      className="text-red-400 hover:text-red-300 text-sm disabled:opacity-50"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-5 shadow-xl">
            <h2 className="text-lg font-semibold mb-4">{editingId ? '编辑预设' : '新建预设'}</h2>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-400">预设名称</label>
                <input
                  type="text"
                  value={presetName}
                  onChange={e => setPresetName(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mt-1"
                  placeholder="例如：SPY 日线 Pivot"
                />
              </div>
              <BacktestConfigForm
                form={form}
                setForm={setForm}
                exitPolicy={exitPolicy}
                setExitPolicy={setExitPolicy}
                parametersJson={parametersJson}
                setParametersJson={setParametersJson}
                strategies={strategies}
                showStrategySelect={false}
              />
              {formError && <p className="text-red-400 text-sm">{formError}</p>}
              <div className="flex gap-2 justify-end pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleSaveModal}
                  disabled={saveMutation.isPending}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold disabled:opacity-50"
                >
                  {saveMutation.isPending ? '保存中…' : '保存'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
