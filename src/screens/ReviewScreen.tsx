import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addManualClip, generateMore, getSession, patchCandidate } from '../api/client'
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
    newRanks,
    allCandidatesCount,
    nextAllIdx,
    selectCard,
    addCandidates,
    markNewRanks,
    setNextAllIdx,
    setSession,
  } = useSessionStore((s) => ({
    apiBase: s.apiBase,
    candidates: s.candidates,
    selectedRank: s.selectedRank,
    newRanks: s.newRanks,
    allCandidatesCount: s.allCandidatesCount,
    nextAllIdx: s.nextAllIdx,
    selectCard: s.selectCard,
    addCandidates: s.addCandidates,
    markNewRanks: s.markNewRanks,
    setNextAllIdx: s.setNextAllIdx,
    setSession: s.setSession,
  }))
  const storeSessionId = useSessionStore((s) => s.sessionId)
  const [addClipMode, setAddClipMode] = useState(false)

  // Reload session state if page was navigated to directly (e.g. dev reload)
  useEffect(() => {
    if (!sessionId || !apiBase) return
    if (storeSessionId === sessionId) return
    getSession(apiBase, sessionId).then((s) => setSession(s)).catch(() => {})
  }, [sessionId, apiBase, storeSessionId, setSession])

  const selectedCandidate = candidates.find((c) => c.rank === selectedRank) ?? null

  const handleAddClip = async (start: number, end: number, pre: string | null, post: string | null) => {
    if (!sessionId) return
    try {
      const clip = await addManualClip(apiBase, sessionId, {
        start_time: start,
        end_time: end,
        pre_track: pre ?? undefined,
        post_track: post ?? undefined,
      })
      addCandidates([clip])
      markNewRanks([clip.rank])
    } catch {}
    setAddClipMode(false)
  }

  const keptCount = candidates.filter((c) => c.kept).length
  const hasMore = nextAllIdx < allCandidatesCount

  const keepAll = () => {
    candidates.forEach((c) => {
      if (!c.kept) {
        useSessionStore.getState().updateCandidate(c.rank, { kept: true })
        if (sessionId) patchCandidate(apiBase, sessionId, c.rank, { kept: true }).catch(() => {})
      }
    })
  }

  const binAll = () => {
    candidates.forEach((c) => {
      if (c.kept) {
        useSessionStore.getState().updateCandidate(c.rank, { kept: false })
        if (sessionId) patchCandidate(apiBase, sessionId, c.rank, { kept: false }).catch(() => {})
      }
    })
  }

  const handleGenerateMore = async () => {
    if (!sessionId) return
    try {
      const { candidates: more, next_all_idx } = await generateMore(apiBase, sessionId, 5)
      addCandidates(more)
      markNewRanks(more.map((c) => c.rank))
      setNextAllIdx(next_all_idx)
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

        {hasMore ? (
          <button
            onClick={handleGenerateMore}
            className="px-3 py-1 text-xs rounded bg-green-100 text-green-800 border border-green-300 hover:bg-green-200 transition-colors"
          >
            Generate More
          </button>
        ) : (
          <span className="px-3 py-1 text-xs rounded border border-border text-muted cursor-default">
            All transitions generated
          </span>
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
        <div className="w-[380px] shrink-0 border-r border-border flex flex-col">
          <div className="flex-1 min-h-0 overflow-y-auto">
            <ClipGrid
              candidates={candidates}
              selectedRank={selectedRank}
              newRanks={newRanks}
              onSelect={(rank) => { setAddClipMode(false); selectCard(rank) }}
              onAddMode={() => { selectCard(null); setAddClipMode(true) }}
            />
          </div>
        </div>

        {/* Video player — right column */}
        <div className="flex-1 p-4 overflow-y-auto">
          <VideoPlayer
            candidate={addClipMode ? null : selectedCandidate}
            addClipMode={addClipMode}
            onAddClip={handleAddClip}
            onCancelAdd={() => setAddClipMode(false)}
          />
        </div>
      </div>
    </div>
  )
}
