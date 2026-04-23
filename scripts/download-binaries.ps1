# Downloads static ffmpeg, ffprobe, and fpcalc binaries for Windows (x64)
# into resources/bin/win/ ready for electron-builder to bundle.
#
# Run once before building the Windows distributable:
#   npm run download-bins:win
#
# Requires: PowerShell 5+ (included in Windows 10/11)

$ErrorActionPreference = "Stop"

$Out = "resources\bin\win"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# ── ffmpeg + ffprobe (BtbN/FFmpeg-Builds — official GPL static Windows builds) ─
# Using the latest GPL build with all codecs included.
$FfmpegRepo  = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
$FfmpegZip   = "ffmpeg-master-latest-win64-gpl.zip"
$FfmpegUrl   = "$FfmpegRepo/$FfmpegZip"

Write-Host "→ Downloading ffmpeg + ffprobe..."
Invoke-WebRequest -Uri $FfmpegUrl -OutFile "$env:TEMP\$FfmpegZip" -UseBasicParsing
Expand-Archive -Path "$env:TEMP\$FfmpegZip" -DestinationPath "$env:TEMP\ffmpeg_extracted" -Force

# The zip has a single top-level folder; find the bin directory inside it
$FfmpegBin = Get-ChildItem "$env:TEMP\ffmpeg_extracted" -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1 -ExpandProperty DirectoryName
Copy-Item "$FfmpegBin\ffmpeg.exe"  "$Out\ffmpeg.exe"
Copy-Item "$FfmpegBin\ffprobe.exe" "$Out\ffprobe.exe"
Remove-Item -Recurse -Force "$env:TEMP\$FfmpegZip", "$env:TEMP\ffmpeg_extracted"

# ── fpcalc (Chromaprint — from official acoustid.org GitHub releases) ─────────
$ChromaVersion = "1.5.1"
$ChromaFile    = "chromaprint-fpcalc-$ChromaVersion-windows-x86_64.zip"
$ChromaUrl     = "https://github.com/acoustid/chromaprint/releases/download/v$ChromaVersion/$ChromaFile"

Write-Host "→ Downloading fpcalc (chromaprint $ChromaVersion)..."
Invoke-WebRequest -Uri $ChromaUrl -OutFile "$env:TEMP\$ChromaFile" -UseBasicParsing
Expand-Archive -Path "$env:TEMP\$ChromaFile" -DestinationPath "$env:TEMP\fpcalc_extracted" -Force

$FpcalcExe = Get-ChildItem "$env:TEMP\fpcalc_extracted" -Recurse -Filter "fpcalc.exe" | Select-Object -First 1 -ExpandProperty FullName
Copy-Item $FpcalcExe "$Out\fpcalc.exe"
Remove-Item -Recurse -Force "$env:TEMP\$ChromaFile", "$env:TEMP\fpcalc_extracted"

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "✓ Binaries ready in $Out\"
Get-ChildItem $Out | Format-Table Name, Length

Write-Host ""
Write-Host "Quick test:"
& "$Out\ffmpeg.exe"  -version 2>&1 | Select-Object -First 1
& "$Out\ffprobe.exe" -version 2>&1 | Select-Object -First 1
& "$Out\fpcalc.exe"  -version 2>&1 | Select-Object -First 1
