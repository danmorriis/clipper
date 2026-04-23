"""
Fingerprint-based transition detection.

Samples the full session audio at regular intervals, queries each sample
against the track fingerprint DB, builds a track timeline, then finds
handoff zones where the dominant track changes A → B.

Each handoff becomes a ClipCandidate centred on the transition midpoint,
carrying pre_track / post_track labels so the review UI can display them
and the export worker can write them to tracklist.txt without re-querying.
"""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from dj_clipper.core.audio_extractor import extract_audio_segment
from dj_clipper.core.fingerprint_db import query_clip
from dj_clipper.models.clip_model import ClipCandidate

# ── Tuning constants ─────────────────────────────────────────────────────────

# Step between sample start points. Smaller = finer resolution but slower.
# At 20 s steps across a 2-hour video: ~360 samples ≈ 3–5 min total.
SAMPLE_STEP: float = 20.0

# Length of each audio sample fed to fpcalc.
SAMPLE_DURATION: float = 20.0

# A sample must clear this fingerprint confidence to be counted as "identified".
MIN_CONFIDENCE: float = 0.60

# Require this many consecutive confident same-track samples before treating
# it as a genuine solo run (filters brief mis-identifications mid-mix).
MIN_SOLO_SAMPLES: int = 1


# ── Internal data types ───────────────────────────────────────────────────────

@dataclass
class _TimelineEntry:
    start: float             # seconds into the video
    track: Optional[str]     # track name (stem), or None if unidentified
    confidence: float


@dataclass
class _TrackRun:
    track: str
    sample_times: List[float] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)

    @property
    def first_time(self) -> float:
        return self.sample_times[0]

    @property
    def last_time(self) -> float:
        return self.sample_times[-1]

    @property
    def avg_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 0.0

    @property
    def n_samples(self) -> int:
        return len(self.sample_times)


# ── Public API ────────────────────────────────────────────────────────────────

def build_track_timeline(
    session_wav: Path,
    db_path: Path,
    video_duration: float,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> List[_TimelineEntry]:
    """
    Sample session_wav at SAMPLE_STEP intervals, fingerprint each sample
    against db_path, and return a timeline of track identifications.

    progress_callback(current, total, timestamp_seconds) is called per sample.
    All temporary WAV files are deleted immediately after each query.
    """
    sample_starts = []
    t = 0.0
    while t + SAMPLE_DURATION <= video_duration:
        sample_starts.append(t)
        t += SAMPLE_STEP

    total = len(sample_starts)
    timeline: List[_TimelineEntry] = []

    for i, start in enumerate(sample_starts):
        if progress_callback:
            progress_callback(i, total, start)

        # Extract sample to a throwaway temp file, delete immediately after
        tmp = Path(tempfile.mktemp(suffix=".wav"))
        try:
            extract_audio_segment(session_wav, start, SAMPLE_DURATION, tmp)
            matches = query_clip(tmp, db_path, min_similarity=MIN_CONFIDENCE)
            if matches:
                timeline.append(_TimelineEntry(
                    start=start,
                    track=matches[0].track_name,
                    confidence=matches[0].confidence,
                ))
            else:
                timeline.append(_TimelineEntry(start=start, track=None, confidence=0.0))
        finally:
            tmp.unlink(missing_ok=True)

    return timeline


def find_transitions(
    timeline: List[_TimelineEntry],
    clip_duration: float,
    video_duration: float,
) -> List[ClipCandidate]:
    """
    Scan the timeline for A→B track handoffs and return ALL ClipCandidate
    objects centred on each transition midpoint, sorted by score descending.

    The caller decides how many to surface to the user.
    """
    if not timeline:
        return []

    # ── 1. Group consecutive same-track entries into runs ─────────────────────
    runs: List[_TrackRun] = []
    for entry in timeline:
        if entry.track is None:
            continue  # skip unidentified samples
        if runs and runs[-1].track == entry.track:
            runs[-1].sample_times.append(entry.start)
            runs[-1].confidences.append(entry.confidence)
        else:
            runs.append(_TrackRun(
                track=entry.track,
                sample_times=[entry.start],
                confidences=[entry.confidence],
            ))

    # ── 2. Filter to confirmed runs (enough consecutive samples) ──────────────
    confirmed = [r for r in runs if r.n_samples >= MIN_SOLO_SAMPLES]

    # ── 3. Find adjacent pairs with different tracks ───────────────────────────
    handoffs: List[Tuple[float, str, str, float]] = []  # (midpoint, pre, post, score)
    for i in range(len(confirmed) - 1):
        a = confirmed[i]
        b = confirmed[i + 1]
        if a.track == b.track:
            continue
        # Midpoint between the last A sample and the first B sample
        mid = (a.last_time + b.first_time) / 2.0
        score = (a.avg_confidence + b.avg_confidence) / 2.0
        handoffs.append((mid, a.track, b.track, score))

    if not handoffs:
        return []

    # ── 4. Rank by confidence score, return all ────────────────────────────────
    handoffs.sort(key=lambda h: h[3], reverse=True)

    # ── 5. Convert to ClipCandidate (sorted by score; rank assigned later) ─────
    selected = handoffs
    candidates: List[ClipCandidate] = []
    for rank, (mid, pre, post, score) in enumerate(selected, 1):
        # Place ~1/3 of clip before midpoint, ~2/3 after — shows A fading out
        # then B establishing itself, which reads better as social content.
        clip_start = max(0.0, mid - clip_duration / 3.0)
        clip_end = clip_start + clip_duration
        if clip_end > video_duration:
            clip_end = video_duration
            clip_start = max(0.0, clip_end - clip_duration)
        candidates.append(ClipCandidate(
            rank=rank,
            start_time=clip_start,
            end_time=clip_end,
            transition_peak_time=mid,
            score=score,
            pre_track=pre,
            post_track=post,
        ))

    return candidates
