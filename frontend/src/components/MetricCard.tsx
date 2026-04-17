interface MetricCardProps {
  label: string
  value: string | number | null
  sub?: string
  color?: 'green' | 'red' | 'blue' | 'gray'
}

export default function MetricCard({ label, value, sub, color = 'gray' }: MetricCardProps) {
  const colors = {
    green: 'text-green-400',
    red: 'text-red-400',
    blue: 'text-blue-400',
    gray: 'text-gray-100',
  }
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colors[color]}`}>
        {value ?? '—'}
      </div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  )
}
