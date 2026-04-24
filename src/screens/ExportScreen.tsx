import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelExport, startExport } from '../api/client'
import ProgressModal from '../components/ProgressModal'
import TitleBarSpacer from '../components/TitleBarSpacer'
import { useSSE } from '../hooks/useSSE'
import { useSessionStore } from '../store/session'
import type { ProgressEvent } from '../types'

interface LogEntry {
  text: string
  type: 'info' | 'success' | 'error'
}

export default function ExportScreen() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const { apiBase, outputDir, candidates } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    outputDir: s.outputDir,
    candidates: s.candidates,
  }))
  const { connect, close } = useSSE()

  const [folder, setFolder] = useState(outputDir ?? '')
  const [log, setLog] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState({ percent: 0, message: '' })
  const [exporting, setExporting] = useState(false)
  const [done, setDone] = useState(false)
  const [tracklist, setTracklist] = useState<string>('')
  const [exportDir, setExportDir] = useState<string>('')
  const [error, setError] = useState('')
  const logEndRef = useRef<HTMLDivElement>(null)

  const keptCount = candidates.filter((c) => c.kept).length

  const addLog = (text: string, type: LogEntry['type'] = 'info') => {
    setLog((prev) => [...prev, { text, type }])
    setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  const browseFolder = async () => {
    if (!window.electronAPI) return
    const f = await window.electronAPI.openFolderDialog()
    if (f) setFolder(f)
  }

  const handleExport = async () => {
    if (!sessionId || !folder) return
    setExporting(true)
    setDone(false)
    setError('')
    setLog([])
    setTracklist('')
    setExportDir('')

    try {
      await startExport(apiBase, sessionId, folder)
      addLog(`Exporting ${keptCount} clip${keptCount !== 1 ? 's' : ''}…`)

      connect(
        `${apiBase}/sessions/${sessionId}/export/stream`,
        (event: ProgressEvent) => {
          if (event.percent !== undefined) {
            setProgress({ percent: event.percent, message: event.message ?? '' })
          }
          if (event.clip_done) {
            const { rank, tracks } = event.clip_done
            const clipName = rank != null ? `Clip ${rank}` : `Clip ${event.clip_done.index + 1}`
            const trackStr = tracks.map((t: any) => t.track_name).join(' → ')
            addLog(`${clipName}.mp4  —  ${trackStr || 'unidentified'}`, 'success')
          }
          if (event.error) {
            setError(event.error)
            addLog(`Error: ${event.error}`, 'error')
            setExporting(false)
          }
          if (event.done && !event.error && !event.cancelled) {
            addLog('Export complete. tracklist.txt written.', 'success')
            setExporting(false)
            setDone(true)
            if (event.tracklist) setTracklist(event.tracklist)
            if (event.export_dir) setExportDir(event.export_dir)
          }
          if (event.cancelled) {
            addLog('Export cancelled.', 'info')
            setExporting(false)
          }
        }
      )
    } catch (err: any) {
      setError(err.message ?? 'Unknown error')
      setExporting(false)
    }
  }

  const handleCancel = async () => {
    if (sessionId) {
      await cancelExport(apiBase, sessionId).catch(() => {})
      close()
    }
    setExporting(false)
  }

  const openFolder = () => {
    const dir = exportDir || folder
    if (dir && window.electronAPI) window.electronAPI.openFolder(dir)
  }

  return (
    <div className="flex flex-col h-full bg-surface">
      <TitleBarSpacer />

      <div className="flex-1 overflow-y-auto px-8 py-4 flex flex-col gap-5 max-w-lg mx-auto w-full">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/review/${sessionId}`)}
            className="text-xs text-muted hover:text-foreground transition-colors"
          >
            ← Back
          </button>
          <h1 className="text-lg font-semibold text-foreground">Export</h1>
        </div>

        <p className="text-xs text-muted">{keptCount} clip{keptCount !== 1 ? 's' : ''} selected for export</p>

        {/* Output folder */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted font-medium uppercase tracking-wide">Output Folder</label>
          <div className="flex gap-2">
            <input
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="/Users/you/Desktop/clips"
              className="flex-1 bg-surface-high border border-border rounded px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-white"
            />
            {window.electronAPI && (
              <button
                onClick={browseFolder}
                className="px-3 py-1.5 text-xs rounded bg-surface-high border border-border text-muted hover:text-foreground"
              >
                Browse
              </button>
            )}
          </div>
          {exportDir && done && (
            <p className="text-[10px] text-muted">Saved to: <span className="text-foreground">{exportDir}</span></p>
          )}
        </div>

        {/* Export button */}
        {!done && (
          <button
            onClick={handleExport}
            disabled={!folder || exporting || keptCount === 0}
            className="py-2.5 rounded-lg bg-accent text-white text-sm font-bold hover:bg-accent/90 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
          >
            Export {keptCount} Clip{keptCount !== 1 ? 's' : ''}
          </button>
        )}

        {/* Clip log */}
        {log.length > 0 && (
          <div className="bg-surface-raised border border-border rounded-lg p-3 max-h-48 overflow-y-auto flex flex-col gap-1">
            {log.map((entry, i) => (
              <span
                key={i}
                className={`text-xs font-mono ${
                  entry.type === 'success' ? 'text-green-600' :
                  entry.type === 'error' ? 'text-red-600' :
                  'text-muted'
                }`}
              >
                {entry.text}
              </span>
            ))}
            <div ref={logEndRef} />
          </div>
        )}

        {/* Tracklist — shown after export completes */}
        {done && tracklist && (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted font-medium uppercase tracking-wide">Tracklist</p>
            <pre className="bg-surface-raised border border-border rounded-lg p-3 text-xs text-foreground font-mono whitespace-pre-wrap select-all leading-relaxed">
              {tracklist}
            </pre>
          </div>
        )}

        {/* Post-export actions */}
        {done && (
          <div className="flex items-center gap-3">
            <button
              onClick={openFolder}
              className="text-xs text-muted hover:text-foreground transition-colors"
            >
              Open in Finder →
            </button>
          </div>
        )}

        {/* Return button — fades in last */}
        {done && (
          <button
            onClick={() => { useSessionStore.getState().reset(); navigate('/') }}
            className="py-2.5 rounded-lg bg-accent text-white text-sm font-bold hover:bg-accent/90 transition-colors animate-fadeIn"
          >
            Return to Menu
          </button>
        )}
      </div>

      {exporting && (
        <ProgressModal
          title="Exporting…"
          percent={progress.percent}
          message={progress.message}
          error={error || null}
          onCancel={handleCancel}
        />
      )}
    </div>
  )
}
