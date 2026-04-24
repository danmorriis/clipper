"""
Analysis runner — Qt-free version of AnalysisWorker.

Runs the full analysis pipeline in a plain thread, putting progress
events onto a queue.Queue instead of emitting Qt signals.

Event shape: {"percent": int, "message": str} during progress.
Terminal events add "done": True and optionally "error" or "cancelled".
"""

import queue
import shutil
import threading
from pathlib import Path
from typing import Optional

from dj_clipper.core.audio_extractor import extract_audio, extract_audio_segment, get_video_duration
from dj_clipper.core.beat_aligner import get_beat_times, snap_to_nearest_beat
from dj_clipper.core.clip_scorer import find_top_moments
from dj_clipper.core.fingerprint_db import build_index
from dj_clipper.core.playlist_resolver import resolve_playlist
from dj_clipper.core.transition_detector import compute_combined_score, compute_spectral_features
from dj_clipper.core.transition_finder import build_track_timeline, find_transitions
from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.models.session_model import SessionState

_BEAT_SEGMENT_DURATION = 30.0
_BEAT_SEGMENT_PRE = 5.0


def _emit(q: queue.Queue, percent: int, message: str) -> None:
    q.put({"percent": percent, "message": message})


def _cleanup(session_dir: Optional[Path]) -> None:
    try:
        if session_dir and session_dir.exists():
            shutil.rmtree(session_dir)
    except Exception:
        pass


def _check_cancel(cancel_event: threading.Event, session_dir: Optional[Path], q: queue.Queue) -> bool:
    if cancel_event.is_set():
        _cleanup(session_dir)
        q.put({"cancelled": True, "done": True})
        return True
    return False


def run_analysis(
    session: SessionState,
    cancel_event: threading.Event,
    progress_queue: queue.Queue,
) -> None:
    """Entry point for ThreadPoolExecutor. Modifies session in-place."""
    session_dir = None
    try:
        session_dir = session.session_temp_dir
        session_dir.mkdir(parents=True, exist_ok=True)

        _emit(progress_queue, 5, "Extracting audio…")
        wav_path = extract_audio(session.video_path, session_dir)
        session.wav_path = wav_path
        if _check_cancel(cancel_event, session_dir, progress_queue):
            return

        _emit(progress_queue, 10, "Reading video metadata…")
        session.video_duration = get_video_duration(session.video_path)
        if _check_cancel(cancel_event, session_dir, progress_queue):
            return

        if session.settings.manual_timestamps:
            all_candidates = _run_timeslot_mode(session, session_dir, wav_path, cancel_event, progress_queue)
        else:
            playlist_ready = (
                session.playlist_path and session.playlist_path.exists()
                and session.search_root and session.search_root.exists()
            )
            if playlist_ready:
                all_candidates = _run_fingerprint_mode(session, session_dir, wav_path, cancel_event, progress_queue)
            else:
                all_candidates = _run_spectral_mode(session, wav_path, cancel_event, progress_queue)

        if all_candidates is None:
            return

        if not session.settings.manual_timestamps:
            n = len(all_candidates)
            for i, candidate in enumerate(all_candidates):
                if _check_cancel(cancel_event, session_dir, progress_queue):
                    return
                pct = 80 + int((i / max(n, 1)) * 18)
                _emit(progress_queue, pct, f"Beat-aligning clip {i + 1} of {n}…")

                seg_start = max(0.0, candidate.start_time - _BEAT_SEGMENT_PRE)
                seg_path = session_dir / f"_beat_tmp_{candidate.rank:03d}.wav"
                try:
                    extract_audio_segment(wav_path, seg_start, _BEAT_SEGMENT_DURATION, seg_path)
                    beat_times = get_beat_times(seg_path)
                    if len(beat_times) > 0:
                        abs_beats = beat_times + seg_start
                        snapped = snap_to_nearest_beat(candidate.start_time, abs_beats)
                        snapped = max(0.0, snapped)
                        if snapped + session.settings.clip_duration <= session.video_duration:
                            candidate.start_time = snapped
                            candidate.end_time = snapped + session.settings.clip_duration
                finally:
                    seg_path.unlink(missing_ok=True)

        session.all_candidates = all_candidates
        if session.settings.clip_all or session.settings.manual_timestamps:
            displayed = list(all_candidates)
        else:
            displayed = _select_top_n(all_candidates, session.settings.n_clips)
        displayed.sort(key=lambda c: c.start_time)
        for i, c in enumerate(displayed, 1):
            c.rank = i
        session.candidates = displayed

        progress_queue.put({"percent": 100, "message": "Analysis complete.", "done": True})

    except Exception as exc:
        progress_queue.put({"error": str(exc), "done": True})


def _run_fingerprint_mode(session, session_dir, wav_path, cancel_event, q):
    found_paths, missing = resolve_playlist(
        session.playlist_path,
        session.search_root,
        on_index_start=lambda: _emit(q, 12, "Scanning music folder…"),
        progress_callback=lambda cur, tot, name: _emit(q, 13, f"Resolving tracks… {cur + 1}/{tot}"),
    )
    if cancel_event.is_set():
        _cleanup(session_dir)
        q.put({"cancelled": True, "done": True})
        return None

    if not found_paths:
        _emit(q, 14, "No tracks resolved — falling back to spectral…")
        return _run_spectral_mode(session, wav_path, cancel_event, q)

    # resolved_track_names is populated after timeline scanning (video appearance order).
    # Set a placeholder here; it will be overwritten after build_track_timeline.

    if missing:
        _emit(q, 14, f"Warning: {len(missing)} track(s) not found on disk")

    db_path = session_dir / "tracklist.json"
    build_index(
        found_paths, db_path,
        progress_callback=lambda done, tot, name: _emit(q, 15 + int((done / max(tot, 1)) * 4), f"Fingerprinting tracks… {done}/{tot}"),
    )
    session.db_path = db_path
    if cancel_event.is_set():
        _cleanup(session_dir)
        q.put({"cancelled": True, "done": True})
        return None

    total_samples = int((session.video_duration - 20.0) / 20.0)
    _emit(q, 20, f"Scanning audio timeline (~{total_samples} samples)…")

    cancelled_flag = [False]

    def timeline_progress(cur, tot, ts):
        if cancel_event.is_set():
            cancelled_flag[0] = True
            return
        pct = 20 + int((cur / max(tot, 1)) * 55)
        _emit(q, pct, f"Collecting… {cur}/{tot} crumbs")

    tl_result = build_track_timeline(
        wav_path, db_path, session.video_duration,
        progress_callback=timeline_progress,
        cancel_event=cancel_event,
    )

    if cancelled_flag[0] or cancel_event.is_set():
        _cleanup(session_dir)
        q.put({"cancelled": True, "done": True})
        return None

    session.timeline = list(tl_result.timeline)

    # Order track names by first appearance in the video, then append any
    # playlist tracks that were never identified in the session.
    seen: set = set()
    ordered: list = []
    for entry in tl_result.timeline:
        if entry.track and entry.track not in seen:
            seen.add(entry.track)
            ordered.append(entry.track)
    for path in found_paths:
        if path.stem not in seen:
            ordered.append(path.stem)
    session.resolved_track_names = ordered

    _emit(q, 76, "Detecting transitions…")
    candidates = find_transitions(
        tl_result.timeline,
        clip_duration=session.settings.clip_duration,
        video_duration=session.video_duration,
        pcm=tl_result.pcm,
        sample_rate=tl_result.sample_rate,
    )

    if not candidates:
        _emit(q, 77, "No transitions found — falling back to spectral…")
        return _run_spectral_mode(session, wav_path, cancel_event, q)

    return candidates


def _run_timeslot_mode(session, session_dir, wav_path, cancel_event, q):
    timestamps = session.settings.manual_timestamps
    clip_dur = session.settings.clip_duration

    timeline = []
    playlist_ready = (
        session.playlist_path and session.playlist_path.exists()
        and session.search_root and session.search_root.exists()
    )
    if playlist_ready:
        found_paths, _ = resolve_playlist(
            session.playlist_path,
            session.search_root,
            on_index_start=lambda: _emit(q, 12, "Scanning music folder…"),
            progress_callback=lambda cur, tot, name: _emit(q, 13, f"Resolving tracks… {cur + 1}/{tot}"),
        )
        if _check_cancel(cancel_event, session_dir, q):
            return None

        if found_paths:
            session.resolved_track_names = sorted(p.stem for p in found_paths)
            db_path = session_dir / "tracklist.json"
            build_index(
                found_paths, db_path,
                progress_callback=lambda done, tot, name: _emit(q, 15 + int((done / max(tot, 1)) * 4), f"Fingerprinting tracks… {done}/{tot}"),
            )
            session.db_path = db_path
            if _check_cancel(cancel_event, session_dir, q):
                return None

            cancelled_flag = [False]

            def timeline_progress(cur, tot, ts):
                if cancel_event.is_set():
                    cancelled_flag[0] = True
                    return
                pct = 20 + int((cur / max(tot, 1)) * 55)
                _emit(q, pct, f"Collecting… {cur}/{tot} crumbs")

            tl_result = build_track_timeline(
                wav_path, db_path, session.video_duration,
                progress_callback=timeline_progress,
                cancel_event=cancel_event,
            )
            timeline = tl_result.timeline
            session.timeline = list(timeline)
            if cancelled_flag[0] or _check_cancel(cancel_event, session_dir, q):
                return None

    _emit(q, 78, "Building timeslot clips…")

    def _track_at(t: float):
        if not timeline:
            return None
        best = min(timeline, key=lambda e: abs(e.start - t))
        return best.track if best.confidence >= 0.0 else None

    candidates = []
    for rank, ts in enumerate(timestamps, 1):
        clip_start = max(0.0, ts)
        clip_end = min(clip_start + clip_dur, session.video_duration)
        if clip_end - clip_start < clip_dur and clip_end == session.video_duration:
            clip_start = max(0.0, clip_end - clip_dur)
        mid = (clip_start + clip_end) / 2.0
        track = _track_at(ts)
        candidates.append(ClipCandidate(
            rank=rank,
            start_time=clip_start,
            end_time=clip_end,
            transition_peak_time=mid,
            score=1.0,
            pre_track=track,
            post_track=None,
        ))

    return candidates


def _run_spectral_mode(session, wav_path, cancel_event, q):
    _emit(q, 20, "Analyzing audio (spectral features)…")
    features = compute_spectral_features(wav_path)
    combined_score = compute_combined_score(features)
    times = features["times"]
    if cancel_event.is_set():
        q.put({"cancelled": True, "done": True})
        return None

    _emit(q, 75, "Finding candidate moments…")
    candidates = find_top_moments(
        combined_score=combined_score,
        times=times,
        beat_times=None,
        clip_duration=session.settings.clip_duration,
        n_clips=999,
        video_duration=session.video_duration,
    )
    return candidates


def _select_top_n(all_candidates, n_clips: int):
    if n_clips >= len(all_candidates):
        return list(all_candidates[:n_clips])
    if n_clips >= len(all_candidates) / 2:
        return list(all_candidates[:n_clips])

    seen_tracks: set = set()
    primary: list = []
    spillover: list = []

    for c in all_candidates:
        involved = {c.pre_track, c.post_track} - {None}
        if not seen_tracks & involved:
            seen_tracks |= involved
            primary.append(c)
        else:
            spillover.append(c)
        if len(primary) >= n_clips:
            break

    if len(primary) < n_clips:
        needed = n_clips - len(primary)
        primary.extend(spillover[:needed])

    return primary[:n_clips]
