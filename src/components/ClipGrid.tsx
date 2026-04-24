import type { ClipCandidate } from '../types'
import ClipCard from './ClipCard'

interface ClipGridProps {
  candidates: ClipCandidate[]
  selectedRank: number | null
  newRanks: Set<number>
  onSelect: (rank: number) => void
  onAddMode: () => void
}

export default function ClipGrid({ candidates, selectedRank, newRanks, onSelect, onAddMode }: ClipGridProps) {
  return (
    <div className="grid grid-cols-2 gap-3 p-3 content-start">
      {candidates.map((c) => (
        <ClipCard
          key={c.rank}
          candidate={c}
          selected={c.rank === selectedRank}
          isNew={newRanks.has(c.rank)}
          onSelect={() => onSelect(c.rank)}
        />
      ))}

      <button
        onClick={onAddMode}
        className="flex items-center justify-center h-24 rounded-lg border-2 border-dashed border-border text-muted text-sm hover:border-foreground/50 hover:text-foreground transition-colors"
      >
        + Add Custom Clip
      </button>
    </div>
  )
}
