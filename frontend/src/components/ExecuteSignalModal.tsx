import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { executeSignal } from '../api/signals'
import type { Signal } from '../types'
import { apiErrorMessage } from '../lib/apiError'
import { useAuthQueryKey } from '../hooks/useAuthQueryKey'

export default function ExecuteSignalModal({
  signal,
  onClose,
}: {
  signal: Signal
  onClose: () => void
}) {
  const qc = useQueryClient()
  const signalsKeyPrefix = useAuthQueryKey('signals')
  const positionsKey = useAuthQueryKey('positions')
  const summaryKey = useAuthQueryKey('position-summary')
  const [quantity, setQuantity] = useState('')
  const [fillPrice, setFillPrice] = useState('')
  const isBuy = signal.direction === 'buy'

  const mutation = useMutation({
    mutationFn: () =>
      executeSignal(signal.id, {
        quantity: Number(quantity),
        fill_price: Number(fillPrice),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: signalsKeyPrefix })
      qc.invalidateQueries({ queryKey: positionsKey })
      qc.invalidateQueries({ queryKey: summaryKey })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-sm space-y-4">
        <h2 className="text-lg font-semibold">
          {isBuy ? '开仓' : '平仓'} — {signal.symbol}
        </h2>
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
          成交单价
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
            disabled={mutation.isPending || !quantity || !fillPrice}
            onClick={() => mutation.mutate()}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:opacity-50"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  )
}
