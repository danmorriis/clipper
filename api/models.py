"""
Pydantic schemas for the FastAPI layer.
Mirrors the existing Python dataclasses without importing PyQt6.
"""

from typing import List, Optional
from pydantic import BaseModel


# ── Output schemas ────────────────────────────────────────────────────────────

class TrackMatchOut(BaseModel):
    track_name: str
    confidence: float
    time_offset: float


class ClipCandidateOut(BaseModel):
    rank: int
    start_time: float
    end_time: float
    transition_peak_time: float
    score: float
    kept: bool
    is_manual: bool
    thumbnail_path: Optional[str]
    matched_tracks: List[TrackMatchOut]
    pre_track: Optional[str]
    post_track: Optional[str]


class GenerateMoreOut(BaseModel):
    candidates: List[ClipCandidateOut]
    next_all_idx: int


class SessionOut(BaseModel):
    session_id: str
    video_path: Optional[str]
    video_duration: float
    candidates: List[ClipCandidateOut]
    all_candidates_count: int
    next_all_idx: int
    resolved_track_names: List[str]
    output_dir: Optional[str]


# ── Input schemas ─────────────────────────────────────────────────────────────

class CreateSessionIn(BaseModel):
    video_path: str
    playlist_path: Optional[str] = None
    search_root: Optional[str] = None
    clip_duration: float = 45.0
    n_clips: int = 10
    clip_all: bool = False
    manual_timestamps: List[float] = []
    output_dir: Optional[str] = None
    b2b: bool = False


class StartExportIn(BaseModel):
    output_dir: str


class PatchCandidateIn(BaseModel):
    kept: Optional[bool] = None
    pre_track: Optional[str] = None
    post_track: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class AddManualClipIn(BaseModel):
    start_time: float
    end_time: float
    pre_track: Optional[str] = None
    post_track: Optional[str] = None


class ValidateVideoIn(BaseModel):
    video_path: str


class ValidateTimestampsIn(BaseModel):
    text: str
    video_duration: float


class SearchRootIn(BaseModel):
    path: str


# ── Converters ────────────────────────────────────────────────────────────────

def candidate_to_out(c) -> ClipCandidateOut:
    return ClipCandidateOut(
        rank=c.rank,
        start_time=c.start_time,
        end_time=c.end_time,
        transition_peak_time=c.transition_peak_time,
        score=c.score,
        kept=c.kept,
        is_manual=c.is_manual,
        thumbnail_path=str(c.thumbnail_path) if c.thumbnail_path else None,
        matched_tracks=[
            TrackMatchOut(
                track_name=m.track_name,
                confidence=m.confidence,
                time_offset=m.time_offset,
            )
            for m in c.matched_tracks
        ],
        pre_track=c.pre_track,
        post_track=c.post_track,
    )


def session_to_out(entry) -> SessionOut:
    s = entry.state
    # In all/timeslot mode every candidate is already displayed — mark pool exhausted
    # so the frontend hides the "Generate More" button.
    clip_all = s.settings.clip_all if s.settings else False
    timeslot = bool(s.settings.manual_timestamps) if s.settings else False
    next_idx = len(s.all_candidates) if (clip_all or timeslot) else entry.next_all_idx
    return SessionOut(
        session_id=s.session_id,
        video_path=str(s.video_path) if s.video_path else None,
        video_duration=s.video_duration,
        candidates=[candidate_to_out(c) for c in s.candidates],
        all_candidates_count=len(s.all_candidates),
        next_all_idx=next_idx,
        resolved_track_names=s.resolved_track_names,
        output_dir=str(s.output_dir) if s.output_dir else None,
    )
