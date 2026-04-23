"""
Local audio fingerprinting using Chromaprint (fpcalc).

Chromaprint builds fingerprints from chroma features (pitch-class profiles),
making it robust to DJ EQ, compression, video encoding artefacts, and two
tracks playing simultaneously.

Public interface:
  build_index(source, db_path) -> db_path
  query_clip(clip_wav_path, db_path) -> List[TrackMatch]
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from dj_clipper.models.clip_model import TrackMatch

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}

# Chromaprint fingerprint chunk size (number of int32 values).
# Each value covers ~0.5 seconds. 120 values ≈ 60 seconds.
_CHUNK = 120

# Fraction of fingerprint bits that must match for a confident identification.
# Chromaprint bit similarity on identical clean audio is ~0.90; on processed
# DJ audio expect 0.60–0.75. Threshold set conservatively to reduce false positives.
MIN_BIT_SIMILARITY = 0.60


def _fpcalc(audio_path: Path, length: int = 120) -> Tuple[float, List[int]]:
    """
    Run fpcalc on an audio file. Returns (duration_seconds, fingerprint_ints).
    length = max seconds of audio to fingerprint (chromaprint default is 120s).
    """
    result = subprocess.run(
        ["fpcalc", "-raw", "-length", str(length), str(audio_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fpcalc failed on {audio_path.name}: {result.stderr.strip()}")

    duration = 0.0
    fingerprint: List[int] = []
    for line in result.stdout.splitlines():
        if line.startswith("DURATION="):
            duration = float(line.split("=", 1)[1])
        elif line.startswith("FINGERPRINT="):
            raw = line.split("=", 1)[1].strip()
            fingerprint = [int(x) for x in raw.split(",") if x]
    return duration, fingerprint


def _bit_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Sliding-window bit error rate between two fingerprint arrays.
    Returns the peak fraction of matching bits across all 32-bit positions,
    found by sliding the shorter array over the longer.
    """
    if len(a) == 0 or len(b) == 0:
        return 0.0

    # Work with the shorter array as the query
    if len(a) > len(b):
        a, b = b, a

    query_len = len(a)
    ref_len = len(b)
    best = 0.0

    # Slide query across reference
    for offset in range(ref_len - query_len + 1):
        window = np.bitwise_xor(
            a,
            b[offset: offset + query_len],
        )
        # Count zero bits (matching bits) in the XOR result
        matching_bits = np.sum(np.unpackbits(window.view(np.uint8)) == 0)
        total_bits = query_len * 32
        score = matching_bits / total_bits
        if score > best:
            best = score

    return best


def build_index(
    source: Union[Path, List[Path]],
    db_path: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """
    Fingerprint audio files using Chromaprint and save to a JSON index at db_path.

    source can be:
      - a directory Path  → indexes all audio files in that directory (non-recursive)
      - a List[Path]      → indexes exactly those files

    The index format is:
      { "track_stem": [int, int, ...], ... }
    """
    if isinstance(source, list):
        tracks = sorted(f for f in source if f.suffix.lower() in AUDIO_EXTENSIONS)
    else:
        tracks = [
            f for f in sorted(source.iterdir())
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]
    if not tracks:
        raise ValueError(f"No audio files to index")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    index: Dict[str, List[int]] = {}
    for i, track in enumerate(tracks):
        if progress_callback:
            progress_callback(i, track.name)
        _, fingerprint = _fpcalc(track)
        if fingerprint:
            index[track.stem] = fingerprint

    db_path.write_text(json.dumps(index))
    return db_path


def query_clip(
    clip_wav_path: Path,
    db_path: Path,
    min_similarity: float = MIN_BIT_SIMILARITY,
) -> List[TrackMatch]:
    """
    Fingerprint clip_wav_path and compare against the Chromaprint index.
    Returns TrackMatch list sorted by confidence descending.

    confidence = peak bit similarity (0.0–1.0) between the clip fingerprint
    and the best-matching window in each reference track.
    """
    if not db_path.exists():
        return []

    index: Dict[str, List[int]] = json.loads(db_path.read_text())
    if not index:
        return []

    _, query_fp = _fpcalc(clip_wav_path)
    if not query_fp:
        return []

    # fpcalc -raw outputs unsigned 32-bit integers — use uint32 to avoid
    # overflow corruption on values above 2^31.
    query_arr = np.array(query_fp, dtype=np.uint32)
    matches: List[TrackMatch] = []

    for track_name, ref_fp in index.items():
        ref_arr = np.array(ref_fp, dtype=np.uint32)
        similarity = _bit_similarity(query_arr, ref_arr)
        if similarity >= min_similarity:
            matches.append(TrackMatch(
                track_name=track_name,
                confidence=round(similarity, 4),
                time_offset=0.0,  # Chromaprint doesn't give per-hash offsets
            ))

    matches.sort(key=lambda m: m.confidence, reverse=True)

    # Require the top match to be meaningfully better than the second-best.
    # With a small DB, both tracks will score moderately — the margin separates
    # genuine matches from "best of a bad lot" false positives.
    if len(matches) >= 2:
        margin = matches[0].confidence - matches[1].confidence
        if margin < 0.08:
            return []

    return matches
