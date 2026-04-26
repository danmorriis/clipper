"""
Local audio fingerprinting using Chromaprint (fpcalc).

Chromaprint builds fingerprints from chroma features (pitch-class profiles),
making it robust to DJ EQ, compression, video encoding artefacts, and two
tracks playing simultaneously.

Public interface:
  build_index(source, db_path) -> db_path
  query_clip(clip_wav_path, db_path) -> List[TrackMatch]
  fingerprint_pcm(pcm_int16, sample_rate) -> List[int]   # fast in-memory path
"""

import ctypes
import ctypes.util
import os
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from dj_clipper.models.clip_model import TrackMatch

# ── libchromaprint direct bindings ────────────────────────────────────────────
# Using the C library directly avoids all subprocess overhead (~8x faster than
# spawning fpcalc for each sample).  Falls back to fpcalc if not found.

_lib: Optional[ctypes.CDLL] = None
_CHROMAPRINT_ALGORITHM_DEFAULT = 1


def _load_chromaprint_lib() -> Optional[ctypes.CDLL]:
    """Try to load libchromaprint; return None if unavailable."""
    candidates = [
        "/opt/homebrew/lib/libchromaprint.dylib",   # Apple Silicon brew
        "/usr/local/lib/libchromaprint.dylib",       # Intel brew
        "libchromaprint.so.1",                        # Linux
        ctypes.util.find_library("chromaprint"),      # system search
    ]
    for path in candidates:
        if path is None:
            continue
        try:
            lib = ctypes.CDLL(path)
            # Wire up the signatures we need
            lib.chromaprint_new.argtypes = [ctypes.c_int]
            lib.chromaprint_new.restype = ctypes.c_void_p
            lib.chromaprint_start.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
            lib.chromaprint_start.restype = ctypes.c_int
            lib.chromaprint_feed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            lib.chromaprint_feed.restype = ctypes.c_int
            lib.chromaprint_finish.argtypes = [ctypes.c_void_p]
            lib.chromaprint_finish.restype = ctypes.c_int
            lib.chromaprint_get_raw_fingerprint.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)),
                ctypes.POINTER(ctypes.c_int),
            ]
            lib.chromaprint_get_raw_fingerprint.restype = ctypes.c_int
            lib.chromaprint_dealloc.argtypes = [ctypes.c_void_p]
            lib.chromaprint_dealloc.restype = None
            lib.chromaprint_free.argtypes = [ctypes.c_void_p]
            lib.chromaprint_free.restype = None
            return lib
        except (OSError, AttributeError):
            continue
    return None


def _get_lib() -> Optional[ctypes.CDLL]:
    global _lib
    if _lib is None:
        _lib = _load_chromaprint_lib()
    return _lib


def fingerprint_pcm(pcm_int16: np.ndarray, sample_rate: int = 16000) -> List[int]:
    """
    Compute a Chromaprint raw fingerprint from an int16 PCM numpy array.

    Uses libchromaprint directly if available (~6ms per 20s chunk); falls back
    to spawning fpcalc (~48ms) if the library is not found.  Both paths produce
    identical fingerprint values.

    Thread-safe: creates a new Chromaprint context for each call.
    """
    lib = _get_lib()
    if lib is not None:
        return _fingerprint_pcm_lib(lib, pcm_int16, sample_rate)
    else:
        return _fingerprint_pcm_fpcalc(pcm_int16, sample_rate)


def _fingerprint_pcm_lib(lib: ctypes.CDLL, pcm_int16: np.ndarray, sample_rate: int) -> List[int]:
    """Fingerprint via libchromaprint ctypes — no subprocess spawning."""
    pcm_bytes = pcm_int16.astype(np.int16).tobytes()
    n_samples = len(pcm_int16)
    ctx = lib.chromaprint_new(_CHROMAPRINT_ALGORITHM_DEFAULT)
    try:
        if not lib.chromaprint_start(ctx, sample_rate, 1):
            return []
        if not lib.chromaprint_feed(ctx, pcm_bytes, n_samples):
            return []
        if not lib.chromaprint_finish(ctx):
            return []
        fp_ptr = ctypes.POINTER(ctypes.c_uint32)()
        fp_size = ctypes.c_int(0)
        if not lib.chromaprint_get_raw_fingerprint(ctx, ctypes.byref(fp_ptr), ctypes.byref(fp_size)):
            return []
        result = list(fp_ptr[:fp_size.value])
        lib.chromaprint_dealloc(fp_ptr)
        return result
    finally:
        lib.chromaprint_free(ctx)


def _fingerprint_pcm_fpcalc(pcm_int16: np.ndarray, sample_rate: int) -> List[int]:
    """Fallback: wrap PCM in a WAV container and pipe to fpcalc."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_int16.astype(np.int16).tobytes())
    wav_bytes = buf.getvalue()
    duration_s = len(pcm_int16) // sample_rate + 1
    proc = subprocess.Popen(
        ["fpcalc", "-raw", "-length", str(duration_s), "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    out, _ = proc.communicate(input=wav_bytes)
    for line in out.decode(errors="ignore").splitlines():
        if line.startswith("FINGERPRINT="):
            raw = line.split("=", 1)[1].strip()
            return [int(x) for x in raw.split(",") if x]
    return []

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}

# Chromaprint fingerprint chunk size (number of int32 values).
# Each value covers ~0.5 seconds. 120 values ≈ 60 seconds.
_CHUNK = 120

# Fraction of fingerprint bits that must match for a confident identification.
# Chromaprint bit similarity on identical clean audio is ~0.90; on processed
# DJ audio expect 0.60–0.75. Threshold set conservatively to reduce false positives.
MIN_BIT_SIMILARITY = 0.65


def _fpcalc(audio_path: Path, length: int = 60) -> Tuple[float, List[int]]:
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


def fpcalc_piped(session_wav: Path, start: float, duration: float) -> List[int]:
    """
    Seek to `start` in session_wav, extract `duration` seconds, and fingerprint —
    all in one pass by piping ffmpeg stdout directly into fpcalc stdin.
    No temp files written. Returns raw fingerprint ints, or [] on failure.
    """
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-ss", str(max(0.0, start)),
            "-i", str(session_wav),
            "-t", str(duration),
            "-c", "copy",          # WAV is already 16kHz mono — just copy
            "-f", "wav", "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    fpcalc = subprocess.Popen(
        ["fpcalc", "-raw", "-length", str(int(duration) + 1), "-"],
        stdin=ffmpeg.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    # Let ffmpeg receive SIGPIPE if fpcalc exits first
    assert ffmpeg.stdout is not None
    ffmpeg.stdout.close()

    output, _ = fpcalc.communicate()
    ffmpeg.wait()

    if fpcalc.returncode != 0:
        return []

    for line in output.splitlines():
        if line.startswith("FINGERPRINT="):
            raw = line.split("=", 1)[1].strip()
            return [int(x) for x in raw.split(",") if x]
    return []


def preload_index(db_path: Path) -> Dict[str, np.ndarray]:
    """
    Load the fingerprint DB and pre-convert all reference fingerprints to
    numpy uint32 arrays.  Pass the result to query_clip_preloaded instead of
    calling json.loads() inside the worker hot-loop.
    """
    raw: Dict[str, List[int]] = json.loads(db_path.read_text())
    return {name: np.array(fp, dtype=np.uint32) for name, fp in raw.items()}


def query_clip_preloaded(
    fingerprint_ints: List[int],
    index: Dict[str, Any],
    min_similarity: float = MIN_BIT_SIMILARITY,
) -> List["TrackMatch"]:
    """
    Compare a pre-computed fingerprint against a pre-loaded index dict.
    No disk I/O — safe to call from parallel worker threads.

    index values may be either List[int] or np.ndarray (pre-converted via
    preload_index for best performance in repeated calls).
    """
    if not fingerprint_ints or not index:
        return []

    query_arr = np.array(fingerprint_ints, dtype=np.uint32)
    matches: List["TrackMatch"] = []

    for track_name, ref_fp in index.items():
        ref_arr = ref_fp if isinstance(ref_fp, np.ndarray) else np.array(ref_fp, dtype=np.uint32)
        similarity = _bit_similarity(query_arr, ref_arr)
        if similarity >= min_similarity:
            matches.append(TrackMatch(
                track_name=track_name,
                confidence=round(similarity, 4),
                time_offset=0.0,
            ))

    matches.sort(key=lambda m: m.confidence, reverse=True)

    if len(matches) >= 2:
        margin = matches[0].confidence - matches[1].confidence
        if margin < 0.10:
            return []

    return matches


def _bit_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Sliding-window bit error rate between two Chromaprint fingerprint arrays.

    Fully vectorised: all sliding windows are stacked into a 2-D matrix and
    XOR'd + popcount'd in one NumPy pass — no Python for-loop.  This reduces
    GIL hold-time dramatically compared to a loop-based approach, making it
    safe to call from many threads concurrently.

    Returns the peak fraction of matching bits (0.0–1.0).
    """
    if len(a) == 0 or len(b) == 0:
        return 0.0

    # Ensure a is the shorter (query) array
    if len(a) > len(b):
        a, b = b, a

    q = len(a)
    n = len(b)
    n_windows = n - q + 1
    if n_windows <= 0:
        # Arrays are the same length — single comparison
        xor = np.bitwise_xor(a, b)
        matching = int(np.sum(np.unpackbits(xor.view(np.uint8)) == 0))
        return matching / (q * 32)

    # Stack all windows: shape (n_windows, q)
    strides = (b.strides[0], b.strides[0])
    windows = np.lib.stride_tricks.as_strided(b, shape=(n_windows, q), strides=strides)

    # XOR query against every window, then count matching bits per window
    xors = np.bitwise_xor(a[None, :], windows)                          # (n_windows, q)
    bit_matches = np.sum(
        np.unpackbits(xors.view(np.uint8).reshape(n_windows, -1), axis=1) == 0,
        axis=1,
    )
    return float(np.max(bit_matches)) / (q * 32)


def build_index(
    source: Union[Path, List[Path]],
    db_path: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Path:
    """
    Fingerprint audio files using Chromaprint and save to a JSON index at db_path.

    source can be:
      - a directory Path  → indexes all audio files in that directory (non-recursive)
      - a List[Path]      → indexes exactly those files

    Fingerprinting runs in parallel (one thread per logical core) since each
    fpcalc call is an independent subprocess.

    progress_callback(completed, total, track_name) is called as each track finishes.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if isinstance(source, list):
        tracks = sorted(f for f in source if f.suffix.lower() in AUDIO_EXTENSIONS)
    else:
        tracks = [
            f for f in sorted(source.iterdir())
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]
    if not tracks:
        raise ValueError("No audio files to index")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    index: Dict[str, List[int]] = {}
    lock = threading.Lock()
    completed = 0

    def _fingerprint(track: Path):
        _, fingerprint = _fpcalc(track, length=120)
        return track, fingerprint

    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 1))) as executor:
        futures = {executor.submit(_fingerprint, t): t for t in tracks}
        for future in as_completed(futures):
            track, fingerprint = future.result()
            if fingerprint:
                with lock:
                    index[track.stem] = fingerprint
            with lock:
                completed += 1
                done = completed
            if progress_callback:
                progress_callback(done, len(tracks), track.name)

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
    """
    if not db_path.exists():
        return []
    index = preload_index(db_path)
    if not index:
        return []
    _, query_fp = _fpcalc(clip_wav_path)
    if not query_fp:
        return []
    return query_clip_preloaded(query_fp, index, min_similarity)
