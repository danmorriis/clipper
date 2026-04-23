import numpy as np
from dj_clipper.core.transition_detector import compute_spectral_features, compute_combined_score
from dj_clipper.config import SAMPLE_RATE
import soundfile as sf
import tempfile
from pathlib import Path


def _make_transition_wav(tmp_path: Path) -> Path:
    """Two sine waves: freq A for first 4s, freq B for last 4s, overlap in middle 2s."""
    duration = 10.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freq_a = np.sin(2 * np.pi * 440 * t)
    freq_b = np.sin(2 * np.pi * 880 * t)

    # Crossfade: A fades out 3–7s, B fades in 3–7s
    fade = np.clip((t - 3.0) / 4.0, 0.0, 1.0)
    signal = freq_a * (1 - fade) + freq_b * fade

    wav_path = tmp_path / "transition.wav"
    sf.write(str(wav_path), signal.astype(np.float32), SAMPLE_RATE)
    return wav_path


def test_compute_spectral_features_keys(tmp_path):
    wav = _make_transition_wav(tmp_path)
    features = compute_spectral_features(wav)
    assert set(features.keys()) == {"rms", "flux", "centroid", "times"}


def test_combined_score_shape(tmp_path):
    wav = _make_transition_wav(tmp_path)
    features = compute_spectral_features(wav)
    score = compute_combined_score(features)
    assert score.shape == features["rms"].shape


def test_combined_score_range(tmp_path):
    wav = _make_transition_wav(tmp_path)
    features = compute_spectral_features(wav)
    score = compute_combined_score(features)
    assert score.min() >= 0.0
    assert score.max() <= 1.0


def test_score_peak_in_transition_region(tmp_path):
    """Peak of combined score should fall in the crossfade region (3–7s) ±2s."""
    wav = _make_transition_wav(tmp_path)
    features = compute_spectral_features(wav)
    score = compute_combined_score(features)
    times = features["times"]
    peak_time = float(times[np.argmax(score)])
    assert 1.0 <= peak_time <= 9.0, f"Peak at {peak_time:.1f}s — outside expected crossfade region"
