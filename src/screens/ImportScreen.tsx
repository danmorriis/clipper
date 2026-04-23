import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TitleBarSpacer from '../components/TitleBarSpacer'
import {
  cancelAnalysis,
  createSession,
  getSearchRoot,
  setSearchRoot,
  startAnalysis,
  validateTimestamps,
  validateVideo,
} from '../api/client'
import DropZone from '../components/DropZone'
import ModeToggle from '../components/ModeToggle'
import ProgressModal from '../components/ProgressModal'
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
  const [showProgress, setShowProgress] = useState(false)
  const [progressError, setProgressError] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)

  // Load saved search root on mount
  useEffect(() => {
    if (!apiBase) return
    getSearchRoot(apiBase).then(({ path }) => { if (path) setSearchRootState(path) }).catch(() => {})
  }, [apiBase])

  // Video drop handler — validate with API
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

  // Timestamp validation — format check runs immediately, bounds check requires a video
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
      setShowProgress(true)
      setProgressError('')

      await startAnalysis(apiBase, session.session_id)

      connect(
        `${apiBase}/sessions/${session.session_id}/analyze/stream`,
        (event: ProgressEvent) => {
          if (event.percent !== undefined) {
            setProgress({ percent: event.percent, message: event.message ?? '' })
          }
          if (event.error) {
            setProgressError(event.error)
          }
          if (event.thumbnails_done || (event.done && !event.error && !event.cancelled)) {
            setShowProgress(false)
            navigate(`/review/${session.session_id}`)
          }
          if (event.cancelled) {
            setShowProgress(false)
          }
        }
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
    setShowProgress(false)
  }

  return (
    <div className="relative isolate flex flex-col h-full bg-surface overflow-hidden">
      <TurntablePlatter />
      <TitleBarSpacer />

      {/* Main content — no page scroll, only textarea scrolls */}
      <div className="flex-1 min-h-0">
        <div className="max-w-lg mx-auto w-full h-full px-8 py-6 flex flex-col gap-6">

          <div className="text-center mb-4">
            <h1 className="text-[48px] font-black tracking-[-0.03em] text-foreground leading-none">
              BISCUIT FACTORY
            </h1>
            <p className="text-[11px] font-light tracking-[0.15em] text-muted uppercase mt-2">
              DJ set transition clipper
            </p>
          </div>

          {/* Drop zones */}
          <div className="flex flex-col gap-3">
            <DropZone
              label="Video"
              sublabel="MP4, MOV, MKV…"
              accept={['mp4', 'mov', 'mkv', 'avi', 'webm']}
              value={videoPath}
              onChange={handleVideoChange}
              error={!!videoError}
            />
            {videoError && <p className="text-xs text-red-700 -mt-2">{videoError}</p>}

            <DropZone
              label="Playlist"
              sublabel="M3U, M3U8, TXT (optional)"
              accept={['m3u', 'm3u8', 'txt']}
              value={playlistPath}
              onChange={setPlaylistPath}
            />
          </div>

          {/* Clip duration — centered */}
          <div className="flex flex-col items-center gap-3">
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

          {/* Mode — centered toggle */}
          <div className="flex flex-col items-center gap-3">
            <label className="text-[11px] text-muted font-medium uppercase tracking-[0.1em]">
              Mode
            </label>
            <ModeToggle value={mode} onChange={setMode} />

            {mode === 'all' && (
              <p className="text-xs italic text-muted text-center mt-1">
                This will make clips of every detected mixing transition.
              </p>
            )}

            {mode === 'topn' && (
              <div className="w-64 flex flex-col gap-2 mt-1">
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
              <div className="w-full flex flex-col gap-1.5 mt-1">
                <label className="text-xs text-muted">Timestamps if you already have them (one per line or comma-separated)</label>
                <textarea
                  value={tsText}
                  onChange={(e) => handleTsChange(e.target.value)}
                  placeholder="10:30&#10;00:45:40&#10;01:34:04"
                  rows={3}
                  className={`ts-textarea overflow-y-auto bg-surface-high border rounded px-3 py-2 text-xs font-mono text-foreground placeholder:text-[#5a5550] outline-none resize-none transition-colors ${
                    tsError ? 'border-red-600' : 'border-border focus:border-foreground'
                  }`}
                />
                {tsError && <p className="text-xs text-red-700">{tsError}</p>}
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Footer — music folder + create button */}
      <div>
        <div className="max-w-lg mx-auto w-full px-8 py-4 flex flex-col gap-3">

          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] text-muted font-medium uppercase tracking-[0.1em]">
              Music Folder
            </label>
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

      {showProgress && (
        <ProgressModal
          title="Analyzing…"
          percent={progress.percent}
          message={progress.message}
          error={progressError || null}
          onCancel={handleCancel}
        />
      )}
    </div>
  )
}
