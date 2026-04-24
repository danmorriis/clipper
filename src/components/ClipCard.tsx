import { useRef, useState } from 'react'
import { patchCandidate, thumbnailUrl } from '../api/client'
import { useSessionStore } from '../store/session'
import type { ClipCandidate } from '../types'
import TrackEditModal from './TrackEditModal'

function cleanTrackName(name: string | null): string {
  if (!name) return ''
  const parts = name.split(' - ').map((seg) => seg.replace(/^\(?\d{1,3}\)?[\.\-\s]+/, '').trim()).filter(Boolean)
  if (parts.length >= 3) return `${parts[0]} - ${parts[parts.length - 1]}`
  return parts.join(' - ')
}

function fmtDur(seconds: number): string {
  const s = Math.round(seconds)
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m === 0) return `${s}s`
  if (rem === 0) return `${m}m`
  return `${m}m${rem}s`
}

function fmtTs(t: number): string {
  const s = Math.floor(t)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

interface ClipCardProps {
  candidate: ClipCandidate
  selected: boolean
  isNew?: boolean
  onSelect: () => void
}

export default function ClipCard({ candidate, selected, isNew = false, onSelect }: ClipCardProps) {
  const { apiBase, sessionId, updateCandidate, resolvedTrackNames } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    sessionId: s.sessionId,
    updateCandidate: s.updateCandidate,
    resolvedTrackNames: s.resolvedTrackNames,
  }))

  const [showTrackEdit, setShowTrackEdit] = useState(false)
  const [imgKey, setImgKey] = useState(0)
  const retryCount = useRef(0)

  const dur = candidate.end_time - candidate.start_time
  const header = `Clip ${candidate.rank}  ·  ${fmtDur(dur)}`

  const pre = cleanTrackName(candidate.pre_track)
  const post = cleanTrackName(candidate.post_track)

  const toggleKept = async () => {
    if (!sessionId) return
    const updated = await patchCandidate(apiBase, sessionId, candidate.rank, { kept: !candidate.kept })
    updateCandidate(candidate.rank, { kept: updated.kept })
  }

  const onTrackSave = async (newPre: string, newPost: string) => {
    if (!sessionId) return
    const updated = await patchCandidate(apiBase, sessionId, candidate.rank, {
      pre_track: newPre || null,
      post_track: newPost || null,
    } as any)
    updateCandidate(candidate.rank, { pre_track: updated.pre_track, post_track: updated.post_track })
    setShowTrackEdit(false)
  }

  const thumbSrc = sessionId ? thumbnailUrl(apiBase, sessionId, candidate.rank) : null

  return (
    <>
      <div
        onClick={onSelect}
        className={`
          relative flex flex-col rounded-lg overflow-hidden cursor-pointer
          border transition-all
          ${selected ? 'border-foreground' : 'border-border hover:border-foreground/40'}
          ${candidate.kept ? 'bg-surface-raised' : 'bg-surface opacity-60'}
        `}
      >
        <div className="relative w-full bg-surface-high" style={{ aspectRatio: '16/9' }}>
          {thumbSrc && (
            <img
              key={imgKey}
              src={thumbSrc}
              alt=""
              className="w-full h-full object-cover"
              onError={() => {
                if (retryCount.current < 6) {
                  retryCount.current++
                  setTimeout(() => setImgKey((k) => k + 1), 1500)
                }
              }}
            />
          )}
          {!thumbSrc && (
            <div className="absolute inset-0 flex items-center justify-center text-muted text-xs">
              No preview
            </div>
          )}
          {isNew && (
            <div className="absolute top-1.5 left-1.5 w-2.5 h-2.5 rounded-full bg-accent" />
          )}
        </div>

        <div className="p-2.5 flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-foreground">{header}</span>
            <span className="text-[10px] text-muted">{fmtTs(candidate.start_time)}</span>
          </div>

          <p className="text-[11px] text-muted truncate">
            {pre && post ? `${pre} → ${post}` : pre || post || 'Unknown track'}
          </p>

        </div>

        <button
          onClick={(e) => { e.stopPropagation(); toggleKept() }}
          className={`
            w-full py-1 text-[10px] font-medium tracking-[0.08em] uppercase
            ${candidate.kept
              ? 'bg-green-100 text-green-700 hover:bg-green-200 hover:text-green-800'
              : 'bg-red-100 text-red-600 hover:bg-red-200 hover:text-red-700'
            }
          `}
        >
          {candidate.kept ? 'Keep' : 'Binned'}
        </button>
      </div>

      {showTrackEdit && (
        <TrackEditModal
          candidate={candidate}
          trackNames={resolvedTrackNames}
          onSave={onTrackSave}
          onClose={() => setShowTrackEdit(false)}
        />
      )}
    </>
  )
}
