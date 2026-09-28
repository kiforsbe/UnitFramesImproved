"""Unit frame art in every current version of World of Warcraft, next to this addon's.

One row per frame (player, target and its elite / rare / boss looks, target of target, boss
frames, the player's status glow) and one column per game version, with the addon's own textures
from Textures/ in the last column. Each piece of art is drawn the way that version draws it: the
Classic versions crop a texture with the coordinates in their frame XML (mirrored for the player);
Retail and WoW Forever draw atlases, putting the elite / rare / boss dragon over the portrait at
the offsets their Lua uses. A cell that's identical to one further left says so.

It also prints, for each texture the addon replaces, the Blizzard version it's closest to and
where it differs, in on-screen coordinates (0,0 = the art's top-left corner, one unit = one pixel
at UI scale 1).

Game files are read from your World of Warcraft folder (every installed version), and downloaded
from wago.tools for versions that aren't installed. Both are cached in tools/out/cache/.

Usage, from the repo root:
    python -m pip install -r tools/requirements.txt
    python tools/compare_unitframe_art.py [--wow-dir "E:/Blizzard/World of Warcraft"] [--open]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is missing: python -m pip install -r tools/requirements.txt")

import wowfiles
from wowfiles import MissingFile

REPO_ROOT = Path(__file__).resolve().parent.parent
MY_TEXTURES = REPO_ROOT / "Textures"
OUT_DIR = REPO_ROOT / "tools" / "out"
CACHE_DIR = OUT_DIR / "cache"

ATLAS_TABLE, ATLAS_MEMBER_TABLE = 897470, 897532  # DBFilesClient/UiTextureAtlas(Member).db2

# (left, right, top, bottom) texture coordinates and on-screen size, from the Classic versions'
# Blizzard_UnitFrame/Classic/PlayerFrame.xml and TargetFrame.xml (the same in all of them).
# left > right means the game draws it mirrored.
PLAYER_CROP = ((0.85546875, 0.1015625, 0.0625, 0.6640625), (193, 77))
TARGET_CROP = ((0.1015625, 1.0, 0.0078125, 0.78125), (230, 99))
TOT_CROP = ((0.015625, 0.7265625, 0.0, 0.703125), (93, 45))
STATUS_CROP = ((0.0, 0.74609375, 0.0, 0.53125), (190, 66))

TARGET_FRAME_SIZE = (232, 100)  # Retail's TargetFrameContainer, which the atlases are placed in


@dataclass(frozen=True)
class Variant:
    title: str
    product: str             # Blizzard's product code
    style: str               # key into ART
    build_name_has: str = ""
    atlas_suffix: str = ""   # tried first when looking up an atlas
    on_wago: bool = True


VARIANTS = [
    Variant("Vanilla", "wow_classic_era", "classic"),
    Variant("TBC", "wow_anniversary", "classic"),
    Variant("Wrath", "wow_classic_titan", "classic"),  # Titan Reforged, China only
    Variant("Mists", "wow_classic", "classic"),
    Variant("Retail", "wow", "retail"),
    # WoW Forever runs as the Classic beta product, and draws the "-c60" copies of Retail's atlases.
    Variant("Forever", "wow_classic_beta", "forever", build_name_has="Forever", atlas_suffix="-c60", on_wago=False),
]

ROWS = [
    ("player", "Player"),
    ("status", "Player status glow"),
    ("target", "Target"),
    ("elite", "Target: elite"),
    ("rare", "Target: rare"),
    ("rareelite", "Target: rare elite"),
    ("worldboss", "Target: boss mob"),
    ("tot", "Target of target"),
    ("boss", "Boss frames"),
]


@dataclass(frozen=True)
class Texture:
    fdid: int
    name: str
    crop: tuple


@dataclass(frozen=True)
class Layer:
    atlas: str
    topright: tuple[int, int] | None = None  # offset from the target frame's TOPRIGHT; None = centred


HUD = "UI-HUD-UnitFrame-"
TARGET = Layer(HUD + "Target-PortraitOn")
RARE_TARGET = Layer(HUD + "Target-Rare-PortraitOn")

ART = {
    # Blizzard_UnitFrame/Classic/TargetFrame.lua: TARGET_FRAME_TEXTURES and CheckClassification.
    "classic": {
        "player": Texture(137026, "UI-TargetingFrame", PLAYER_CROP),
        "status": Texture(130935, "UI-Player-Status", STATUS_CROP),
        "target": Texture(137026, "UI-TargetingFrame", TARGET_CROP),
        "elite": Texture(137015, "UI-TargetingFrame-Elite", TARGET_CROP),
        "rare": Texture(137021, "UI-TargetingFrame-Rare", TARGET_CROP),
        "rareelite": Texture(137020, "UI-TargetingFrame-Rare-Elite", TARGET_CROP),
        "worldboss": Texture(137015, "UI-TargetingFrame-Elite", TARGET_CROP),
        "tot": Texture(137027, "UI-TargetofTargetFrame", TOT_CROP),
        "boss": Texture(337503, "UI-UnitFrame-Boss", TARGET_CROP),
    },
    # Blizzard_UnitFrame/Mainline/TargetFrame.lua: CheckClassification and the boss frame setup.
    "retail": {
        "player": [Layer(HUD + "Player-PortraitOn")],
        "status": [Layer(HUD + "Player-PortraitOn-Status")],
        "target": [TARGET],
        "elite": [TARGET, Layer(HUD + "Target-PortraitOn-Boss-Gold", (-11, -8))],
        "rare": [RARE_TARGET],
        "rareelite": [RARE_TARGET, Layer(HUD + "Target-PortraitOn-Boss-Rare-Silver", (-11, -8))],
        "worldboss": [TARGET, Layer(HUD + "Target-PortraitOn-Boss-Gold-Winged", (8, -8))],
        "tot": [Layer(HUD + "TargetofTarget-PortraitOn")],
        "boss": [Layer(HUD + "Target-Boss-Small-PortraitOff")],
    },
}
# Forever: Blizzard_UnitFrame/Camelot/TargetFrameUtils.lua, GetBossPortraitFrameData.
ART["forever"] = {
    **ART["retail"],
    "elite": [TARGET, Layer(HUD + "Target-PortraitOn-Boss-Gold", (0, 1))],
    "rare": [RARE_TARGET, Layer(HUD + "Target-PortraitOn-Boss-Rare-Silver-Winged", (8, -7))],
    "rareelite": [RARE_TARGET, Layer(HUD + "Target-PortraitOn-Boss-Rare-Silver-Winged", (8, -7))],
    "worldboss": [TARGET, Layer(HUD + "Target-PortraitOn-Boss-Gold-Winged", (11, -4))],
}

# The addon's textures, drawn with the Classic crops it uses them with (UnitFramesImproved_Classic.lua).
MINE = {
    "player": ("UI-TargetingFrame.blp", PLAYER_CROP, ""),
    "status": ("UI-Player-Status.blp", STATUS_CROP, ""),
    "target": ("UI-TargetingFrame.blp", TARGET_CROP, ""),
    "elite": ("UI-TargetingFrame-Elite.blp", TARGET_CROP, ""),
    "rare": ("UI-TargetingFrame-Rare.blp", TARGET_CROP, ""),
    "rareelite": ("UI-TargetingFrame-Rare-Elite.blp", TARGET_CROP, ""),
    "worldboss": ("UI-TargetingFrame-Elite.blp", TARGET_CROP, ""),
    "boss": ("UI-UnitFrame-Boss.blp", TARGET_CROP, "shipped, not used by the code"),
}
MINE_TITLE = "UnitFramesImproved"

# Classic draws the status glow with alphaMode="ADD" (PlayerFrame.xml): black is see-through.
ADDITIVE_ROWS = {"status"}


# --- Reading the game's art -----------------------------------------------------------------------

def decode(data: bytes) -> Image.Image:
    # Pillow can't read BLP2 encoding 3 (raw BGRA, used by newer atlases): the first mipmap is
    # just the pixels, at the offset in the header.
    if data[:4] == b"BLP2" and data[8] == 3:
        width, height = struct.unpack_from("<II", data, 12)
        offset = struct.unpack_from("<I", data, 20)[0]
        return Image.frombytes("RGBA", (width, height), data[offset:offset + width * height * 4], "raw", "BGRA")
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except (OSError, ValueError, NotImplementedError) as error:
        raise MissingFile(f"can't decode the texture: {error}") from error


class Source:
    """One game build's files, cached in tools/out/cache/<product>/<version>/."""

    def __init__(self, build, fallback=None):
        self.build, self.fallback = build, fallback
        self.cache = CACHE_DIR / build.product / build.version

    def files(self, fdids) -> dict[int, bytes | MissingFile]:
        out, todo = {}, []
        for fdid in set(fdids):
            cached = self.cache / str(fdid)
            if cached.exists():
                out[fdid] = cached.read_bytes()
            else:
                todo.append(fdid)
        if todo:
            found = self.build.files(todo)
            retry = [fdid for fdid, data in found.items() if isinstance(data, MissingFile)]
            if retry and self.fallback:
                found.update({fdid: data for fdid, data in self.fallback.files(retry).items() if isinstance(data, bytes)})
            for fdid, data in found.items():
                if isinstance(data, bytes):
                    self.cache.mkdir(parents=True, exist_ok=True)
                    (self.cache / str(fdid)).write_bytes(data)
            out.update(found)
        return out

    def image(self, fdid: int) -> Image.Image:
        data = self.files([fdid])[fdid]
        if isinstance(data, MissingFile):
            raise data
        return decode(data)


def open_source(variant: Variant, install, use_wago: bool) -> tuple[Source | None, str]:
    build = install.builds.get(variant.product) if install else None
    if build and variant.build_name_has and variant.build_name_has not in build.name:
        return None, f"{variant.product} is installed as {build.name}"
    if build:
        fallback = wowfiles.WagoBuild(build.product, build.version) if use_wago and variant.on_wago else None
        return Source(build, fallback), f"{build.version}, installed"
    if use_wago and variant.on_wago:
        version = wowfiles.wago_latest(variant.product)
        if version:
            return Source(wowfiles.WagoBuild(variant.product, version)), f"{version}, wago.tools"
    return None, "not installed" + ("" if variant.on_wago else ", not on wago.tools")


class Atlases:
    def __init__(self, source: Source, suffix: str):
        tables = source.files([ATLAS_TABLE, ATLAS_MEMBER_TABLE])
        for data in tables.values():
            if isinstance(data, MissingFile):
                raise data
        dbd_cache = CACHE_DIR / "dbd"
        self.textures = {row["ID"]: row for row in wowfiles.read_db2(tables[ATLAS_TABLE], "UiTextureAtlas", dbd_cache)}
        self.members = {}
        for row in wowfiles.read_db2(tables[ATLAS_MEMBER_TABLE], "UiTextureAtlasMember", dbd_cache):
            name = row["CommittedName"].lower()
            # Some names are in two atlases, at 1x and 2x: keep the 1x one, the size the game uses.
            if name not in self.members or self._width(row) < self._width(self.members[name]):
                self.members[name] = row
        self.source, self.suffix = source, suffix

    @staticmethod
    def _width(member: dict) -> int:
        return member["CommittedRight"] - member["CommittedLeft"]

    def member(self, name: str) -> dict:
        member = (self.suffix and self.members.get((name + self.suffix).lower())) or self.members.get(name.lower())
        if member is None:
            raise MissingFile(f"no atlas {name}")
        return member

    def fdid(self, name: str) -> int:
        return self.textures[self.member(name)["UiTextureAtlasID"]]["FileDataID"]

    def image(self, name: str) -> Image.Image:
        member = self.member(name)
        atlas = self.textures[member["UiTextureAtlasID"]]
        texture = self.source.image(atlas["FileDataID"])
        sx, sy = texture.width / atlas["AtlasWidth"], texture.height / atlas["AtlasHeight"]
        piece = texture.crop((round(member["CommittedLeft"] * sx), round(member["CommittedTop"] * sy),
                              round(member["CommittedRight"] * sx), round(member["CommittedBottom"] * sy)))
        size = (member["OverrideWidth"] or self._width(member),
                member["OverrideHeight"] or member["CommittedBottom"] - member["CommittedTop"])
        return piece if piece.size == size else piece.resize(size, Image.Resampling.LANCZOS)


def additive_to_alpha(image: Image.Image) -> Image.Image:
    """A texture drawn with additive blending, as an ordinary transparent one that looks the same
    over a dark background: brightness becomes opacity."""
    out = Image.new("RGBA", image.size)
    pixels, target = image.load(), out.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, _ = pixels[x, y]
            alpha = max(r, g, b)
            if alpha:
                target[x, y] = (r * 255 // alpha, g * 255 // alpha, b * 255 // alpha, alpha)
    return out


def as_drawn(image: Image.Image, crop: tuple) -> Image.Image:
    """The texture as a Classic frame draws it: cropped, mirrored if left > right, at on-screen size."""
    (left, right, top, bottom), size = crop
    width, height = image.size
    box = (round(min(left, right) * width), round(top * height), round(max(left, right) * width), round(bottom * height))
    piece = image.crop(box)
    if left > right:
        piece = piece.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return piece.resize(size, Image.Resampling.LANCZOS)


def draw_layers(atlases: Atlases, layers: list[Layer]) -> Image.Image:
    width, height = TARGET_FRAME_SIZE
    placed = []
    for layer in layers:
        image = atlases.image(layer.atlas)
        if layer.topright is None:
            x, y = (width - image.width) / 2, (height - image.height) / 2
        else:
            x, y = width + layer.topright[0] - image.width, -layer.topright[1]
        placed.append((image, round(x), round(y)))
    left = min(x for _, x, _ in placed)
    top = min(y for _, _, y in placed)
    right = max(x + image.width for image, x, _ in placed)
    bottom = max(y + image.height for image, _, y in placed)
    canvas = Image.new("RGBA", (right - left, bottom - top))
    for image, x, y in placed:
        canvas.alpha_composite(image, (x - left, y - top))
    return canvas


def atlas_caption(atlases: Atlases, layers: list[Layer]) -> str:
    names = []
    for layer in layers:
        name = atlases.member(layer.atlas)["CommittedName"]
        names.append(name[len(HUD):] if name.lower().startswith(HUD.lower()) else name)
    return "\n+ ".join(names)


@dataclass
class Cell:
    image: Image.Image | None
    caption: str
    texture: Image.Image | None = None  # the whole texture, for comparing against the addon's
    error: bool = False


def classic_cells(source: Source) -> dict[str, Cell]:
    art = ART["classic"]
    files = source.files({texture.fdid for texture in art.values()})
    cells = {}
    for row, texture in art.items():
        try:
            data = files[texture.fdid]
            if isinstance(data, MissingFile):
                raise data
            image = decode(data)
        except MissingFile as error:
            cells[row] = Cell(None, f"{texture.name}\n{error}", error=True)
            continue
        if row in ADDITIVE_ROWS:
            image = additive_to_alpha(image)
        cells[row] = Cell(as_drawn(image, texture.crop), texture.name, image)
    return cells


def atlas_cells(source: Source, style: str, suffix: str) -> dict[str, Cell]:
    atlases = Atlases(source, suffix)
    art = ART[style]
    fdids = set()
    for layers in art.values():
        for layer in layers:
            try:
                fdids.add(atlases.fdid(layer.atlas))
            except MissingFile:
                pass
    source.files(fdids)  # one pass over the build's file list for all of them

    cells = {}
    for row, layers in art.items():
        try:
            cells[row] = Cell(draw_layers(atlases, layers), atlas_caption(atlases, layers))
        except MissingFile as error:
            cells[row] = Cell(None, str(error), error=True)
    return cells


def mine_cells() -> dict[str, Cell]:
    cells = {}
    for row, _ in ROWS:
        if row not in MINE:
            cells[row] = Cell(None, "not replaced:\nBlizzard's art is used")
            continue
        file, crop, note = MINE[row]
        image = Image.open(MY_TEXTURES / file).convert("RGBA")
        if row in ADDITIVE_ROWS:
            image = additive_to_alpha(image)
        cells[row] = Cell(as_drawn(image, crop), file + (f"\n({note})" if note else ""), image)
    return cells


# --- Where the addon's art differs ----------------------------------------------------------------

def premultiplied(pixel: tuple) -> tuple:
    # Colour under fully transparent pixels is invisible in game, so don't count it as a change.
    r, g, b, a = pixel
    return (r * a // 255, g * a // 255, b * a // 255, a)


def changed_mask(theirs: Image.Image, mine: Image.Image, threshold: int) -> Image.Image:
    if theirs.size != mine.size:
        theirs = theirs.resize(mine.size, Image.Resampling.LANCZOS)
    mask = Image.new("L", mine.size, 0)
    a_pixels, b_pixels, out = theirs.load(), mine.load(), mask.load()
    for y in range(mine.height):
        for x in range(mine.width):
            a, b = premultiplied(a_pixels[x, y]), premultiplied(b_pixels[x, y])
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


def to_drawn(box: tuple, texture_size: tuple, crop: tuple) -> tuple | None:
    """A texture-pixel box in on-screen coordinates, or None if it's outside the drawn crop."""
    (left, right, top, bottom), (width, height) = crop
    tex_w, tex_h = texture_size
    xs = sorted((edge / tex_w - left) / (right - left) * width for edge in (box[0], box[2]))
    ys = [(edge / tex_h - top) / (bottom - top) * height for edge in (box[1], box[3])]
    x0, x1 = max(xs[0], 0), min(xs[1], width)
    y0, y1 = max(ys[0], 0), min(ys[1], height)
    if x0 >= x1 or y0 >= y1:
        return None
    return (round(x0), round(y0), round(x1), round(y1))


def report_differences(columns: list, args: argparse.Namespace) -> None:
    mine = columns[-1][2]
    print("\nWhere the addon's textures differ from Blizzard's")
    for row, label in ROWS:
        if row not in MINE or mine[row].texture is None:
            continue
        counts = []
        for title, _, cells in columns[:-1]:
            theirs = cells.get(row)
            if theirs and theirs.texture is not None:
                mask = changed_mask(theirs.texture, mine[row].texture, args.threshold)
                counts.append((sum(1 for value in mask.getdata() if value), title, mask))
        if not counts:
            continue
        counts.sort(key=lambda item: item[0])
        changed, closest, mask = counts[0]
        others = ", ".join(f"{title} {count}" for count, title, _ in counts[1:])
        print(f"{label} ({MINE[row][0]}): closest to {closest}, {changed} texture pixels differ"
              + (f" (others: {others})" if others else ""))
        for count, box in changed_regions(mask, args.min_region):
            drawn = to_drawn(box, mine[row].texture.size, MINE[row][1])
            where = f"x {drawn[0]}-{drawn[2]}, y {drawn[1]}-{drawn[3]} on screen" if drawn else "outside the drawn area"
            print(f"    {count:5d} px  {where}  (texture x {box[0]}-{box[2]}, y {box[1]}-{box[3]})")


# --- The sheet ------------------------------------------------------------------------------------

PAD = 14


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has one fixed-size default font
        return ImageFont.load_default()


def on_checkerboard(image: Image.Image, cell: int = 8) -> Image.Image:
    board = Image.new("RGBA", image.size, (58, 58, 58, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, image.height, cell):
        for x in range((y // cell) % 2 * cell, image.width, cell * 2):
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(86, 86, 86, 255))
    board.alpha_composite(image)
    return board


def mark_duplicates(columns: list) -> None:
    for row, _ in ROWS:
        seen = {}
        for title, _, cells in columns:
            cell = cells.get(row)
            if cell is None or cell.image is None:
                continue
            key = hashlib.sha1(cell.image.tobytes() + repr(cell.image.size).encode()).hexdigest()
            if key in seen:
                cell.caption += f"\nsame as {seen[key]}"
            else:
                seen[key] = title


def compose(columns: list, scale: int) -> Image.Image:
    title_font, subtitle_font, label_font, caption_font = font(22), font(14), font(17), font(13)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def text_size(text: str, which) -> tuple[int, int]:
        box = measure.multiline_textbbox((0, 0), text, font=which, spacing=3)
        return box[2], box[3]

    scaled = {}
    for c, (_, _, cells) in enumerate(columns):
        for row, _ in ROWS:
            cell = cells.get(row)
            if cell and cell.image is not None:
                image = cell.image.resize((cell.image.width * scale, cell.image.height * scale), Image.Resampling.NEAREST)
                scaled[c, row] = on_checkerboard(image)

    label_width = max(text_size(label, label_font)[0] for _, label in ROWS) + PAD * 2
    col_widths = []
    for c, (title, subtitle, cells) in enumerate(columns):
        widths = [text_size(title, title_font)[0], text_size(subtitle, subtitle_font)[0], 160]
        for row, _ in ROWS:
            if (c, row) in scaled:
                widths.append(scaled[c, row].width)
            if row in cells:
                widths.append(text_size(cells[row].caption, caption_font)[0])
        col_widths.append(max(widths))

    header_height = 70
    row_heights = []
    for row, label in ROWS:
        heights = [text_size(label, label_font)[1]]
        for c, (_, _, cells) in enumerate(columns):
            art = scaled[c, row].height + 8 if (c, row) in scaled else 0
            caption = text_size(cells[row].caption, caption_font)[1] if row in cells else 0
            heights.append(art + caption)
        row_heights.append(max(heights) + PAD * 2)

    width = label_width + sum(col_widths) + PAD * len(columns)
    sheet = Image.new("RGBA", (width, header_height + sum(row_heights)), (16, 16, 16, 255))
    draw = ImageDraw.Draw(sheet)
    x = label_width
    for (title, subtitle, _), col_width in zip(columns, col_widths):
        draw.text((x, PAD), title, font=title_font, fill=(255, 210, 0, 255))
        draw.text((x, PAD + 30), subtitle, font=subtitle_font, fill=(170, 170, 170, 255))
        x += col_width + PAD

    y = header_height
    for (row, label), row_height in zip(ROWS, row_heights):
        draw.line((PAD, y, width - PAD, y), fill=(48, 48, 48, 255))
        draw.text((PAD, y + PAD), label, font=label_font, fill=(235, 235, 235, 255))
        x = label_width
        for c, ((_, _, cells), col_width) in enumerate(zip(columns, col_widths)):
            top = y + PAD
            if (c, row) in scaled:
                sheet.alpha_composite(scaled[c, row], (x, top))
                top += scaled[c, row].height + 8
            if row in cells:
                colour = (230, 120, 120, 255) if cells[row].error else (200, 200, 200, 255)
                draw.multiline_text((x, top), cells[row].caption, font=caption_font, fill=colour, spacing=3)
            x += col_width + PAD
        y += row_height
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wow-dir", type=Path, help="World of Warcraft folder (default: found on your drives)")
    parser.add_argument("--no-download", action="store_true", help="don't use wago.tools for versions that aren't installed")
    parser.add_argument("--scale", type=int, default=2, help="zoom factor for the sheet (default: 2)")
    parser.add_argument("--threshold", type=int, default=24, help="per-channel difference (0-255) that counts as changed (default: 24)")
    parser.add_argument("--min-region", type=int, default=12, help="smallest patch of changed pixels to report (default: 12)")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "unitframe-art-comparison.png", help="where to write the sheet")
    parser.add_argument("--open", action="store_true", help="open the sheet when done")
    args = parser.parse_args()

    wow_dir = args.wow_dir or wowfiles.find_wow_dir()
    install = wowfiles.LocalInstall(wow_dir) if wow_dir else None
    print(f"World of Warcraft folder: {wow_dir or 'not found (use --wow-dir)'}")

    columns = []  # (title, subtitle, {row: Cell})
    for variant in VARIANTS:
        source, subtitle = open_source(variant, install, not args.no_download)
        print(f"{variant.title}: {subtitle}")
        cells = {}
        if source is not None:
            try:
                if variant.style == "classic":
                    cells = classic_cells(source)
                else:
                    cells = atlas_cells(source, variant.style, variant.atlas_suffix)
            except (MissingFile, OSError) as error:
                subtitle = f"{subtitle}: {error}"
                print(f"    {error}")
        columns.append((variant.title, subtitle, cells))
    columns.append((MINE_TITLE, "Textures/", mine_cells()))

    mark_duplicates(columns)
    report_differences(columns, args)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    compose(columns, args.scale).save(args.out)
    print(f"\nWrote {args.out}")
    if args.open:
        if hasattr(os, "startfile"):
            os.startfile(args.out)
        else:
            print("--open is only supported on Windows")


if __name__ == "__main__":
    main()
