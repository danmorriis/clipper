import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dj_clipper.config import TEMP_DIR
from dj_clipper.core.audio_extractor import extract_audio, extract_audio_segment, stretch_audio
from dj_clipper.core.fingerprint_db import query_clip
from dj_clipper.models.clip_model import ClipCandidate, TrackMatch

# Staggered window sizes tried in order. Each side stops as soon as a match
# clears min_confidence — so 30s is usually sufficient for clean solo audio.
SEARCH_WINDOWS = (30.0, 45.0, 60.0)

# Tempo ratios to try per window. Covers ±7% in 3% steps.
TEMPO_RATIOS = (0.93, 0.96, 0.98, 1.00, 1.02, 1.04, 1.07)

# Accept matches above this confidence. Lower than the default 0.1 because
# DJ audio is processed (EQ, compression, mixer chain) and confidences are
# inherently lower than clean broadcast audio.
MIN_CONFIDENCE = 0.05


def _query_with_tempo_search(
    wav_path: Path,
    db_path: Path,
    temp_dir: Path,
    ratios: Tuple[float, ...] = TEMPO_RATIOS,
) -> Dict[str, TrackMatch]:
    """
    Query wav_path against db_path at each tempo ratio.
    Returns track_name → best TrackMatch across all ratios.
    Stretched temp WAVs are deleted immediately after each query.
    """
    best: Dict[str, TrackMatch] = {}
    for ratio in ratios:
        if abs(ratio - 1.0) < 0.001:
            matches = query_clip(wav_path, db_path)
        else:
            stretched = temp_dir / f"{wav_path.stem}_t{ratio:.4f}_{uuid.uuid4().hex[:6]}.wav"
            try:
                stretch_audio(wav_path, stretched, ratio)
                matches = query_clip(stretched, db_path)
            except Exception:
                matches = []
            finally:
                if stretched.exists():
                    stretched.unlink()

        for m in matches:
            if m.track_name not in best or m.confidence > best[m.track_name].confidence:
                best[m.track_name] = m

    return best


def _search_side(
    session_wav: Path,
    seg_start: float,
    seg_end: float,
    db_path: Path,
    temp_dir: Path,
    windows: Tuple[float, ...] = SEARCH_WINDOWS,
    ratios: Tuple[float, ...] = TEMPO_RATIOS,
    min_confidence: float = MIN_CONFIDENCE,
    video_duration: float = 0.0,
) -> Optional[TrackMatch]:
    """
    Try progressively larger windows on one side of a clip until a confident
    match is found or all window sizes are exhausted.

    seg_start/seg_end define the *anchor edge* of the clip:
      - Pre-clip:  seg_start = clip.start_time - window, seg_end = clip.start_time
      - Post-clip: seg_start = clip.end_time,            seg_end = clip.end_time + window
    The caller adjusts seg_start/seg_end per window size; this function receives
    the final bounds for one window attempt.
    """
    # Clamp to valid audio range
    actual_start = max(0.0, seg_start)
    actual_end = seg_end
    if video_duration > 0:
        actual_end = min(actual_end, video_duration)
    duration = actual_end - actual_start
    if duration < 10.0:
        return None

    wav = temp_dir / f"side_{uuid.uuid4().hex[:10]}.wav"
    try:
        extract_audio_segment(session_wav, actual_start, duration, wav)
        hits = _query_with_tempo_search(wav, db_path, temp_dir, ratios)
        candidates = [m for m in hits.values() if m.confidence >= min_confidence]
        if candidates:
            return max(candidates, key=lambda m: m.confidence)
    finally:
        if wav.exists():
            wav.unlink()

    return None


def identify_tracks(
    clip_path: Path,
    db_path: Path,
    session_wav: Optional[Path] = None,
    candidate: Optional[ClipCandidate] = None,
    video_duration: float = 0.0,
    min_confidence: float = MIN_CONFIDENCE,
) -> List[TrackMatch]:
    """
    Identify the two tracks in a DJ transition clip.

    Strategy (staggered search):
      Pre-clip side:  try 30s → 45s → 60s of audio before clip start.
                      This window should contain track A playing solo.
      Post-clip side: try 30s → 45s → 60s of audio after clip end.
                      This window should contain track B playing solo.

    Each side stops as soon as confidence clears min_confidence, so the
    fast 30s path is taken whenever the audio is clean enough.

    If the pre and post matches are the SAME track (shouldn't happen at a real
    transition), only the higher-confidence one is returned.

    Falls back to querying the clip itself if session_wav is unavailable.
    All temp files are deleted immediately after each query.
    """
    temp_dir = TEMP_DIR / "track_id_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, TrackMatch] = {}

    if session_wav and session_wav.exists() and candidate is not None:
        # ── Pre-clip: staggered search backwards from clip start ──────────
        for window in SEARCH_WINDOWS:
            seg_start = candidate.start_time - window
            seg_end = candidate.start_time
            match = _search_side(
                session_wav, seg_start, seg_end, db_path, temp_dir,
                min_confidence=min_confidence, video_duration=video_duration,
            )
            if match:
                results[match.track_name] = match
                break  # found a confident pre-clip match — stop escalating

        # ── Post-clip: staggered search forwards from clip end ────────────
        for window in SEARCH_WINDOWS:
            seg_start = candidate.end_time
            seg_end = candidate.end_time + window
            match = _search_side(
                session_wav, seg_start, seg_end, db_path, temp_dir,
                min_confidence=min_confidence, video_duration=video_duration,
            )
            if match:
                # Only add if it's a different track from the pre-clip match
                if match.track_name not in results:
                    results[match.track_name] = match
                elif match.confidence > results[match.track_name].confidence:
                    results[match.track_name] = match
                break

    # ── Fallback: clip itself (no session WAV, or both sides failed) ──────
    if not results:
        clip_wav_dir = temp_dir / "clip_wav"
        clip_wav = None
        try:
            clip_wav = extract_audio(clip_path, clip_wav_dir)
            hits = _query_with_tempo_search(clip_wav, db_path, temp_dir)
            for name, m in hits.items():
                if m.confidence >= min_confidence:
                    results[name] = m
        finally:
            if clip_wav and clip_wav.exists():
                clip_wav.unlink()

    matches = sorted(results.values(), key=lambda m: m.confidence, reverse=True)
    return matches


def write_tracklist_txt(
    output_dir: Path,
    results: List[Tuple[ClipCandidate, List[TrackMatch]]],
) -> Path:
    """Write human-readable tracklist.txt. Returns path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "tracklist.txt"
    lines = []
    for candidate, matches in results:
        clip_name = f"clip_{candidate.rank:03d}.mp4"
        lines.append(clip_name)
        if matches:
            for match in matches:
                lines.append(
                    f'  Track: "{match.track_name}"  (confidence: {match.confidence:.2f})'
                )
        else:
            lines.append("  Track: (no match found)")
        lines.append("")
    txt_path.write_text("\n".join(lines))
    return txt_path
