import type { ClipMode } from '../types'

const MODES: { value: ClipMode; label: string }[] = [
  { value: 'topn', label: 'Top #' },
  { value: 'all', label: 'All' },
  { value: 'timeslots', label: 'Timestamps' },
]

interface ModeToggleProps {
  value: ClipMode
  onChange: (mode: ClipMode) => void
}

export default function ModeToggle({ value, onChange }: ModeToggleProps) {
  return (
    <div className="relative flex bg-surface-high rounded-full p-[3px] gap-0">
      {MODES.map((m) => (
        <button
          key={m.value}
          onClick={() => onChange(m.value)}
          className={`
            relative z-10 px-5 py-1.5 rounded-full text-xs font-semibold transition-colors
            ${value === m.value ? 'bg-foreground text-surface' : 'text-muted hover:text-foreground'}
          `}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
