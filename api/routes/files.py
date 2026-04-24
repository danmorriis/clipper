import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api import session_store

router = APIRouter(tags=["files"])

_TS_RE = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')


@router.get("/sessions/{session_id}/thumbnails/{rank}")
def get_thumbnail(session_id: str, rank: int):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    candidate = next((c for c in entry.state.candidates if c.rank == rank), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.thumbnail_path or not Path(candidate.thumbnail_path).exists():
        raise HTTPException(status_code=404, detail="Thumbnail not ready")

    return FileResponse(str(candidate.thumbnail_path), media_type="image/jpeg")


@router.get("/video")
def serve_video(path: str):
    """Serve a local video file for the HTML5 player."""
    video_path = Path(path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(video_path), media_type="video/mp4")


@router.post("/validate/video")
def validate_video(body: dict):
    """Run ffprobe to check the video exists and return its duration."""
    video_path = Path(body.get("video_path", ""))
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="File not found")

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="ffprobe not found — install ffmpeg (brew install ffmpeg)")
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail="Not a valid video file")

    try:
        duration = float(result.stdout.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Could not read duration")

    return {"duration_seconds": duration}


@router.post("/validate/timestamps")
def validate_timestamps(body: dict):
    """Parse timestamp text and return valid seconds + error info."""
    import re as _re
    text = body.get("text", "")
    video_duration = float(body.get("video_duration", 0))

    tokens = _re.split(r'[,\n]+', text)
    valid = []
    malformed = []
    out_of_bounds = []

    for raw in tokens:
        t = raw.strip()
        if not t:
            continue
        if not _TS_RE.match(t):
            malformed.append(t)
            continue
        parts = t.split(":")
        if len(parts) == 2:
            seconds = int(parts[0]) * 60 + int(parts[1])
        else:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if seconds >= video_duration:
            out_of_bounds.append(t)
        else:
            valid.append(seconds)

    return {
        "valid": valid,
        "malformed": malformed,
        "out_of_bounds": out_of_bounds,
    }
