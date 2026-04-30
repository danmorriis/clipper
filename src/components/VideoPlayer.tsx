/**
 * Video player panel. Shows the HTML5 video element, playback controls,
 * and (optionally) the trim bar in edit mode.
 */

import { useEffect, useRef, useState } from 'react'
import { frameUrl, identifyAt, patchCandidate, videoUrl } from '../api/client'
import { useSessionStore } from '../store/session'
import type { ClipCandidate } from '../types'
import TrackEditModal from './TrackEditModal'
import TrimBar from './TrimBar'

const CTX_PAD = 180  // seconds of context around clip shown in trim bar

interface VideoPlayerProps {
  candidate: ClipCandidate | null
  /** When true the player covers the full video for new-clip creation */
  addClipMode?: boolean
  defaultClipDuration?: number
  onAddClip?: (start: number, end: number, pre: string | null, post: string | null) => void
  onCancelAdd?: () => void
}

function fmtTime(s: number): string {
  const t = Math.floor(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = t % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export default function VideoPlayer({ candidate, addClipMode = false, defaultClipDuration = 45, onAddClip, onCancelAdd }: VideoPlayerProps) {
  const { apiBase, videoPath, videoDuration, updateCandidate, resolvedTrackNames } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    videoPath: s.videoPath,
    videoDuration: s.videoDuration,
    updateCandidate: s.updateCandidate,
    resolvedTrackNames: s.resolvedTrackNames,
  }))
  const sessionId = useSessionStore((s) => s.sessionId)

  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [editMode, setEditMode] = useState(false)
  const [unlocked, setUnlocked] = useState(false)
  const [showTrackEdit, setShowTrackEdit] = useState(false)
  const maxClipRef = useRef(60)

  // Add-clip mode: detected track labels updated on handle commit
  const [addPreTrack, setAddPreTrack] = useState<string | null>(null)
  const [addPostTrack, setAddPostTrack] = useState<string | null>(null)

  // Trim state (live during drag)
  const [trimStart, setTrimStart] = useState(0)
  const [trimEnd, setTrimEnd] = useState(60)
  const pendingTrimRef = useRef({ start: 0, end: 60 })

  const clipStartRef = useRef(0)
  const clipEndRef = useRef(60)
  const seekTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Initialise trim state when entering add-clip mode
  useEffect(() => {
    if (!addClipMode) return
    clipStartRef.current = 0
    clipEndRef.current = defaultClipDuration
    setTrimStart(0)
    setTrimEnd(defaultClipDuration)
    pendingTrimRef.current = { start: 0, end: defaultClipDuration }
    setAddPreTrack(null)
    setAddPostTrack(null)
    setEditMode(false)
    setUnlocked(false)
    maxClipRef.current = 60
    const video = videoRef.current
    if (video) { video.pause(); video.currentTime = 0; setCurrentTime(0); setPlaying(false) }
  }, [addClipMode, defaultClipDuration])

  useEffect(() => {
    if (!candidate) return
    clipStartRef.current = candidate.start_time
    clipEndRef.current = candidate.end_time
    setTrimStart(candidate.start_time)
    setTrimEnd(candidate.end_time)
    pendingTrimRef.current = { start: candidate.start_time, end: candidate.end_time }
    setEditMode(false)
    setUnlocked(false)
    maxClipRef.current = 60

    const video = videoRef.current
    if (video) {
      video.pause()
      setPlaying(false)
      const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked)
        video.play().catch(() => {})
      }
      video.addEventListener('seeked', onSeeked)
      video.currentTime = candidate.start_time
      setCurrentTime(candidate.start_time)
    }
  }, [candidate?.rank])

  // Clip window enforcement + timeline sync.
  // Must re-run when candidate changes: on first render candidate is null so the
  // video element doesn't exist yet, meaning videoRef.current is null and listeners
  // would never attach with a [] dep array.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onTimeUpdate = () => {
      setCurrentTime(video.currentTime)
      if (video.currentTime >= clipEndRef.current) {
        video.pause()
        setPlaying(false)
      }
    }
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)

    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
    }
  }, [candidate?.rank])

  // Spacebar play/pause
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code === 'Space' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault()
        togglePlay()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [playing])

  if (!videoPath || (!candidate && !addClipMode)) {
    return (
      <div className="flex h-full items-center justify-center text-muted text-sm">
        Select a clip to preview
      </div>
    )
  }

  const src = videoUrl(apiBase, videoPath)
  const getFrameUrl = (t: number) => frameUrl(apiBase, videoPath, t)

  // In add-clip mode, context = full video; in edit mode = ±CTX_PAD around clip
  const ctxStartAdd = 0
  const ctxEndAdd = videoDuration

  const togglePlay = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      if (video.currentTime >= clipEndRef.current) {
        video.currentTime = clipStartRef.current
      }
      video.play()
    } else {
      video.pause()
    }
  }

  const stop = () => {
    const video = videoRef.current
    if (!video) return
    video.pause()
    video.currentTime = clipStartRef.current
    setCurrentTime(clipStartRef.current)
    setPlaying(false)
  }

  const ctxStart = candidate ? Math.max(0, candidate.start_time - CTX_PAD) : 0
  const ctxEnd = candidate ? Math.min(videoDuration, candidate.end_time + CTX_PAD) : videoDuration

  const handleEnterEdit = () => {
    setEditMode(true)
    setUnlocked(false)
    maxClipRef.current = 60
  }

  const handleLockToggle = () => {
    const nowUnlocked = !unlocked
    setUnlocked(nowUnlocked)
    maxClipRef.current = nowUnlocked ? Infinity : 60

    // Locking: if current duration exceeds 60s, snap end back to start + 60
    if (!nowUnlocked && trimEnd - trimStart > 60) {
      const snappedEnd = trimStart + 60
      clipEndRef.current = snappedEnd
      setTrimEnd(snappedEnd)
      pendingTrimRef.current = { start: trimStart, end: snappedEnd }
      const video = videoRef.current
      if (video) {
        video.currentTime = trimStart
        setCurrentTime(trimStart)
      }
    }
  }

  const handleTrimChange = (start: number, end: number) => {
    clipStartRef.current = start
    clipEndRef.current = end
    setTrimStart(start)
    setTrimEnd(end)
    pendingTrimRef.current = { start, end }
    setCurrentTime(start)
    // Debounce the actual video seek — seeking on every mousemove is expensive,
    // especially when the context window spans the full video in add-clip mode.
    if (seekTimerRef.current !== null) clearTimeout(seekTimerRef.current)
    seekTimerRef.current = setTimeout(() => {
      seekTimerRef.current = null
      if (videoRef.current) videoRef.current.currentTime = start
    }, 120)
  }

  const handleApply = async () => {
    if (!sessionId || !candidate) return
    const { start, end } = pendingTrimRef.current
    const updated = await patchCandidate(apiBase, sessionId, candidate.rank, {
      start_time: start,
      end_time: end,
    })
    updateCandidate(candidate.rank, { start_time: updated.start_time, end_time: updated.end_time })
    clipStartRef.current = updated.start_time
    clipEndRef.current = updated.end_time
    setEditMode(false)
    setUnlocked(false)
  }

  const handleCancel = () => {
    if (!candidate) return
    const video = videoRef.current
    clipStartRef.current = candidate.start_time
    clipEndRef.current = candidate.end_time
    setTrimStart(candidate.start_time)
    setTrimEnd(candidate.end_time)
    if (video) video.currentTime = candidate.start_time
    setEditMode(false)
    setUnlocked(false)
  }

  const pre = addClipMode ? addPreTrack : candidate?.pre_track ?? null
  const post = addClipMode ? addPostTrack : candidate?.post_track ?? null

  // Called when trim handles are released in add-clip mode — identify tracks live
  const handleAddClipCommit = async (start: number, end: number) => {
    pendingTrimRef.current = { start, end }
    if (!sessionId) return

    // Round 1: timeline-based pair confirmation (primary), with side hint so
    // the backend searches in the right direction from each handle position.
    const [preRes, postRes] = await Promise.all([
      identifyAt(apiBase, sessionId, start, { side: 'pre' }).catch(() => ({ track: null })),
      identifyAt(apiBase, sessionId, end, { side: 'post' }).catch(() => ({ track: null })),
    ])

    let preTrack = preRes.track
    let postTrack = postRes.track

    // Round 2: if one side is still unknown, use the known side's position in
    // the ordered playlist to target just its immediate neighbour and retry with
    // a relaxed threshold.
    if (!preTrack && postTrack) {
      const hinted = await identifyAt(apiBase, sessionId, start, { side: 'pre', hint: { track: postTrack, position: 'post' } }).catch(() => ({ track: null }))
      preTrack = hinted.track
    } else if (!postTrack && preTrack) {
      const hinted = await identifyAt(apiBase, sessionId, end, { side: 'post', hint: { track: preTrack, position: 'pre' } }).catch(() => ({ track: null }))
      postTrack = hinted.track
    }

    setAddPreTrack(preTrack)
    setAddPostTrack(postTrack)
  }

  const handleConfirmAddClip = () => {
    const { start, end } = pendingTrimRef.current
    onAddClip?.(start, end, addPreTrack, addPostTrack)
  }

  const onTrackSave = async (newPre: string, newPost: string) => {
    if (!sessionId || !candidate) return
    const updated = await patchCandidate(apiBase, sessionId, candidate.rank, {
      pre_track: newPre || null,
      post_track: newPost || null,
    } as any)
    updateCandidate(candidate.rank, { pre_track: updated.pre_track, post_track: updated.post_track })
    setShowTrackEdit(false)
  }

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Video — counter-invert so the picture stays correct in dark mode */}
      <div className="no-invert relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '16/9' }}>
        <video
          ref={videoRef}
          src={src}
          className="w-full h-full object-contain"
          preload="metadata"
        />
      </div>

      {/* Playback controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={togglePlay}
          className="w-8 h-8 flex items-center justify-center rounded bg-surface-high hover:bg-border text-foreground"
        >
          {playing ? (
            <svg width="11" height="13" viewBox="0 0 11 13" fill="currentColor">
              <rect x="0" y="0" width="3.5" height="13" rx="1"/>
              <rect x="7.5" y="0" width="3.5" height="13" rx="1"/>
            </svg>
          ) : (
            <svg width="11" height="13" viewBox="0 0 11 13" fill="currentColor">
              <path d="M1 0.5L10.5 6.5L1 12.5V0.5Z"/>
            </svg>
          )}
        </button>
        <button
          onClick={stop}
          className="w-8 h-8 flex items-center justify-center rounded bg-surface-high hover:bg-border text-foreground"
        >
          <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor">
            <rect x="0" y="0" width="11" height="11" rx="1.5"/>
          </svg>
        </button>
        <span className="text-xs text-muted font-mono ml-1">
          {addClipMode
            ? fmtTime(currentTime)
            : `${fmtTime(Math.max(0, currentTime - trimStart))} / ${fmtTime(trimEnd - trimStart)}`
          }
        </span>

        {/* Seek bar */}
        <input
          type="range"
          min={addClipMode ? 0 : trimStart}
          max={addClipMode ? videoDuration : trimEnd}
          step={0.1}
          value={currentTime}
          onChange={(e) => {
            const t = parseFloat(e.target.value)
            if (videoRef.current) videoRef.current.currentTime = t
          }}
          className="flex-1"
        />
      </div>

      {/* Track labels + Edit Clip */}
      <div className="flex flex-col text-xs text-muted">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            {addClipMode ? (
              <span className="truncate block">
                {pre && post
                  ? `${pre} → ${post}`
                  : pre || post || <span className="italic">Drag handles to identify tracks…</span>}
              </span>
            ) : (
              <button
                onClick={() => setShowTrackEdit(true)}
                className="truncate block w-full text-left hover:text-foreground transition-colors"
                title="Click to edit tracks"
              >
                {pre && post
                  ? `${pre} → ${post}`
                  : pre || post || <span className="italic">Unknown track — click to set</span>}
              </button>
            )}
          </div>
          {!addClipMode && !editMode && candidate && !candidate.is_manual && (
            <button
              onClick={handleEnterEdit}
              className="shrink-0 px-3 py-1 text-xs rounded bg-surface-high border border-border text-muted hover:text-foreground hover:border-foreground/50 transition-colors"
            >
              Edit Clip
            </button>
          )}
        </div>
      </div>

      {/* Trim bar — always in add-clip mode, only in edit mode otherwise */}
      {(addClipMode || editMode) && (
        <div className="no-invert flex flex-col gap-2">
          <TrimBar
            ctxStart={addClipMode ? ctxStartAdd : ctxStart}
            ctxEnd={addClipMode ? ctxEndAdd : ctxEnd}
            trimStart={trimStart}
            trimEnd={trimEnd}
            playhead={currentTime}
            unlocked={unlocked}
            maxClip={maxClipRef.current}
            getFrameUrl={getFrameUrl}
            onTrimChange={handleTrimChange}
            onCommit={addClipMode
              ? (s, e) => { handleAddClipCommit(s, e) }
              : (s, e) => { pendingTrimRef.current = { start: s, end: e } }
            }
            onSeek={(t) => { if (videoRef.current) videoRef.current.currentTime = t }}
          />

          {/* Lock button — in both edit and add-clip modes */}
          {(editMode || addClipMode) && (
            <div className="flex justify-center">
              <button
                onClick={handleLockToggle}
                className="w-8 h-8 flex items-center justify-center rounded bg-surface-high border border-border text-foreground hover:border-foreground/50 transition-colors"
                title={unlocked ? 'Lock to 1 minute' : 'Unlock from 1 minute'}
              >
                {unlocked ? (
                  <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
                    <path d="M11 7V5a4 4 0 0 0-8 0v2H2a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1zm-5 0V5a2 2 0 1 1 4 0v2H6z" opacity="0.4"/>
                    <rect x="1" y="7" width="12" height="9" rx="1"/>
                    <circle cx="7" cy="12" r="1.5" fill="white"/>
                  </svg>
                ) : (
                  <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
                    <path d="M3 7V5a4 4 0 0 1 8 0v2h1a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h1zm2 0h4V5a2 2 0 1 0-4 0v2z"/>
                    <rect x="1" y="7" width="12" height="9" rx="1"/>
                    <circle cx="7" cy="12" r="1.5" fill="white"/>
                  </svg>
                )}
              </button>
            </div>
          )}

          {/* Add-clip mode buttons */}
          {addClipMode && (
            <div className="flex gap-2 justify-end">
              <button
                onClick={onCancelAdd}
                className="px-4 py-1.5 text-xs rounded bg-surface-high text-muted hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmAddClip}
                className="px-4 py-1.5 text-xs rounded bg-orange-500 text-white hover:bg-orange-400 transition-colors font-medium"
              >
                Add Clip
              </button>
            </div>
          )}

          {/* Cancel / Apply — regular edit mode */}
          {editMode && (
            <div className="flex gap-2 justify-end">
              <button
                onClick={handleCancel}
                className="px-4 py-1.5 text-xs rounded bg-surface-high text-muted hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleApply}
                className="px-4 py-1.5 text-xs rounded bg-accent text-white hover:bg-accent/90 transition-colors"
              >
                Apply
              </button>
            </div>
          )}
        </div>
      )}
      {showTrackEdit && candidate && (
        <TrackEditModal
          candidate={candidate}
          trackNames={resolvedTrackNames}
          onSave={onTrackSave}
          onClose={() => setShowTrackEdit(false)}
        />
      )}
    </div>
  )
}
