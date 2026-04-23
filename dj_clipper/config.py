import tempfile
from pathlib import Path

SAMPLE_RATE = 16000          # Hz — sufficient for all audio features, 6x smaller than 48kHz stereo
HOP_LENGTH = 512             # librosa default
TEMP_DIR = Path(tempfile.gettempdir()) / "dj_clipper"
MIN_CLIP_GAP_SECONDS = 60    # minimum seconds between selected clip peaks
PRE_TRANSITION_OFFSET = 10.0 # seconds before transition peak = clip start point
MIN_VIDEO_DURATION = 300     # reject videos shorter than 5 minutes
THUMBNAIL_SEEK_OFFSET = 5.0  # seconds into clip to grab thumbnail frame
