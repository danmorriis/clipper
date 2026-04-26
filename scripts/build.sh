#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DJ Clipper — full build & distribution script
#
# Usage:
#   bash scripts/build.sh          # auto-detect platform
#   bash scripts/build.sh --mac    # force macOS build
#   bash scripts/build.sh --win    # force Windows build (cross-compile from Mac)
#   bash scripts/build.sh --skip-python   # skip PyInstaller (use existing dist/)
#
# Prerequisites (both platforms):
#   - Python 3.11+ with dependencies: pip install -r requirements.txt
#   - PyInstaller:  pip install pyinstaller
#   - Node.js 18+:  npm install
#   - ffmpeg + fpcalc in resources/bin/{mac,win}/  (run download-binaries script first)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶  $*${NC}"; }
success() { echo -e "${GREEN}✓  $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠  $*${NC}"; }
error()   { echo -e "${RED}✗  $*${NC}"; exit 1; }

# ── Argument parsing ─────────────────────────────────────────────────────────
PLATFORM=""
SKIP_PYTHON=false

for arg in "$@"; do
  case "$arg" in
    --mac)          PLATFORM="mac" ;;
    --win)          PLATFORM="win" ;;
    --skip-python)  SKIP_PYTHON=true ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

# Auto-detect if not forced
if [[ -z "$PLATFORM" ]]; then
  case "$(uname -s)" in
    Darwin)  PLATFORM="mac" ;;
    Linux)   PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="win" ;;
    *) error "Unrecognised OS: $(uname -s). Pass --mac or --win explicitly." ;;
  esac
fi

info "Building DJ Clipper for platform: $PLATFORM"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Prerequisite checks ───────────────────────────────────────────────────────
command -v node      >/dev/null 2>&1 || error "node not found. Install Node.js 18+."
command -v npm       >/dev/null 2>&1 || error "npm not found."
command -v python3   >/dev/null 2>&1 || error "python3 not found."
command -v pyinstaller >/dev/null 2>&1 || error "pyinstaller not found. Run: pip install pyinstaller"

# Check bundled binaries exist for the target platform
BIN_DIR="resources/bin/$PLATFORM"
if [[ ! -d "$BIN_DIR" ]] || [[ -z "$(ls -A "$BIN_DIR" 2>/dev/null)" ]]; then
  warn "Binaries missing at $BIN_DIR"
  if [[ "$PLATFORM" == "mac" ]]; then
    info "Running: bash scripts/download-binaries.sh"
    bash scripts/download-binaries.sh
  else
    error "Run 'bash scripts/download-binaries.sh' (or the .ps1 on Windows) to download ffmpeg/fpcalc before building."
  fi
fi

# ── Step 1: Python backend (PyInstaller) ────────────────────────────────────
if [[ "$SKIP_PYTHON" == true ]]; then
  warn "Skipping Python build (--skip-python). Using existing dist/dj_clipper_api/."
  [[ -d "dist/dj_clipper_api" ]] || error "dist/dj_clipper_api not found — cannot skip Python build."
else
  info "Step 1/3 — Building Python backend with PyInstaller…"
  # Clean previous build artefacts so PyInstaller doesn't reuse stale objects
  rm -rf build/dj_clipper_api dist/dj_clipper_api

  pyinstaller dj_clipper_api.spec --noconfirm

  [[ -d "dist/dj_clipper_api" ]] || error "PyInstaller failed — dist/dj_clipper_api not produced."
  success "Python backend built → dist/dj_clipper_api/"
fi

# ── Step 2: Frontend + Electron TypeScript ───────────────────────────────────
info "Step 2/3 — Building React frontend and compiling Electron…"
npm install --prefer-offline 2>&1 | tail -3
npm run build    # vite build + tsc -p tsconfig.node.json
success "Frontend built → dist/ (Vite) and electron/*.js"

# ── Step 3: Electron-builder package ────────────────────────────────────────
info "Step 3/3 — Packaging with electron-builder (target: $PLATFORM)…"

case "$PLATFORM" in
  mac)
    npx electron-builder --mac --config electron-builder.yml
    success "macOS build complete → release/ (.dmg)"
    ;;
  win)
    # Cross-compiling from macOS to Windows is supported by electron-builder for
    # the Electron/JS bundle, but the Python binary (dj_clipper_api) must be built
    # ON a Windows machine with PyInstaller — the Mac binary won't run on Windows.
    # See WINDOWS NOTE below.
    npx electron-builder --win --config electron-builder.yml
    success "Windows build complete → release/ (.exe installer)"
    ;;
  linux)
    npx electron-builder --linux --config electron-builder.yml
    success "Linux build complete → release/ (AppImage)"
    ;;
esac

echo ""
success "All done! Distributable files are in the release/ directory."
