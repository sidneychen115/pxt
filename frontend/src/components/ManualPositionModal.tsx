import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createManualFill } from '../api/positions'
import { apiErrorMessage } from '../lib/apiError'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

export default function ManualPositionModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const positionsKey = useAuthQueryKey('positions')
  const summaryKey = useAuthQueryKey('position-summary')
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [fillPrice, setFillPrice] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      createManualFill({
        symbol: symbol.trim().toUpperCase(),
        quantity: Number(quantity),
        fill_price: Number(fillPrice),
        side: 'buy',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: positionsKey })
      qc.invalidateQueries({ queryKey: summaryKey })
      onClose()
    },
  })

  const canSubmit =
    symbol.trim().length > 0 &&
    quantity !== '' &&
    fillPrice !== '' &&
    Number(quantity) > 0 &&
    Number(fillPrice) > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-sm space-y-4">
        <h2 className="text-lg font-semibold">手动开仓</h2>
        <p className="text-xs text-gray-500">
          录入已在券商持有的仓位；若已有同标的持仓，将按加权平均合并成本。
        </p>
        <label className="block text-sm text-gray-400">
          标的代码
          <input
            type="text"
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            placeholder="AAPL"
            className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white font-mono uppercase"
          />
        </label>
        <label className="block text-sm text-gray-400">
          股数
          <input
            type="number"
            min="0"
            step="any"
            value={quantity}
            onChange={e => setQuantity(e.target.value)}
            className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
          />
        </label>
        <label className="block text-sm text-gray-400">
          成本单价
          <input
            type="number"
            min="0"
            step="any"
            value={fillPrice}
            onChange={e => setFillPrice(e.target.value)}
            className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
          />
        </label>
        {mutation.isError && (
          <p className="text-red-400 text-sm">{apiErrorMessage(mutation.error)}</p>
        )}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-400">
            取消
          </button>
          <button
            type="button"
            disabled={mutation.isPending || !canSubmit}
            onClick={() => mutation.mutate()}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:opacity-50"
          >
            确认录入
          </button>
        </div>
      </div>
    </div>
  )
}
