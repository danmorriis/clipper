"""
Utilities for cleaning raw audio filename stems into display-friendly track names.
"""

import re

# Matches a leading track number within any segment, e.g. "01 ", "02. ", "(03) ", "4-"
_TRACK_NUM_RE = re.compile(r'^\(?\d{1,3}\)?[\.\-\s]+')


def _strip_track_num(segment: str) -> str:
    """Strip a leading track number from a single name segment."""
    return _TRACK_NUM_RE.sub("", segment).strip()


def clean_track_name(name: str) -> str:
    """
    Strip leading track numbers and album segment from a raw filename stem.

    Rules applied in order:
      1. Split on " - ".
      2. Strip leading track number prefixes from every part
         (covers both "01 - Artist - Title" and "Artist - 01 Title").
      3. If three or more parts remain, drop the middle (album) parts;
         keep only the first (artist) and last (title).

    Examples
    --------
    "01 - Artist - Album - Title"  →  "Artist - Title"
    "Artist - 01 Title"            →  "Artist - Title"
    "Artist - Album - Title"       →  "Artist - Title"
    "02. Artist - Title"           →  "Artist - Title"
    "Artist - Title"               →  "Artist - Title"
    "Just A Title"                 →  "Just A Title"
    """
    parts = [_strip_track_num(p) for p in name.split(" - ") if p.strip()]
    if len(parts) >= 3:
        return f"{parts[0]} - {parts[-1]}"
    return " - ".join(parts)
