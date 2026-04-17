export default function SignalBadge({ direction }: { direction: string }) {
  const styles: Record<string, string> = {
    buy: 'bg-green-900 text-green-300 border border-green-700',
    sell: 'bg-red-900 text-red-300 border border-red-700',
    hold: 'bg-gray-800 text-gray-400 border border-gray-700',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${styles[direction] ?? styles.hold}`}>
      {direction}
    </span>
  )
}
