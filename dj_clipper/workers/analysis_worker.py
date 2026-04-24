import shutil
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

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


class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)   # SessionState
    error = pyqtSignal(str)
    cancelled = pyqtSignal()


class AnalysisWorker(QRunnable):
    """
    Full analysis pipeline with two modes:

    FINGERPRINT MODE (playlist provided at import):
      1. Extract audio
      2. Resolve playlist → build fingerprint DB
      3. Sample full audio at 20s intervals → build track timeline
      4. Detect A→B handoffs → ClipCandidates (pre_track/post_track set)
      5. Beat-align ALL discovered candidates

    SPECTRAL FALLBACK (no playlist):
      1. Extract audio
      2. Librosa spectral features → find energy/flux peaks
      3. Beat-align candidates

    session.all_candidates holds the full sorted pool.
    session.candidates is the top-N slice (or all, if clip_all=True).
    Beat segment WAVs are deleted immediately after each clip to avoid bloat.
    """

    def __init__(self, session: SessionState, cancel_event: threading.Event):
        super().__init__()
        self.signals = WorkerSignals()
        self.session = session
        self.cancel_event = cancel_event

    def _cleanup(self, session_dir: Path) -> None:
        """Delete the session temp dir (never touches source files)."""
        try:
            if session_dir and session_dir.exists():
                shutil.rmtree(session_dir)
        except Exception:
            pass

    def _check_cancel(self, session_dir: Path) -> bool:
        """Return True (and emit cancelled + clean up) if cancellation was requested."""
        if self.cancel_event.is_set():
            self._cleanup(session_dir)
            self.signals.cancelled.emit()
            return True
        return False

    def run(self) -> None:
        session_dir = None
        try:
            session = self.session
            session_dir = session.session_temp_dir
            session_dir.mkdir(parents=True, exist_ok=True)

            # ── Step 1: Extract audio ────────────────────────────────────────
            self.signals.progress.emit(5, "Extracting audio…")
            wav_path = extract_audio(session.video_path, session_dir)
            session.wav_path = wav_path
            if self._check_cancel(session_dir):
                return

            # ── Step 2: Video duration ───────────────────────────────────────
            self.signals.progress.emit(10, "Reading video metadata…")
            session.video_duration = get_video_duration(session.video_path)
            if self._check_cancel(session_dir):
                return

            # ── Branch: timeslot mode, fingerprint mode, or spectral fallback ─
            if session.settings.manual_timestamps:
                all_candidates = self._run_timeslot_mode(session, session_dir, wav_path)
            else:
                playlist_ready = (
                    session.playlist_path and session.playlist_path.exists()
                    and session.search_root and session.search_root.exists()
                )
                if playlist_ready:
                    all_candidates = self._run_fingerprint_mode(session, session_dir, wav_path)
                else:
                    all_candidates = self._run_spectral_mode(session, wav_path)

            if all_candidates is None:
                # Sub-method already emitted cancelled; clean up temp dir
                self._cleanup(session_dir)
                return

            # ── Beat-align (skipped for timeslot mode — user specified exact times)
            if not session.settings.manual_timestamps:
                n = len(all_candidates)
                for i, candidate in enumerate(all_candidates):
                    if self._check_cancel(session_dir):
                        return
                    pct = 80 + int((i / max(n, 1)) * 18)
                    self.signals.progress.emit(pct, f"Beat-aligning clip {i + 1} of {n}…")

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

            # ── Store full pool; surface top-N (or all), sorted by timestamp ──
            session.all_candidates = all_candidates  # score order — used by "generate more"
            if session.settings.clip_all or session.settings.manual_timestamps:
                displayed = list(all_candidates)
            else:
                displayed = self._select_top_n(
                    all_candidates, session.settings.n_clips
                )
            displayed.sort(key=lambda c: c.start_time)
            # Re-assign ranks to match chronological display order
            for i, c in enumerate(displayed, 1):
                c.rank = i
            session.candidates = displayed

            self.signals.progress.emit(100, "Analysis complete.")
            self.signals.finished.emit(session)

        except Exception as exc:
            self.signals.error.emit(str(exc))

    # ── Fingerprint mode ─────────────────────────────────────────────────────

    def _run_fingerprint_mode(self, session, session_dir, wav_path):
        """Resolve playlist → build DB → timeline → find ALL transitions."""

        # Resolve playlist tracks
        self.signals.progress.emit(12, "Resolving playlist tracks…")
        found_paths, missing = resolve_playlist(
            session.playlist_path,
            session.search_root,
            progress_callback=lambda cur, tot, name: self.signals.progress.emit(
                12, f"Resolving tracks… {cur + 1}/{tot}"
            ),
        )
        if self.cancel_event.is_set():
            self.signals.cancelled.emit()
            return None

        if not found_paths:
            self.signals.progress.emit(14, "No tracks resolved — falling back to spectral…")
            return self._run_spectral_mode(session, wav_path)

        # Store sorted track names for the review UI's track-correction dropdowns
        session.resolved_track_names = sorted(p.stem for p in found_paths)

        if missing:
            self.signals.progress.emit(
                14, f"Warning: {len(missing)} track(s) not found on disk"
            )

        # Build fingerprint DB
        self.signals.progress.emit(15, f"Building fingerprint index ({len(found_paths)} tracks)…")
        db_path = session_dir / "tracklist.json"
        build_index(found_paths, db_path)
        session.db_path = db_path
        if self.cancel_event.is_set():
            self.signals.cancelled.emit()
            return None

        # Sample timeline across full video
        total_samples = int((session.video_duration - 20.0) / 20.0)
        self.signals.progress.emit(20, f"Scanning audio timeline (~{total_samples} samples)…")

        cancelled_flag = [False]

        def timeline_progress(cur, tot, ts):
            if self.cancel_event.is_set():
                cancelled_flag[0] = True
                return
            pct = 20 + int((cur / max(tot, 1)) * 55)
            self.signals.progress.emit(pct, f"Collecting… {cur}/{tot} crumbs")

        timeline = build_track_timeline(
            wav_path, db_path, session.video_duration,
            progress_callback=timeline_progress,
            cancel_event=self.cancel_event,
        )

        if cancelled_flag[0] or self.cancel_event.is_set():
            self.signals.cancelled.emit()
            return None

        # Find ALL transitions (no n_clips cap — worker slices later)
        self.signals.progress.emit(76, "Detecting transitions…")
        candidates = find_transitions(
            timeline,
            clip_duration=session.settings.clip_duration,
            video_duration=session.video_duration,
        )

        if not candidates:
            self.signals.progress.emit(77, "No transitions found — falling back to spectral…")
            return self._run_spectral_mode(session, wav_path)

        return candidates

    # ── Timeslot mode ─────────────────────────────────────────────────────────

    def _run_timeslot_mode(self, session, session_dir, wav_path):
        """
        Create ClipCandidates at the user-specified timestamps.
        If a playlist is available, run fingerprinting to assign track labels.
        No transition detection or beat alignment is performed.
        """
        timestamps = session.settings.manual_timestamps
        clip_dur = session.settings.clip_duration

        # Build a track timeline if playlist is available, for track ID
        timeline = []
        playlist_ready = (
            session.playlist_path and session.playlist_path.exists()
            and session.search_root and session.search_root.exists()
        )
        if playlist_ready:
            self.signals.progress.emit(12, "Resolving playlist tracks…")
            from dj_clipper.core.playlist_resolver import resolve_playlist
            found_paths, _ = resolve_playlist(
                session.playlist_path,
                session.search_root,
                progress_callback=lambda cur, tot, name: self.signals.progress.emit(
                    12, f"Resolving tracks… {cur + 1}/{tot}"
                ),
            )
            if self._check_cancel(session_dir):
                return None

            if found_paths:
                session.resolved_track_names = sorted(p.stem for p in found_paths)
                self.signals.progress.emit(15, f"Building fingerprint index ({len(found_paths)} tracks)…")
                from dj_clipper.core.fingerprint_db import build_index
                db_path = session_dir / "tracklist.json"
                build_index(found_paths, db_path)
                session.db_path = db_path
                if self._check_cancel(session_dir):
                    return None

                cancelled_flag = [False]
                def timeline_progress(cur, tot, ts):
                    if self.cancel_event.is_set():
                        cancelled_flag[0] = True
                        return
                    pct = 20 + int((cur / max(tot, 1)) * 55)
                    self.signals.progress.emit(pct, f"Collecting… {cur}/{tot} crumbs")

                from dj_clipper.core.transition_finder import build_track_timeline
                timeline = build_track_timeline(
                    wav_path, db_path, session.video_duration,
                    progress_callback=timeline_progress,
                    cancel_event=self.cancel_event,
                )
                if cancelled_flag[0] or self._check_cancel(session_dir):
                    return None

        self.signals.progress.emit(78, "Building timeslot clips…")

        def _track_at(t: float):
            """Return the identified track name closest to timestamp t."""
            if not timeline:
                return None
            best = min(timeline, key=lambda e: abs(e.start - t))
            return best.track if best.confidence >= 0.0 else None

        candidates = []
        for rank, ts in enumerate(timestamps, 1):
            clip_start = max(0.0, ts)
            clip_end = min(clip_start + clip_dur, session.video_duration)
            # Clamp start if clip would overrun
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

    # ── Spectral fallback ────────────────────────────────────────────────────

    def _run_spectral_mode(self, session, wav_path):
        """Librosa spectral features → energy/flux peaks (all peaks, worker slices)."""
        self.signals.progress.emit(20, "Analyzing audio (spectral features)…")
        features = compute_spectral_features(wav_path)
        combined_score = compute_combined_score(features)
        times = features["times"]
        if self.cancel_event.is_set():
            self.signals.cancelled.emit()
            return None

        self.signals.progress.emit(75, "Finding candidate moments…")
        candidates = find_top_moments(
            combined_score=combined_score,
            times=times,
            beat_times=None,
            clip_duration=session.settings.clip_duration,
            n_clips=999,          # get all peaks; worker slices to n_clips later
            video_duration=session.video_duration,
        )
        return candidates

    # ── Track-diversity selection ─────────────────────────────────────────────

    def _select_top_n(self, all_candidates, n_clips: int):
        """
        Pick the top-N candidates by score, but if n_clips is fewer than half the
        total pool, prefer clips that involve tracks not already represented.
        Candidates that can't avoid a duplicate are still included to fill n_clips.
        """
        if n_clips >= len(all_candidates):
            return list(all_candidates[:n_clips])

        # Only apply diversity logic when we're picking a minority of the pool
        if n_clips >= len(all_candidates) / 2:
            return list(all_candidates[:n_clips])

        seen_tracks: set = set()
        primary:  list = []
        spillover: list = []

        for c in all_candidates:   # already sorted by score desc
            involved = {c.pre_track, c.post_track} - {None}
            if not seen_tracks & involved:
                seen_tracks |= involved
                primary.append(c)
            else:
                spillover.append(c)
            if len(primary) >= n_clips:
                break

        # Pad with highest-scoring duplicates if we couldn't fill from unique clips
        if len(primary) < n_clips:
            needed = n_clips - len(primary)
            primary.extend(spillover[:needed])

        return primary[:n_clips]
