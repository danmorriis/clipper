from typing import List, Optional

import numpy as np
from scipy.signal import argrelmax

from dj_clipper.config import MIN_CLIP_GAP_SECONDS, PRE_TRANSITION_OFFSET
from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.core.beat_aligner import snap_to_nearest_beat


def find_top_moments(
    combined_score: np.ndarray,
    times: np.ndarray,
    clip_duration: float,
    n_clips: int,
    video_duration: float,
    beat_times: Optional[np.ndarray] = None,
    min_gap: float = MIN_CLIP_GAP_SECONDS,
    pre_offset: float = PRE_TRANSITION_OFFSET,
) -> List[ClipCandidate]:
    """
    Find the top N transition moments from the combined score array.
    beat_times is optional — if None, clip starts are placed at raw_start
    without snapping. Beat snapping is applied per-clip by the worker after
    extracting short audio segments (Option D).
    """
    # 1. Find local peaks
    peak_indices = argrelmax(combined_score, order=50)[0]
    if len(peak_indices) == 0:
        return []

    # 2. Sort peaks by score descending
    peak_indices = sorted(peak_indices, key=lambda i: combined_score[i], reverse=True)

    # 3. Greedy selection with gap enforcement
    selected_peak_times = []
    selected = []

    for idx in peak_indices:
        peak_time = float(times[idx])
        if any(abs(peak_time - t) < min_gap for t in selected_peak_times):
            continue

        raw_start = peak_time - pre_offset
        if beat_times is not None and len(beat_times) > 0:
            start = snap_to_nearest_beat(raw_start, beat_times)
        else:
            start = raw_start
        start = max(0.0, start)
        end = start + clip_duration
        if end > video_duration:
            continue

        selected_peak_times.append(peak_time)
        selected.append((peak_time, start, end, float(combined_score[idx])))

        if len(selected) >= n_clips:
            break

    # 4. Sort chronologically and assign rank
    selected.sort(key=lambda x: x[1])
    candidates = []
    for rank, (peak_time, start, end, score) in enumerate(selected, start=1):
        candidates.append(ClipCandidate(
            rank=rank,
            start_time=start,
            end_time=end,
            transition_peak_time=peak_time,
            score=score,
        ))
    return candidates
