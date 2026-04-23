import numpy as np
from dj_clipper.core.clip_scorer import find_top_moments


def _synthetic_score(peaks_at: list, length: int = 1000, total_seconds: float = 600.0):
    """Score array with sharp peaks at given second values."""
    score = np.zeros(length)
    times = np.linspace(0, total_seconds, length)
    for t in peaks_at:
        idx = np.argmin(np.abs(times - t))
        score[idx] = 1.0
        # Small shoulders so argrelmax detects it
        if idx > 0:
            score[idx - 1] = 0.5
        if idx < length - 1:
            score[idx + 1] = 0.5
    return score, times


def test_finds_top_peaks():
    score, times = _synthetic_score([120.0, 300.0, 450.0])
    beat_times = np.arange(0, 600.0, 0.5)
    candidates = find_top_moments(
        score, times, beat_times,
        clip_duration=30.0, n_clips=3,
        video_duration=600.0, min_gap=60.0,
    )
    assert len(candidates) == 3


def test_gap_enforcement():
    # Peaks at 120, 165 (45s apart < 60s min_gap), 300 — should only get 2
    # Note: peaks must be >30s apart so argrelmax(order=50) at 0.6s/index detects both
    score, times = _synthetic_score([120.0, 165.0, 300.0])
    beat_times = np.arange(0, 600.0, 0.5)
    candidates = find_top_moments(
        score, times, beat_times,
        clip_duration=30.0, n_clips=3,
        video_duration=600.0, min_gap=60.0,
    )
    assert len(candidates) == 2
    starts = [c.start_time for c in candidates]
    # Verify no two clips are within 60s of each other (by peak times)
    peaks = [c.transition_peak_time for c in candidates]
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            assert abs(peaks[i] - peaks[j]) >= 60.0


def test_candidates_are_chronological():
    score, times = _synthetic_score([300.0, 120.0, 450.0])
    beat_times = np.arange(0, 600.0, 0.5)
    candidates = find_top_moments(
        score, times, beat_times,
        clip_duration=30.0, n_clips=3,
        video_duration=600.0, min_gap=60.0,
    )
    starts = [c.start_time for c in candidates]
    assert starts == sorted(starts)


def test_clips_within_video_bounds():
    score, times = _synthetic_score([580.0])  # Peak near end
    beat_times = np.arange(0, 600.0, 0.5)
    candidates = find_top_moments(
        score, times, beat_times,
        clip_duration=30.0, n_clips=5,
        video_duration=600.0, min_gap=60.0,
    )
    for c in candidates:
        assert c.end_time <= 600.0


def test_beat_aligned_start():
    score, times = _synthetic_score([120.0])
    beat_times = np.array([109.5, 110.0, 110.5, 111.0])  # beats near expected start (120-10=110)
    candidates = find_top_moments(
        score, times, beat_times,
        clip_duration=30.0, n_clips=1,
        video_duration=600.0, min_gap=60.0,
    )
    assert len(candidates) == 1
    assert candidates[0].start_time in beat_times
