from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List


@dataclass
class TrackMatch:
    track_name: str     # filename without extension
    confidence: float   # audfprint hash hit ratio (0.0–1.0)
    time_offset: float  # seconds into the clip where the match occurs


@dataclass
class ClipCandidate:
    rank: int
    start_time: float            # seconds, beat-aligned
    end_time: float              # start_time + clip_duration
    transition_peak_time: float  # raw detected score peak / transition midpoint
    score: float                 # 0.0–1.0 fingerprint confidence or spectral score
    kept: bool = True            # user's review decision
    is_manual: bool = False      # True for clips created via "Add Custom Clip"
    thumbnail_path: Optional[Path] = None
    matched_tracks: List[TrackMatch] = field(default_factory=list)
    # Set by transition_finder when playlist is provided at analysis time
    pre_track: Optional[str] = None   # track playing before the transition
    post_track: Optional[str] = None  # track playing after the transition
