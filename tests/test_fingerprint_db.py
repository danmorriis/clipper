from pathlib import Path
import pytest
from dj_clipper.core.fingerprint_db import build_index, query_clip

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_index_creates_db(tmp_path):
    db_path = tmp_path / "test.afpt"
    build_index(FIXTURES, db_path)
    assert db_path.exists()


def test_self_match_confidence(tmp_path):
    """Index all fixtures, query track_a — should self-match with confidence > 0."""
    db_path = tmp_path / "test.afpt"
    build_index(FIXTURES, db_path)

    # Extract WAV from track_a for querying
    import soundfile as sf
    import numpy as np
    from dj_clipper.config import SAMPLE_RATE
    track_a = FIXTURES / "track_a.mp3"
    import librosa
    y, _ = librosa.load(str(track_a), sr=SAMPLE_RATE, mono=True)
    query_wav = tmp_path / "query.wav"
    sf.write(str(query_wav), y, SAMPLE_RATE)

    matches = query_clip(query_wav, db_path)
    assert len(matches) > 0, "Expected at least one match for self-query"
    assert matches[0].confidence > 0.0


def test_no_match_for_empty_audio(tmp_path):
    """Silence should return no confident matches."""
    import soundfile as sf
    import numpy as np
    from dj_clipper.config import SAMPLE_RATE

    db_path = tmp_path / "test.afpt"
    build_index(FIXTURES, db_path)

    silence = np.zeros(SAMPLE_RATE * 5, dtype=np.float32)
    silence_wav = tmp_path / "silence.wav"
    sf.write(str(silence_wav), silence, SAMPLE_RATE)

    matches = query_clip(silence_wav, db_path)
    high_confidence = [m for m in matches if m.confidence >= 0.3]
    assert len(high_confidence) == 0
