"""Local copies of the base game's unit frame textures, from every current version of World of
Warcraft, as BLP and PNG.

Which textures: every one the unit frames draw in the art comparison (compare_unitframe_art.py),
in any of its rows, with or without the addon, so also those whose names the code puts together
(like "UI-PVP-"..factionGroup); and every texture and atlas that the unit frame UI files
(PlayerFrame*, TargetFrame*) name outright, like the bar fills and icons, which the comparison
doesn't draw. Each version's from its own build.

One copy of each distinct image goes in tools/out/textures/blizzard/: <name>.blp as the game has
it, and <name>.png to look at or edit (blp.py turns a PNG back into a BLP). A texture whose image
differs between versions gets a copy per image, with the versions in the file name. index.txt
says, for each, which versions have it, its FileDataIDs and game paths, and for an atlas texture,
where in it the atlases the unit frames use are.

The folder is rewritten on each run. It's Blizzard's art, so it stays local: tools/out/ isn't in
git.

Usage, from the repo root:
    python -m pip install -r tools/requirements.txt
    python tools/export_base_textures.py [--wow-dir "E:/Blizzard/World of Warcraft"] [--no-download]
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

import blp
import compare_unitframe_art as compare
import unitframe_ui
import wowfiles
from unitframe_ui import FrameArt
from wowfiles import MissingFile

OUT_DIR = compare.OUT_DIR / "textures" / "blizzard"
STRING = re.compile(r'"([^"\r\n]{3,200})"|\'([^\'\r\n]{3,200})\'')   # in the XML and the Lua
NOT_TEXTURES = (".lua", ".xml", ".toc")


@dataclass
class Use:
    fdid: int
    name: str | None     # as the UI code names the file (None for an atlas's texture)
    how: str             # "drawn" or "named"
    atlas: str | None = None


@dataclass
class Texture:
    data: bytes
    image: Image.Image
    names: list[str] = field(default_factory=list)   # as the code names it, then from the listfile
    versions: list[str] = field(default_factory=list)
    fdids: set[int] = field(default_factory=set)
    how: set[str] = field(default_factory=set)
    atlases: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)   # name: left, top, right, bottom
    file_name: str = ""


def stem(path: str) -> str:
    return Path(path.replace("\\", "/")).stem


def drawn(source, listfile, variant, art: compare.Art) -> list[Use]:
    """What the comparison's rows draw, with and without the addon."""
    flavor = unitframe_ui.FLAVORS[variant.flavor]
    uses = []
    for addon in (None, compare.ADDON):
        loaded = unitframe_ui.read_frame_art(source.files, listfile, flavor, art.atlas_size, addon)
        for frame in loaded.art.values():
            if not isinstance(frame, FrameArt):
                continue
            for piece in frame.pieces:
                if piece.local_file:
                    continue
                try:
                    fdid = art.atlases.fdid(piece.atlas) if piece.atlas else piece.fdid
                except MissingFile:
                    continue
                if fdid:
                    uses.append(Use(fdid, None if piece.atlas else stem(piece.file), "drawn", piece.atlas))
    return uses


def named(source, listfile, variant, art: compare.Art) -> list[Use]:
    """Texture paths and atlas names written out in the unit frame UI files."""
    flavor = unitframe_ui.FLAVORS[variant.flavor]
    _, paths = unitframe_ui._load_order(source.files, listfile, flavor)
    files = unitframe_ui.UIFiles(source.files, listfile)
    uses = []
    for _, content in files.in_load_order([path for path in paths if unitframe_ui.UI_FILE.search(path)]):
        for match in STRING.finditer(content.decode("utf-8", "replace")):
            value = (match.group(1) or match.group(2)).replace("\\\\", "\\")
            if value.lower().startswith("interface") and ("\\" in value or "/" in value):
                if value.lower().endswith(NOT_TEXTURES):
                    continue
                path = unitframe_ui.texture_file(value)
                fdid = listfile.find(path) or listfile.find(re.sub(r"\.tga$", ".blp", path, flags=re.I))
                if fdid:
                    uses.append(Use(fdid, stem(value), "named"))
                continue
            try:
                uses.append(Use(art.atlases.fdid(value), None, "named", value))
            except (MissingFile, KeyError):
                pass
    return uses


def atlas_box(art: compare.Art, name: str) -> tuple[int, int, int, int]:
    member = art.atlases.member(name)
    return (member["CommittedLeft"], member["CommittedTop"], member["CommittedRight"], member["CommittedBottom"])


def collect(args: argparse.Namespace) -> dict[str, Texture]:
    wow_dir = args.wow_dir or wowfiles.find_wow_dir()
    install = wowfiles.LocalInstall(wow_dir) if wow_dir else None
    print(f"World of Warcraft folder: {wow_dir or 'not found (use --wow-dir)'}")
    listfile = wowfiles.Listfile(compare.CACHE_DIR, allow_download=not args.no_download)
    textures: dict[str, Texture] = {}   # by image
    for variant in compare.VARIANTS:
        source, subtitle = compare.open_source(variant, install, not args.no_download)
        if source is None:
            print(f"{variant.title}: {subtitle}: skipped")
            continue
        art = compare.Art(source, variant.atlas_suffix)
        uses = []
        for find in (drawn, named):
            try:
                uses += find(source, listfile, variant, art)
            except (MissingFile, OSError) as error:
                print(f"{variant.title}: {error}")
        data = source.files({use.fdid for use in uses})
        count = 0
        for fdid in dict.fromkeys(use.fdid for use in uses):
            content = data.get(fdid)
            try:
                if not isinstance(content, bytes):
                    raise MissingFile(str(content) if content else "not in the build")
                image = blp.read(content)
            except (MissingFile, OSError, ValueError, NotImplementedError) as error:
                print(f"{variant.title}: FileDataID {fdid} ({listfile.path(fdid) or 'not in the listfile'}): {error}")
                continue
            key = hashlib.sha1(image.tobytes() + repr(image.size).encode()).hexdigest()
            texture = textures.setdefault(key, Texture(content, image))
            count += texture.versions[-1:] != [variant.title]
            if variant.title not in texture.versions:
                texture.versions.append(variant.title)
            texture.fdids.add(fdid)
            for use in uses:
                if use.fdid != fdid:
                    continue
                texture.how.add(use.how)
                if use.name and use.name not in texture.names:
                    texture.names.insert(sum(1 for name in texture.names if name != name.lower()), use.name)
                if use.atlas:
                    try:
                        texture.atlases.setdefault(use.atlas, atlas_box(art, use.atlas))
                    except MissingFile:
                        pass
            path = listfile.path(fdid)
            if path and stem(path) not in texture.names:
                texture.names.append(stem(path))
            if not texture.names:
                texture.names.append(str(fdid))
        print(f"{variant.title}: {subtitle}: {count} textures")
    return textures


def file_names(textures: dict[str, Texture]) -> None:
    """Each texture's first name, with its versions added when another image has the same name."""
    by_name: dict[str, list[Texture]] = {}
    for texture in textures.values():
        by_name.setdefault(texture.names[0].lower(), []).append(texture)
    for group in by_name.values():
        for texture in group:
            texture.file_name = texture.names[0] + (f" ({', '.join(texture.versions)})" if len(group) > 1 else "")


def write(textures: dict[str, Texture]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in [*OUT_DIR.glob("*.blp"), *OUT_DIR.glob("*.png"), *OUT_DIR.glob("index.txt")]:
        old.unlink()
    index = []
    for texture in sorted(textures.values(), key=lambda texture: texture.file_name.lower()):
        (OUT_DIR / f"{texture.file_name}.blp").write_bytes(texture.data)
        texture.image.save(OUT_DIR / f"{texture.file_name}.png")
        index.append(f"{texture.file_name}  ({blp.describe(texture.data) if texture.data[:4] == b'BLP2' else 'not a BLP2'})")
        index.append(f"    versions: {', '.join(texture.versions)}; {' and '.join(sorted(texture.how))} in the unit frame code")
        if len(texture.names) > 1:
            index.append(f"    also named: {', '.join(texture.names[1:])}")
        for fdid in sorted(texture.fdids):
            index.append(f"    FileDataID {fdid}")
        for name, (left, top, right, bottom) in sorted(texture.atlases.items(), key=lambda item: item[0].lower()):
            index.append(f"    atlas {name}: x {left}-{right}, y {top}-{bottom}")
    (OUT_DIR / "index.txt").write_text("\n".join(index) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wow-dir", type=Path, help="World of Warcraft folder (default: found on your drives)")
    parser.add_argument("--no-download", action="store_true", help="don't use wago.tools, only what's installed or cached")
    args = parser.parse_args()
    textures = collect(args)
    file_names(textures)
    write(textures)
    print(f"\n{len(textures)} distinct textures, as .blp and .png, in {OUT_DIR}, listed in index.txt")


if __name__ == "__main__":
    main()
