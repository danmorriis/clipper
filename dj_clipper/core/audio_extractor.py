import json
import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    pass


def extract_audio(video_path: Path, output_dir: Path) -> Path:
    """Run FFmpeg to produce 16kHz mono WAV. Raises AudioExtractionError on failure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "audio.wav"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ac", "1",
            "-ar", "16000",
            "-vn",
            str(wav_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(result.stderr.decode())
    return wav_path


def extract_audio_segment(source_wav: Path, start_sec: float, duration_sec: float, output_path: Path) -> Path:
    """Cut a short segment from an already-extracted WAV. Used for per-clip beat tracking."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_sec = max(0.0, start_sec)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(source_wav),
            "-t", str(duration_sec),
            "-c", "copy",
            str(output_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(result.stderr.decode())
    return output_path


def stretch_audio(input_wav: Path, output_wav: Path, ratio: float) -> Path:
    """
    Time-stretch a WAV by ratio using FFmpeg atempo (0.5–2.0 range).
    ratio > 1.0 speeds up (higher effective BPM match); ratio < 1.0 slows down.
    Deletes nothing — caller is responsible for cleanup.
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(input_wav),
            "-af", f"atempo={ratio:.4f}",
            str(output_wav),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(result.stderr.decode())
    return output_wav


def get_video_duration(video_path: Path) -> float:
    """ffprobe JSON → format.duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(result.stderr.decode())
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
