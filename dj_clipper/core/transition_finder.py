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
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

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
MIN_CONFIDENCE: float = 0.65

# Minimum consecutive same-track samples to count as a genuine run.
# 1 = accept any single identification.  Tracks in short-format mixes can have
# a clean identification window of only 30–60 s (1–3 samples), so requiring 2
# would miss them entirely.  Crossfade false positives are handled instead by
# _smooth_sandwiched_runs (for same-track neighbours) and the margin threshold.
MIN_SOLO_SAMPLES: int = 1

# Absorb runs of ≤ this many samples that are sandwiched between two runs of
# the same track — these are crossfade fingerprint noise, not genuine tracks.
_SANDWICH_THRESHOLD: int = 2

# Minimum seconds of *continuous* unidentified audio before treating the gap as
# a genuine unknown track rather than an A→B crossfade.  With transitions up to
# 1 minute (3 samples at 20 s steps), 60 s bridges crossfades cleanly while
# still catching absent tracks that play for 1-2 minutes (3-6 None samples).
_MIN_UNKNOWN_SECONDS: float = 60.0


# ── Return type ──────────────────────────────────────────────────────────────

class TimelineResult(NamedTuple):
    timeline: List["_TimelineEntry"]
    pcm: np.ndarray
    sample_rate: int


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
    timeline = [results[s] for s in sample_starts if s in results]
    return TimelineResult(timeline=timeline, pcm=pcm, sample_rate=sample_rate)


def _smooth_sandwiched_runs(runs: List[_TrackRun]) -> List[_TrackRun]:
    """
    Absorb short runs that are sandwiched between two runs of the same track.

    During a crossfade the fingerprinter sometimes briefly identifies the
    incoming track before flipping back to the outgoing one, producing
    patterns like [A(10), B(1), A(8)].  B here is noise, not a genuine
    track appearance.  We merge runs[i] and the following same-track run
    into runs[i-1] when runs[i].n_samples <= _SANDWICH_THRESHOLD.

    Iterates until stable to handle cascading patterns.
    """
    changed = True
    while changed:
        changed = False
        if len(runs) < 3:
            break
        result: List[_TrackRun] = [runs[0]]
        i = 1
        while i < len(runs):
            if (
                i < len(runs) - 1
                and runs[i].n_samples <= _SANDWICH_THRESHOLD
                and result[-1].track == runs[i + 1].track
            ):
                # Absorb the sandwiched run and the following continuation
                result[-1].sample_times.extend(runs[i].sample_times)
                result[-1].confidences.extend(runs[i].confidences)
                result[-1].sample_times.extend(runs[i + 1].sample_times)
                result[-1].confidences.extend(runs[i + 1].confidences)
                i += 2
                changed = True
            else:
                result.append(runs[i])
                i += 1
        runs = result
    return runs


def confirm_track_near(
    timeline: List[_TimelineEntry],
    midpoint: float,
    side: str,
    window: float = 120.0,
    bound: Optional[float] = None,
) -> Tuple[Optional[str], float]:
    """
    Find the most reliable track ID on one side of a transition midpoint.

    Scans identified timeline samples within `window` seconds of `midpoint`
    on the given side ('pre' = backwards, 'post' = forwards), optionally
    clamped to `bound`.  Prefers the first adjacent pair (gap ≤ SAMPLE_STEP+1s)
    that agree on the same track; falls back to the single highest-confidence
    sample.  Returns (track_name, confidence) or (None, 0.0).

    bound: for 'pre', earliest allowed sample time (e.g. run start);
           for 'post', latest allowed sample time (e.g. run end).
    """
    if side == 'pre':
        lo = max(bound, midpoint - window) if bound is not None else midpoint - window
        candidates = [
            e for e in timeline
            if lo <= e.start < midpoint and e.track is not None
        ]
        candidates.sort(key=lambda e: e.start, reverse=True)  # closest-first
    else:
        hi = min(bound, midpoint + window) if bound is not None else midpoint + window
        candidates = [
            e for e in timeline
            if midpoint < e.start <= hi and e.track is not None
        ]
        candidates.sort(key=lambda e: e.start)  # closest-first

    if not candidates:
        return None, 0.0

    # Prefer the first adjacent pair agreeing on the same track
    for i in range(len(candidates) - 1):
        a_e = candidates[i]
        b_e = candidates[i + 1]
        if abs(a_e.start - b_e.start) <= SAMPLE_STEP + 1.0 and a_e.track == b_e.track:
            return a_e.track, (a_e.confidence + b_e.confidence) / 2.0

    # Fallback: highest-confidence single identified sample
    best = max(candidates, key=lambda e: e.confidence)
    return best.track, best.confidence


def find_transitions(
    timeline: List[_TimelineEntry],
    clip_duration: float,
    video_duration: float,
    pcm: Optional[np.ndarray] = None,
    sample_rate: Optional[int] = None,
) -> List[ClipCandidate]:
    """
    Return one ClipCandidate per detected A→B track boundary, sorted by
    average fingerprint confidence descending.  Expect N−1 candidates for
    N identified tracks.
    """
    if not timeline:
        return []

    # ── 1. Group consecutive same-track entries into runs ────────────────────────
    # Unidentified samples (track=None) are treated as a distinct "__unidentified__"
    # run rather than skipped, so gaps caused by tracks not in the DB still
    # produce a run boundary and a transition on each side.
    _UNKNOWN = '__unidentified__'
    runs: List[_TrackRun] = []
    for entry in timeline:
        track = entry.track if entry.track is not None else _UNKNOWN
        if runs and runs[-1].track == track:
            runs[-1].sample_times.append(entry.start)
            runs[-1].confidences.append(entry.confidence)
        else:
            runs.append(_TrackRun(
                track=track,
                sample_times=[entry.start],
                confidences=[entry.confidence],
            ))

    # ── 2. Remove crossfade noise (brief same-track-sandwiched interjections) ──
    # This also absorbs short __unidentified__ blips sandwiched between runs of
    # the same track (crossfade fingerprint noise, not genuine unknown tracks).
    runs = _smooth_sandwiched_runs(runs)

    # ── 3. Filter runs ────────────────────────────────────────────────────────────
    # Known tracks: any run of ≥ MIN_SOLO_SAMPLES is genuine.
    # Unknown blocks: apply a higher threshold so long crossfades (where neither
    # A nor B clears the fingerprint threshold for up to 2 minutes) are bridged
    # directly as A→B rather than producing a spurious Unknown label.  When
    # discarded, the neighbouring A and B runs become adjacent and their midpoint
    # correctly spans the crossfade zone.
    _min_unknown = max(1, int(_MIN_UNKNOWN_SECONDS / SAMPLE_STEP))
    confirmed = [
        r for r in runs
        if r.n_samples >= (_min_unknown if r.track == _UNKNOWN else MIN_SOLO_SAMPLES)
    ]

    # ── 3b. Assign stable labels to surviving unidentified runs ──────────────────
    # Each Unknown block that cleared the threshold represents a genuine track not
    # in the fingerprint DB — label sequentially for display in the review UI.
    unknown_counter = 0
    for run in confirmed:
        if run.track == _UNKNOWN:
            unknown_counter += 1
            run.track = f'Unknown {unknown_counter}'

    # ── 4. One handoff per adjacent pair of different tracks ──────────────────
    # Use confirm_track_near to pick the track from the closest confirmed pair
    # on each side of the midpoint, rather than the whole-run average label.
    handoffs: List[Tuple[float, str, str, float]] = []
    for i in range(len(confirmed) - 1):
        a = confirmed[i]
        b = confirmed[i + 1]
        if a.track == b.track:
            continue
        mid = (a.last_time + b.first_time) / 2.0

        pre_track, pre_conf = confirm_track_near(timeline, mid, 'pre', bound=a.first_time)
        post_track, post_conf = confirm_track_near(timeline, mid, 'post', bound=b.last_time)
        if pre_track is None:
            pre_track, pre_conf = a.track, a.avg_confidence
        if post_track is None:
            post_track, post_conf = b.track, b.avg_confidence

        # If the closest samples on both sides resolve to the same track (crossfade
        # ambiguity), fall back to the run-level labels which are guaranteed different.
        if pre_track == post_track:
            pre_track, pre_conf = a.track, a.avg_confidence
            post_track, post_conf = b.track, b.avg_confidence

        if pre_track == post_track:
            continue

        score = (pre_conf + post_conf) / 2.0
        handoffs.append((mid, pre_track, post_track, score))

    if not handoffs:
        return []

    # ── 5. Highest-confidence transitions first ───────────────────────────────
    handoffs.sort(key=lambda h: h[3], reverse=True)

    # ── 5b. Deduplicate: keep only the highest-confidence occurrence of each
    # (pre_track, post_track) pair.  A→B twice in a set is treated as one
    # transition; the lower-confidence duplicate adds no information.
    seen_pairs: set = set()
    unique: list = []
    for h in handoffs:
        pair = (h[1], h[2])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique.append(h)
    handoffs = unique

    # ── 6. Convert to ClipCandidates (rank assigned later by caller) ──────────
    candidates: List[ClipCandidate] = []
    for rank, (mid, pre, post, score) in enumerate(handoffs, 1):
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
