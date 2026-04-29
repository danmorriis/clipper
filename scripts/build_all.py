#!/usr/bin/env python3
"""
DJ Clipper — cross-platform build script
Detects your OS, downloads all required binaries, compiles the Python backend,
builds the React/Electron frontend, and produces a distributable package.

Usage:
    macOS:    python3 scripts/build_all.py
    Windows:  python  scripts\\build_all.py

Output:
    macOS  → release/*.dmg
    Windows → release/*.exe
"""

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path

# ── Platform detection ─────────────────────────────────────────────────────────
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

if not IS_MAC and not IS_WIN:
    print("ERROR: Only macOS and Windows are supported.")
    sys.exit(1)

# ── Re-launch inside the project venv if we're not already in it ───────────────
# This handles Homebrew / externally-managed Python environments on macOS.
REPO_EARLY = Path(__file__).resolve().parent.parent
_VENV_PYTHON = REPO_EARLY / ".venv311" / "bin" / "python3"
if IS_MAC and _VENV_PYTHON.exists() and Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
BIN_DIR = REPO / "resources" / "bin" / ("mac" if IS_MAC else "win")
DIST_API = REPO / "dist" / "dj_clipper_api"

# ── Colours (skipped on Windows cmd which doesn't support ANSI by default) ────
USE_COLOUR = IS_MAC or os.environ.get("TERM") == "xterm"
CYAN   = "\033[0;36m"  if USE_COLOUR else ""
GREEN  = "\033[0;32m"  if USE_COLOUR else ""
YELLOW = "\033[1;33m"  if USE_COLOUR else ""
RED    = "\033[0;31m"  if USE_COLOUR else ""
NC     = "\033[0m"     if USE_COLOUR else ""

def info(msg):    print(f"{CYAN}▶  {msg}{NC}")
def success(msg): print(f"{GREEN}✓  {msg}{NC}")
def warn(msg):    print(f"{YELLOW}⚠  {msg}{NC}")
def error(msg):
    print(f"{RED}✗  {msg}{NC}")
    sys.exit(1)

# ── Helper: run a command, exit on failure ─────────────────────────────────────
def run(cmd, cwd=None, shell=False, env=None):
    """Run a command list (or shell string). Exits on non-zero return code."""
    cwd = cwd or REPO
    result = subprocess.run(cmd, cwd=cwd, shell=shell, env=env)
    if result.returncode != 0:
        error(f"Command failed (exit {result.returncode}): {cmd if isinstance(cmd, str) else ' '.join(str(c) for c in cmd)}")

# ── Helper: find an executable, accounting for Windows .cmd wrappers ──────────
def require(name, install_hint=""):
    candidates = [name, name + ".cmd", name + ".exe"] if IS_WIN else [name]
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    msg = f"'{name}' not found in PATH."
    if install_hint:
        msg += f"\n   → {install_hint}"
    error(msg)

# ══════════════════════════════════════════════════════════════════════════════
# Step 0 — Check prerequisites
# ══════════════════════════════════════════════════════════════════════════════
def check_prereqs():
    info("Checking prerequisites…")

    # Python version
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        error(f"Python 3.11+ required. You have {major}.{minor}.")

    require("node",  "Install Node.js 18+ from https://nodejs.org")
    require("npm",   "Install Node.js 18+ from https://nodejs.org")

    # PyInstaller — install into current Python env if missing
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        warn("PyInstaller not found — installing…")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Python deps
    info("Installing Python dependencies…")
    run([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt"), "-q"])

    success("Prerequisites OK")

# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Download platform binaries (ffmpeg, ffprobe, fpcalc)
# ══════════════════════════════════════════════════════════════════════════════
def download_binaries():
    expected = ["ffmpeg", "ffprobe", "fpcalc"] if IS_MAC else ["ffmpeg.exe", "ffprobe.exe", "fpcalc.exe"]
    already_have = all((BIN_DIR / b).exists() for b in expected)

    if already_have:
        success(f"Binaries already present in {BIN_DIR.relative_to(REPO)}/")
        return

    info("Downloading platform binaries (ffmpeg, ffprobe, fpcalc)…")
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    if IS_MAC:
        run(["bash", str(SCRIPTS / "download-binaries.sh")])
    else:
        run([
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPTS / "download-binaries.ps1"),
        ])

    success("Binaries downloaded")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Build Python backend with PyInstaller
# ══════════════════════════════════════════════════════════════════════════════
def build_python():
    info("Building Python backend with PyInstaller…")

    # Clean stale artefacts so PyInstaller doesn't reuse them
    for stale in [REPO / "build" / "dj_clipper_api", DIST_API]:
        if stale.exists():
            shutil.rmtree(stale)

    run([sys.executable, "-m", "PyInstaller", str(REPO / "dj_clipper_api.spec"), "--noconfirm"])

    if not DIST_API.exists():
        error("PyInstaller finished but dist/dj_clipper_api/ was not produced.")

    success("Python backend built → dist/dj_clipper_api/")

# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Install Node deps + build React/Electron frontend
# ══════════════════════════════════════════════════════════════════════════════
def build_frontend():
    info("Installing Node dependencies…")
    npm = require("npm")
    run([npm, "install", "--prefer-offline"])

    info("Building React frontend and compiling Electron…")
    run([npm, "run", "build"])

    success("Frontend built → dist/ and electron/")

# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Package with electron-builder
# ══════════════════════════════════════════════════════════════════════════════
def package():
    info(f"Packaging with electron-builder ({'macOS → .dmg' if IS_MAC else 'Windows → .exe'})…")
    npx = require("npx")
    flag = "--mac" if IS_MAC else "--win"
    env = os.environ.copy()
    # Use the already-installed Electron binary from node_modules to avoid a network download
    electron_dist = REPO / "node_modules" / "electron" / "dist"
    if electron_dist.exists():
        env["ELECTRON_OVERRIDE_DIST_PATH"] = str(electron_dist)
    run([npx, "electron-builder", flag, "--config", "electron-builder.yml"], env=env)

    release_dir = REPO / "release"
    if IS_MAC:
        dmgs = list(release_dir.glob("*.dmg"))
        if dmgs:
            success(f"macOS build complete → {dmgs[0].relative_to(REPO)}")
        else:
            warn("electron-builder finished but no .dmg found in release/")
    else:
        exes = list(release_dir.glob("*.exe"))
        if exes:
            success(f"Windows build complete → {exes[0].relative_to(REPO)}")
        else:
            warn("electron-builder finished but no .exe found in release/")

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    os_name = f"macOS ({platform.mac_ver()[0]})" if IS_MAC else f"Windows ({platform.version()})"
    print()
    info(f"DJ Clipper build — {os_name}")
    print()

    check_prereqs()
    print()
    download_binaries()
    print()
    # Frontend must run before PyInstaller — Vite clears dist/ on build
    build_frontend()
    print()
    build_python()
    print()
    package()
    print()
    success("All done!  Distributable is in the release/ directory.")
    print()

if __name__ == "__main__":
    main()
