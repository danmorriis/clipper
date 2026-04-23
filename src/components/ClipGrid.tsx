import { useState } from 'react'
import { addManualClip } from '../api/client'
import { useSessionStore } from '../store/session'
import type { ClipCandidate } from '../types'
import ClipCard from './ClipCard'
import ManualClipModal from './ManualClipModal'

interface ClipGridProps {
  candidates: ClipCandidate[]
  selectedRank: number | null
  onSelect: (rank: number) => void
}

export default function ClipGrid({ candidates, selectedRank, onSelect }: ClipGridProps) {
  const { apiBase, sessionId, videoDuration, updateCandidate } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    sessionId: s.sessionId,
    videoDuration: s.videoDuration,
    updateCandidate: s.updateCandidate,
  }))
  const addCandidates = useSessionStore((s) => s.addCandidates)

  const [showManual, setShowManual] = useState(false)

  const handleAddManual = async (start: number, end: number, pre?: string, post?: string) => {
    if (!sessionId) return
    const clip = await addManualClip(apiBase, sessionId, {
      start_time: start,
      end_time: end,
      pre_track: pre,
      post_track: post,
    })
    addCandidates([clip])
    setShowManual(false)
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3 overflow-y-auto p-3 content-start">
        {candidates.map((c) => (
          <ClipCard
            key={c.rank}
            candidate={c}
            selected={c.rank === selectedRank}
            onSelect={() => onSelect(c.rank)}
          />
        ))}

        <button
          onClick={() => setShowManual(true)}
          className="flex items-center justify-center h-24 rounded-lg border-2 border-dashed border-border text-muted text-sm hover:border-foreground/50 hover:text-foreground transition-colors"
        >
          + Add Custom Clip
        </button>
      </div>

      {showManual && (
        <ManualClipModal
          videoDuration={videoDuration}
          onAdd={handleAddManual}
          onClose={() => setShowManual(false)}
        />
      )}
    </>
  )
}
