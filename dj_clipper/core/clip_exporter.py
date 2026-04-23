import subprocess
from pathlib import Path

from dj_clipper.models.clip_model import ClipCandidate


class ExportError(Exception):
    pass


def export_clip(video_path: Path, candidate: ClipCandidate, output_dir: Path, index: int) -> Path:
    """
    Export a clip using fast input-seeking + re-encode for frame-accurate duration.

    Stream copy (-c copy) cuts at keyframe boundaries, producing clips that are
    seconds longer or shorter than requested.  Re-encoding with ultrafast preset
    is slower but guarantees the output matches start_time → end_time exactly.
    setpts/asetpts reset timestamps so the clip starts at 0:00.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"clip_{index:03d}.mp4"
    duration = candidate.end_time - candidate.start_time
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss",      str(candidate.start_time),
            "-i",       str(video_path),
            "-t",       str(duration),
            "-vf",      "setpts=PTS-STARTPTS",
            "-af",      "asetpts=PTS-STARTPTS",
            "-c:v",     "libx264",
            "-preset",  "ultrafast",
            "-c:a",     "aac",
            "-movflags", "+faststart",
            str(output_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise ExportError(result.stderr.decode())
    return output_path


def extract_thumbnail(video_path: Path, time_seconds: float, output_path: Path, width: int = 320) -> Path:
    """FFmpeg single-frame extract."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(time_seconds),
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            str(output_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise ExportError(result.stderr.decode())
    return output_path
