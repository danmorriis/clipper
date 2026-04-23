from pathlib import Path
import soundfile as sf
from dj_clipper.core.audio_extractor import extract_audio, get_video_duration

FIXTURE_VIDEO = Path(__file__).parent / "fixtures" / "test_video.mp4"
KNOWN_DURATION = 10.0


def test_extract_audio_creates_wav(tmp_path):
    wav = extract_audio(FIXTURE_VIDEO, tmp_path)
    assert wav.exists()
    assert wav.suffix == ".wav"


def test_extract_audio_is_16khz_mono(tmp_path):
    wav = extract_audio(FIXTURE_VIDEO, tmp_path)
    info = sf.info(str(wav))
    assert info.samplerate == 16000
    assert info.channels == 1


def test_extract_audio_duration_correct(tmp_path):
    wav = extract_audio(FIXTURE_VIDEO, tmp_path)
    info = sf.info(str(wav))
    duration = info.frames / info.samplerate
    assert abs(duration - KNOWN_DURATION) < 0.1


def test_get_video_duration():
    duration = get_video_duration(FIXTURE_VIDEO)
    assert abs(duration - KNOWN_DURATION) < 0.1
