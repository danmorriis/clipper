import threading
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from dj_clipper.core.clip_exporter import export_clip
from dj_clipper.core.fingerprint_db import build_index
from dj_clipper.core.playlist_resolver import resolve_playlist
from dj_clipper.core.track_matcher import identify_tracks, write_tracklist_txt
from dj_clipper.core.track_utils import clean_track_name
from dj_clipper.models.clip_model import ClipCandidate, TrackMatch
from dj_clipper.models.session_model import SessionState

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a"}


class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    clip_done = pyqtSignal(int, str, list)   # clip_index, path_str, List[TrackMatch]
    finished = pyqtSignal(object)            # SessionState
    error = pyqtSignal(str)
    cancelled = pyqtSignal()


class ExportWorker(QRunnable):
    """
    Exports kept clips and writes tracklist.txt.

    If analysis already identified tracks (fingerprint mode), those results
    are used directly and no re-querying is done. If not (spectral fallback),
    and a tracklist_dir is set on the session, a post-export identify pass runs.
    """

    def __init__(self, session: SessionState, cancel_event: threading.Event):
        super().__init__()
        self.signals = WorkerSignals()
        self.session = session
        self.cancel_event = cancel_event

    def run(self) -> None:
        try:
            session = self.session
            kept = session.kept_clips
            output_dir = session.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)

            total_kept = len(kept)
            results: List[Tuple[ClipCandidate, List[TrackMatch]]] = []

            # ── Export clips ─────────────────────────────────────────────────
            for i, candidate in enumerate(kept):
                if self.cancel_event.is_set():
                    self.signals.cancelled.emit()
                    return
                pct = int((i / max(total_kept, 1)) * 60)
                self.signals.progress.emit(pct, f"Exporting clip {i + 1} of {total_kept}…")

                clip_path = export_clip(
                    video_path=session.video_path,
                    candidate=candidate,
                    output_dir=output_dir,
                    index=i + 1,
                )

                # Use tracks from analysis phase if available
                analysis_matches = self._matches_from_candidate(candidate)
                results.append((candidate, analysis_matches))
                self.signals.clip_done.emit(i, str(clip_path), analysis_matches)

            if self.cancel_event.is_set():
                self.signals.cancelled.emit()
                return

            # ── Optional: post-export track ID (spectral fallback only) ──────
            # Skip if analysis already identified tracks (db_path set + candidates have tracks).
            analysis_identified = any(c.pre_track or c.post_track for c in kept)

            if not analysis_identified and session.db_path and session.db_path.exists():
                results = self._identify_pass(session, results, output_dir, start_pct=60)
            elif not analysis_identified and session.tracklist_dir and session.tracklist_dir.exists():
                # Legacy: plain folder of audio files, no playlist
                self.signals.progress.emit(60, "Building fingerprint index…")
                db_path = output_dir / "tracklist.json"
                track_files = [
                    f for f in session.tracklist_dir.iterdir()
                    if f.suffix.lower() in AUDIO_EXTENSIONS
                ]
                if track_files:
                    build_index(track_files, db_path)
                    session.db_path = db_path
                    results = self._identify_pass(session, results, output_dir, start_pct=65)

            # ── Write tracklist.txt ───────────────────────────────────────────
            self.signals.progress.emit(99, "Writing tracklist.txt…")
            self._write_tracklist(output_dir, results)

            self.signals.progress.emit(100, "Export complete.")
            self.signals.finished.emit(session)

        except Exception as exc:
            self.signals.error.emit(str(exc))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _matches_from_candidate(self, candidate: ClipCandidate) -> List[TrackMatch]:
        """Convert pre/post track labels into TrackMatch objects."""
        matches = []
        seen = set()
        for track_name in (candidate.pre_track, candidate.post_track):
            if track_name and track_name not in seen:
                seen.add(track_name)
                matches.append(TrackMatch(
                    track_name=track_name,
                    confidence=candidate.score,
                    time_offset=0.0,
                ))
        # Also include any matched_tracks set directly
        for m in candidate.matched_tracks:
            if m.track_name not in seen:
                seen.add(m.track_name)
                matches.append(m)
        return matches

    def _identify_pass(self, session, results, output_dir, start_pct):
        """Post-export staggered pre/post identification for spectral-mode clips."""
        kept = session.kept_clips
        clip_files = sorted(output_dir.glob("clip_*.mp4"))
        for i, (candidate, existing_matches) in enumerate(results):
            if self.cancel_event.is_set():
                return results
            pct = start_pct + int((i / max(len(results), 1)) * (98 - start_pct))
            self.signals.progress.emit(pct, f"Identifying tracks for clip {i + 1}…")
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
                    self.signals.clip_done.emit(i, str(clip_path), matches)
        return results

    def _write_tracklist(self, output_dir: Path, results):
        """
        Write tracklist.txt using filenames that match the exported files.

        Files are named clip_001.mp4, clip_002.mp4, … in export order.
        The tracklist uses the same numbering so they always correspond.
        """
        lines = []
        for file_idx, (candidate, matches) in enumerate(results, 1):
            filename = f"clip_{file_idx:03d}"
            t = int(candidate.start_time)
            ts = f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"

            if candidate.pre_track or candidate.post_track:
                pre  = clean_track_name(candidate.pre_track)  if candidate.pre_track  else "unknown"
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
