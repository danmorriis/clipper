import threading
from pathlib import Path
from typing import List

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from dj_clipper.config import THUMBNAIL_SEEK_OFFSET
from dj_clipper.core.clip_exporter import extract_thumbnail
from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.models.session_model import SessionState


class WorkerSignals(QObject):
    thumbnail_ready = pyqtSignal(int, str)  # candidate rank, thumbnail_path_str
    finished = pyqtSignal()
    error = pyqtSignal(str)


class ThumbnailWorker(QRunnable):
    """
    Extracts JPEG thumbnails for each ClipCandidate in a background thread.

    Emits thumbnail_ready(rank, path) for each clip so the UI can update
    cards incrementally without waiting for all thumbnails to finish.
    """

    def __init__(
        self,
        session: SessionState,
        cancel_event: threading.Event,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self.session = session
        self.cancel_event = cancel_event

    def run(self) -> None:
        try:
            session = self.session
            thumb_dir = session.session_temp_dir / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)

            for candidate in session.candidates:
                if self.cancel_event.is_set():
                    return

                seek_time = candidate.start_time + THUMBNAIL_SEEK_OFFSET
                thumb_path = thumb_dir / f"thumb_{candidate.rank:03d}.jpg"

                extract_thumbnail(
                    video_path=session.video_path,
                    time_seconds=seek_time,
                    output_path=thumb_path,
                )

                candidate.thumbnail_path = thumb_path
                self.signals.thumbnail_ready.emit(candidate.rank, str(thumb_path))

            self.signals.finished.emit()

        except Exception as exc:
            self.signals.error.emit(str(exc))
