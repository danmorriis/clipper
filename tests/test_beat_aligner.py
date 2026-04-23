import numpy as np
import soundfile as sf
from pathlib import Path
from dj_clipper.core.beat_aligner import get_beat_times, snap_to_nearest_beat
from dj_clipper.config import SAMPLE_RATE


def _make_click_track(tmp_path: Path, bpm: float = 120.0, duration: float = 10.0) -> Path:
    """Synthesize a click track at the given BPM."""
    n_samples = int(SAMPLE_RATE * duration)
    signal = np.zeros(n_samples, dtype=np.float32)
    beat_interval = int(SAMPLE_RATE * 60.0 / bpm)
    click_len = int(SAMPLE_RATE * 0.01)  # 10ms click
    for i in range(0, n_samples, beat_interval):
        end = min(i + click_len, n_samples)
        signal[i:end] = 0.8
    wav_path = tmp_path / "click.wav"
    sf.write(str(wav_path), signal, SAMPLE_RATE)
    return wav_path


def test_beat_times_spacing(tmp_path):
    """120 BPM click track → mean spacing ≈ 0.5s ±0.05s."""
    wav = _make_click_track(tmp_path, bpm=120.0)
    beats = get_beat_times(wav)
    assert len(beats) >= 5, "Too few beats detected"
    spacings = np.diff(beats)
    mean_spacing = float(np.mean(spacings))
    assert abs(mean_spacing - 0.5) < 0.05, f"Mean beat spacing {mean_spacing:.3f}s — expected ~0.5s"


def test_snap_to_nearest_beat():
    beat_times = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
    assert snap_to_nearest_beat(1.1, beat_times) == 1.0
    assert snap_to_nearest_beat(1.9, beat_times) == 2.0
    assert snap_to_nearest_beat(0.0, beat_times) == 0.5


def test_snap_empty_beats():
    assert snap_to_nearest_beat(3.0, np.array([])) == 3.0
