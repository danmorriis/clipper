"""
Thumbnail runner — Qt-free version of ThumbnailWorker.

Extracts thumbnails in a background thread, putting thumbnail_ready
events onto a queue.Queue so the SSE stream can forward them.
"""

import queue
import threading

from dj_clipper.config import THUMBNAIL_SEEK_OFFSET
from dj_clipper.core.clip_exporter import extract_thumbnail
from dj_clipper.models.session_model import SessionState


def run_thumbnails(
    session: SessionState,
    cancel_event: threading.Event,
    progress_queue: queue.Queue,
) -> None:
    """Entry point for ThreadPoolExecutor. Updates candidate.thumbnail_path in-place."""
    try:
        thumb_dir = session.session_temp_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        for candidate in session.candidates:
            if cancel_event.is_set():
                progress_queue.put({"cancelled": True, "done": True})
                return

            seek_time = candidate.start_time + THUMBNAIL_SEEK_OFFSET
            thumb_path = thumb_dir / f"thumb_{candidate.rank:03d}.jpg"

            extract_thumbnail(
                video_path=session.video_path,
                time_seconds=seek_time,
                output_path=thumb_path,
            )

            candidate.thumbnail_path = thumb_path
            progress_queue.put({
                "thumbnail_ready": {
                    "rank": candidate.rank,
                    "path": str(thumb_path),
                },
            })

        progress_queue.put({"thumbnails_done": True})

    except Exception as exc:
        progress_queue.put({"error": str(exc)})
