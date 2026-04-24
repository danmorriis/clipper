import { useState } from 'react'
import type { ClipCandidate } from '../types'

interface TrackEditModalProps {
  candidate: ClipCandidate
  trackNames: string[]
  onSave: (pre: string, post: string) => void
  onClose: () => void
}

export default function TrackEditModal({ candidate, trackNames, onSave, onClose }: TrackEditModalProps) {
  const [pre, setPre] = useState(candidate.pre_track ?? '')
  const [post, setPost] = useState(candidate.post_track ?? '')

  return (
    <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface-raised border border-border rounded-xl p-5 w-[360px] flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-foreground">Edit Tracks — Clip {candidate.rank}</h3>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Track Before</span>
          <input
            list={`track-names-${candidate.rank}-pre`}
            value={pre}
            onChange={(e) => setPre(e.target.value)}
            placeholder="Artist - Track name"
            className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground"
          />
          <datalist id={`track-names-${candidate.rank}-pre`}>
            {trackNames.map((t) => <option key={t} value={t} />)}
          </datalist>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Track After</span>
          <input
            list={`track-names-${candidate.rank}-post`}
            value={post}
            onChange={(e) => setPost(e.target.value)}
            placeholder="Artist - Track name"
            className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground"
          />
          <datalist id={`track-names-${candidate.rank}-post`}>
            {trackNames.map((t) => <option key={t} value={t} />)}
          </datalist>
        </label>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs rounded bg-surface-high text-muted hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(pre, post)}
            className="px-4 py-1.5 text-xs rounded bg-accent text-white hover:bg-accent/90"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
