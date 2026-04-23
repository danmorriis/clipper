"""
Export runner — Qt-free version of ExportWorker.

Runs the export pipeline in a plain thread, putting progress events
(including clip_done events) onto a queue.Queue.
"""

import queue
import threading
from pathlib import Path
from typing import List, Tuple

from dj_clipper.core.clip_exporter import export_clip
from dj_clipper.core.fingerprint_db import build_index
from dj_clipper.core.playlist_resolver import resolve_playlist
from dj_clipper.core.track_matcher import identify_tracks
from dj_clipper.core.track_utils import clean_track_name
from dj_clipper.models.clip_model import ClipCandidate, TrackMatch
from dj_clipper.models.session_model import SessionState

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}


def _emit(q: queue.Queue, percent: int, message: str) -> None:
    q.put({"percent": percent, "message": message})


def run_export(
    session: SessionState,
    cancel_event: threading.Event,
    progress_queue: queue.Queue,
) -> None:
    """Entry point for ThreadPoolExecutor."""
    try:
        kept = session.kept_clips
        output_dir = session.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        total_kept = len(kept)
        results: List[Tuple[ClipCandidate, List[TrackMatch]]] = []

        for i, candidate in enumerate(kept):
            if cancel_event.is_set():
                progress_queue.put({"cancelled": True, "done": True})
                return
            pct = int((i / max(total_kept, 1)) * 60)
            _emit(progress_queue, pct, f"Exporting clip {i + 1} of {total_kept}…")

            clip_path = export_clip(
                video_path=session.video_path,
                candidate=candidate,
                output_dir=output_dir,
                index=i + 1,
            )

            analysis_matches = _matches_from_candidate(candidate)
            results.append((candidate, analysis_matches))
            progress_queue.put({
                "percent": pct,
                "message": f"Exported clip {i + 1}",
                "clip_done": {
                    "index": i,
                    "path": str(clip_path),
                    "tracks": [
                        {"track_name": m.track_name, "confidence": m.confidence}
                        for m in analysis_matches
                    ],
                },
            })

        if cancel_event.is_set():
            progress_queue.put({"cancelled": True, "done": True})
            return

        analysis_identified = any(c.pre_track or c.post_track for c in kept)

        if not analysis_identified and session.db_path and session.db_path.exists():
            results = _identify_pass(session, results, output_dir, start_pct=60, cancel_event=cancel_event, q=progress_queue)
        elif not analysis_identified and session.tracklist_dir and session.tracklist_dir.exists():
            _emit(progress_queue, 60, "Building fingerprint index…")
            db_path = output_dir / "tracklist.json"
            track_files = [
                f for f in session.tracklist_dir.iterdir()
                if f.suffix.lower() in AUDIO_EXTENSIONS
            ]
            if track_files:
                build_index(track_files, db_path)
                session.db_path = db_path
                results = _identify_pass(session, results, output_dir, start_pct=65, cancel_event=cancel_event, q=progress_queue)

        _emit(progress_queue, 99, "Writing tracklist.txt…")
        _write_tracklist(output_dir, results)

        progress_queue.put({"percent": 100, "message": "Export complete.", "done": True})

    except Exception as exc:
        progress_queue.put({"error": str(exc), "done": True})


def _matches_from_candidate(candidate: ClipCandidate) -> List[TrackMatch]:
    matches = []
    seen = set()
    for track_name in (candidate.pre_track, candidate.post_track):
        if track_name and track_name not in seen:
            seen.add(track_name)
            matches.append(TrackMatch(track_name=track_name, confidence=candidate.score, time_offset=0.0))
    for m in candidate.matched_tracks:
        if m.track_name not in seen:
            seen.add(m.track_name)
            matches.append(m)
    return matches


def _identify_pass(session, results, output_dir, start_pct, cancel_event, q):
    clip_files = sorted(output_dir.glob("clip_*.mp4"))
    for i, (candidate, existing_matches) in enumerate(results):
        if cancel_event.is_set():
            return results
        pct = start_pct + int((i / max(len(results), 1)) * (98 - start_pct))
        _emit(q, pct, f"Identifying tracks for clip {i + 1}…")
        clip_path = clip_files[i] if i < len(clip_files) else None
        if clip_path and clip_path.exists():
            matches = identify_tracks(
                clip_path=clip_path,
                db_path=session.db_path,
                session_wav=session.wav_path,
                candidate=candidate,
                video_duration=session.video_duration,
            )
            if matches:
                candidate.matched_tracks = matches
                results[i] = (candidate, matches)
                q.put({
                    "percent": pct,
                    "message": f"Identified clip {i + 1}",
                    "clip_done": {
                        "index": i,
                        "path": str(clip_path),
                        "tracks": [
                            {"track_name": m.track_name, "confidence": m.confidence}
                            for m in matches
                        ],
                    },
                })
    return results


def _write_tracklist(output_dir: Path, results):
    lines = []
    for file_idx, (candidate, matches) in enumerate(results, 1):
        filename = f"clip_{file_idx:03d}"
        t = int(candidate.start_time)
        ts = f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"

        if candidate.pre_track or candidate.post_track:
            pre = clean_track_name(candidate.pre_track) if candidate.pre_track else "unknown"
            post = clean_track_name(candidate.post_track) if candidate.post_track else "unknown"
            lines.append(f"{filename} @ {ts}: {pre} → {post}")
        elif matches:
            track_str = " / ".join(clean_track_name(m.track_name) for m in matches)
            lines.append(f"{filename} @ {ts}: {track_str}")
        else:
            lines.append(f"{filename} @ {ts}: unidentified")

    tl_path = output_dir / "tracklist.txt"
    tl_path.write_text("\n".join(lines))
    return tl_path
