# DJ Clipper — React/Electron Frontend Migration Plan

## Context

DJ Clipper is a working PyQt6 macOS desktop app. The Python backend (audio extraction, fingerprinting, beat alignment, export) is fully decoupled from the UI layer via worker threads and a clean `SessionState` data model. The goal is to replace the PyQt6 UI with a React/Electron frontend — keeping every piece of functionality and the full user journey identical — to get a more polished, maintainable, and distributable app.

No Python backend logic changes. No user journey changes. UI layer only.

Target distribution: macOS `.dmg` and Windows `.exe`.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Electron App                       │
│                                                     │
│  ┌─────────────┐     HTTP/SSE      ┌─────────────┐ │
│  │  React UI   │ ◄──────────────► │  FastAPI    │ │
│  │  (renderer) │                   │  (Python)   │ │
│  └─────────────┘                   └──────┬──────┘ │
│  Electron main                            │        │
│  - spawns Python                    existing       │
│  - native file dialogs              workers &      │
│  - app lifecycle                    core modules   │
└─────────────────────────────────────────────────────┘
```

**Key decisions:**
- **FastAPI + uvicorn** on `localhost:PORT` (random port): cleanest separation, standard HTTP tooling
- **SSE (Server-Sent Events)** for progress streaming: simpler than WebSockets for one-directional worker progress
- **Electron main process** spawns the Python process on startup, kills it on quit
- **HTML5 `<video>`** for clip playback (replaces QMediaPlayer)
- **Custom SVG TrimBar** mirroring the Python `_t_to_x`/`_x_to_t` coordinate math exactly
- **Vite + React + TypeScript + Tailwind CSS** for the frontend

---

## What Gets Replaced vs. Kept

| Layer | Current | New |
|---|---|---|
| Screens & navigation | PyQt6 QStackedWidget | React Router (3 routes) |
| Video player | QMediaPlayer + QVideoWidget | `<video>` element |
| Trim bar | QPainter custom widget | SVG React component |
| File drop zones | QDropEvent | HTML drag-drop + Electron dialog |
| Progress overlay | QDialog (modal) | React modal component |
| Clip card grid | QGridLayout + QFrame | CSS grid + React cards |
| Sliding toggle | Custom QPainter | CSS animated pill |
| Worker threads | QRunnable + QThreadPool | FastAPI BackgroundTasks + ThreadPoolExecutor |
| Progress signals | Qt pyqtSignal | SSE stream |
| QSettings persistence | QSettings | JSON file via FastAPI `/persist/` routes |
| App entry point | `main.py` (QApplication) | `electron/main.ts` (spawns Python) |
| **All core modules** | **unchanged** | **unchanged** |
| **All worker logic** | **unchanged** | **unchanged** |
| **All data models** | **unchanged** | **unchanged** |

---

## Phase 1 — Python API Layer ✅

Wraps existing workers in a FastAPI app. The PyQt6 app continues to work in parallel.

**Files created:**
- `api/main.py` — FastAPI app, CORS, startup/shutdown
- `api/models.py` — Pydantic schemas
- `api/session_store.py` — in-memory dict of active sessions
- `api/runners/analysis.py` — Qt-free analysis runner
- `api/runners/export.py` — Qt-free export runner
- `api/runners/thumbnail.py` — Qt-free thumbnail runner
- `api/routes/sessions.py` — session CRUD
- `api/routes/analysis.py` — trigger analysis, SSE stream
- `api/routes/candidates.py` — list/patch/add candidates
- `api/routes/export.py` — trigger export, SSE stream
- `api/routes/files.py` — serve thumbnails, video, validation
- `api/routes/persist.py` — search-root persistence

**Key endpoints:**
```
POST   /sessions                         create session
GET    /sessions/{id}                    full session state
POST   /sessions/{id}/analyze            start analysis
GET    /sessions/{id}/analyze/stream     SSE progress
POST   /sessions/{id}/analyze/cancel     cancel
GET    /sessions/{id}/candidates         list candidates
PATCH  /sessions/{id}/candidates/{rank}  update kept/tracks/trim
POST   /sessions/{id}/candidates         add manual clip
POST   /sessions/{id}/generate-more      surface more from pool
GET    /sessions/{id}/thumbnails/{rank}  serve JPEG thumbnail
GET    /video?path=…                     serve video for HTML5
POST   /sessions/{id}/export             start export
GET    /sessions/{id}/export/stream      SSE progress
POST   /sessions/{id}/export/cancel      cancel
POST   /validate/video                   ffprobe check
POST   /validate/timestamps              parse + validate
GET    /persist/search-root              read saved music folder
PUT    /persist/search-root              save music folder
GET    /healthz                          readiness probe
```

**Test Phase 1:**
```bash
cd clipper
uvicorn api.main:app --reload --port 9001
# Then use curl or Postman to create a session and trigger analysis
```

---

## Phase 2 — Electron Shell ✅

**Files created:**
- `electron/main.ts` — main process (spawns Python, native dialogs, IPC)
- `electron/preload.ts` — contextBridge API exposed to renderer
- `electron/pythonManager.ts` — spawn/kill Python, wait for readiness

**`window.electronAPI` interface:**
```typescript
openFileDialog(options): Promise<string[]>
openFolderDialog(): Promise<string | null>
openFolder(path: string): void
getApiBase(): Promise<string>     // "http://127.0.0.1:PORT"
platform(): string
```

---

## Phase 3 — React Import Screen ✅

Drop video + playlist, pick settings, run analysis with SSE progress modal.

**Files:** `src/screens/ImportScreen.tsx`, `src/components/DropZone.tsx`, `src/components/ModeToggle.tsx`, `src/components/ProgressModal.tsx`, `src/hooks/useSSE.ts`

---

## Phase 4 — React Review Screen ✅

Clip grid + video player + SVG trim bar.

**Files:** `src/screens/ReviewScreen.tsx`, `src/components/ClipCard.tsx`, `src/components/ClipGrid.tsx`, `src/components/VideoPlayer.tsx`, `src/components/TrimBar.tsx`, `src/components/TrackEditModal.tsx`, `src/components/ManualClipModal.tsx`, `src/hooks/useVideoPlayer.ts`, `src/hooks/useTrimBar.ts`

---

## Phase 5 — React Export Screen ✅

Output folder picker, export trigger, real-time log, open-in-Finder/Explorer.

**Files:** `src/screens/ExportScreen.tsx`

---

## Phase 6 — Cross-platform Fixes ✅

Four known issues must be resolved before the app works correctly on Windows and packages cleanly on both platforms. None touch the Python core.

### 6a. Replace `uvicorn[standard]` with plain `uvicorn`

`uvicorn[standard]` pulls in `uvloop`, which is Unix-only and will fail on Windows.

**Fix:** Change `api/requirements.txt`:
```
# Before
uvicorn[standard]==0.29.0
# After
uvicorn==0.29.0
```
Also update the dev install instructions in the Getting Started section below.
Plain uvicorn uses asyncio on all platforms — performance difference is negligible for this use case.

### 6b. Fix PyInstaller binary path for Windows

`electron/pythonManager.ts` hardcodes the binary name without `.exe`, so the packaged app will fail to launch the API on Windows.

**Fix in `electron/pythonManager.ts`** (prod branch of `startPython`):
```typescript
const ext = process.platform === 'win32' ? '.exe' : ''
const bin = path.join(process.resourcesPath, `dj_clipper_api${ext}`)
```

### 6c. Make title bar cross-platform

`electron/main.ts` uses `titleBarStyle: 'hiddenInset'`, which is macOS-only. On Windows it has no effect but the `drag-region` spacer div looks wrong (it wastes 32px with no custom title bar to justify it).

**Fix in `electron/main.ts`**:
```typescript
const isMac = process.platform === 'darwin'
mainWindow = new BrowserWindow({
  // ...
  titleBarStyle: isMac ? 'hiddenInset' : 'default',
  // ...
})
```
And in each screen, conditionally render the drag-region div:
```tsx
{window.electronAPI?.platform() === 'darwin' && (
  <div className="drag-region h-8 shrink-0" />
)}
```

### 6d. Bundle ffmpeg, ffprobe, and fpcalc — wire up PATH

The packaged app has no guarantee that `ffmpeg`, `ffprobe`, or `fpcalc` are on the user's PATH. They must be bundled in `resources/bin/` and prepended to `process.env.PATH` before spawning the Python process.

**Steps:**
1. Download platform binaries:
   - macOS: `ffmpeg`, `ffprobe` (static build from evermeet.cx or ffmpeg.org), `fpcalc` (from acoustid.org)
   - Windows: `ffmpeg.exe`, `ffprobe.exe`, `fpcalc.exe` (from gyan.dev or acoustid.org)
2. Place in `resources/bin/mac/` and `resources/bin/win/` (gitignored — large binaries)
3. Add to `electron-builder.yml` extraResources
4. **Fix in `electron/pythonManager.ts`**, at the top of `startPython()`:
```typescript
if (app.isPackaged) {
  const binDir = path.join(process.resourcesPath, 'bin',
    process.platform === 'darwin' ? 'mac' : 'win')
  process.env.PATH = `${binDir}${path.delimiter}${process.env.PATH}`
}
```

---

## Phase 7 — Packaging ✅

Do Phase 6 first. Then:

### Python side — PyInstaller

Use `--onedir` (not `--onefile`) for faster startup. `--onefile` self-extracts on every launch, adding ~2–3s cold-start latency. `--onedir` extracts once at install time.

librosa has many dynamic imports PyInstaller misses. Use the `.spec` file below rather than the CLI directly.

**`dj_clipper_api.spec`** (create this file):
```python
# pyinstaller dj_clipper_api.spec
a = Analysis(
    ['api/main.py'],
    pathex=['.'],
    datas=[('dj_clipper', 'dj_clipper')],
    hiddenimports=[
        'librosa', 'librosa.core', 'librosa.feature', 'librosa.effects',
        'librosa.util', 'librosa.filters', 'librosa.onset',
        'scipy.signal', 'scipy.fft', 'scipy.ndimage',
        'sklearn.utils._cython_blas', 'sklearn.neighbors._partition_nodes',
        'soundfile', 'numpy', 'resampy', 'numba', 'llvmlite',
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.asyncio',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.h11_impl',
        'fastapi', 'starlette', 'sse_starlette',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name='dj_clipper_api',
          console=False)  # console=True for debugging
coll = COLLECT(exe, a.binaries, a.datas, name='dj_clipper_api')
```

Build commands:
```bash
# macOS (run on a Mac)
pyinstaller dj_clipper_api.spec
# Output: dist/dj_clipper_api/ (directory)

# Windows (run on Windows — PyInstaller cannot cross-compile)
pyinstaller dj_clipper_api.spec
```

Update `electron-builder.yml` to use `--onedir` output:
```yaml
extraResources:
  - from: dist/dj_clipper_api   # directory, not single file
    to: dj_clipper_api
  - from: resources/bin         # ffmpeg/fpcalc platform binaries
    to: bin
```

Update `electron/pythonManager.ts` prod launch command:
```typescript
// onedir: binary is inside the directory
const binName = process.platform === 'win32' ? 'dj_clipper_api.exe' : 'dj_clipper_api'
const bin = path.join(process.resourcesPath, 'dj_clipper_api', binName)
```

### Electron side

```bash
# macOS
npm run dist
# Produces: release/DJ Clipper-1.0.0.dmg

# Windows (run on Windows, or use electron-builder's --win flag on CI)
npm run dist -- --win
# Produces: release/DJ Clipper Setup 1.0.0.exe
```

### Code signing (required for distribution to end users)

**macOS:**
- Need Apple Developer account ($99/yr)
- Set env vars `CSC_LINK` (p12 cert), `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`
- electron-builder handles signing + notarization automatically when these are set
- Without this: Gatekeeper blocks the app on any Mac that hasn't explicitly allowed it

**Windows:**
- EV code signing cert (~$300–500/yr from DigiCert, Sectigo, etc.)
- Without it: SmartScreen shows "Windows protected your PC" warning on first launch (users can click "Run anyway" — annoying but not a hard block)
- Set `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD` for electron-builder

### CI recommendation (GitHub Actions)

Build on the target platform — PyInstaller and electron-builder cannot cross-compile.
- macOS build: `macos-latest` runner → produces `.dmg`
- Windows build: `windows-latest` runner → produces `.exe`

---

## Getting Started (dev)

```bash
# Python API deps (note: plain uvicorn, not uvicorn[standard])
pip install fastapi uvicorn==0.29.0 sse-starlette pydantic aiofiles

# Node deps
npm install

# Run in dev mode (Vite + Electron + Python API all together)
npm run dev
```

> Without Electron, run Vite and the API separately:
> ```bash
> uvicorn api.main:app --reload --port 9001
> VITE_API_BASE=http://127.0.0.1:9001 npx vite
> ```

---

## File Structure

```
clipper/
├── dj_clipper/          ← UNCHANGED (all Python core)
│   ├── core/
│   ├── models/
│   ├── workers/
│   └── ui/              ← (PyQt6 — remove when shipping Phase 7)
├── api/                 ← FastAPI wrapper
│   ├── main.py
│   ├── models.py
│   ├── session_store.py
│   ├── runners/
│   └── routes/
├── electron/            ← Electron main process
│   ├── main.ts
│   ├── preload.ts
│   └── pythonManager.ts
├── src/                 ← React frontend
│   ├── screens/
│   ├── components/
│   ├── hooks/
│   ├── store/
│   └── api/
├── resources/
│   └── bin/             ← ffmpeg + fpcalc binaries (gitignored, add before Phase 7)
│       ├── mac/         ← ffmpeg, ffprobe, fpcalc (macOS static builds)
│       └── win/         ← ffmpeg.exe, ffprobe.exe, fpcalc.exe
├── dj_clipper_api.spec  ← PyInstaller spec file (create in Phase 7)
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── REACT_MIGRATION_PLAN.md
```
