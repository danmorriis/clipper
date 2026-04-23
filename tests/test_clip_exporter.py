from pathlib import Path
from dj_clipper.core.clip_exporter import export_clip, extract_thumbnail
from dj_clipper.models.clip_model import ClipCandidate

FIXTURE_VIDEO = Path(__file__).parent / "fixtures" / "test_video.mp4"


def _make_candidate(start=1.0, duration=5.0) -> ClipCandidate:
    return ClipCandidate(
        rank=1,
        start_time=start,
        end_time=start + duration,
        transition_peak_time=start + 2.0,
        score=0.9,
    )


def test_export_clip_creates_file(tmp_path):
    candidate = _make_candidate(start=1.0, duration=5.0)
    out = export_clip(FIXTURE_VIDEO, candidate, tmp_path, index=1)
    assert out.exists()
    assert out.name == "clip_001.mp4"


def test_export_clip_zero_padded_index(tmp_path):
    candidate = _make_candidate()
    out = export_clip(FIXTURE_VIDEO, candidate, tmp_path, index=12)
    assert out.name == "clip_012.mp4"


def test_extract_thumbnail_creates_jpeg(tmp_path):
    thumb_path = tmp_path / "thumb_001.jpg"
    out = extract_thumbnail(FIXTURE_VIDEO, time_seconds=2.0, output_path=thumb_path)
    assert out.exists()
    assert out.stat().st_size > 0
