/**
 * Video player panel. Shows the HTML5 video element, playback controls,
 * and (optionally) the trim bar in edit mode.
 */

import { useEffect, useRef, useState } from 'react'
import { patchCandidate, videoUrl } from '../api/client'
import { useSessionStore } from '../store/session'
import type { ClipCandidate } from '../types'
import TrimBar from './TrimBar'

const CTX_PAD = 300  // seconds of context around clip shown in trim bar

interface VideoPlayerProps {
  candidate: ClipCandidate | null
}

function fmtTime(s: number): string {
  const t = Math.floor(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = t % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export default function VideoPlayer({ candidate }: VideoPlayerProps) {
  const { apiBase, videoPath, videoDuration, updateCandidate } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    videoPath: s.videoPath,
    videoDuration: s.videoDuration,
    updateCandidate: s.updateCandidate,
    sessionId: s.sessionId,
  }))
  const sessionId = useSessionStore((s) => s.sessionId)

  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [editMode, setEditMode] = useState(false)
  const [unlocked, setUnlocked] = useState(false)
  const maxClipRef = useRef(60)

  // Trim state (live during drag)
  const [trimStart, setTrimStart] = useState(0)
  const [trimEnd, setTrimEnd] = useState(60)
  const pendingTrimRef = useRef({ start: 0, end: 60 })

  const clipStartRef = useRef(0)
  const clipEndRef = useRef(60)

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
      video.currentTime = candidate.start_time
      setCurrentTime(candidate.start_time)
    }
  }, [candidate?.rank])

  // Clip window enforcement
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
  }, [])

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

  if (!candidate || !videoPath) {
    return (
      <div className="flex h-full items-center justify-center text-muted text-sm">
        Select a clip to preview
      </div>
    )
  }

  const src = videoUrl(apiBase, videoPath)

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

  const ctxStart = Math.max(0, candidate.start_time - CTX_PAD)
  const ctxEnd = Math.min(videoDuration, candidate.end_time + CTX_PAD)

  const handleEnterEdit = () => {
    setEditMode(true)
    setUnlocked(false)
    maxClipRef.current = 60
  }

  const handleLockToggle = () => {
    const nowUnlocked = !unlocked
    setUnlocked(nowUnlocked)
    maxClipRef.current = nowUnlocked ? Infinity : 60
  }

  const handleTrimChange = (start: number, end: number) => {
    clipStartRef.current = start
    clipEndRef.current = end
    setTrimStart(start)
    setTrimEnd(end)
    pendingTrimRef.current = { start, end }
    const video = videoRef.current
    if (video && (video.currentTime < start || video.currentTime > end)) {
      video.currentTime = start
    }
  }

  const handleApply = async () => {
    const { start, end } = pendingTrimRef.current
    if (!sessionId) return
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
    const video = videoRef.current
    clipStartRef.current = candidate.start_time
    clipEndRef.current = candidate.end_time
    setTrimStart(candidate.start_time)
    setTrimEnd(candidate.end_time)
    if (video) video.currentTime = candidate.start_time
    setEditMode(false)
    setUnlocked(false)
  }

  const trackLabel = () => {
    const pre = candidate.pre_track
    const post = candidate.post_track
    if (pre && post) return `${pre} → ${post}`
    if (pre) return pre
    if (post) return post
    return null
  }

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Video */}
      <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '16/9' }}>
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
          className="w-8 h-8 flex items-center justify-center rounded bg-surface-high hover:bg-border text-foreground text-sm"
        >
          {playing ? '⏸' : '▶'}
        </button>
        <button
          onClick={stop}
          className="w-8 h-8 flex items-center justify-center rounded bg-surface-high hover:bg-border text-foreground text-sm"
        >
          ⏹
        </button>
        <span className="text-xs text-muted font-mono ml-1">
          {fmtTime(currentTime)} / {fmtTime(candidate.end_time)}
        </span>

        {/* Seek bar */}
        <input
          type="range"
          min={candidate.start_time}
          max={candidate.end_time}
          step={0.1}
          value={currentTime}
          onChange={(e) => {
            const t = parseFloat(e.target.value)
            if (videoRef.current) videoRef.current.currentTime = t
          }}
          className="flex-1"
        />
      </div>

      {/* Track label */}
      {trackLabel() && (
        <p className="text-xs text-muted truncate">{trackLabel()}</p>
      )}

      {/* Edit Clip button — hidden for manual clips and when in edit mode */}
      {!editMode && !candidate.is_manual && (
        <button
          onClick={handleEnterEdit}
          className="self-start text-xs text-muted hover:text-foreground transition-colors"
        >
          Edit Clip
        </button>
      )}

      {/* Trim bar — only in edit mode */}
      {editMode && (
        <>
          <TrimBar
            ctxStart={ctxStart}
            ctxEnd={ctxEnd}
            trimStart={trimStart}
            trimEnd={trimEnd}
            playhead={currentTime}
            unlocked={unlocked}
            maxClip={maxClipRef.current}
            onTrimChange={handleTrimChange}
            onCommit={(s, e) => { pendingTrimRef.current = { start: s, end: e } }}
            onSeek={(t) => { if (videoRef.current) videoRef.current.currentTime = t }}
          />

          {/* Lock button */}
          <div className="flex justify-center">
            <button
              onClick={handleLockToggle}
              className="text-lg select-none"
              title={unlocked ? 'Lock to 1 minute' : 'Unlock from 1 minute'}
            >
              {unlocked ? '🔓' : '🔒'}
            </button>
          </div>

          {/* Cancel / Apply */}
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
        </>
      )}
    </div>
  )
}
