import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

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


_MEDIA_TYPES = {
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska',
    '.avi': 'video/x-msvideo',
    '.webm': 'video/webm',
}


@router.get("/video")
def serve_video(path: str, request: Request):
    """Serve a local video file with HTTP Range support so the HTML5 player can seek."""
    video_path = Path(path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if video_path.suffix.lower() not in _MEDIA_TYPES:
        raise HTTPException(status_code=403, detail="File type not permitted")

    file_size = video_path.stat().st_size
    content_type = _MEDIA_TYPES.get(video_path.suffix.lower(), 'video/mp4')
    range_header = request.headers.get('Range')

    if not range_header:
        return FileResponse(str(video_path), media_type=content_type,
                            headers={'Accept-Ranges': 'bytes'})

    match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        raise HTTPException(status_code=416, detail="Invalid Range header")

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else min(start + 1024 * 1024 - 1, file_size - 1)
    end = min(end, file_size - 1)

    if start >= file_size:
        raise HTTPException(status_code=416, detail="Range Not Satisfiable",
                            headers={'Content-Range': f'bytes */{file_size}'})

    length = end - start + 1

    def stream():
        with open(video_path, 'rb') as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        stream(),
        status_code=206,
        media_type=content_type,
        headers={
            'Content-Range': f'bytes {start}-{end}/{file_size}',
            'Accept-Ranges': 'bytes',
            'Content-Length': str(length),
        },
    )


@router.get("/video/frame")
def get_frame(path: str, t: float = 0.0):
    """
    Extract a single video frame at timestamp t (seconds) and return it as JPEG.
    Uses fast keyframe seek so this is typically <200 ms even for large files.
    """
    video_path = Path(path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if video_path.suffix.lower() not in _MEDIA_TYPES:
        raise HTTPException(status_code=403, detail="File type not permitted")

    result = subprocess.run(
        [
            "ffmpeg",
            "-ss", str(max(0.0, t)),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "5",          # JPEG quality (2=best, 31=worst)
            "-f", "image2",
            "-vcodec", "mjpeg",
            "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise HTTPException(status_code=500, detail="Frame extraction failed")

    return Response(
        content=result.stdout,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


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
