export interface TrackMatch {
  track_name: string
  confidence: number
  time_offset: number
}

export interface ClipCandidate {
  rank: number
  start_time: number
  end_time: number
  transition_peak_time: number
  score: number
  kept: boolean
  is_manual: boolean
  thumbnail_path: string | null
  matched_tracks: TrackMatch[]
  pre_track: string | null
  post_track: string | null
}

export interface Session {
  session_id: string
  video_path: string | null
  video_duration: number
  candidates: ClipCandidate[]
  all_candidates_count: number
  next_all_idx: number
  resolved_track_names: string[]
  output_dir: string | null
}

export type ClipMode = 'topn' | 'all' | 'timeslots'

export interface AnalysisParams {
  videoPath: string
  playlistPath?: string
  searchRoot?: string
  clipDuration: number
  nClips: number
  clipAll: boolean
  manualTimestamps: number[]
  outputDir?: string
}

// SSE progress event
export interface ProgressEvent {
  percent?: number
  message?: string
  done?: boolean
  error?: string
  cancelled?: boolean
  thumbnail_ready?: { rank: number; path: string }
  thumbnails_done?: boolean
  clip_done?: { index: number; rank?: number; path: string; tracks: { track_name: string; confidence: number }[] }
  tracklist?: string
  export_dir?: string
}
