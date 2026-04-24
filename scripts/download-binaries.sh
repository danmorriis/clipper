#!/usr/bin/env bash
# Downloads static ffmpeg, ffprobe, and fpcalc binaries for macOS
# into resources/bin/mac/ ready for electron-builder to bundle.
#
# Run once before building the macOS distributable:
#   npm run download-bins:mac
#
# Requires: curl, unzip, shasum (all included in macOS)

set -euo pipefail

OUT="resources/bin/mac"
mkdir -p "$OUT"

# ── Detect architecture ───────────────────────────────────────────────────────
ARCH="$(uname -m)"
echo "→ Architecture: $ARCH"

# ── ffmpeg + ffprobe (from evermeet.cx — trusted static macOS builds) ─────────
# evermeet.cx builds are Intel only. For Apple Silicon they run via Rosetta 2,
# or you can swap these URLs for arm64 builds from the BtbN/FFmpeg-Builds repo.
FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
FFPROBE_URL="https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"

echo "→ Downloading ffmpeg…"
curl -L --progress-bar "$FFMPEG_URL" -o /tmp/ffmpeg.zip
unzip -o /tmp/ffmpeg.zip -d /tmp/ffmpeg_extracted
cp /tmp/ffmpeg_extracted/ffmpeg "$OUT/ffmpeg"
chmod +x "$OUT/ffmpeg"
rm -rf /tmp/ffmpeg.zip /tmp/ffmpeg_extracted

echo "→ Downloading ffprobe…"
curl -L --progress-bar "$FFPROBE_URL" -o /tmp/ffprobe.zip
unzip -o /tmp/ffprobe.zip -d /tmp/ffprobe_extracted
cp /tmp/ffprobe_extracted/ffprobe "$OUT/ffprobe"
chmod +x "$OUT/ffprobe"
rm -rf /tmp/ffprobe.zip /tmp/ffprobe_extracted

# ── fpcalc (Chromaprint — from official acoustid.org GitHub releases) ─────────
CHROMA_VERSION="1.5.1"
if [ "$ARCH" = "arm64" ]; then
  CHROMA_FILE="chromaprint-fpcalc-${CHROMA_VERSION}-macos-arm64.tar.gz"
else
  CHROMA_FILE="chromaprint-fpcalc-${CHROMA_VERSION}-macos-x86_64.tar.gz"
fi
CHROMA_URL="https://github.com/acoustid/chromaprint/releases/download/v${CHROMA_VERSION}/${CHROMA_FILE}"

echo "→ Downloading fpcalc (chromaprint ${CHROMA_VERSION})…"
curl -L --progress-bar "$CHROMA_URL" -o /tmp/fpcalc.tar.gz
tar -xzf /tmp/fpcalc.tar.gz -C /tmp
cp "/tmp/chromaprint-fpcalc-${CHROMA_VERSION}-macos-"*/fpcalc "$OUT/fpcalc"
chmod +x "$OUT/fpcalc"
rm -rf /tmp/fpcalc.tar.gz "/tmp/chromaprint-fpcalc-${CHROMA_VERSION}-macos-"*

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✓ Binaries ready in $OUT/"
ls -lh "$OUT"
echo ""
echo "Quick test:"
"$OUT/ffmpeg" -version 2>&1 | head -1
"$OUT/ffprobe" -version 2>&1 | head -1
"$OUT/fpcalc" -version 2>&1 | head -1
