import { useState } from 'react'

function parseTs(text: string): number | null {
  const parts = text.split(':').map(Number)
  if (parts.some(isNaN)) return null
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return null
}

interface ManualClipModalProps {
  videoDuration: number
  onAdd: (start: number, end: number, pre?: string, post?: string) => void
  onClose: () => void
}

export default function ManualClipModal({ videoDuration, onAdd, onClose }: ManualClipModalProps) {
  const [startText, setStartText] = useState('')
  const [endText, setEndText] = useState('')
  const [preTrack, setPreTrack] = useState('')
  const [postTrack, setPostTrack] = useState('')
  const [error, setError] = useState('')

  const handleAdd = () => {
    const start = parseTs(startText.trim())
    const end = parseTs(endText.trim())
    if (start === null || end === null) {
      setError('Use mm:ss or hh:mm:ss format')
      return
    }
    if (start >= end) {
      setError('Start must be before end')
      return
    }
    if (end > videoDuration) {
      setError('End time exceeds video duration')
      return
    }
    onAdd(start, end, preTrack || undefined, postTrack || undefined)
  }

  return (
    <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface-raised border border-border rounded-xl p-5 w-[360px] flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-foreground">Add Custom Clip</h3>

        <div className="flex gap-3">
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-xs text-muted">Start</span>
            <input
              value={startText}
              onChange={(e) => { setStartText(e.target.value); setError('') }}
              placeholder="0:00:00"
              className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground font-mono"
            />
          </label>
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-xs text-muted">End</span>
            <input
              value={endText}
              onChange={(e) => { setEndText(e.target.value); setError('') }}
              placeholder="0:00:45"
              className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground font-mono"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Track Before (optional)</span>
          <input
            value={preTrack}
            onChange={(e) => setPreTrack(e.target.value)}
            placeholder="Artist - Track"
            className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Track After (optional)</span>
          <input
            value={postTrack}
            onChange={(e) => setPostTrack(e.target.value)}
            placeholder="Artist - Track"
            className="bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground"
          />
        </label>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs rounded bg-surface-high text-muted hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            className="px-4 py-1.5 text-xs rounded bg-accent text-white hover:bg-accent/90"
          >
            Add Clip
          </button>
        </div>
      </div>
    </div>
  )
}
