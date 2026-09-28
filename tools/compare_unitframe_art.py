"""Unit frame art in every current version of World of Warcraft, next to this addon's.

One row per frame and situation (the player, PvP flagged or not, and its status glow; the target,
PvP flagged and too high level, and its elite / rare / boss looks; target of target; boss frames)
and one column per game version. Each cell is what that version's own UI code draws: which
textures and atlases, cropped how, how big, where, and in what order all come from the
Blizzard_UnitFrame XML and Lua in the build (see unitframe_ui.py). That includes the pieces some
versions add over the frame, like WoW Forever's level circle and PvP badge. The addon's textures
from Textures/ get their own column, after the last Classic version, each drawn where the Classic
frame draws the texture it replaces. A cell that's identical to one further left says so.

It also prints, for each texture the addon replaces, the Blizzard version it's closest to and
where it differs, in on-screen coordinates (0,0 = the texture's top-left corner as drawn, one
unit = one pixel at UI scale 1).

Game files are read from your World of Warcraft folder (every installed version), and downloaded
from wago.tools for versions that aren't installed. File paths are looked up in the community
listfile (github.com/wowdev/wow-listfile). All of it is cached in tools/out/cache/.

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
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is missing: python -m pip install -r tools/requirements.txt")

import unitframe_ui
import wowfiles
from unitframe_ui import MAIN_ART, FrameArt, Loaded, Piece
from wowfiles import MissingFile

REPO_ROOT = Path(__file__).resolve().parent.parent
MY_TEXTURES = REPO_ROOT / "Textures"
OUT_DIR = REPO_ROOT / "tools" / "out"
CACHE_DIR = OUT_DIR / "cache"

ATLAS_TABLE, ATLAS_MEMBER_TABLE = 897470, 897532  # DBFilesClient/UiTextureAtlas(Member).db2


@dataclass(frozen=True)
class Variant:
    title: str
    product: str             # Blizzard's product code
    flavor: str              # key into unitframe_ui.FLAVORS
    build_name_has: str = ""
    atlas_suffix: str = ""   # tried first when looking up an atlas
    on_wago: bool = True


VARIANTS = [
    Variant("Vanilla", "wow_classic_era", "vanilla"),
    Variant("TBC", "wow_anniversary", "tbc"),
    Variant("Wrath", "wow_classic_titan", "wrath"),  # Titan Reforged, China only
    Variant("Mists", "wow_classic", "mists"),
    # WoW Forever runs as the Classic beta product, and draws the "-c60" copies of Retail's atlases.
    Variant("Forever", "wow_classic_beta", "forever", build_name_has="Forever", atlas_suffix="-c60", on_wago=False),
    Variant("Retail", "wow", "retail"),
]

ROWS = [  # keys into unitframe_ui.SHOTS
    ("player", "Player"),
    ("player_pvp", "Player:\nPvP flagged"),
    ("status", "Player status glow"),
    ("target", "Target"),
    ("target_pvp", "Target:\nPvP flagged,\nlevel too high"),
    ("elite", "Target: elite"),
    ("rare", "Target: rare"),
    ("rareelite", "Target: rare elite"),
    ("worldboss", "Target: boss mob"),
    ("tot", "Target of target"),
    ("boss", "Boss frames"),
]

# The addon's textures (UnitFramesImproved_Classic.lua), each drawn in place of the Classic frame's
# own. What's drawn over it (the PvP flag, the skull) stays Blizzard's.
MINE = {
    "player": ("UI-TargetingFrame.blp", ""),
    "player_pvp": ("UI-TargetingFrame.blp", ""),
    "status": ("UI-Player-Status.blp", ""),
    "target": ("UI-TargetingFrame.blp", ""),
    "target_pvp": ("UI-TargetingFrame.blp", ""),
    "elite": ("UI-TargetingFrame-Elite.blp", ""),
    "rare": ("UI-TargetingFrame-Rare.blp", ""),
    "rareelite": ("UI-TargetingFrame-Rare-Elite.blp", ""),
    "worldboss": ("UI-TargetingFrame-Elite.blp", ""),
    "boss": ("UI-UnitFrame-Boss.blp", "shipped, not used by the code"),
}
MINE_TITLE = "UnitFramesImproved"
MINE_AFTER = "Mists"  # the addon's art is Classic art: after the last Classic version, before Forever and Retail

HUD = "UI-HUD-UnitFrame-"


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

    def size(self, name: str) -> tuple[int, int]:
        """The size the game draws it at when told to use the atlas's size."""
        member = self.member(name)
        return (member["OverrideWidth"] or self._width(member),
                member["OverrideHeight"] or member["CommittedBottom"] - member["CommittedTop"])

    def image(self, name: str) -> Image.Image:
        member = self.member(name)
        atlas = self.textures[member["UiTextureAtlasID"]]
        texture = self.source.image(atlas["FileDataID"])
        sx, sy = texture.width / atlas["AtlasWidth"], texture.height / atlas["AtlasHeight"]
        piece = texture.crop((round(member["CommittedLeft"] * sx), round(member["CommittedTop"] * sy),
                              round(member["CommittedRight"] * sx), round(member["CommittedBottom"] * sy)))
        size = self.size(name)
        return piece if piece.size == size else piece.resize(size, Image.Resampling.LANCZOS)


class Art:
    """A build's textures and atlases, for the pieces its frames draw."""

    def __init__(self, source: Source, atlas_suffix: str):
        self.source, self.atlas_suffix = source, atlas_suffix
        self._atlases = None

    @property
    def atlases(self) -> Atlases:
        if self._atlases is None:  # only read when a frame uses one
            self._atlases = Atlases(self.source, self.atlas_suffix)
        return self._atlases

    def atlas_size(self, name: str) -> tuple[int, int]:
        return self.atlases.size(name)

    def prefetch(self, pieces) -> None:
        """Reads all the textures in one pass over the build's file list."""
        fdids = set()
        for piece in pieces:
            try:
                fdids.add(self.atlases.fdid(piece.atlas) if piece.atlas else piece.fdid)
            except MissingFile:
                pass
        self.source.files(fdid for fdid in fdids if fdid is not None)

    def texture(self, piece: Piece) -> Image.Image:
        """The whole texture (or atlas member) the piece draws some of."""
        image = self.atlases.image(piece.atlas) if piece.atlas else self.source.image(piece.fdid)
        return additive_to_alpha(image) if piece.additive else image

    def name(self, piece: Piece) -> str:
        """As the UI code names it (the atlas table has most names in lower case), with the suffix
        of the copy drawn instead, if there is one."""
        name = piece.name
        if piece.atlas and self.atlas_suffix:
            if self.atlases.member(piece.atlas)["CommittedName"].lower() == (piece.atlas + self.atlas_suffix).lower():
                name += self.atlas_suffix
        return name[len(HUD):] if name.lower().startswith(HUD.lower()) else name


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
    """The texture as a frame draws it: cropped, mirrored if left > right, at on-screen size."""
    (left, right, top, bottom), size = crop
    width, height = image.size
    box = (round(min(left, right) * width), round(top * height), round(max(left, right) * width), round(bottom * height))
    piece = image.crop(box)
    if left > right:
        piece = piece.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return piece.resize(size, Image.Resampling.LANCZOS)


def crop_of(piece: Piece) -> tuple:
    return piece.coords, piece.size


def draw(frame: FrameArt, textures: dict[Piece, Image.Image]) -> Image.Image:
    """The frame's pieces, each where the frame puts it, in the order it draws them."""
    left = min(piece.rect[0] for piece in frame.pieces)
    top = min(piece.rect[1] for piece in frame.pieces)
    placed = [(as_drawn(textures[piece], crop_of(piece)), round(piece.rect[0] - left), round(piece.rect[1] - top))
              for piece in frame.pieces]
    canvas = Image.new("RGBA", (max(x + image.width for image, x, _ in placed),
                                max(y + image.height for image, _, y in placed)))
    for image, x, y in placed:
        canvas.alpha_composite(image, (x, y))
    if frame.scale != 1:
        canvas = canvas.resize((round(canvas.width * frame.scale), round(canvas.height * frame.scale)), Image.Resampling.LANCZOS)
    return canvas


@dataclass
class Cell:
    image: Image.Image | None
    caption: str
    texture: Image.Image | None = None  # the whole texture of the frame's own art, to compare with the addon's
    crop: tuple | None = None           # how that texture is drawn: (coords, size)
    error: bool = False
    frame: FrameArt | None = None
    textures: dict = field(default_factory=dict)


def main_piece(frame: FrameArt) -> Piece | None:
    return next((piece for piece in frame.pieces if piece.key in MAIN_ART), None)


def scale_note(frame: FrameArt) -> str:
    return f"\n(the frame is at scale {frame.scale:g})" if frame.scale != 1 else ""


def game_cells(loaded: Loaded, art: Art) -> dict[str, Cell]:
    frames = {row: frame for row, frame in loaded.art.items() if isinstance(frame, FrameArt)}
    art.prefetch(piece for frame in frames.values() for piece in frame.pieces)
    cells = {}
    for row, frame in loaded.art.items():
        if not isinstance(frame, FrameArt):
            cells[row] = Cell(None, str(frame), error=True)
            continue
        try:
            textures = {piece: art.texture(piece) for piece in frame.pieces}
            caption = "\n+ ".join(art.name(piece) for piece in frame.pieces) + scale_note(frame)
        except MissingFile as error:
            cells[row] = Cell(None, f"{', '.join(piece.name for piece in frame.pieces)}\n{error}", error=True)
            continue
        main = main_piece(frame)
        compared = main is not None and main.atlas is None   # the Classic textures the addon replaces
        cells[row] = Cell(draw(frame, textures), caption, textures[main] if compared else None,
                          crop_of(main) if compared else None, frame=frame, textures=textures)
    return cells


def mine_cells(reference: dict[str, Cell] | None) -> dict[str, Cell]:
    """The addon's textures, drawn in the frames of the first Classic version that could be read."""
    cells = {}
    for row, _ in ROWS:
        if row not in MINE:
            cells[row] = Cell(None, "not replaced:\nBlizzard's art is used")
            continue
        file, note = MINE[row]
        theirs = reference.get(row) if reference else None
        main = main_piece(theirs.frame) if theirs and theirs.frame else None
        if main is None:
            cells[row] = Cell(None, f"{file}\n(no Classic frame to draw it in)", error=True)
            continue
        image = decode((MY_TEXTURES / file).read_bytes())
        if main.additive:
            image = additive_to_alpha(image)
        textures = {**theirs.textures, main: image}
        caption = file + "".join(f"\n+ Blizzard's {piece.name}" for piece in theirs.frame.pieces if piece != main)
        cells[row] = Cell(draw(theirs.frame, textures), caption + (f"\n({note})" if note else ""), image,
                          crop_of(main), frame=theirs.frame, textures=textures)
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
    mine = next(cells for title, _, cells in columns if title == MINE_TITLE)
    print("\nWhere the addon's textures differ from Blizzard's")
    reported = set()   # the PvP rows draw the same textures as the plain ones
    for row, label in ROWS:
        cell = mine.get(row)
        if row not in MINE or cell is None or cell.texture is None or (MINE[row][0], cell.crop) in reported:
            continue
        if MINE[row][1]:   # a texture the addon ships but doesn't draw: nothing in game to compare it with
            continue
        reported.add((MINE[row][0], cell.crop))
        counts = []
        for title, _, cells in columns:
            theirs = cells.get(row)
            if title != MINE_TITLE and theirs and theirs.texture is not None:
                mask = changed_mask(theirs.texture, cell.texture, args.threshold)
                counts.append((sum(1 for value in mask.getdata() if value), title, mask))
        if not counts:
            continue
        counts.sort(key=lambda item: item[0])
        changed, closest, mask = counts[0]
        others = ", ".join(f"{title} {count}" for count, title, _ in counts[1:])
        print(f"{label.replace(chr(10), ' ')} ({MINE[row][0]}): closest to {closest}, {changed} texture pixels differ"
              + (f" (others: {others})" if others else ""))
        for count, box in changed_regions(mask, args.min_region):
            drawn = to_drawn(box, cell.texture.size, cell.crop)
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
        draw.multiline_text((PAD, y + PAD), label, font=label_font, fill=(235, 235, 235, 255), spacing=3)
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
    parser.add_argument("--no-download", action="store_true", help="don't use wago.tools or GitHub, only what's installed or cached")
    parser.add_argument("--scale", type=int, default=2, help="zoom factor for the sheet (default: 2)")
    parser.add_argument("--threshold", type=int, default=24, help="per-channel difference (0-255) that counts as changed (default: 24)")
    parser.add_argument("--min-region", type=int, default=12, help="smallest patch of changed pixels to report (default: 12)")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "unitframe-art-comparison.png", help="where to write the sheet")
    parser.add_argument("--open", action="store_true", help="open the sheet when done")
    args = parser.parse_args()

    wow_dir = args.wow_dir or wowfiles.find_wow_dir()
    install = wowfiles.LocalInstall(wow_dir) if wow_dir else None
    print(f"World of Warcraft folder: {wow_dir or 'not found (use --wow-dir)'}")
    listfile = wowfiles.Listfile(CACHE_DIR, allow_download=not args.no_download)

    columns = []  # (title, subtitle, {row: Cell})
    reference = None  # the first Classic version's cells, which the addon's textures are drawn in
    for variant in VARIANTS:
        source, subtitle = open_source(variant, install, not args.no_download)
        print(f"{variant.title}: {subtitle}")
        flavor = unitframe_ui.FLAVORS[variant.flavor]
        cells = {}
        if source is not None:
            art = Art(source, variant.atlas_suffix)
            try:
                loaded = unitframe_ui.read_frame_art(source.files, listfile, flavor, art.atlas_size)
                print(f"    {loaded.toc}" + (f"; couldn't read {', '.join(loaded.unreadable)}" if loaded.unreadable else ""))
                cells = game_cells(loaded, art)
            except (MissingFile, OSError) as error:
                subtitle = f"{subtitle}: {error}"
                print(f"    {error}")
            for row, cell in cells.items():
                if cell.error:
                    print(f"    {row}: {cell.caption.replace(chr(10), ' ')}")
        if reference is None and flavor.classic and cells:
            reference = cells
        columns.append((variant.title, subtitle, cells))
        if variant.title == MINE_AFTER:
            columns.append((MINE_TITLE, "Textures/", mine_cells(reference)))

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
