from pathlib import Path

import numpy as np
import librosa

from dj_clipper.config import SAMPLE_RATE, HOP_LENGTH


def compute_spectral_features(wav_path: Path, sr: int = SAMPLE_RATE) -> dict:
    """Returns {'rms', 'flux', 'centroid', 'times'} as np.ndarrays."""
    y, _ = librosa.load(str(wav_path), sr=sr, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
    flux = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP_LENGTH)[0]
    times = librosa.times_like(rms, sr=sr, hop_length=HOP_LENGTH)
    return {"rms": rms, "flux": flux, "centroid": centroid, "times": times}


def compute_combined_score(features: dict, window_seconds: float = 2.0) -> np.ndarray:
    """Weighted combination of normalized spectral features. Returns score in [0,1]."""
    rms = features["rms"]
    flux = features["flux"]
    centroid = features["centroid"]

    def norm(x):
        mn, mx = x.min(), x.max()
        if mx == mn:
            return np.zeros_like(x)
        return (x - mn) / (mx - mn)

    window_frames = max(1, int(window_seconds * SAMPLE_RATE / HOP_LENGTH))

    def rolling_variance(x, w):
        variance = np.zeros_like(x, dtype=float)
        for i in range(len(x)):
            lo = max(0, i - w // 2)
            hi = min(len(x), i + w // 2 + 1)
            variance[i] = np.var(x[lo:hi])
        return variance

    flux_norm = norm(flux)
    rms_var = norm(rolling_variance(rms, window_frames))
    centroid_var = norm(rolling_variance(centroid, window_frames))

    score = 0.5 * flux_norm + 0.3 * rms_var + 0.2 * centroid_var
    return score


if __name__ == "__main__":
    import sys
    wav = Path(sys.argv[1])
    features = compute_spectral_features(wav)
    score = compute_combined_score(features)
    times = features["times"]
    top = np.argsort(score)[-10:][::-1]
    print("Top 10 transition candidates:")
    for i in top:
        print(f"  t={times[i]:.1f}s  score={score[i]:.3f}")
