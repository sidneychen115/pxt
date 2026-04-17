import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineStyle } from 'lightweight-charts'
import type { EquityPoint } from '../types'

interface EquityChartProps {
  data: EquityPoint[]
  initialCapital: number
}

export default function EquityChart({ data, initialCapital }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#111827' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1F2937' }, horzLines: { color: '#1F2937' } },
      width: containerRef.current.clientWidth,
      height: 300,
    })

    const equitySeries = chart.addLineSeries({
      color: '#3B82F6',
      lineWidth: 2,
      title: 'Portfolio Equity',
    })

    const baselineSeries = chart.addLineSeries({
      color: '#6B7280',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Initial Capital',
    })

    const chartData = data.map(p => ({
      time: p.ts.split('T')[0] as `${number}-${number}-${number}`,
      value: p.equity,
    }))

    equitySeries.setData(chartData)
    baselineSeries.setData(
      chartData.map(p => ({ time: p.time, value: initialCapital }))
    )

    chart.timeScale().fitContent()

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current!.clientWidth })
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data, initialCapital])

  return <div ref={containerRef} className="w-full" />
}
