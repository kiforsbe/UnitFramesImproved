"""Blizzard's BLP textures, to and from PNG, for editing the addon's art in an image editor.

    export: BLP -> PNG. With no files given, every texture in Textures/, into tools/out/textures/
            (not next to them: build.ps1 ships everything in Textures/).
    import: PNG (or any image Pillow opens) -> BLP, into Textures/ under the same name, replacing
            the texture that's there.

Textures are written the way the game's own UI textures are: BLP2, DXT compressed with every
mipmap level, and DXT3 by default, like all of the addon's textures so far. --encoding dxt5 has
smoother alpha gradients (DXT3 has 16 levels of alpha, DXT5 interpolates); --encoding raw is
lossless and 4x the size, with no mipmaps, like WoW Forever's big atlases. Sizes have to be powers
of two (e.g. 256x128).

Usage, from the repo root:
    python -m pip install -r tools/requirements.txt
    python tools/blp.py export [Textures/UI-TargetingFrame.blp ...] [--out-dir DIR]
    python tools/blp.py import tools/out/textures/UI-TargetingFrame.png [...] [--out-dir DIR] [--encoding dxt3|dxt5|raw]
"""

from __future__ import annotations

import argparse
import io
import struct
import sys
from pathlib import Path

try:
    import PIL
    from PIL import Image
except ImportError:
    sys.exit("Pillow is missing: python -m pip install -r tools/requirements.txt")

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXTURES = REPO_ROOT / "Textures"
EXPORT_DIR = REPO_ROOT / "tools" / "out" / "textures"

# magic, "type" (1: not JPEG), encoding, alpha depth, alpha encoding, has mipmaps, width, height,
# then the offset and size of each of up to 16 mipmap levels. A 256-colour palette follows, unused
# (all zero) unless the encoding is 1.
HEADER = struct.Struct("<4sI4B2I16I16I")
PALETTE_SIZE = 1024
DDS_HEADER_SIZE = 128   # "DDS " and its 124-byte header, before the blocks

# encoding, alpha depth, alpha encoding: as in the game's own files
ENCODINGS = {
    "dxt3": (2, 8, 1),
    "dxt5": (2, 8, 7),
    "raw": (3, 8, 8),   # BGRA, 4 bytes a pixel
}


def read(data: bytes) -> Image.Image:
    """A BLP (or any image Pillow opens), as RGBA."""
    # Pillow can't read BLP2 encoding 3 (raw BGRA): the first mipmap is just the pixels, at the
    # offset in the header.
    if data[:4] == b"BLP2" and data[8] == 3:
        width, height = struct.unpack_from("<II", data, 12)
        offset = struct.unpack_from("<I", data, 20)[0]
        return Image.frombytes("RGBA", (width, height), data[offset:offset + width * height * 4], "raw", "BGRA")
    return Image.open(io.BytesIO(data)).convert("RGBA")


def is_power_of_two(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def mipmaps(image: Image.Image) -> list[Image.Image]:
    """The image, then each half the size of the one before, down to 1x1."""
    levels = [image]
    width, height = image.size
    while (width, height) != (1, 1):
        width, height = max(width // 2, 1), max(height // 2, 1)
        levels.append(image.resize((width, height), Image.Resampling.LANCZOS))
    return levels


def dxt(image: Image.Image, pixel_format: str) -> bytes:
    """The image's DXT blocks: 8 bytes of alpha, then 8 of colour, for each 4x4 block, row by row.
    Levels smaller than a block are padded with transparency; the game only samples the image's
    own pixels.

    The colour half comes from Pillow's DDS encoder, but not the alpha: Pillow 11.3's DXT3 alpha
    ORs together the last two pixels of each row of a block (alphas 2 and 3 of 15 come out as 3
    and 3), and its DXT5 alpha always uses the mode that spends two of the eight values on 0 and
    255, leaving 0/51/102/153/204/255 for a gradient."""
    width, height = (max(4, (size + 3) // 4 * 4) for size in image.size)
    if (width, height) != image.size:
        padded = Image.new("RGBA", (width, height))
        padded.paste(image)
        image = padded
    out = io.BytesIO()
    try:
        image.save(out, "DDS", pixel_format=pixel_format)
    except (ValueError, OSError, KeyError) as error:
        sys.exit(f"This Pillow ({PIL.__version__}) can't write {pixel_format} ({error}): "
                 "python -m pip install -r tools/requirements.txt")
    pillow = out.getvalue()[DDS_HEADER_SIZE:]
    expected = width * height // 16 * 16
    if len(pillow) != expected:
        raise RuntimeError(f"expected {expected} bytes of {pixel_format} from Pillow, got {len(pillow)}")
    alpha = image.getchannel("A").tobytes()
    encode_alpha = dxt3_alpha if pixel_format == "DXT3" else dxt5_alpha
    blocks = bytearray()
    for index in range(len(pillow) // 16):
        x, y = index % (width // 4) * 4, index // (width // 4) * 4
        values = [alpha[(y + row) * width + x + column] for row in range(4) for column in range(4)]
        blocks += encode_alpha(values) + pillow[index * 16 + 8:index * 16 + 16]
    return bytes(blocks)


def dxt3_alpha(values: list[int]) -> bytes:
    """4 bits a pixel, two to a byte, the first pixel in the low bits."""
    nibbles = [(value * 15 + 127) // 255 for value in values]
    return bytes(nibbles[i] | nibbles[i + 1] << 4 for i in range(0, 16, 2))


def dxt5_alpha(values: list[int]) -> bytes:
    """Two end values and a 3-bit index a pixel into the eight values they give. If the first is
    the larger, the other six are evenly between them; if not, four are, and the last two are 0
    and 255. Whichever fits the block better."""
    low, high = min(values), max(values)
    inner = [value for value in values if 0 < value < 255] or [0]
    candidates = [(min(inner), max(inner))]   # 0 and 255 come free
    if high > low:
        candidates.append((high, low))
    best = None
    for first, second in candidates:
        if first > second:
            palette = [first, second] + [((7 - k) * first + k * second) // 7 for k in range(1, 7)]
        else:
            palette = [first, second] + [((5 - k) * first + k * second) // 5 for k in range(1, 5)] + [0, 255]
        indices = [min(range(8), key=lambda i: abs(palette[i] - value)) for value in values]
        error = sum(abs(palette[i] - value) for i, value in zip(indices, values))
        if best is None or error < best[0]:
            best = (error, first, second, indices)
    _, first, second, indices = best
    bits = sum(index << (3 * i) for i, index in enumerate(indices))
    return bytes([first, second]) + bits.to_bytes(6, "little")


def write(image: Image.Image, encoding: str = "dxt3") -> bytes:
    image = image.convert("RGBA")
    width, height = image.size
    if not (is_power_of_two(width) and is_power_of_two(height)):
        raise ValueError(f"is {width}x{height}: textures have to be powers of two in each direction, like 256x128")
    kind, alpha_depth, alpha_encoding = ENCODINGS[encoding]
    if encoding == "raw":
        levels = [image.tobytes("raw", "BGRA")]
    else:
        levels = [dxt(level, encoding.upper()) for level in mipmaps(image)]
    if len(levels) > 16:
        raise ValueError(f"is {width}x{height}: too big for a BLP's 16 mipmap levels")
    offsets, sizes, offset = [], [], HEADER.size + PALETTE_SIZE
    for level in levels:
        offsets.append(offset)
        sizes.append(len(level))
        offset += len(level)
    padding = [0] * (16 - len(levels))
    header = HEADER.pack(b"BLP2", 1, kind, alpha_depth, alpha_encoding, int(len(levels) > 1), width, height,
                         *offsets, *padding, *sizes, *padding)
    return header + bytes(PALETTE_SIZE) + b"".join(levels)


def describe(data: bytes) -> str:
    kind, alpha_encoding = data[8], data[10]
    name = {3: "raw BGRA", 1: "palette"}.get(kind) or {0: "DXT1", 1: "DXT3", 7: "DXT5"}.get(alpha_encoding, "DXT?")
    width, height = struct.unpack_from("<II", data, 12)
    levels = sum(1 for offset in struct.unpack_from("<16I", data, 20) if offset)
    return f"{width}x{height}, {name}, {levels} mipmap level{'s' if levels != 1 else ''}"


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def export(files: list[Path], out_dir: Path) -> int:
    failed = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = out_dir / (path.stem + ".png")
        try:
            data = path.read_bytes()
            read(data).save(target)
        except (OSError, ValueError, NotImplementedError, struct.error) as error:
            print(f"{relative(path)}: can't read it: {error}")
            failed += 1
            continue
        print(f"{relative(path)} ({describe(data)}) -> {relative(target)}")
    return failed


def import_(files: list[Path], out_dir: Path, encoding: str) -> int:
    failed = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = out_dir / (path.stem + ".blp")
        try:
            with Image.open(path) as image:
                data = write(image, encoding)
            read(data)   # can be read back
        except (OSError, ValueError) as error:
            print(f"{relative(path)}: {error}")
            failed += 1
            continue
        replaced = target.exists()
        target.write_bytes(data)
        print(f"{relative(path)} -> {relative(target)} ({describe(data)}){' (replaced)' if replaced else ''}")
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    to_png = commands.add_parser("export", help="BLP -> PNG")
    to_png.add_argument("files", nargs="*", type=Path, help="BLP files (default: all of Textures/)")
    to_png.add_argument("--out-dir", type=Path, default=EXPORT_DIR, help="default: tools/out/textures")
    to_blp = commands.add_parser("import", help="PNG -> BLP")
    to_blp.add_argument("files", nargs="+", type=Path, help="images to convert")
    to_blp.add_argument("--out-dir", type=Path, default=TEXTURES, help="default: Textures/")
    to_blp.add_argument("--encoding", choices=ENCODINGS, default="dxt3", help="default: dxt3")
    args = parser.parse_args()

    if args.command == "export":
        failed = export(args.files or sorted(TEXTURES.glob("*.blp")), args.out_dir)
    else:
        failed = import_(args.files, args.out_dir, args.encoding)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
