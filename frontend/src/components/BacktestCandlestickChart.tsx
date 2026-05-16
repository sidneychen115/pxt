import { useEffect, useRef } from 'react'
import { ColorType, createChart } from 'lightweight-charts'
import type { CandlestickData, SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts'
import { formatAppChartDay } from '../lib/formatTime'
import type { BacktestOhlcResponse, BacktestTrade } from '../types'

const DAILY_LIKE = new Set(['1d', '1wk', '1mo'])

/** Lightweight Charts rejects unsorted candles (strict increasing) / markers (non-decreasing). */
function prepareCandles(ohlc: BacktestOhlcResponse): CandlestickData[] {
  const tf = ohlc.timeframe
  const raw: CandlestickData[] = ohlc.bars.map(b => ({
    time: b.time as Time,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }))
  if (raw.length === 0) return raw
  if (DAILY_LIKE.has(tf)) {
    const byDay = new Map<string, CandlestickData>()
    for (const c of raw) {
      byDay.set(String(c.time), c)
    }
    return Array.from(byDay.keys())
      .sort((a, b) => a.localeCompare(b))
      .map(k => byDay.get(k)!)
  }
  raw.sort((a, b) => Number(a.time) - Number(b.time))
  const out: CandlestickData[] = []
  for (const c of raw) {
    const t = Number(c.time)
    const last = out[out.length - 1]
    if (last != null && Number(last.time) === t) {
      out[out.length - 1] = c
      continue
    }
    out.push(c)
  }
  return out
}

function cmpChartTime(a: Time, b: Time): number {
  if (typeof a === 'string' && typeof b === 'string') {
    return a < b ? -1 : a > b ? 1 : 0
  }
  return Number(a) - Number(b)
}

/** SeriesMarker must be ascending by `time`; equal times allowed */
function sortedMarkers(markers: SeriesMarker<Time>[]): SeriesMarker<Time>[] {
  return [...markers].sort((x, y) => {
    const c = cmpChartTime(x.time, y.time)
    if (c !== 0) return c
    if (x.position === y.position) return 0
    return x.position === 'belowBar' ? -1 : 1
  })
}

function tradeEventToChartTime(iso: string, timeframe: string): Time | null {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  if (DAILY_LIKE.has(timeframe)) {
    return formatAppChartDay(iso) as Time
  }
  return Math.floor(d.getTime() / 1000) as UTCTimestamp
}

/** Bar index for zoom when exact trade time was dropped by downsampling. */
function barIndexForTradeTime(
  candleData: CandlestickData[],
  target: Time,
  timeframe: string,
  edge: 'left' | 'right',
): number {
  const n = candleData.length
  if (n === 0) return 0
  const times = candleData.map(c => c.time)
  const direct = times.indexOf(target)
  if (direct >= 0) return direct
  if (DAILY_LIKE.has(timeframe)) {
    const ts = String(target)
    if (edge === 'left') {
      let best = 0
      for (let i = 0; i < n; i++) {
        if (String(times[i]) <= ts) best = i
      }
      return best
    }
    let best = n - 1
    for (let i = n - 1; i >= 0; i--) {
      if (String(times[i]) >= ts) best = i
    }
    return best
  }
  const tn = Number(target)
  let best = 0
  let bestDiff = Infinity
  for (let i = 0; i < n; i++) {
    const diff = Math.abs(Number(times[i]) - tn)
    if (diff < bestDiff) {
      bestDiff = diff
      best = i
    }
  }
  return best
}

interface BacktestCandlestickChartProps {
  ohlc: BacktestOhlcResponse
  trades: BacktestTrade[]
  /** Zoom viewport to this trade after data load (same symbol as `trades`). */
  focusTradeId?: number | null
}

export default function BacktestCandlestickChart({ ohlc, trades, focusTradeId = null }: BacktestCandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#111827' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1F2937' }, horzLines: { color: '#1F2937' } },
      width: containerRef.current.clientWidth,
      height: 560,
    })

    const series = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    const candleData = prepareCandles(ohlc)

    if (candleData.length > 0) {
      try {
        series.setData(candleData)
      } catch (e) {
        console.warn('BacktestCandlestickChart: setData failed', e)
      }
    }

    // Markers only render when their `time` matches a bar in the series (server downsampling keeps trade bars).
    const timeSet = new Set(candleData.map(c => c.time))
    const markers: SeriesMarker<Time>[] = []
    const tf = ohlc.timeframe
    for (const t of trades) {
      const entryT = tradeEventToChartTime(t.entry_time, tf)
      if (entryT != null && timeSet.has(entryT)) {
        markers.push({
          time: entryT,
          position: 'belowBar',
          color: '#4ade80',
          shape: 'arrowUp',
          text: '买',
        })
      }
      if (t.exit_time) {
        const exitT = tradeEventToChartTime(t.exit_time, tf)
        if (exitT != null && timeSet.has(exitT)) {
          markers.push({
            time: exitT,
            position: 'aboveBar',
            color: '#f87171',
            shape: 'arrowDown',
            text: '卖',
          })
        }
      }
    }
    try {
      series.setMarkers(sortedMarkers(markers))
    } catch (e) {
      console.warn('BacktestCandlestickChart: setMarkers failed', e)
    }

    if (candleData.length > 0) {
      const trade = focusTradeId != null ? trades.find(tr => tr.id === focusTradeId) : undefined
      if (trade) {
        const entryT = tradeEventToChartTime(trade.entry_time, tf)
        const exitT = trade.exit_time ? tradeEventToChartTime(trade.exit_time, tf) : entryT
        if (entryT != null && exitT != null) {
          let i0 = barIndexForTradeTime(candleData, entryT, tf, 'left')
          let i1 = trade.exit_time ? barIndexForTradeTime(candleData, exitT, tf, 'right') : i0
          if (i0 > i1) [i0, i1] = [i1, i0]
          const span = i1 - i0
          const pad = Math.max(3, Math.min(40, Math.floor(span * 0.25) + 5))
          const fromIdx = Math.max(0, i0 - pad)
          let toIdx = Math.min(candleData.length - 1, i1 + pad)
          let fIdx = fromIdx
          if (fIdx === toIdx && candleData.length > 1) {
            if (toIdx < candleData.length - 1) toIdx += 1
            else if (fIdx > 0) fIdx -= 1
          }
          chart.timeScale().setVisibleRange({
            from: candleData[fIdx].time,
            to: candleData[toIdx].time,
          })
        } else {
          chart.timeScale().fitContent()
        }
      } else {
        chart.timeScale().fitContent()
      }
    }

    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [ohlc, trades, focusTradeId])

  return <div ref={containerRef} className="w-full" />
}
