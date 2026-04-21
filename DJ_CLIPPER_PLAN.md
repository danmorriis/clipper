# DJ Clipper — Agent Handoff Document

> **For the implementing agent:** This is a complete, approved plan. Build it exactly as specified. When the user is ready to test, they will provide a sample DJ video and a folder of MP3/AIFF/WAV audio files (the tracks played in the set). Read this entire document before writing any code.

---

## What This Is

A local macOS desktop app that automates extracting social media clips from 1–2 hour DJ footage videos. The user currently spends hours manually scrubbing footage, trimming clips, and identifying tracks. This tool replaces that entire workflow.

**User's workflow after this is built:**
1. Drop DJ video into the app
2. Set clip count (5–20) and duration (30s / 45s / 60s)
3. Click "Find Clips" — app auto-detects the best transition moments
4. Review clips in-app (watch each one, mark keep or bin)
5. Point to folder of audio files (the tracks they played)
6. Click Export → get individual clip MP4s + `tracklist.txt` listing matched tracks per clip

**Key domain knowledge:** Clips must be taken during a DJ mixing transition (when two tracks are being crossfaded together), never during a single clean track. The clip should start ~10 seconds before the transition completes. Audio-based detection only (no visual/camera analysis) for v1.

---

## Tech Stack

| Purpose | Tool | Install |
|---|---|---|
| Audio feature analysis | `librosa` | `pip install librosa` |
| Beat tracking | `madmom` | `pip install cython mido && pip install madmom` |
| Track fingerprinting | `audfprint` | `pip install git+https://github.com/dpwe/audfprint.git` |
| Video I/O (all operations) | `FFmpeg` | `brew install ffmpeg` |
| Desktop UI | `PyQt6` | `pip install PyQt6` |
| Background processing | `QThreadPool + QRunnable` | (part of PyQt6) |
| Testing | `pytest` + `pytest-qt` | `pip install pytest pytest-qt` |

**Critical install notes:**
- Pin `numpy<2.0` (e.g. `numpy==1.26.4`) — madmom uses deprecated NumPy 2.x APIs and will break
- Install `cython` and `mido` BEFORE madmom
- audfprint has no PyPI release — install from GitHub only
- FFmpeg must be on PATH; app checks at startup and shows error dialog if missing

**Startup FFmpeg check (main.py):**
```python
def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
```

---

## Project Structure

```
dj_clipper/
├── main.py                      # QApplication init, FFmpeg check, launch MainWindow
├── config.py                    # App-wide constants (see below)
├── requirements.txt
│
├── core/
│   ├── audio_extractor.py       # FFmpeg: video → 16kHz mono WAV; get_video_duration()
│   ├── transition_detector.py   # librosa: spectral features + combined score array
│   ├── beat_aligner.py          # madmom: beat times; snap_to_nearest_beat()
│   ├── clip_scorer.py           # find_top_moments(): peaks, gap filter, beat-snap
│   ├── clip_exporter.py         # FFmpeg: stream-copy clip; extract_thumbnail()
│   ├── fingerprint_db.py        # audfprint: build_index() from folder; query_clip()
│   └── track_matcher.py         # identify_tracks() per clip; write_tracklist_txt()
│
├── models/
│   ├── clip_model.py            # ClipCandidate + TrackMatch dataclasses
│   └── session_model.py         # SessionState: holds all runtime state for the session
│
├── workers/
│   ├── analysis_worker.py       # QRunnable: full analysis pipeline + progress signals
│   ├── export_worker.py         # QRunnable: export clips + track matching
│   └── thumbnail_worker.py      # QRunnable: extract JPEG thumbnails via FFmpeg
│
├── ui/
│   ├── main_window.py           # QMainWindow + QStackedWidget panel switcher
│   ├── import_panel.py          # Screen 1: drop zone + settings
│   ├── review_panel.py          # Screen 2: clip grid + video player
│   ├── export_panel.py          # Screen 3: tracklist folder + export progress log
│   └── widgets/
│       ├── drop_zone.py         # QLabel subclass, drag-drop, emits video_dropped(Path)
│       ├── clip_card.py         # Thumbnail + keep/bin toggle, emits selected signal
│       ├── video_player.py      # QMediaPlayer + QVideoWidget + scrub slider
│       └── progress_overlay.py  # Modal progress dialog with cancel (threading.Event)
│
└── tests/
    ├── fixtures/                # Small synthetic test MP4 + MP3 files (commit these)
    ├── test_audio_extractor.py
    ├── test_transition_detector.py
    ├── test_beat_aligner.py
    ├── test_clip_scorer.py
    ├── test_fingerprint_db.py
    └── test_track_matcher.py
```

---

## config.py — Constants

```python
import tempfile
from pathlib import Path

SAMPLE_RATE = 16000          # Hz — sufficient for all audio features, 6x smaller than 48kHz stereo
HOP_LENGTH = 512             # librosa default
TEMP_DIR = Path(tempfile.gettempdir()) / "dj_clipper"
MIN_CLIP_GAP_SECONDS = 60    # minimum seconds between selected clip peaks
PRE_TRANSITION_OFFSET = 10.0 # seconds before transition peak = clip start point
MIN_VIDEO_DURATION = 300     # reject videos shorter than 5 minutes
AUDFPRINT_DB_NAME = "tracklist.afpt"
THUMBNAIL_SEEK_OFFSET = 5.0  # seconds into clip to grab thumbnail frame
```

---

## Data Models (models/clip_model.py)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

@dataclass
class TrackMatch:
    track_name: str     # filename without extension
    confidence: float   # audfprint hash hit ratio (0.0–1.0)
    time_offset: float  # seconds into the clip where the match occurs

@dataclass
class ClipCandidate:
    rank: int
    start_time: float            # seconds, beat-aligned
    end_time: float              # start_time + clip_duration
    transition_peak_time: float  # raw detected score peak this clip is anchored to
    score: float                 # 0.0–1.0 combined audio interestingness score
    kept: bool = True            # user's review decision
    thumbnail_path: Optional[Path] = None
    matched_tracks: List[TrackMatch] = field(default_factory=list)
```

---

## Processing Pipeline — Phase A: Analysis

Triggered when user clicks "Find Clips". Runs in `AnalysisWorker` (QRunnable).

```
video.mp4
  │
  ▼
audio_extractor.extract_audio(video_path, output_dir) → audio.wav
  FFmpeg: ffmpeg -i video.mp4 -ac 1 -ar 16000 -vn audio.wav -y
  Also: get_video_duration() via ffprobe JSON output
  │
  ▼
transition_detector.compute_spectral_features(wav_path) → dict
  librosa.feature.rms()                    → rms envelope
  librosa.onset.onset_strength()           → spectral flux (onset strength envelope)
  librosa.feature.spectral_centroid()      → centroid
  librosa.times_like()                     → times array
  │
  ▼
transition_detector.compute_combined_score(features) → np.ndarray
  Normalize each feature to [0,1] via (x - min) / (max - min)
  Compute rolling-window variance of rms and centroid (window ≈ 2s)
    → high variance = two tracks competing = transition zone
  score = 0.5 * flux_norm + 0.3 * rms_variance_norm + 0.2 * centroid_variance_norm
  │
  ▼
beat_aligner.get_beat_times(wav_path) → np.ndarray of beat times in seconds
  madmom: RNNBeatProcessor()(wav_path) → activations
          DBNBeatTrackingProcessor(fps=100)(activations) → beat_times
  │
  ▼
clip_scorer.find_top_moments(score, times, beat_times, clip_duration, n_clips) → List[ClipCandidate]
  1. scipy.signal.argrelmax(score, order=50) → local peak indices
  2. Sort peaks by score descending
  3. Greedy selection: skip peaks within MIN_CLIP_GAP_SECONDS of already-selected peaks
  4. For each selected peak at time T:
       raw_start = T - PRE_TRANSITION_OFFSET
       start = snap_to_nearest_beat(raw_start, beat_times)
       start = max(0.0, start)
       end = start + clip_duration
       skip if end > video_duration
  5. Re-sort selected candidates chronologically, assign rank
  │
  ▼
thumbnail_worker: for each candidate, extract frame at start + THUMBNAIL_SEEK_OFFSET
  FFmpeg: ffmpeg -ss {time} -i video.mp4 -vframes 1 -vf scale=320:-1 thumb_{n}.jpg -y
```

---

## Processing Pipeline — Phase B: Export

Triggered when user clicks "Export Clips + Identify Tracks". Runs in `ExportWorker` (QRunnable).

```
For each kept ClipCandidate:
  │
  ▼
clip_exporter.export_clip(video_path, candidate, output_dir, index) → clip_NNN.mp4
  FFmpeg: ffmpeg -ss {start} -i video.mp4 -t {duration} -c copy -avoid_negative_ts 1 clip_{n:03d}.mp4 -y
  NOTE: -c copy = stream copy, no re-encode → near-instant. May be off <1 frame at boundaries (acceptable).
  │
  ▼ (if tracklist_dir provided)
fingerprint_db.build_index(tracklist_dir, db_path) → tracklist.afpt   [ONCE, cached]
  For each MP3/WAV/FLAC/AIFF in tracklist_dir:
    subprocess: python -m audfprint add --dbase {db_path} {track_file}
  Cache: re-index only if tracklist_dir path changes OR file count/mtime changes
  NOTE: indexing ~50 tracks takes ~8 minutes first time. This is expected and normal.
  │
  ▼
track_matcher.identify_tracks(clip_path, db_path) → List[TrackMatch]
  1. Extract WAV from clip (reuse audio_extractor.extract_audio)
  2. subprocess: python -m audfprint match --dbase {db_path} {clip_wav}
  3. Parse stdout for match lines
  4. Filter to confidence >= 0.1
  5. Return sorted by confidence desc (expect 1–2 matches during active mixing)
  │
  ▼
track_matcher.write_tracklist_txt(output_dir, results) → tracklist.txt
  Format:
    clip_001.mp4
      Track: "Artist Name - Song Title"  (confidence: 0.87)
      Track: "Artist Name - Song Title"  (confidence: 0.61)

    clip_002.mp4
      Track: "Artist Name - Song Title"  (confidence: 0.93)
```

---

## UI — Screen 1: Import Panel

```
┌──────────────────────────────────────────────┐
│  DJ Clipper                                  │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │                                      │   │
│  │       Drop DJ video here             │   │
│  │       (or click to browse)           │   │
│  │                                      │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  Clip Duration:   [30s]  [45s]  [60s]       │
│                   (QButtonGroup, exclusive)  │
│                                              │
│  Number of Clips:  ────O────  5 ──── 20     │
│                    (QSlider, int, label)     │
│                                              │
│  [      Find Clips      ]                   │
│  (QPushButton, disabled until video dropped) │
└──────────────────────────────────────────────┘
```

- `DropZone(QLabel)`: override `dragEnterEvent`, `dropEvent` → emit `video_dropped(Path)`
- On "Find Clips": read settings from widgets → build `SessionState` → launch `AnalysisWorker` via `QThreadPool.globalInstance().start(worker)` → show `ProgressOverlay`
- `ProgressOverlay`: modal `QDialog` with `QProgressBar`, status label, Cancel button → cancel sets a `threading.Event` that workers check between steps

---

## UI — Screen 2: Review Panel

```
┌────────────────────────┬──────────────────────────────┐
│  ← Back                │                [Export →]   │
├────────────────────────┤                              │
│  Clips (12 found)      │  ┌────────────────────────┐ │
│                        │  │                        │ │
│  ┌──────┐  ┌──────┐    │  │    QVideoWidget        │ │
│  │  1   │  │  2   │    │  │                        │ │
│  │      │  │      │    │  └────────────────────────┘ │
│  │ [K]  │  │ [B]  │    │  [▶]  [■]   00:14 / 00:30  │
│  └──────┘  └──────┘    │  ─────O──────────────────── │
│  ┌──────┐  ┌──────┐    │  (QSlider for scrubbing)    │
│  │  3   │  │  4   │    │                              │
│  │      │  │      │    │  Clip 3  —  @ 00:47:12      │
│  │ [K]  │  │ [K]  │    │  Score: 0.84                │
│  └──────┘  └──────┘    │                              │
│  ...                   │                              │
│  [Keep All] [Bin All]  │                              │
└────────────────────────┴──────────────────────────────┘
```

- Left: `QScrollArea` containing a flow layout of `ClipCard` widgets
- `ClipCard(QFrame)`: thumbnail (`QLabel` with `QPixmap`), clip number, keep/bin toggle (`QPushButton` styled green/red), score badge; emits `selected(ClipCandidate)` signal on click
- Right: `VideoPlayer` widget; clicking a `ClipCard` loads that clip's time range via `QMediaPlayer.setSource()` and `QMediaPlayer.setPosition()`
- "Export" button disabled until ≥1 clip is marked kept
- "← Back" returns to Screen 1 (asks confirmation if analysis would be lost)

---

## UI — Screen 3: Export Panel

```
┌──────────────────────────────────────────────┐
│  ← Back     Export                           │
│                                              │
│  Output folder:                              │
│  [~/Desktop/DJ_Clips_2026-04-21]  [Browse]  │
│                                              │
│  Tracklist folder (optional):                │
│  [Not set — track ID will be skipped] [Browse] │
│                                              │
│  [  Export Clips + Identify Tracks  ]        │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ Progress log (QTextEdit, read-only)  │   │
│  │ [✓] Exported clip_001.mp4            │   │
│  │ [✓] Matched: Artist – Track Name     │   │
│  │ [ ] Exporting clip_002.mp4...        │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  [  Open Output Folder  ]  ← appears when done │
└──────────────────────────────────────────────┘
```

- Default output dir: `~/Desktop/DJ_Clips_{YYYY-MM-DD}`
- "Open Output Folder": `subprocess.run(["open", str(output_dir)])`
- If tracklist folder not set: skip fingerprinting, export clips only
- Progress log lines appended as `ExportWorker` emits `clip_done` signals

---

## Worker Signals Pattern

All workers follow this pattern (PyQt6 requires signals on a QObject, not QRunnable):

```python
class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)   # percent, status message
    finished = pyqtSignal(object)     # result payload
    error = pyqtSignal(str)           # error message

class AnalysisWorker(QRunnable):
    def __init__(self, video_path, settings, cancel_event):
        super().__init__()
        self.signals = WorkerSignals()
        self.video_path = video_path
        self.settings = settings
        self.cancel_event = cancel_event  # threading.Event

    def run(self):
        try:
            # Step 1
            self.signals.progress.emit(10, "Extracting audio...")
            wav = extract_audio(self.video_path, TEMP_DIR / session_id)
            if self.cancel_event.is_set(): return

            # Step 2
            self.signals.progress.emit(30, "Analyzing audio...")
            features = compute_spectral_features(wav)
            if self.cancel_event.is_set(): return

            # ... etc through all steps ...

            self.signals.finished.emit(candidates)
        except Exception as e:
            self.signals.error.emit(str(e))
```

`ExportWorker` emits an additional `clip_done = pyqtSignal(int, str, list)` signal (clip_index, clip_path, List[TrackMatch]) so the UI can update the progress log per clip.

---

## Core Function Signatures

### core/audio_extractor.py
```python
def extract_audio(video_path: Path, output_dir: Path) -> Path:
    """Run FFmpeg to produce 16kHz mono WAV. Raises AudioExtractionError on failure."""

def get_video_duration(video_path: Path) -> float:
    """ffprobe JSON → format.duration in seconds."""
```

### core/transition_detector.py
```python
def compute_spectral_features(wav_path: Path, sr: int = SAMPLE_RATE) -> dict:
    """Returns {'rms', 'flux', 'centroid', 'times'} as np.ndarrays."""

def compute_combined_score(features: dict, window_seconds: float = 2.0) -> np.ndarray:
    """Weighted combination of normalized spectral features. Returns score in [0,1]."""
```

### core/beat_aligner.py
```python
def get_beat_times(wav_path: Path) -> np.ndarray:
    """madmom RNNBeatProcessor + DBNBeatTrackingProcessor → beat times in seconds."""

def snap_to_nearest_beat(time_seconds: float, beat_times: np.ndarray) -> float:
    """np.argmin(np.abs(beat_times - time_seconds)) → nearest beat time."""
```

### core/clip_scorer.py
```python
def find_top_moments(
    combined_score: np.ndarray,
    times: np.ndarray,
    beat_times: np.ndarray,
    clip_duration: float,
    n_clips: int,
    video_duration: float,
    min_gap: float = MIN_CLIP_GAP_SECONDS,
    pre_offset: float = PRE_TRANSITION_OFFSET,
) -> List[ClipCandidate]:
```

### core/clip_exporter.py
```python
def export_clip(video_path: Path, candidate: ClipCandidate, output_dir: Path, index: int) -> Path:
    """FFmpeg stream copy. Returns output path."""

def extract_thumbnail(video_path: Path, time_seconds: float, output_path: Path, width: int = 320) -> Path:
    """FFmpeg single-frame extract."""
```

### core/fingerprint_db.py
```python
def build_index(tracklist_dir: Path, db_path: Path, progress_callback=None) -> Path:
    """Index all MP3/WAV/FLAC/AIFF files via audfprint subprocess. Returns db_path."""

def query_clip(clip_wav_path: Path, db_path: Path) -> List[TrackMatch]:
    """Query audfprint, parse stdout, return matches."""
```

### core/track_matcher.py
```python
def identify_tracks(clip_path: Path, db_path: Path, min_confidence: float = 0.1) -> List[TrackMatch]:
    """Extract audio from clip → query fingerprint DB → return sorted matches."""

def write_tracklist_txt(output_dir: Path, results: List[Tuple[ClipCandidate, List[TrackMatch]]]) -> Path:
    """Write human-readable tracklist.txt. Returns path."""
```

---

## Implementation Order

Build and test each phase before starting the next. Each phase is independently runnable.

### Phase 1 — Core Audio Pipeline (no UI, run as scripts)
1. `config.py`
2. `core/audio_extractor.py` → test: verify WAV output is 16kHz mono, duration correct
3. `core/transition_detector.py` → test: print score stats, optionally plot with matplotlib
4. `core/beat_aligner.py` → test: print first 20 beats, verify ~0.5s spacing at 120 BPM
5. `models/clip_model.py` + `core/clip_scorer.py` → test: synthetic score array, verify top-N selection and gap enforcement

### Phase 2 — Export Pipeline
6. `core/clip_exporter.py` → test: export a 30s clip, verify in QuickTime
7. `core/fingerprint_db.py` → test: index 5 files, query one → confirm self-match > 0.3 confidence
8. `core/track_matcher.py` → integration test with real clip against real DB

### Phase 3 — Workers
9. `models/session_model.py`
10. `workers/analysis_worker.py` → test in minimal QApplication, verify signals fire
11. `workers/export_worker.py` → same
12. `workers/thumbnail_worker.py`

### Phase 4 — UI Panels (in dependency order)
13. `ui/widgets/drop_zone.py`
14. `ui/widgets/video_player.py`
15. `ui/import_panel.py`
16. `ui/widgets/clip_card.py`
17. `ui/review_panel.py`
18. `ui/export_panel.py`
19. `ui/main_window.py` — wire everything together with QStackedWidget

### Phase 5 — Integration & Hardening
20. End-to-end smoke test with real footage
21. Error handling: FFmpeg missing, video too short, no fingerprint matches, user cancels
22. Temp cleanup: `atexit.register(shutil.rmtree, session_dir, ignore_errors=True)`

---

## Testing Approach

### Unit Tests
Each test file uses small synthetic fixtures in `tests/fixtures/` (commit a 10s MP4 and 3 short MP3s — do not commit large files).

| File | What to test |
|---|---|
| `test_audio_extractor.py` | WAV output is 16kHz mono; duration within 0.1s of known value |
| `test_transition_detector.py` | Synthesize two overlapping sine waves at different freqs → assert score peak falls in overlap region ±2s |
| `test_beat_aligner.py` | Synthesize 120 BPM click track → assert mean beat spacing ≈ 0.5s ±0.02 |
| `test_clip_scorer.py` | Synthetic peaks at t=120,300,450 → assert top-2 with min_gap=60 are non-overlapping and beat-aligned |
| `test_fingerprint_db.py` | Index 3 fixtures → query each → self-match confidence > 0.3; silence query → empty result |
| `test_track_matcher.py` | Real clip from known position → assert matched track name = expected |

### Integration Test with Real Sample Data
The user has provided:
- A DJ video file (in project directory)
- An AIFF audio file (sample track, in project directory)

**Steps:**
1. Add `if __name__ == "__main__":` block to `transition_detector.py` — print top-10 candidate timestamps → user manually scrubs video to verify they're during mixing transitions
2. Export 5–10 clips, watch each — verify clips start during active mixing (not a clean solo track) and feel musically aligned
3. Index the AIFF + any other tracks → query clips → verify track names match what was actually played
4. Full UI flow end-to-end

### Performance Expectations (2-hour video, Apple Silicon M-series)
| Step | Expected time |
|---|---|
| Audio extraction (FFmpeg) | < 30s |
| Librosa spectral analysis | 1–2 min |
| Madmom beat tracking | 3–5 min (neural network, CPU-bound — this is normal) |
| Thumbnail extraction | < 5s per clip |
| audfprint indexing 50 tracks | ~8 min first time (cached after) |
| audfprint query per clip | 5–15s |
| Clip export (stream copy) | < 2s per clip |

---

## requirements.txt

```
librosa==0.10.2
soundfile==0.12.1
numpy==1.26.4
scipy==1.13.0
madmom==0.16.1
PyQt6==6.7.0
PyQt6-Qt6==6.7.0
PyQt6-sip==13.6.0
tqdm==4.66.4
pytest==8.2.0
pytest-qt==4.4.0
```

Plus install separately (not on PyPI):
```bash
brew install ffmpeg
pip install cython mido
pip install git+https://github.com/dpwe/audfprint.git
```

---

## Key Design Decisions (reasoning preserved for agent)

| Decision | Rationale |
|---|---|
| FFmpeg via subprocess (not PyAV) | Simpler, `-c copy` stream copy avoids re-encoding entirely |
| audfprint via subprocess (not import) | No clean importable public API; CLI is the intended interface |
| 16kHz mono WAV for analysis | Sufficient for all audio features; 6x smaller than 48kHz stereo |
| madmom over librosa for beats | librosa beat tracking degrades on DJ mixes (complex rhythmic content); madmom RNN is significantly more robust |
| QStackedWidget for panels | Three discrete screens, idiomatic PyQt6 — no widget creation/destruction on each switch |
| QThreadPool + QRunnable | Lighter than QThread subclasses; pool manages concurrency; recommended PyQt6 pattern for background tasks |
| Signals via QObject helper on QRunnable | PyQt6 requires signals to live on a QObject; QRunnable isn't one — use a WorkerSignals(QObject) stored on the worker |
| Stream copy on export | No re-encode = near-instant; boundary may be <1 frame off at non-keyframe cuts; acceptable for social clips |
| Audfprint DB cached per session | Re-index only on tracklist folder change (check mtime + file count); 50-track index takes ~8 min |
| MediaPipe visual detection | Deferred to v2 — audio transitions are the primary and sufficient signal |
| numpy pinned < 2.0 | madmom uses deprecated NumPy APIs; will crash on NumPy 2.x |
