import { create } from 'zustand'
import type { ClipCandidate } from '../types'

interface SessionStore {
  // API base URL (set once on startup from electron preload)
  apiBase: string
  setApiBase: (base: string) => void

  // Session
  sessionId: string | null
  videoPath: string | null
  videoDuration: number
  candidates: ClipCandidate[]
  allCandidatesCount: number
  nextAllIdx: number
  resolvedTrackNames: string[]
  outputDir: string | null

  // UI state
  selectedRank: number | null
  newRanks: Set<number>

  // Actions
  markNewRanks: (ranks: number[]) => void
  clearNewRank: (rank: number) => void
  setSession: (session: {
    session_id: string
    video_path: string | null
    video_duration: number
    candidates: ClipCandidate[]
    all_candidates_count: number
    next_all_idx: number
    resolved_track_names: string[]
    output_dir: string | null
  }) => void
  setCandidates: (candidates: ClipCandidate[]) => void
  updateCandidate: (rank: number, patch: Partial<ClipCandidate>) => void
  addCandidates: (newOnes: ClipCandidate[]) => void
  selectCard: (rank: number | null) => void
  reset: () => void
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  apiBase: '',
  setApiBase: (base) => set({ apiBase: base }),

  sessionId: null,
  videoPath: null,
  videoDuration: 0,
  candidates: [],
  allCandidatesCount: 0,
  nextAllIdx: 0,
  resolvedTrackNames: [],
  outputDir: null,
  selectedRank: null,
  newRanks: new Set<number>(),

  markNewRanks: (ranks) =>
    set((state) => ({ newRanks: new Set([...state.newRanks, ...ranks]) })),

  clearNewRank: (rank) =>
    set((state) => {
      const next = new Set(state.newRanks)
      next.delete(rank)
      return { newRanks: next }
    }),

  setSession: (s) =>
    set({
      sessionId: s.session_id,
      videoPath: s.video_path,
      videoDuration: s.video_duration,
      candidates: s.candidates,
      allCandidatesCount: s.all_candidates_count,
      nextAllIdx: s.next_all_idx,
      resolvedTrackNames: s.resolved_track_names,
      outputDir: s.output_dir,
    }),

  setCandidates: (candidates) => set({ candidates }),

  updateCandidate: (rank, patch) =>
    set((state) => ({
      candidates: state.candidates.map((c) =>
        c.rank === rank ? { ...c, ...patch } : c
      ),
    })),

  addCandidates: (newOnes) =>
    set((state) => {
      const merged = [...state.candidates, ...newOnes]
      merged.sort((a, b) => a.start_time - b.start_time)
      merged.forEach((c, i) => { c.rank = i + 1 })
      return { candidates: merged }
    }),

  selectCard: (rank) =>
    set((state) => {
      if (rank === null) return { selectedRank: null }
      const newRanks = new Set(state.newRanks)
      newRanks.delete(rank)
      return { selectedRank: rank, newRanks }
    }),

  reset: () =>
    set({
      sessionId: null,
      videoPath: null,
      videoDuration: 0,
      candidates: [],
      allCandidatesCount: 0,
      nextAllIdx: 0,
      resolvedTrackNames: [],
      outputDir: null,
      selectedRank: null,
    }),
}))
