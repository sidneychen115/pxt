import { useState } from 'react'

export function ExpandCollapseButton({
  open,
  onToggle,
  expandLabel,
  collapseLabel,
  className = 'mt-1 text-[11px] text-blue-400 hover:text-blue-300',
}: {
  open: boolean
  onToggle: () => void
  expandLabel: string
  collapseLabel: string
  className?: string
}) {
  return (
    <button type="button" onClick={onToggle} className={className}>
      {open ? collapseLabel : expandLabel}
    </button>
  )
}

export function useCollapsible(initial = false) {
  const [open, setOpen] = useState(initial)
  return { open, toggle: () => setOpen(v => !v), setOpen }
}
