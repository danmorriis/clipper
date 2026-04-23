import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dj_clipper.models.clip_model import ClipCandidate


@dataclass
class AnalysisSettings:
    clip_duration: float       # seconds (30, 45, or 60)
    n_clips: int               # 5–20
    clip_all: bool = False     # if True, surface all discovered transitions
    manual_timestamps: List[float] = field(default_factory=list)  # specific timeslot mode


@dataclass
class SessionState:
    """Holds all runtime state for a single analysis+export session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # Inputs
    video_path: Optional[Path] = None
    settings: Optional[AnalysisSettings] = None

    # Analysis outputs
    wav_path: Optional[Path] = None
    video_duration: float = 0.0
    candidates: List[ClipCandidate] = field(default_factory=list)
    # Full pool of discovered transitions (candidates is a top-N slice of this)
    all_candidates: List[ClipCandidate] = field(default_factory=list)
    # Track names resolved from the playlist (alphabetical); empty when no playlist used
    resolved_track_names: List[str] = field(default_factory=list)

    # Export inputs
    output_dir: Optional[Path] = None
    tracklist_dir: Optional[Path] = None  # legacy: directory of audio files
    playlist_path: Optional[Path] = None  # .m3u / .m3u8 / .txt playlist
    search_root: Optional[Path] = None    # root folder to search for playlist tracks
    db_path: Optional[Path] = None

    @property
    def kept_clips(self) -> List[ClipCandidate]:
        return [c for c in self.candidates if c.kept]

    @property
    def session_temp_dir(self) -> Path:
        from dj_clipper.config import TEMP_DIR
        return TEMP_DIR / self.session_id
