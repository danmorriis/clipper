import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TitleBarSpacer from '../components/TitleBarSpacer'
import {
  cancelAnalysis,
  createSession,
  getSearchRoot,
  getSession,
  setSearchRoot,
  startAnalysis,
  validateTimestamps,
  validateVideo,
} from '../api/client'
import DropZone from '../components/DropZone'
import ModeToggle from '../components/ModeToggle'
import TurntablePlatter from '../components/TurntablePlatter'
import { useSSE } from '../hooks/useSSE'
import { useSessionStore } from '../store/session'
import type { ClipMode, ProgressEvent } from '../types'

const DURATIONS = [30, 45, 60]
const TS_RE = /^\d{1,2}:\d{2}(:\d{2})?$/

export default function ImportScreen() {
  const { apiBase, setSession, setCandidates } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    setSession: s.setSession,
    setCandidates: s.setCandidates,
  }))
  const navigate = useNavigate()
  const { connect, close } = useSSE()

  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [videoDuration, setVideoDuration] = useState(0)
  const [playlistPath, setPlaylistPath] = useState<string | null>(null)
  const [searchRoot, setSearchRootState] = useState('')
  const [clipDuration, setClipDuration] = useState(45)
  const [mode, setMode] = useState<ClipMode>('topn')
  const [nClips, setNClips] = useState(10)
  const [tsText, setTsText] = useState('')
  const [tsError, setTsError] = useState('')
  const [videoError, setVideoError] = useState('')

  const [progress, setProgress] = useState({ percent: 0, message: '' })
  const [analysing, setAnalysing] = useState(false)
  const [fadingOut, setFadingOut] = useState(false)
  const [progressError, setProgressError] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)

  const isMac = window.electronAPI?.platform() === 'darwin'
  const titleBarHeight = isMac ? 32 : 0

  useEffect(() => {
    if (!apiBase) return
    getSearchRoot(apiBase).then(({ path }) => { if (path) setSearchRootState(path) }).catch(() => {})
  }, [apiBase])

  const handleVideoChange = async (path: string) => {
    setVideoPath(path)
    setVideoError('')
    try {
      const { duration_seconds } = await validateVideo(apiBase, path)
      if (duration_seconds < 300) {
        setVideoError('Video must be at least 5 minutes long')
      } else {
        setVideoDuration(duration_seconds)
      }
    } catch {
      setVideoError('Could not read video file')
    }
  }

  const handleTsChange = async (text: string) => {
    setTsText(text)
    if (!text.trim()) { setTsError(''); return }

    const lines = text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)
    const malformed = lines.filter((l) => !TS_RE.test(l))
    if (malformed.length > 0) {
      setTsError(`Invalid format: ${malformed.join(', ')} — use mm:ss or hh:mm:ss`)
      return
    }

    if (!videoDuration) { setTsError(''); return }

    try {
      const result = await validateTimestamps(apiBase, text, videoDuration)
      if (result.out_of_bounds.length > 0) {
        setTsError(`Out of range: ${result.out_of_bounds.join(', ')}`)
      } else {
        setTsError('')
      }
    } catch {
      setTsError('')
    }
  }

  const handleSearchRootChange = async (path: string) => {
    setSearchRootState(path)
    if (path) {
      try { await setSearchRoot(apiBase, path) } catch {}
    }
  }

  const browseSearchRoot = async () => {
    if (!window.electronAPI) return
    const folder = await window.electronAPI.openFolderDialog()
    if (folder) handleSearchRootChange(folder)
  }

  const canCreate = videoPath && videoDuration >= 300 && !videoError && (mode !== 'timeslots' || (tsText.trim() && !tsError))

  const handleCreate = async () => {
    if (!canCreate) return

    let manualTimestamps: number[] = []
    if (mode === 'timeslots') {
      const result = await validateTimestamps(apiBase, tsText, videoDuration)
      if (result.malformed.length || result.out_of_bounds.length) return
      manualTimestamps = result.valid
    }

    try {
      const session = await createSession(apiBase, {
        videoPath: videoPath!,
        playlistPath: playlistPath ?? undefined,
        searchRoot: searchRoot || undefined,
        clipDuration,
        nClips,
        clipAll: mode === 'all',
        manualTimestamps,
      })
      setSession(session)
      setSessionId(session.session_id)
      setProgress({ percent: 0, message: 'Starting…' })
      setAnalysing(true)
      setProgressError('')

      await startAnalysis(apiBase, session.session_id)

      connect(
        `${apiBase}/sessions/${session.session_id}/analyze/stream`,
        (event: ProgressEvent) => {
          if (event.percent !== undefined) {
            setProgress({ percent: event.percent, message: event.message ?? '' })
          }
          if (event.thumbnail_ready) {
            setProgress({ percent: 100, message: 'Generating thumbnails…' })
          }
          if (event.error) {
            setProgressError(event.error)
          }
          if (event.thumbnails_done) {
            setFadingOut(true)
            getSession(apiBase, session.session_id)
              .then((fresh) => setSession(fresh))
              .catch(() => {})
              .finally(() => {
                setTimeout(() => navigate(`/review/${session.session_id}`), 700)
              })
          }
          if (event.cancelled) {
            setAnalysing(false)
          }
        },
        undefined,
        (ev) => !!ev.thumbnails_done || !!ev.error || !!ev.cancelled,
      )
    } catch (err: any) {
      setProgressError(err.message ?? 'Unknown error')
    }
  }

  const handleCancel = async () => {
    if (sessionId) {
      await cancelAnalysis(apiBase, sessionId).catch(() => {})
      close()
    }
    setAnalysing(false)
  }

  const uiOpacity = { opacity: analysing ? 0 : 1, pointerEvents: analysing ? 'none' : 'auto' } as const

  return (
    <div
      className="relative isolate h-full bg-surface overflow-hidden transition-opacity duration-700"
      style={{ opacity: fadingOut ? 0 : 1 }}
    >
      <TurntablePlatter analysing={analysing} percent={progress.percent} />

      {/* macOS drag region */}
      <TitleBarSpacer />

      {/* Progress overlay — tracks platter center */}
      {analysing && (
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ zIndex: 10, transform: 'translateY(20px)' }}
        >
          <div className="flex flex-col items-center gap-2">
            <p className="text-[11px] font-light tracking-[0.15em] text-muted uppercase">
              {progress.message}
            </p>
            {progressError && <p className="text-xs text-red-700">{progressError}</p>}
            <button
              onClick={handleCancel}
              className="mt-2 px-4 py-1.5 rounded-full text-[10px] font-medium tracking-[0.1em] uppercase text-muted border border-muted hover:text-foreground hover:border-foreground transition-colors pointer-events-auto"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/*
        Title — pinned to window top, independent of platter position.
        512px wide, centred horizontally.
      */}
      <div
        className="absolute left-1/2 -translate-x-1/2 w-[512px] px-8 pt-6 transition-opacity duration-500"
        style={{ top: titleBarHeight, ...uiOpacity }}
      >
        <div className="text-center relative">
          <h1 className="text-[48px] font-black tracking-[-0.03em] text-foreground leading-none">
            CLIP LAB
          </h1>
          <p className="text-[11px] font-light tracking-[0.15em] text-muted uppercase mt-2">
            DJ set transition clipper
          </p>
          <p className="absolute top-full left-0 right-0 text-[10px] font-light tracking-[0.15em] text-muted uppercase mt-1">
            by biscuit boy
          </p>
        </div>
      </div>

      {/*
        Controls — anchored to the platter centre so they move with the SVG on resize.

        Derivation (at default 840 × 1280 window):
          platter centre y  = window_height/2 + 20  = 440
          controls block top (desired) = 256  (so clip-dur with -mt-6 renders at y=232)
          offset from platter centre   = 440 − 256 = 184 px
          top:50% references window centre (420), not platter centre (440)
          → translateY = −(184 − 20) = −164 px
      */}
      <div
        className="absolute left-1/2 w-[512px] px-8 transition-opacity duration-500"
        style={{ top: '50%', transform: 'translate(-50%, -164px)', ...uiOpacity }}
      >
        <div className="flex flex-col gap-5">

          {/* Clip duration */}
          <div className="flex flex-col items-center gap-3 -mt-6">
            <label className="text-[11px] text-muted font-medium uppercase tracking-[0.1em]">
              Clip Duration
            </label>
            <div className="flex gap-2">
              {DURATIONS.map((d) => (
                <button
                  key={d}
                  onClick={() => setClipDuration(d)}
                  className={`px-5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
                    clipDuration === d
                      ? 'bg-foreground text-surface'
                      : 'bg-surface-high text-muted hover:text-foreground'
                  }`}
                >
                  {d}s
                </button>
              ))}
            </div>
          </div>

          {/* Mode */}
          <div className="flex flex-col items-center gap-3">
            <label className="text-[11px] text-muted font-medium uppercase tracking-[0.1em]">
              Mode
            </label>
            <ModeToggle value={mode} onChange={setMode} />

            {/* Fixed-height container — prevents drop zones from shifting between modes */}
            <div className="w-full flex flex-col items-center justify-center h-24">
              {mode === 'all' && (
                <p className="text-xs italic text-muted text-center mb-6">
                  This will make clips of <span className="font-bold not-italic text-accent">every</span> detected mixing transition.
                </p>
              )}

              {mode === 'topn' && (
                <div className="w-64 flex flex-col gap-2 mb-6">
                  <div className="flex justify-between items-center">
                    <label className="text-xs text-muted">Number of clips</label>
                    <span className="text-xs font-semibold text-foreground">{nClips}</span>
                  </div>
                  <input
                    type="range"
                    min={5}
                    max={20}
                    value={nClips}
                    onChange={(e) => setNClips(parseInt(e.target.value))}
                  />
                </div>
              )}

              {mode === 'timeslots' && (
                <div className="w-full flex flex-col gap-1.5 mb-6 -mx-2 px-0" style={{ width: 'calc(100% + 1rem)' }}>
                  <label className="text-xs text-muted text-center">
                    Timestamps if you already have them (one per line or comma-separated)
                  </label>
                  <textarea
                    value={tsText}
                    onChange={(e) => handleTsChange(e.target.value)}
                    placeholder="10:30, 00:45:40"
                    rows={1}
                    className={`ts-textarea overflow-y-auto bg-surface-high border rounded px-3 py-2 text-xs font-mono text-foreground placeholder:text-[#5a5550] outline-none resize-none transition-colors ${
                      tsError ? 'border-red-600' : 'border-border focus:border-foreground'
                    }`}
                  />
                  {tsError && <p className="text-xs text-red-700">{tsError}</p>}
                </div>
              )}
            </div>
          </div>

          {/* Drop zones — extended outward so outer top corners reach the circle edge */}
          <div className="flex gap-3 items-start -mt-10" style={{ marginLeft: -10, marginRight: -10 }}>
            <div className="flex-1">
              <DropZone
                label="Video"
                sublabel="MP4, MOV, MKV…"
                accept={['mp4', 'mov', 'mkv', 'avi', 'webm']}
                value={videoPath}
                onChange={handleVideoChange}
                error={!!videoError}
                errorMessage={videoError || undefined}
                style={{ height: 220, borderRadius: '8px 8px 8px 269px', paddingBottom: 48, paddingLeft: 28 }}
              />
            </div>

            <div className="flex-1">
              <DropZone
                label="Tracklist"
                sublabel="M3U, M3U8, TXT (optional)"
                accept={['m3u', 'm3u8', 'txt']}
                value={playlistPath}
                onChange={setPlaylistPath}
                style={{ height: 220, borderRadius: '8px 8px 269px 8px', paddingBottom: 48, paddingRight: 28 }}
              />
            </div>
          </div>

        </div>
      </div>

      {/* Footer — fixed 512px wide, pinned to window bottom */}
      <div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[512px] transition-opacity duration-500"
        style={uiOpacity}
      >
        <div className="px-8 py-4 flex flex-col gap-3">

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <label className="text-[11px] text-muted font-medium uppercase tracking-[0.1em]">
                Music Folder
              </label>
              <div className="relative group">
                <div className="w-3.5 h-3.5 rounded-full border border-muted flex items-center justify-center cursor-default">
                  <span className="text-[9px] text-muted leading-none">i</span>
                </div>
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-2.5 py-2 rounded bg-foreground text-surface text-[10px] leading-relaxed opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-150 z-50">
                  Location of your music files for ID matching — top level folder on your USB or drive that contains all your music.
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <input
                value={searchRoot}
                onChange={(e) => setSearchRootState(e.target.value)}
                onBlur={(e) => handleSearchRootChange(e.target.value)}
                placeholder="Path to your music library"
                className="flex-1 bg-surface-high border border-border rounded-lg px-3 py-2 text-xs text-foreground outline-none focus:border-foreground transition-colors placeholder:text-muted"
              />
              {window.electronAPI && (
                <button
                  onClick={browseSearchRoot}
                  className="px-3 py-2 text-xs rounded-lg bg-surface-high border border-border text-muted hover:text-foreground transition-colors"
                >
                  Browse
                </button>
              )}
            </div>
          </div>

          <button
            onClick={handleCreate}
            disabled={!canCreate}
            className="w-full py-3 rounded-lg bg-accent text-white text-sm font-bold hover:bg-accent/90 disabled:opacity-25 disabled:cursor-not-allowed transition-all"
          >
            Create Clips
          </button>

        </div>
      </div>

    </div>
  )
}
