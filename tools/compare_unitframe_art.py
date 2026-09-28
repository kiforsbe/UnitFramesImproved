"""Side-by-side comparison of Blizzard's stock classic unit frame art and this addon's
replacements in Textures/, one row per frame type.

Columns: Blizzard's original, the addon's version, and the pixels the addon changed (red, over a
faded copy of the addon's art). Each texture is shown the way the game draws it - cropped to the
texture coordinates Blizzard's Classic frame XML uses, mirrored for the player frame, at its
on-screen size - so the changes line up with frame coordinates. The same changes are printed as
boxes in those coordinates (0,0 = the art's top-left corner).

Blizzard's originals come from Gethe/wow-ui-textures (a git mirror of the game's interface
textures) and are downloaded once into tools/out/blizzard/. Pass --blizzard-dir to use a folder of
textures exported from your own client instead (.png, .blp or .tga, found by file name).

Usage, from the repo root:
    python -m pip install -r tools/requirements.txt
    python tools/compare_unitframe_art.py [--scale 2] [--open]
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is missing: python -m pip install -r tools/requirements.txt")

REPO_ROOT = Path(__file__).resolve().parent.parent
MY_TEXTURES = REPO_ROOT / "Textures"
OUT_DIR = REPO_ROOT / "tools" / "out"
MIRROR_URL = "https://raw.githubusercontent.com/Gethe/wow-ui-textures/{branch}/{path}"

# (left, right, top, bottom) texture coordinates and on-screen size of each piece of art, from
# Blizzard's Classic Era frame XML (Blizzard_UnitFrame/Classic/PlayerFrame.xml, TargetFrame.xml).
# left > right means the game draws it mirrored.
PLAYER_CROP = ((0.85546875, 0.1015625, 0.0625, 0.6640625), (193, 77))
TARGET_CROP = ((0.1015625, 1.0, 0.0078125, 0.78125), (230, 99))
TOT_CROP = ((0.015625, 0.7265625, 0.0, 0.703125), (93, 45))
STATUS_CROP = ((0.0, 0.74609375, 0.0, 0.53125), (190, 66))


@dataclass(frozen=True)
class Art:
    label: str
    blizzard: str           # path inside the texture mirror
    mine: str | None        # file in Textures/, or None where the addon keeps Blizzard's art
    crop: tuple | None = None  # None shows the whole texture


ARTS = [
    Art("Player frame", "TARGETINGFRAME/UI-TargetingFrame.PNG", "UI-TargetingFrame.blp", PLAYER_CROP),
    Art("Target frame", "TARGETINGFRAME/UI-TargetingFrame.PNG", "UI-TargetingFrame.blp", TARGET_CROP),
    Art("Target frame - elite", "TARGETINGFRAME/UI-TargetingFrame-Elite.PNG", "UI-TargetingFrame-Elite.blp", TARGET_CROP),
    Art("Target frame - rare", "TARGETINGFRAME/UI-TargetingFrame-Rare.PNG", "UI-TargetingFrame-Rare.blp", TARGET_CROP),
    Art("Target frame - rare elite", "TARGETINGFRAME/UI-TargetingFrame-Rare-Elite.PNG", "UI-TargetingFrame-Rare-Elite.blp", TARGET_CROP),
    Art("Target of target", "TARGETINGFRAME/UI-TargetofTargetFrame.PNG", None, TOT_CROP),
    Art("Focus frame (whole texture)", "TARGETINGFRAME/UI-FocusTargetingFrame.PNG", "UI-FocusTargetingFrame.blp"),
    Art("Boss frame (whole texture)", "TARGETINGFRAME/UI-UnitFrame-Boss.PNG", "UI-UnitFrame-Boss.blp"),
    Art("Player status glow", "CHARACTERFRAME/UI-Player-Status.PNG", "UI-Player-Status.blp", STATUS_CROP),
]

COLUMNS = ("Blizzard (stock classic)", "UnitFramesImproved", "Changed pixels")
PAD = 12


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has one fixed-size default font
        return ImageFont.load_default()


def find_local(folder: Path, stem: str) -> Path:
    for path in folder.rglob("*"):
        if path.is_file() and path.stem.lower() == stem.lower() and path.suffix.lower() in (".png", ".blp", ".tga"):
            return path
    sys.exit(f"No {stem} texture (.png/.blp/.tga) under {folder}")


def blizzard_texture(art: Art, args: argparse.Namespace) -> Path:
    if args.blizzard_dir:
        return find_local(args.blizzard_dir, Path(art.blizzard).stem)

    cached = OUT_DIR / "blizzard" / args.branch / art.blizzard
    if not cached.exists():
        url = MIRROR_URL.format(branch=args.branch, path=art.blizzard)
        print(f"Downloading {url}")
        cached.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            cached.write_bytes(response.read())
    return cached


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def as_drawn(image: Image.Image, crop: tuple | None) -> Image.Image:
    """The texture as the game draws it: cropped, mirrored if left > right, at on-screen size."""
    if crop is None:
        return image
    (left, right, top, bottom), size = crop
    width, height = image.size
    box = (round(min(left, right) * width), round(top * height), round(max(left, right) * width), round(bottom * height))
    piece = image.crop(box)
    if left > right:
        piece = piece.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return piece.resize(size, Image.Resampling.LANCZOS)


def premultiplied(pixel: tuple) -> tuple:
    # Colour under fully transparent pixels is invisible in game, so don't count it as a change.
    r, g, b, a = pixel
    return (r * a // 255, g * a // 255, b * a // 255, a)


def changed_mask(blizzard: Image.Image, mine: Image.Image, threshold: int) -> Image.Image:
    if blizzard.size != mine.size:
        blizzard = blizzard.resize(mine.size, Image.Resampling.LANCZOS)
    mask = Image.new("L", mine.size, 0)
    theirs, ours, out = blizzard.load(), mine.load(), mask.load()
    for y in range(mine.height):
        for x in range(mine.width):
            a, b = premultiplied(theirs[x, y]), premultiplied(ours[x, y])
            if max(abs(i - j) for i, j in zip(a, b)) > threshold:
                out[x, y] = 255
    return mask


def changed_regions(mask: Image.Image, min_pixels: int) -> list[tuple[int, tuple[int, int, int, int]]]:
    """(pixel count, bounding box) of each connected patch of changed pixels, largest first."""
    width, height = mask.size
    pixels = mask.load()
    seen = set()
    regions = []
    for y in range(height):
        for x in range(width):
            if not pixels[x, y] or (x, y) in seen:
                continue
            seen.add((x, y))
            stack = [(x, y)]
            x0, y0, x1, y1, count = x, y, x, y, 0
            while stack:
                cx, cy = stack.pop()
                count += 1
                x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx), max(y1, cy)
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            if count >= min_pixels:
                regions.append((count, (x0, y0, x1 + 1, y1 + 1)))
    return sorted(regions, reverse=True)


def to_drawn(box: tuple, texture_size: tuple, crop: tuple | None) -> tuple | None:
    """A texture-pixel box in on-screen art coordinates, or None if it's outside the drawn crop."""
    if crop is None:
        return box
    (left, right, top, bottom), (width, height) = crop
    tex_w, tex_h = texture_size
    xs = sorted((box[0] / tex_w - left) / (right - left) * width for box_x in (0, 2) for box in [box[:0] + (box[box_x],)])
    ys = [(edge / tex_h - top) / (bottom - top) * height for edge in (box[1], box[3])]
    x0, x1 = max(xs[0], 0), min(xs[1], width)
    y0, y1 = max(ys[0], 0), min(ys[1], height)
    if x0 >= x1 or y0 >= y1:
        return None
    return (round(x0), round(y0), round(x1), round(y1))


def diff_view(mine: Image.Image, mask: Image.Image) -> Image.Image:
    view = Image.new("RGBA", mine.size, (24, 24, 24, 255))
    faded = mine.copy()
    faded.putalpha(faded.getchannel("A").point(lambda a: a * 2 // 5))
    view.alpha_composite(faded)
    view.paste(Image.new("RGBA", mine.size, (255, 48, 48, 255)), (0, 0), mask)
    return view


def on_checkerboard(image: Image.Image, cell: int = 8) -> Image.Image:
    board = Image.new("RGBA", image.size, (58, 58, 58, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, image.height, cell):
        for x in range((y // cell) % 2 * cell, image.width, cell * 2):
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(86, 86, 86, 255))
    board.alpha_composite(image)
    return board


def placeholder(size: tuple, text: str) -> Image.Image:
    panel = Image.new("RGBA", size, (24, 24, 24, 255))
    ImageDraw.Draw(panel).multiline_text((PAD, PAD), text, font=font(14), fill=(200, 200, 200, 255))
    return panel


def build_row(art: Art, args: argparse.Namespace) -> tuple[list[Image.Image], list[str]]:
    blizzard = load(blizzard_texture(art, args))
    shown_blizzard = on_checkerboard(as_drawn(blizzard, art.crop))

    if art.mine is None:
        note = "No replacement:\nthe addon keeps\nBlizzard's art."
        panels = [shown_blizzard, placeholder(shown_blizzard.size, note), placeholder(shown_blizzard.size, "-")]
        return panels, ["  no replacement in Textures/ - Blizzard's art is used"]

    mine = load(MY_TEXTURES / art.mine)
    mask = changed_mask(blizzard, mine, args.threshold)
    panels = [shown_blizzard, on_checkerboard(as_drawn(mine, art.crop)), as_drawn(diff_view(mine, mask), art.crop)]

    changed = sum(1 for value in mask.getdata() if value)
    report = [f"  {changed} of {mine.width * mine.height} texture pixels changed ({art.mine} is {mine.width}x{mine.height}, "
              f"Blizzard's is {blizzard.width}x{blizzard.height})"]
    for count, box in changed_regions(mask, args.min_region):
        drawn = to_drawn(box, mine.size, art.crop)
        where = f"x {drawn[0]}-{drawn[2]}, y {drawn[1]}-{drawn[3]} on screen" if drawn else "outside the drawn area"
        report.append(f"    {count:5d} px  {where}  (texture x {box[0]}-{box[2]}, y {box[1]}-{box[3]})")
    return panels, report


def compose(rows: list[tuple[str, list[Image.Image]]], scale: int) -> Image.Image:
    title_font, label_font = font(18), font(15)
    scaled = [(label, [p.resize((p.width * scale, p.height * scale), Image.Resampling.NEAREST) for p in panels])
              for label, panels in rows]
    col_widths = [max(panels[i].width for _, panels in scaled) for i in range(len(COLUMNS))]
    label_h, header_h = 24, 32
    heights = [label_h + max(p.height for p in panels) + PAD for _, panels in scaled]

    sheet = Image.new("RGBA", (sum(col_widths) + PAD * (len(COLUMNS) + 1), header_h + sum(heights) + PAD), (16, 16, 16, 255))
    draw = ImageDraw.Draw(sheet)
    x = PAD
    for title, width in zip(COLUMNS, col_widths):
        draw.text((x, PAD // 2), title, font=title_font, fill=(255, 210, 0, 255))
        x += width + PAD

    y = header_h
    for (label, panels), height in zip(scaled, heights):
        draw.text((PAD, y), label, font=label_font, fill=(230, 230, 230, 255))
        x = PAD
        for panel, width in zip(panels, col_widths):
            sheet.alpha_composite(panel, (x, y + label_h))
            x += width + PAD
        y += height
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", default="classic", help="wow-ui-textures branch to take Blizzard's art from (default: classic)")
    parser.add_argument("--blizzard-dir", type=Path, help="use Blizzard textures from this folder instead of downloading them")
    parser.add_argument("--scale", type=int, default=2, help="zoom factor for the sheet (default: 2)")
    parser.add_argument("--threshold", type=int, default=24, help="per-channel difference (0-255) that counts as changed (default: 24)")
    parser.add_argument("--min-region", type=int, default=12, help="smallest patch of changed pixels to report (default: 12)")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "unitframe-art-comparison.png", help="where to write the sheet")
    parser.add_argument("--open", action="store_true", help="open the sheet when done")
    args = parser.parse_args()

    rows = []
    for art in ARTS:
        panels, report = build_row(art, args)
        rows.append((art.label, panels))
        print(art.label)
        print("\n".join(report))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    compose(rows, args.scale).save(args.out)
    print(f"\nWrote {args.out}")
    if args.open:
        os.startfile(args.out) if hasattr(os, "startfile") else print("--open is only supported on Windows")


if __name__ == "__main__":
    main()
