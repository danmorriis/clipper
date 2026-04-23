from pathlib import Path

import librosa
import numpy as np


def get_beat_times(wav_path: Path) -> np.ndarray:
    """
    Use librosa's beat tracker to find beat positions in a WAV file.
    Returns beat times in seconds as a numpy array.

    librosa.beat.beat_track is fast (~0.5s on a 30s clip), requires no
    compiled Cython extensions, and works with any Python 3.9+ version.
    """
    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return beat_times


def snap_to_nearest_beat(time_seconds: float, beat_times: np.ndarray) -> float:
    """Return the beat time nearest to time_seconds."""
    if len(beat_times) == 0:
        return time_seconds
    idx = np.argmin(np.abs(beat_times - time_seconds))
    return float(beat_times[idx])
