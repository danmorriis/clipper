#!/usr/bin/env python3
"""Generate DJ Clipper app icon — 1024x1024 PNG."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

SIZE = 1024
BG_COLOR = "#c5bfb8"
CIRCLE_COLOR = "#d94e00"
TEXT_COLOR = "#1e1a18"

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

out_dir = Path(__file__).parent.parent / "resources" / "icons"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "icon.png"

img = Image.new("RGBA", (SIZE, SIZE), BG_COLOR)
draw = ImageDraw.Draw(img)

# Orange circle — 50% diameter, centered
diameter = int(SIZE * 0.50)
radius = diameter // 2
cx, cy = SIZE // 2, SIZE // 2
draw.ellipse(
    [cx - radius, cy - radius, cx + radius, cy + radius],
    fill=CIRCLE_COLOR,
)

# Text: "CLIP" line 1, "LAB" line 2
# Try increasing font sizes until both lines fit within 85% of the canvas width
max_width = int(SIZE * 0.85)
font_size = 60
font = ImageFont.truetype(FONT_PATH, font_size)

while font_size < 500:
    font = ImageFont.truetype(FONT_PATH, font_size)
    w1 = draw.textlength("CLIP", font=font)
    w2 = draw.textlength("LAB", font=font)
    if max(w1, w2) > max_width:
        font_size -= 1
        font = ImageFont.truetype(FONT_PATH, font_size)
        break
    font_size += 2

# Measure line heights
bbox1 = draw.textbbox((0, 0), "CLIP", font=font)
bbox2 = draw.textbbox((0, 0), "LAB", font=font)
line_h1 = bbox1[3] - bbox1[1]
line_h2 = bbox2[3] - bbox2[1]
gap = int(font_size * 0.08)
total_h = line_h1 + gap + line_h2

w1 = draw.textlength("CLIP", font=font)
w2 = draw.textlength("LAB", font=font)

y_start = (SIZE - total_h) // 2

draw.text(((SIZE - w1) / 2, y_start), "CLIP", fill=TEXT_COLOR, font=font)
draw.text(((SIZE - w2) / 2, y_start + line_h1 + gap), "LAB", fill=TEXT_COLOR, font=font)

img.save(out_path)
print(f"✓ Saved {out_path}  ({SIZE}x{SIZE})")
