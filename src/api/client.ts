/**
 * Typed fetch wrappers around the FastAPI backend.
 * All functions accept apiBase as the first arg so the Electron preload
 * injection is transparent.
 */

import type { AnalysisParams, ClipCandidate, Session } from '../types'

async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, init)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export function createSession(base: string, params: AnalysisParams): Promise<Session> {
  return request(base, '/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_path: params.videoPath,
      playlist_path: params.playlistPath ?? null,
      search_root: params.searchRoot ?? null,
      clip_duration: params.clipDuration,
      n_clips: params.nClips,
      clip_all: params.clipAll,
      manual_timestamps: params.manualTimestamps,
      output_dir: params.outputDir ?? null,
    }),
  })
}

export function getSession(base: string, sessionId: string): Promise<Session> {
  return request(base, `/sessions/${sessionId}`)
}

// ── Analysis ──────────────────────────────────────────────────────────────────

export function startAnalysis(base: string, sessionId: string): Promise<{ status: string }> {
  return request(base, `/sessions/${sessionId}/analyze`, { method: 'POST' })
}

export function cancelAnalysis(base: string, sessionId: string): Promise<{ status: string }> {
  return request(base, `/sessions/${sessionId}/analyze/cancel`, { method: 'POST' })
}

// ── Candidates ────────────────────────────────────────────────────────────────

export function listCandidates(base: string, sessionId: string): Promise<ClipCandidate[]> {
  return request(base, `/sessions/${sessionId}/candidates`)
}

export function patchCandidate(
  base: string,
  sessionId: string,
  rank: number,
  patch: Partial<Pick<ClipCandidate, 'kept' | 'pre_track' | 'post_track' | 'start_time' | 'end_time'>>
): Promise<ClipCandidate> {
  return request(base, `/sessions/${sessionId}/candidates/${rank}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function addManualClip(
  base: string,
  sessionId: string,
  clip: { start_time: number; end_time: number; pre_track?: string; post_track?: string }
): Promise<ClipCandidate> {
  return request(base, `/sessions/${sessionId}/candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(clip),
  })
}

export function generateMore(
  base: string,
  sessionId: string,
  count = 5
): Promise<ClipCandidate[]> {
  return request(base, `/sessions/${sessionId}/generate-more?count=${count}`, { method: 'POST' })
}

// ── Export ────────────────────────────────────────────────────────────────────

export function startExport(
  base: string,
  sessionId: string,
  outputDir: string
): Promise<{ status: string }> {
  return request(base, `/sessions/${sessionId}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ output_dir: outputDir }),
  })
}

export function cancelExport(base: string, sessionId: string): Promise<{ status: string }> {
  return request(base, `/sessions/${sessionId}/export/cancel`, { method: 'POST' })
}

// ── Validation & persistence ──────────────────────────────────────────────────

export function validateVideo(base: string, videoPath: string): Promise<{ duration_seconds: number }> {
  return request(base, '/validate/video', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_path: videoPath }),
  })
}

export function validateTimestamps(
  base: string,
  text: string,
  videoDuration: number
): Promise<{ valid: number[]; malformed: string[]; out_of_bounds: string[] }> {
  return request(base, '/validate/timestamps', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, video_duration: videoDuration }),
  })
}

export function getSearchRoot(base: string): Promise<{ path: string }> {
  return request(base, '/persist/search-root')
}

export function setSearchRoot(base: string, path: string): Promise<{ path: string }> {
  return request(base, '/persist/search-root', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
}

// ── URL helpers ───────────────────────────────────────────────────────────────

export function thumbnailUrl(base: string, sessionId: string, rank: number): string {
  return `${base}/sessions/${sessionId}/thumbnails/${rank}`
}

export function videoUrl(base: string, videoPath: string): string {
  return `${base}/video?path=${encodeURIComponent(videoPath)}`
}
