"""
Generate Clip Lab app icon.

Creates a 1024x1024 PNG with:
  - Background: #c5bfb8
  - Orange circle (50% diameter): #d94e00
  - Text "CLIP" / "LAB" in Inter Black, foreground #1e1a18

Then converts to .icns (macOS) and .ico (Windows).

Usage:
  python3 scripts/generate_icon.py
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ensure_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Installing Pillow...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])


ensure_pillow()

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FONT_PATH = Path("/tmp/Inter-Black.ttf")
OUT_DIR = REPO / "resources" / "icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
BG = (197, 191, 184)       # #c5bfb8
ORANGE = (217, 78, 0)      # #d94e00
TEXT_COLOR = (30, 26, 24)  # #1e1a18


def make_png() -> Path:
    img = Image.new("RGBA", (SIZE, SIZE), BG + (255,))
    draw = ImageDraw.Draw(img)

    # Orange circle: 50% diameter centred
    r = SIZE * 0.25  # radius = 25% → diameter = 50%
    cx, cy = SIZE / 2, SIZE / 2
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=ORANGE + (255,),
    )

    # Text: "CLIP" then "LAB", stacked
    font_size = 340
    font = ImageFont.truetype(str(FONT_PATH), font_size)

    for word, y_frac in [("CLIP", 0.22), ("LAB", 0.55)]:
        bbox = draw.textbbox((0, 0), word, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (SIZE - w) / 2 - bbox[0]
        y = SIZE * y_frac - bbox[1]
        draw.text((x, y), word, font=font, fill=TEXT_COLOR + (255,))

    out = OUT_DIR / "icon.png"
    img.save(out, "PNG")
    print(f"Saved {out}")
    return out


def make_icns(png: Path) -> Path:
    out = OUT_DIR / "icon.icns"
    iconset = Path("/tmp/icon.iconset")
    iconset.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    img = Image.open(png)
    for s in sizes:
        resized = img.resize((s, s), Image.LANCZOS)
        resized.save(iconset / f"icon_{s}x{s}.png")
        if s <= 512:
            resized2 = img.resize((s * 2, s * 2), Image.LANCZOS)
            resized2.save(iconset / f"icon_{s}x{s}@2x.png")

    subprocess.check_call(["iconutil", "-c", "icns", str(iconset), "-o", str(out)])
    print(f"Saved {out}")
    return out


def make_ico(png: Path) -> Path:
    out = OUT_DIR / "icon.ico"
    img = Image.open(png).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    imgs = [img.resize(s, Image.LANCZOS) for s in sizes]
    imgs[0].save(out, format="ICO", sizes=sizes, append_images=imgs[1:])
    print(f"Saved {out}")
    return out


if __name__ == "__main__":
    if not FONT_PATH.exists():
        print(f"Inter-Black.ttf not found at {FONT_PATH}")
        print("Downloading...")
        import urllib.request
        url = "https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuBWYMZg.ttf"
        urllib.request.urlretrieve(url, str(FONT_PATH))
        print("Done.")

    png = make_png()
    make_icns(png)
    make_ico(png)
    print("\nAll icons generated successfully.")
