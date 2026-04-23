import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { generateMore, getSession } from '../api/client'
import ClipGrid from '../components/ClipGrid'
import TitleBarSpacer from '../components/TitleBarSpacer'
import VideoPlayer from '../components/VideoPlayer'
import { useSessionStore } from '../store/session'

export default function ReviewScreen() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()

  const {
    apiBase,
    candidates,
    selectedRank,
    allCandidatesCount,
    nextAllIdx,
    selectCard,
    addCandidates,
    setSession,
    setCandidates,
  } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    candidates: s.candidates,
    selectedRank: s.selectedRank,
    allCandidatesCount: s.allCandidatesCount,
    nextAllIdx: s.nextAllIdx,
    selectCard: s.selectCard,
    addCandidates: s.addCandidates,
    setSession: s.setSession,
    setCandidates: s.setCandidates,
  }))
  const storeSessionId = useSessionStore((s) => s.sessionId)

  // Reload session state if page was navigated to directly (e.g. dev reload)
  useEffect(() => {
    if (!sessionId || !apiBase) return
    if (storeSessionId === sessionId) return
    getSession(apiBase, sessionId).then((s) => setSession(s)).catch(() => {})
  }, [sessionId, apiBase, storeSessionId, setSession])

  const selectedCandidate = candidates.find((c) => c.rank === selectedRank) ?? null

  const keptCount = candidates.filter((c) => c.kept).length
  const hasMore = nextAllIdx < allCandidatesCount

  const keepAll = () => {
    candidates.forEach((c) => {
      if (!c.kept) {
        useSessionStore.getState().updateCandidate(c.rank, { kept: true })
      }
    })
  }

  const binAll = () => {
    candidates.forEach((c) => {
      if (c.kept) {
        useSessionStore.getState().updateCandidate(c.rank, { kept: false })
      }
    })
  }

  const handleGenerateMore = async () => {
    if (!sessionId) return
    try {
      const more = await generateMore(apiBase, sessionId, 5)
      addCandidates(more)
    } catch {}
  }

  return (
    <div className="flex flex-col h-full bg-surface">
      <TitleBarSpacer />

      {/* Top bar */}
      <div className="no-drag flex items-center gap-3 px-4 py-2.5 border-b border-border shrink-0">
        <button
          onClick={() => navigate('/')}
          className="text-xs text-muted hover:text-foreground transition-colors"
        >
          ← Back
        </button>
        <span className="text-sm font-medium text-foreground">{candidates.length} Clips</span>
        <span className="text-xs text-muted">{keptCount} selected</span>

        <div className="flex-1" />

        {hasMore && (
          <button
            onClick={handleGenerateMore}
            className="text-xs text-muted hover:text-foreground transition-colors"
          >
            Generate More
          </button>
        )}

        <button onClick={keepAll} className="text-xs text-muted hover:text-foreground transition-colors">
          Keep All
        </button>
        <button onClick={binAll} className="text-xs text-muted hover:text-foreground transition-colors">
          Bin All
        </button>

        <button
          onClick={() => navigate(`/export/${sessionId}`)}
          disabled={keptCount === 0}
          className="px-4 py-1.5 text-xs rounded bg-accent text-white hover:bg-accent/90 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          Export ({keptCount})
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Clip grid — left column */}
        <div className="w-[380px] shrink-0 border-r border-border overflow-hidden flex flex-col">
          <ClipGrid
            candidates={candidates}
            selectedRank={selectedRank}
            onSelect={selectCard}
          />
        </div>

        {/* Video player — right column */}
        <div className="flex-1 p-4 overflow-y-auto">
          <VideoPlayer candidate={selectedCandidate} />
        </div>
      </div>
    </div>
  )
}
