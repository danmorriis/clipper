"""
Playlist resolver: parse a DJ playlist file and find matching audio files
by recursively searching a root folder (USB drive, Google Drive mount, etc.).

Supported playlist formats:
  - M3U / M3U8: uses embedded absolute paths when they exist on disk;
                falls back to fuzzy display-name matching otherwise
  - rekordbox TXT export: tab-separated (UTF-16 LE), extracts Artist + Title
  - Plain text: one track per line (artist – title, filename, or full path)

Matching is fuzzy (case-insensitive, punctuation-normalised, token-based)
so minor spelling differences and missing file extensions don't break it.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}

# Minimum fuzzy match ratio to accept a file as matching a track name.
MATCH_THRESHOLD = 0.60


# ── Encoding helpers ──────────────────────────────────────────────────────────

def _read_text(path: Path) -> str:
    """
    Read a text file, auto-detecting UTF-16 (rekordbox export) vs UTF-8.
    rekordbox TXT exports begin with a UTF-16 LE BOM (0xFF 0xFE).
    """
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


# ── Playlist parsing ──────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, strip accents, collapse punctuation/whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_m3u_entries(lines: List[str]) -> List[Tuple[str, Optional[Path]]]:
    """
    Parse M3U/M3U8 lines into (display_name, embedded_path_or_None) pairs.

    display_name comes from #EXTINF metadata (preferred) or the path stem.
    embedded_path is the raw path line as a Path object (may not exist on disk).
    """
    entries: List[Tuple[str, Optional[Path]]] = []
    pending_extinf: Optional[str] = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            if "," in line:
                pending_extinf = line.split(",", 1)[1].strip()
        elif not line.startswith("#"):
            embedded = Path(line)
            display = pending_extinf if pending_extinf else embedded.stem
            entries.append((display, embedded))
            pending_extinf = None
    if pending_extinf:
        # Dangling #EXTINF with no path line
        entries.append((pending_extinf, None))
    return entries


def _parse_rekordbox_txt(lines: List[str]) -> List[str]:
    """
    rekordbox TXT: tab-separated, header row first.
    Columns we care about: 'Track Title' and 'Artist'.
    """
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split("\t")]
    # rekordbox uses "Track Title" — match any header containing "title"
    title_col  = next((i for i, h in enumerate(header) if "title" in h), None)
    artist_col = next((i for i, h in enumerate(header) if "artist" in h), None)
    tracks = []
    for line in lines[1:]:
        parts = line.split("\t")
        if title_col is not None and title_col < len(parts):
            title  = parts[title_col].strip()
            artist = parts[artist_col].strip() if artist_col is not None and artist_col < len(parts) else ""
            if not title:
                continue
            if artist:
                tracks.append(f"{artist} {title}")
            else:
                tracks.append(title)
    return tracks


def parse_playlist(playlist_path: Path) -> List[str]:
    """
    Parse a playlist file and return a list of track name strings.
    Supports: .m3u, .m3u8, rekordbox .txt export, plain text.
    """
    text = _read_text(playlist_path)
    lines = text.splitlines()
    ext = playlist_path.suffix.lower()

    if ext in (".m3u", ".m3u8"):
        return [name for name, _ in _parse_m3u_entries(lines)]

    if ext == ".txt":
        if lines and "\t" in lines[0]:
            parsed = _parse_rekordbox_txt(lines)
            if parsed:
                return parsed
        # Fall through to plain text

    # Plain text: one track name per line, skip blank/comment lines
    tracks = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "/" in line or "\\" in line:
            line = Path(line).stem
        tracks.append(line)
    return tracks


# ── File discovery ────────────────────────────────────────────────────────────

def _build_file_index(root: Path) -> Dict[str, Path]:
    """
    Recursively index all audio files under root.
    Returns { normalised_stem: full_path }.
    """
    index: Dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.suffix.lower() in AUDIO_EXTENSIONS and path.is_file():
            index[_normalise(path.stem)] = path
    return index


def _token_overlap(a: str, b: str) -> float:
    """
    Token-set F1: rewards shared words regardless of order or extra tokens.
    Returns 2 * |common| / (|a_tokens| + |b_tokens|).
    """
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    common = len(ta & tb)
    return 2 * common / (len(ta) + len(tb))


def _best_match(
    track_name: str,
    file_index: Dict[str, Path],
) -> Optional[Tuple[Path, float]]:
    """
    Find the best-matching file for track_name in file_index.
    Score = max(SequenceMatcher ratio, token-overlap F1).
    Returns (path, score) or None if nothing clears MATCH_THRESHOLD.
    """
    norm = _normalise(track_name)
    best_score = 0.0
    best_path: Optional[Path] = None

    for stem, path in file_index.items():
        seq_score = SequenceMatcher(None, norm, stem).ratio()
        tok_score = _token_overlap(norm, stem)
        score = max(seq_score, tok_score)
        if score > best_score:
            best_score = score
            best_path = path

    if best_score >= MATCH_THRESHOLD and best_path:
        return best_path, best_score
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_playlist(
    playlist_path: Path,
    search_root: Optional[Path] = None,
    progress_callback=None,
) -> Tuple[List[Path], List[str]]:
    """
    Parse playlist_path and resolve each track to an audio file Path.

    Resolution strategy (M3U/M3U8):
      1. If the embedded absolute path exists on disk → use it directly.
      2. Otherwise → fuzzy-match the display name against files under search_root.

    Resolution strategy (TXT / plain text):
      → Fuzzy-match the track name string against files under search_root.

    search_root is required for fuzzy fallback. If None, only direct M3U paths work.

    Returns:
      found   — list of resolved audio file Paths (deduplicated, in playlist order)
      missing — list of track name strings that could not be resolved
    """
    text = _read_text(playlist_path)
    lines = text.splitlines()
    ext = playlist_path.suffix.lower()

    # Build (display_name, embedded_path_or_None) pairs
    if ext in (".m3u", ".m3u8"):
        entries: List[Tuple[str, Optional[Path]]] = _parse_m3u_entries(lines)
    elif ext == ".txt" and lines and "\t" in lines[0]:
        track_names = _parse_rekordbox_txt(lines)
        entries = [(name, None) for name in track_names]
    else:
        track_names = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "/" in line or "\\" in line:
                line = Path(line).stem
            track_names.append(line)
        entries = [(name, None) for name in track_names]

    if not entries:
        return [], []

    # Build fuzzy index lazily (only if any entry needs it)
    _file_index: Optional[Dict[str, Path]] = None

    def file_index() -> Dict[str, Path]:
        nonlocal _file_index
        if _file_index is None:
            if search_root is None:
                _file_index = {}
            else:
                _file_index = _build_file_index(search_root)
        return _file_index

    found: List[Path] = []
    missing: List[str] = []
    seen: set = set()

    for i, (display_name, embedded_path) in enumerate(entries):
        if progress_callback:
            progress_callback(i, len(entries), display_name)

        resolved: Optional[Path] = None

        # 1. Try embedded path from M3U directly
        if embedded_path is not None and embedded_path.suffix.lower() in AUDIO_EXTENSIONS:
            if embedded_path.is_file():
                resolved = embedded_path

        # 2. Fuzzy search fallback
        if resolved is None:
            result = _best_match(display_name, file_index())
            if result:
                resolved = result[0]

        if resolved is not None:
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                found.append(resolved)
        else:
            missing.append(display_name)

    return found, missing
