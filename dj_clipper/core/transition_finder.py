"""
Fingerprint-based transition detection.

Samples the full session audio at regular intervals, queries each sample
against the track fingerprint DB, builds a track timeline, then finds
handoff zones where the dominant track changes A → B.

Each handoff becomes a ClipCandidate centred on the transition midpoint,
carrying pre_track / post_track labels so the review UI can display them
and the export worker can write them to tracklist.txt without re-querying.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import scipy.io.wavfile as wavfile

from dj_clipper.core.fingerprint_db import fingerprint_pcm, preload_index, query_clip_preloaded
from dj_clipper.models.clip_model import ClipCandidate

# ── Tuning constants ─────────────────────────────────────────────────────────

# Step between sample start points. Smaller = finer resolution but slower.
# At 20 s steps across a 2-hour video: ~360 samples.
SAMPLE_STEP: float = 20.0

# Length of each audio sample fed to the fingerprinter.
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

def _fingerprint_sample_pcm(
    pcm: np.ndarray,
    sample_rate: int,
    index: Dict[str, np.ndarray],
    start: float,
) -> _TimelineEntry:
    """
    Slice a pre-decoded PCM array, fingerprint via libchromaprint (no subprocess),
    and compare against the pre-loaded index.  Entirely in-memory, thread-safe.
    """
    s = int(start * sample_rate)
    e = int((start + SAMPLE_DURATION) * sample_rate)
    chunk = pcm[s:e]
    if len(chunk) == 0:
        return _TimelineEntry(start=start, track=None, confidence=0.0)

    fp_ints = fingerprint_pcm(chunk, sample_rate)
    if fp_ints:
        matches = query_clip_preloaded(fp_ints, index, MIN_CONFIDENCE)
        if matches:
            return _TimelineEntry(start=start, track=matches[0].track_name, confidence=matches[0].confidence)
    return _TimelineEntry(start=start, track=None, confidence=0.0)


def build_track_timeline(
    session_wav: Path,
    db_path: Path,
    video_duration: float,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> List[_TimelineEntry]:
    """
    Sample session_wav at SAMPLE_STEP intervals, fingerprint each sample
    in parallel, and return a timeline of track identifications sorted
    chronologically.

    Strategy:
      1. Decode the full session WAV to a numpy int16 array once (no per-sample
         disk I/O or subprocess overhead from ffmpeg).
      2. Slice PCM chunks in memory — instant numpy indexing.
      3. Fingerprint each chunk via libchromaprint directly (ctypes call releases
         the GIL, giving true thread-level parallelism). Falls back to fpcalc
         subprocess if the library is unavailable.
      4. Compare against the pre-loaded fingerprint index (no JSON reads in loop).

    progress_callback(current, total, timestamp_seconds) fires as each sample
    completes (non-deterministic order in parallel mode).
    cancel_event, if set, causes remaining futures to be abandoned.
    """
    sample_starts: List[float] = []
    t = 0.0
    while t + SAMPLE_DURATION <= video_duration:
        sample_starts.append(t)
        t += SAMPLE_STEP

    total = len(sample_starts)
    if total == 0:
        return []

    # Decode WAV once into memory — eliminates per-sample ffmpeg spawns and
    # concurrent disk I/O contention.  A 2-hour 16kHz mono int16 WAV is ~230 MB.
    sample_rate, pcm = wavfile.read(str(session_wav))
    if pcm.ndim > 1:
        pcm = pcm[:, 0]  # take first channel if stereo
    pcm = pcm.astype(np.int16)

    # Load DB once and pre-convert to numpy arrays — avoids repeated JSON reads
    # and np.array() conversions inside each worker call.
    index: Dict[str, np.ndarray] = preload_index(db_path)

    # 80% of logical cores.  libchromaprint releases the GIL during computation,
    # so threads achieve real parallelism without disk contention.
    max_workers = max(1, int((os.cpu_count() or 1) * 0.8))
    completed_count = 0
    counter_lock = threading.Lock()
    results: Dict[float, _TimelineEntry] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_start = {
            executor.submit(_fingerprint_sample_pcm, pcm, sample_rate, index, start): start
            for start in sample_starts
        }

        for future in as_completed(future_to_start):
            if cancel_event and cancel_event.is_set():
                for f in future_to_start:
                    f.cancel()
                break

            start = future_to_start[future]
            try:
                entry = future.result()
            except Exception:
                entry = _TimelineEntry(start=start, track=None, confidence=0.0)

            results[start] = entry

            with counter_lock:
                completed_count += 1
                count = completed_count

            if progress_callback:
                progress_callback(count, total, start)

    # Reconstruct in chronological order (futures complete out of order)
    return [results[s] for s in sample_starts if s in results]


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
