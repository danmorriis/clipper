import { useEffect, useRef, useState } from 'react'
import type { ClipCandidate } from '../types'

interface TrackEditModalProps {
  candidate: ClipCandidate
  trackNames: string[]
  onSave: (pre: string, post: string) => void
  onClose: () => void
}

function TrackCombobox({
  value,
  onChange,
  trackNames,
  placeholder,
  id,
}: {
  value: string
  onChange: (v: string) => void
  trackNames: string[]
  placeholder: string
  id: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={containerRef} className="relative" id={id}>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        autoComplete="off"
        className="w-full bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground"
      />
      {open && (
        <div className="absolute z-50 top-full mt-0.5 left-0 right-0 bg-surface-raised border border-border rounded shadow-lg max-h-48 overflow-y-auto">
          {['Unknown', ...trackNames].map((t) => (
            <div
              key={t}
              onMouseDown={(e) => {
                e.preventDefault()
                onChange(t === 'Unknown' ? 'Unknown' : t)
                setOpen(false)
              }}
              className={`px-2.5 py-1.5 text-xs cursor-pointer hover:bg-surface-high ${
                (t === 'Unknown' ? value === '' : value === t) ? 'text-foreground font-medium' : 'text-muted'
              }`}
            >
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  )
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
          <TrackCombobox
            id={`track-pre-${candidate.rank}`}
            value={pre}
            onChange={setPre}
            trackNames={trackNames}
            placeholder="Artist - Track name"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Track After</span>
          <TrackCombobox
            id={`track-post-${candidate.rank}`}
            value={post}
            onChange={setPost}
            trackNames={trackNames}
            placeholder="Artist - Track name"
          />
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
