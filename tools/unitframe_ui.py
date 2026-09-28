"""What each game build's unit frames draw, read from that build's own UI code.

The build's Blizzard_UnitFrame TOC says which files the client loads (the Classic versions load
Classic\\*, Retail and WoW Forever load Mainline\\*, and Forever adds its Camelot\\* overrides). The
XML in them gives each texture: its template, file or atlas, texture coordinates, size, anchors and
draw layer. The Lua that runs when the frame loads (its OnLoad script) and when it shows a unit
(CheckClassification, and the PvP flag code) then changes some of them.

That Lua is run by a small interpreter that understands just enough: if/elseif/else, locals and
fields, returns, tables, string concatenation, the Set* / Show / Hide calls on textures, and calls
from one function into another (at statement level, only the OnLoad chain is followed). The game
API calls that matter are answered for the situation being drawn (the unit's classification, PvP
flag and faction); any other unknown value counts as true, and fields the code never set are nil,
as in Lua. Text has no size here, so art anchored to a font string lands at the string's anchor.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field

from wowfiles import MissingFile

UI_DIR = "Interface/AddOns/Blizzard_UnitFrame/"


@dataclass(frozen=True)
class Flavor:
    family: str                     # the TOC's [Family] folder
    game: str                       # the TOC's [Game] folder
    game_types: frozenset[str]      # what AllowLoadGameType / ExcludeLoadGameType match
    toc_suffixes: tuple[str, ...]   # Blizzard_UnitFrame_<suffix>.toc, tried before Blizzard_UnitFrame.toc

    @property
    def classic(self) -> bool:
        return self.family == "Classic"


def _flavor(family: str, game: str, types: str, suffixes: str) -> Flavor:
    return Flavor(family, game, frozenset(types.split()), tuple(suffixes.split()))


FLAVORS = {
    "vanilla": _flavor("Classic", "Vanilla", "classic vanilla", "Vanilla Classic"),
    "tbc": _flavor("Classic", "TBC", "classic tbc", "TBC BCC Classic"),
    "wrath": _flavor("Classic", "Wrath", "classic wrath", "Wrath WOTLKC Classic"),
    "mists": _flavor("Classic", "Mists", "classic mists", "Mists Classic"),
    "retail": _flavor("Mainline", "Standard", "mainline standard", "Mainline Standard"),
    "forever": _flavor("Mainline", "Camelot", "mainline camelot", "Camelot Mainline"),
}

# Textures are picked by parentKey, or by name without the frame's name in front ("$parentTexture",
# "PlayerFrameTexture" and "PlayerStatusTexture" become "texture" and "statustexture").
FRAME_ART = frozenset({"texture", "frametexture", "bossportraitframetexture", "levelbackgroundcircle"})
PVP_ART = frozenset({"pvpicon", "pvpbackgroundcircle", "pvpbackgroundicon", "highleveltexture"})
MAIN_ART = ("texture", "statustexture")  # the frame's own texture, as opposed to what's drawn over it


@dataclass(frozen=True)
class Shot:
    """One row of the comparison: a frame, in a situation."""
    frame: str
    keys: frozenset[str]
    calls: tuple[str, ...] = ()     # run after the frame's OnLoad: its mixins' methods, or global functions
    classification: str = "normal"
    pvp: bool = False               # PvP flagged (Alliance), and too high level to show the level


def _target(classification: str = "normal", pvp: bool = False) -> Shot:
    calls = ("CheckClassification",) + (("CheckFaction",) if pvp else ())
    return Shot("TargetFrame", FRAME_ART | (PVP_ART if pvp else frozenset()), calls, classification, pvp)


SHOTS = {
    "player": Shot("PlayerFrame", FRAME_ART),
    "player_pvp": Shot("PlayerFrame", FRAME_ART | PVP_ART, ("PlayerFrame_UpdatePvPStatus",), pvp=True),
    "status": Shot("PlayerFrame", frozenset({"statustexture"})),
    "target": _target(),
    "target_pvp": _target(pvp=True),
    "elite": _target("elite"),
    "rare": _target("rare"),
    "rareelite": _target("rareelite"),
    "worldboss": _target("worldboss"),
    "tot": Shot("TargetFrameToT", FRAME_ART),
    "boss": Shot("Boss1TargetFrame", FRAME_ART),
}

# Mainline shows the PvP flag through UnitFrameUtil, with the art in the build's PvPIndicatorStyle
# table, on the textures the frame's GetPvPIndicatorElements returns.
PVP_ELEMENTS = ("GetPvPIndicatorElements", "PlayerFrame_GetPvPIndicatorElements")

UI_FILE = re.compile(r"(?:^|/)(?:PlayerFrame|TargetFrame(?!Aura)|UnitFramePvPIndicatorStyle)\w*\.(?:xml|lua)$", re.I)


@dataclass(frozen=True)
class Piece:
    """One texture, as the frame draws it."""
    key: str
    atlas: str | None
    file: str | None                            # the path the UI code gives
    fdid: int | None
    coords: tuple[float, float, float, float]   # left, right, top, bottom; left > right is mirrored
    rect: tuple[float, float, float, float]     # left, top, right, bottom; 0,0 = the frame's top-left
    additive: bool

    @property
    def name(self) -> str:
        if self.atlas:
            return self.atlas
        return re.split(r"[\\/]", self.file)[-1] if self.file else f"file {self.fdid}"

    @property
    def size(self) -> tuple[int, int]:
        return round(self.rect[2] - self.rect[0]), round(self.rect[3] - self.rect[1])


@dataclass(frozen=True)
class FrameArt:
    pieces: tuple[Piece, ...]
    scale: float = 1.0   # the frame's own scale, when its code sets one


@dataclass
class Loaded:
    toc: str
    art: dict[str, FrameArt | MissingFile]
    unreadable: list[str] = field(default_factory=list)   # UI files the TOC lists that couldn't be read


def read_frame_art(get_files, listfile, flavor: Flavor, atlas_size) -> Loaded:
    """get_files(fdids) returns {fdid: bytes or MissingFile}; atlas_size(name) returns (width, height)."""
    toc, paths = _load_order(get_files, listfile, flavor)
    fdids, unreadable = {}, []
    for path in paths:
        if UI_FILE.search(path):
            try:
                fdids[path] = listfile.fdid(UI_DIR + path)
            except MissingFile:
                unreadable.append(path)
    data = get_files(list(fdids.values()))
    xml, lua = [], []
    for path, fdid in fdids.items():
        content = data.get(fdid)
        if not isinstance(content, bytes):
            unreadable.append(path)
        elif path.lower().endswith(".xml"):
            xml.append(content)
        else:
            lua.append(content.decode("utf-8", "replace"))

    ui, code = UI(xml), Lua(lua)
    art = {}
    for row, shot in SHOTS.items():
        try:
            art[row] = _shot(ui, code, shot, listfile, atlas_size)
        except MissingFile as error:
            art[row] = error
    return Loaded(toc, art, unreadable)


def _load_order(get_files, listfile, flavor: Flavor) -> tuple[str, list[str]]:
    """The TOC the client picks, and the files it loads, in order, relative to the addon folder."""
    names = [f"Blizzard_UnitFrame_{suffix}.toc" for suffix in flavor.toc_suffixes] + ["Blizzard_UnitFrame.toc"]
    fdids = {}
    for name in names:
        try:
            fdids[name] = listfile.fdid(UI_DIR + name)
        except MissingFile:
            pass
    data = get_files(list(fdids.values()))
    for name in names:
        content = data.get(fdids.get(name))
        if isinstance(content, bytes):
            allowed, files = parse_toc(content.decode("utf-8", "replace"), flavor)
            if allowed:
                return name, files
    raise MissingFile("no Blizzard_UnitFrame TOC for this version")


def parse_toc(text: str, flavor: Flavor) -> tuple[bool, list[str]]:
    def types(values: str) -> set[str]:
        return {value.strip().lower() for value in values.split(",") if value.strip()}

    allowed, files = True, []
    for line in text.splitlines():
        line = line.strip()
        header = re.match(r"##\s*AllowLoadGameType\s*:\s*(.+)", line, re.I)
        if header and not types(header.group(1)) & flavor.game_types:
            allowed = False
        if not line or line.startswith("#"):
            continue
        path, rest = re.match(r"(\S+)\s*(.*)", line).groups()
        load = True
        for directive, values in re.findall(r"\[(\w+)\s+([^\]]*)\]", rest):
            if directive.lower() == "allowloadgametype" and not types(values) & flavor.game_types:
                load = False
            if directive.lower() == "excludeloadgametype" and types(values) & flavor.game_types:
                load = False
        if load:
            files.append(path.replace("[Family]", flavor.family).replace("[Game]", flavor.game).replace("\\", "/"))
    return allowed, files


def _shot(ui: UI, lua: Lua, shot: Shot, listfile, atlas_size) -> FrameArt:
    root = ui.instance(shot.frame)
    context = Context(lua, root, {
        "UnitClassification": shot.classification,
        "UnitIsBossMob": shot.classification == "worldboss",
        "UnitFactionGroup": "Alliance",
        "UnitIsPVP": shot.pvp,
        "UnitIsPVPFreeForAll": False,
        "UnitIsMercenary": False,
    })
    context.run_script("OnLoad")
    for name in shot.calls:
        context.call(name)
    if shot.pvp:
        context.pvp_indicator()

    pieces = []
    layout = Layout(root, atlas_size)
    for region in root.drawable():
        key = region.short_key(root)
        if key not in shot.keys or not (region.atlas or region.file or region.fdid):
            continue
        forced = shot.pvp and key == "highleveltexture"
        if not (forced and region.shown or region.visible()) or region.alpha == 0:
            continue
        rect = layout.screen_rect(region)
        if rect is None or rect[2] - rect[0] < 0.5 or rect[3] - rect[1] < 0.5:
            continue
        fdid = region.fdid
        if fdid is None and region.file:
            fdid = listfile.fdid(texture_file(region.file))
        pieces.append((region.order, Piece(key, region.atlas, region.file, fdid, region.coords, rect, region.additive)))
    if not pieces:
        raise MissingFile(f"{shot.frame} draws none of its frame art")
    pieces.sort(key=lambda item: item[0])
    return FrameArt(tuple(piece for _, piece in pieces), root.scale)


def texture_file(path: str) -> str:
    return path if re.search(r"\.\w{3,4}$", path) else path + ".blp"


# --- XML ------------------------------------------------------------------------------------------

LAYERS = {"BACKGROUND": 0, "BORDER": 1, "ARTWORK": 2, "OVERLAY": 3, "HIGHLIGHT": 4}
POINTS = {"TOPLEFT": (0, 1), "TOP": (0.5, 1), "TOPRIGHT": (1, 1), "LEFT": (0, 0.5), "CENTER": (0.5, 0.5),
          "RIGHT": (1, 0.5), "BOTTOMLEFT": (0, 0), "BOTTOM": (0.5, 0), "BOTTOMRIGHT": (1, 0)}
REGION_TAGS = {"Texture", "FontString", "Line"}


@dataclass
class Anchor:
    point: str
    relative_point: str
    x: float = 0.0
    y: float = 0.0
    relative_to: str | None = None       # a global name
    relative_key: str | None = None      # "$parent.$parent.Key"
    relative: Region | None = None       # set by Lua


class Region:
    """A frame or texture in one copy of a frame."""

    def __init__(self, tag: str, attrs: dict, parent: Region | None, order: tuple):
        self.tag, self.attrs, self.parent, self.order = tag, attrs, parent, order
        self.key = attrs.get("parentKey")
        self.name = None
        self.children: list[Region] = []
        self.keyed: dict[str, Region] = {}
        self.fields: dict = {}
        self.scripts: dict = {}
        self.mixins: list[str] = []
        self.size: tuple[float | None, float | None] = (None, None)
        self.anchors: dict[str, Anchor] = {}
        self.all_points = attrs.get("setAllPoints") == "true"
        self.coords = (0.0, 1.0, 0.0, 1.0)
        self.atlas = attrs.get("atlas")
        self.file = attrs.get("file")
        self.fdid = None
        self.size_atlas = self.atlas if attrs.get("useAtlasSize") == "true" else None
        self.shown = attrs.get("hidden") != "true"
        self.alpha = float(attrs.get("alpha", 1))
        self.scale = float(attrs.get("scale", 1))
        self.additive = attrs.get("alphaMode", "").upper() == "ADD"

    def __repr__(self) -> str:
        return f"<{self.tag} {self.name or self.key}>"

    def get(self, name: str):
        if name in self.fields:
            return self.fields[name]
        return self.keyed.get(name)

    def top(self) -> Region:
        region = self
        while region.parent is not None:
            region = region.parent
        return region

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def find_name(self, name: str) -> Region | None:
        name = name.lower()
        return next((region for region in self.walk() if region.name and region.name.lower() == name), None)

    def drawable(self):
        """The textures this frame draws itself, not those of the unit frames and bars inside it."""
        for child in self.children:
            if child.tag in REGION_TAGS:
                yield child
            elif child.tag == "Frame":
                yield from child.drawable()

    def visible(self) -> bool:
        region = self
        while region is not None:
            if not region.shown:
                return False
            region = region.parent
        return True

    def named_ancestor(self) -> str | None:
        region = self.parent
        while region is not None and not region.name:
            region = region.parent
        return region.name if region is not None else None

    def short_key(self, root: Region) -> str:
        if self.key:
            return self.key.lower()
        name = self.name or ""
        prefixes = [self.named_ancestor(), root.name]
        if root.name and root.name.endswith("Frame"):
            prefixes.append(root.name[:-len("Frame")])
        best = max((p for p in prefixes if p and len(name) > len(p) and name.lower().startswith(p.lower())), key=len, default="")
        return name[len(best):].lower()


class UI:
    """The XML files, in load order: their templates, and the frames they create."""

    def __init__(self, files: list[bytes]):
        self.templates: dict[str, ElementTree.Element] = {}
        self.frames: dict[str, ElementTree.Element] = {}
        for data in files:
            root = ElementTree.fromstring(data)
            for element in root.iter():
                element.tag = element.tag.rsplit("}", 1)[-1]
            for element in root:
                name = (element.get("name") or "").lower()
                if not name:
                    continue
                if element.get("virtual") == "true":
                    self.templates[name] = element
                elif element.tag not in REGION_TAGS:
                    self.frames[name] = element
        self._count = 0

    def instance(self, name: str) -> Region:
        """A new copy of the frame with this global name."""
        element = self.frames.get(name.lower())
        if element is not None:
            return self._build(element, None, 0, (2, 0))
        for element in self.frames.values():   # a frame that's part of another, like Retail's TargetFrameToT
            found = self._build(element, None, 0, (2, 0)).find_name(name)
            if found is not None and found.tag not in REGION_TAGS:
                return found
        raise MissingFile(f"no {name} in the UI files")

    def _chain(self, element, seen=()) -> list:
        chain = []
        for name in (element.get("inherits") or "").split(","):
            template = self.templates.get(name.strip().lower())
            if template is not None and template not in seen:
                chain += self._chain(template, seen + (template,))
        return chain + [element]

    def _build(self, element, parent: Region | None, level: int, layer: tuple) -> Region:
        chain = self._chain(element)
        attrs, mixins = {}, []
        for source in chain:
            attrs.update(source.attrib)
            mixins += [mixin.strip() for mixin in (source.get("mixin") or "").split(",") if mixin.strip()]
        self._count += 1
        region = Region(element.tag, attrs, parent, (level, *layer, self._count))
        region.mixins = list(dict.fromkeys(mixins))
        if attrs.get("name"):
            region.name = re.sub(r"\$parent", region.named_ancestor() or "", attrs["name"], flags=re.I)

        for source in chain:
            for child in source:
                if child.tag == "Size":
                    width, height = xml_size(child)
                    region.size = (width if width is not None else region.size[0],
                                   height if height is not None else region.size[1])
                elif child.tag == "Anchors":
                    for anchor in child.findall("Anchor"):
                        parsed = xml_anchor(anchor, region)
                        region.anchors[parsed.point] = parsed
                elif child.tag == "TexCoords":
                    region.coords = tuple(float(child.get(side, default)) for side, default in
                                          (("left", 0), ("right", 1), ("top", 0), ("bottom", 1)))
                elif child.tag == "KeyValues":
                    for value in child.findall("KeyValue"):
                        region.fields[value.get("key")] = key_value(value)
                elif child.tag == "Scripts":
                    for script in child:
                        region.scripts[script.tag] = script

        for source in chain:
            for layers in source.findall("Layers"):
                for layer_element in layers.findall("Layer"):
                    order = (LAYERS.get(layer_element.get("level", "ARTWORK").upper(), 2),
                             int(layer_element.get("textureSubLevel", 0)))
                    for child in layer_element:
                        if child.tag in REGION_TAGS:
                            self._add(region, self._build(child, region, level, order))
            frames = source.find("Frames")
            if frames is not None:
                for child in frames:
                    child_level = level if child.get("useParentLevel") == "true" else level + 1
                    self._add(region, self._build(child, region, child_level, (2, 0)))
        return region

    @staticmethod
    def _add(parent: Region, child: Region) -> None:
        parent.children.append(child)
        if child.key:
            parent.keyed[child.key] = child


def xml_size(element) -> tuple[float | None, float | None]:
    dimension = element.find("AbsDimension")
    source = dimension if dimension is not None else element
    x, y = source.get("x"), source.get("y")
    return (float(x) if x is not None else None, float(y) if y is not None else None)


def xml_anchor(element, region: Region) -> Anchor:
    point = element.get("point", "CENTER").upper()
    offset = element.find("Offset/AbsDimension")
    if offset is None:
        offset = element.find("Offset")
    source = offset if offset is not None else element
    relative_to = element.get("relativeTo")
    if relative_to:
        relative_to = re.sub(r"\$parent", region.named_ancestor() or "", relative_to, flags=re.I)
    return Anchor(point, (element.get("relativePoint") or point).upper(), float(source.get("x", 0)),
                  float(source.get("y", 0)), relative_to, element.get("relativeKey"))


def key_value(element):
    value, kind = element.get("value"), (element.get("type") or "string").lower()
    if kind == "boolean":
        return value == "true"
    if kind == "number":
        return float(value)
    if kind == "string":
        return value
    return UNKNOWN


class Layout:
    """Where each region is, from its anchors and size, in the frame's coordinates."""

    def __init__(self, root: Region, atlas_size):
        self.root, self.atlas_size, self.cache = root, atlas_size, {}

    def screen_rect(self, region: Region) -> tuple | None:
        rect, frame = self.rect(region), self.rect(self.root)
        if rect is None:
            return None
        left, bottom, right, top = rect
        return left, frame[3] - top, right, frame[3] - bottom

    def size(self, region: Region) -> tuple[float | None, float | None]:
        if region.size_atlas:
            try:
                return tuple(float(n) for n in self.atlas_size(region.size_atlas))
            except MissingFile:
                pass
        return region.size

    def rect(self, region: Region) -> tuple | None:
        """left, bottom, right, top (y up, as the game has it)."""
        if region is self.root:
            width, height = self.size(region)
            return 0.0, 0.0, width or 0.0, height or 0.0
        if region in self.cache:
            return self.cache[region]
        self.cache[region] = None   # an anchor loop places nothing
        self.cache[region] = result = self._rect(region)
        return result

    def _rect(self, region: Region) -> tuple | None:
        if region.parent is None:
            return None
        anchors = list(region.anchors.values())
        if not anchors:
            if region.all_points is not False:
                target = region.all_points if isinstance(region.all_points, Region) else region.parent
                return self.rect(target)
            anchors = [Anchor("TOPLEFT", "TOPLEFT")]   # unanchored: the game puts it at the parent's top-left

        width, height = self.size(region)
        scale = region.scale
        xs, ys = [], []
        for anchor in anchors:
            target = self.relative(anchor, region)
            rect = self.rect(target) if target is not None else None
            if rect is None:
                continue
            fx, fy = POINTS.get(anchor.relative_point, (0.5, 0.5))
            px, py = POINTS.get(anchor.point, (0.5, 0.5))
            xs.append((px, rect[0] + fx * (rect[2] - rect[0]) + anchor.x * scale))
            ys.append((py, rect[1] + fy * (rect[3] - rect[1]) + anchor.y * scale))
        horizontal = solve(xs, width * scale if width is not None else None)
        vertical = solve(ys, height * scale if height is not None else None)
        if horizontal is None or vertical is None:
            return None
        return horizontal[0], vertical[0], horizontal[1], vertical[1]

    @staticmethod
    def relative(anchor: Anchor, region: Region) -> Region | None:
        if anchor.relative is not None:
            return anchor.relative
        if anchor.relative_key:
            current = region
            for part in anchor.relative_key.split("."):
                if current is None:
                    return None
                current = current.parent if part.lower() == "$parent" else current.get(part)
            return current if isinstance(current, Region) else None
        if anchor.relative_to:
            return region.top().find_name(anchor.relative_to)
        return region.parent


def solve(constraints: list[tuple[float, float]], length: float | None) -> tuple[float, float] | None:
    """The start and end of a span, from where points on it are (fraction along it, position)."""
    points = dict(constraints)
    if not points:
        return None
    if len(points) >= 2:
        (f1, p1), (f2, p2) = min(points.items()), max(points.items())
        length = (p2 - p1) / (f2 - f1)
        return p1 - f1 * length, p1 - f1 * length + length
    (fraction, position), = points.items()
    length = length or 0.0
    return position - fraction * length, position - fraction * length + length


# --- Lua ------------------------------------------------------------------------------------------

class Unknown:
    """A value the interpreter can't know. It counts as true and equals nothing."""

    def __repr__(self) -> str:
        return "<unknown>"


UNKNOWN = Unknown()
GLOBALS = object()    # _G
LUA_KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in",
                "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}
KEYWORD = re.compile(r"\b(if|elseif|else|then|end|do|function|repeat|until|return)\b")
BLOCK = re.compile(r"\b(function|if|do|repeat|end|until)\b")
ASSIGNMENT = re.compile(r"(?m)(?:^|(?<=then)|(?<=else)|(?<=\bdo)|(?<=;))[ \t]*(local[ \t]+)?"
                        r"((?:[A-Za-z_][\w.]*(?:\[[^\]\n]*\])*)(?:[ \t]*,[ \t]*[A-Za-z_][\w.]*)*)[ \t]*=(?!=)")
LOCAL_DECLARATION = re.compile(r"(?m)^[ \t]*local[ \t]+([A-Za-z_][\w \t,]*?)[ \t]*;?[ \t]*$")
CALL = re.compile(r"(?<![\w.:])[A-Za-z_]\w*(?:[ \t]*(?:[.:][ \t]*[A-Za-z_]\w*|\[[^\]\n]*\]))*[ \t]*\(")
ONLOAD = re.compile(r"OnLoad", re.I)
REGION_METHODS = {"SetAtlas", "SetTexture", "SetTexCoord", "SetPoint", "ClearAllPoints", "SetAllPoints", "Show",
                  "Hide", "SetShown", "SetScale", "SetSize", "SetWidth", "SetHeight", "SetAlpha", "GetName",
                  "IsShown", "GetParent"}


def truthy(value) -> bool:
    return value is not None and value is not False


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), text)


def blank_lua(text: str) -> str:
    """The code with comments and string contents replaced by spaces (same length, same lines),
    so keywords and brackets are only found in code."""
    out = list(text)
    i, n = 0, len(text)

    def blank(start: int, stop: int) -> None:
        for j in range(start, min(stop, n)):
            if out[j] != "\n":
                out[j] = " "

    while i < n:
        long_bracket = re.match(r"(--)?\[(=*)\[", text[i:i + 12])
        if long_bracket:
            close = "]" + long_bracket.group(2) + "]"
            stop = text.find(close, i + long_bracket.end())
            stop = n if stop < 0 else stop + len(close)
            blank(i, stop)
            i = stop
        elif text.startswith("--", i):
            stop = text.find("\n", i)
            stop = n if stop < 0 else stop
            blank(i, stop)
            i = stop
        elif text[i] in "\"'":
            j = i + 1
            while j < n and text[j] != text[i] and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
        else:
            i += 1
    return "".join(out)


def split_top_level(text: str, separator: str = ",") -> list[str]:
    parts, depth, current, quote, escaped = [], 0, "", None, False
    for char in text:
        if quote:
            current += char
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def statement_end(code: str, position: int, stop: int) -> int:
    depth = 0
    for i in range(position, stop):
        char = code[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return i
        elif depth == 0 and char in "\n;":
            return i
    return stop


def matching_paren(code: str, open_at: int, stop: int) -> int:
    depth = 0
    for i in range(open_at, stop):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return stop


@dataclass
class Function:
    params: list[str]
    method: bool          # defined with ":", so it has self
    events: list


class Lua:
    """The Lua files, in load order: their functions and file-level tables."""

    def __init__(self, sources: list[str]):
        self.files = [(text, blank_lua(text)) for text in sources]
        self.tables: dict[str, dict] = {}
        for text, code in self.files:
            self._read_tables(text, code)
        self._functions: dict[str, Function | None] = {}

    def _read_tables(self, text: str, code: str) -> None:
        literal = r'("(?:[^"\\\n]|\\.)*"|true|false|-?\d+(?:\.\d+)?)'
        for match in re.finditer(r"(?m)^(?:local[ \t]+)?([\w.]+)[ \t]*=[ \t]*\{", code):
            body_end = code.find("}", match.end())
            entries = {key: parse_literal(value) for key, value in
                       re.findall(r"(\w+)\s*=\s*" + literal, text[match.end():body_end])}
            if entries:
                self.tables[match.group(1).rsplit(".", 1)[-1]] = entries
        for match in re.finditer(r'(?m)^(\w+)(?:\[\s*"(\w+)"\s*\]|\.(\w+))[ \t]*=[ \t]*' + literal, text):
            table = self.tables.get(match.group(1))
            if table is not None and code[match.start()] == text[match.start()]:
                table[match.group(2) or match.group(3)] = parse_literal(match.group(4))

    def has(self, name: str) -> bool:
        return self.function(name) is not None

    def function(self, name: str) -> Function | None:
        if name not in self._functions:
            self._functions[name] = self._compile(name)
        return self._functions[name]

    def _compile(self, name: str) -> Function | None:
        parts = re.split(r"[.:]", name)
        header = re.compile(r"\bfunction\s+" + r"\s*[.:]\s*".join(map(re.escape, parts)) + r"\s*\(([^)]*)\)")
        for text, code in reversed(self.files):   # the last file loaded wins
            matches = list(header.finditer(code))
            if not matches:
                continue
            match = matches[-1]
            depth, stop = 1, len(code)
            for block in BLOCK.finditer(code, match.end()):
                depth += -1 if block.group(1) in ("end", "until") else 1
                if depth == 0:
                    stop = block.start()
                    break
            params = [param.strip() for param in match.group(1).split(",") if param.strip()]
            method = ":" in match.group(0).split("(")[0]
            return Function(params, method, compile_body(text, code, match.end(), stop))
        return None

    def run(self, name: str, context: Context, args: list, self_value=None) -> list:
        function = self.function(name)
        if function is None or len(context.stack) > 16:
            return []
        env = {"self": self_value if self_value is not None else context.root} if function.method else {}
        for i, param in enumerate(function.params):
            if param != "...":
                env[param] = args[i] if i < len(args) else None
        context.stack.append(name)
        try:
            return execute(function.events, self, context, env)
        finally:
            context.stack.pop()

    def run_snippet(self, text: str, context: Context) -> None:
        code = blank_lua(text)
        execute(compile_body(text, code, 0, len(code)), self, context, {"self": context.root})


def parse_literal(value: str):
    if value.startswith('"'):
        return unescape(value[1:-1])
    if value in ("true", "false"):
        return value == "true"
    return float(value)


def compile_body(text: str, code: str, start: int, stop: int) -> list:
    """The body's statements in order, as (position, kind, data)."""
    events = []
    keywords = list(KEYWORD.finditer(code, start, stop))
    for k, keyword in enumerate(keywords):
        word = keyword.group(1)
        if word in ("if", "elseif"):
            then = next((m for m in keywords[k + 1:] if m.group(1) == "then"), None)
            events.append((keyword.start(), word, text[keyword.end():then.start() if then else stop]))
        elif word in ("else", "end", "do", "repeat", "until", "function"):
            events.append((keyword.start(), word, None))
        elif word == "return":
            events.append((keyword.start(), "return", text[keyword.end():statement_end(code, keyword.end(), stop)]))

    for match in ASSIGNMENT.finditer(code, start, stop):
        targets = match.group(2)
        if targets.split(".")[0].strip() in LUA_KEYWORDS:
            continue
        rhs = text[match.end():statement_end(code, match.end(), stop)]
        events.append((match.start(2), "assign", (bool(match.group(1)), split_top_level(targets), rhs)))
    for match in LOCAL_DECLARATION.finditer(code, start, stop):
        if "=" not in match.group(0) and not match.group(1).startswith("function"):
            events.append((match.start(1), "assign", (True, split_top_level(match.group(1)), None)))

    for match in CALL.finditer(code, start, stop):
        first = re.match(r"\w+", match.group(0)).group(0)
        if first in LUA_KEYWORDS:
            continue
        before = code[start:match.start()].rstrip(" \t")
        if before and not before.endswith(("\n", ";")) and not re.search(r"\b(then|else|do|end)$", before):
            continue
        close = matching_paren(code, match.end() - 1, stop)
        events.append((match.start(), "call", text[match.start():close + 1]))

    events.sort(key=lambda event: event[0])
    return events


def execute(events: list, lua: Lua, context: Context, env: dict) -> list:
    blocks = [[True, True, True]]   # [enclosing block runs, this branch runs, a branch was taken]
    for _, kind, data in events:
        parent, active, taken = blocks[-1]
        if kind == "if":
            runs = active and truthy(evaluate(data, lua, context, env))
            blocks.append([active, runs, runs])
        elif kind == "elseif":
            runs = parent and not taken and truthy(evaluate(data, lua, context, env))
            blocks[-1][1:] = [runs, taken or runs]
        elif kind == "else":
            blocks[-1][1:] = [parent and not taken, True]
        elif kind in ("do", "repeat"):
            blocks.append([active, active, True])
        elif kind == "function":   # a function defined in here runs later, if at all
            blocks.append([False, False, True])
        elif kind in ("end", "until"):
            if len(blocks) == 1:
                break
            blocks.pop()
        elif not active:
            continue
        elif kind == "return":
            return evaluate_list(data, lua, context, env)
        elif kind == "assign":
            assign(*data, lua, context, env)
        elif kind == "call":
            Parser(data, lua, context, env, statement=True).expression()
    return []


def evaluate(text: str, lua: Lua, context: Context, env: dict):
    return Parser(text, lua, context, env).expression()


def evaluate_list(text: str, lua: Lua, context: Context, env: dict) -> list:
    values = []
    parts = split_top_level(text)
    for i, part in enumerate(parts):
        parser = Parser(part, lua, context, env)
        value = parser.expression()
        if i == len(parts) - 1 and parser.whole_call is not None:
            values += parser.whole_call   # a call at the end of a list gives all its values
        else:
            values.append(value)
    return values


def assign(local: bool, targets: list[str], rhs: str | None, lua: Lua, context: Context, env: dict) -> None:
    values = evaluate_list(rhs, lua, context, env) if rhs is not None else []
    for i, target in enumerate(targets):
        value = values[i] if i < len(values) else None
        if local or (re.fullmatch(r"\w+", target) and target in env):
            env[target] = value
            continue
        match = re.fullmatch(r"(.+?)\s*(?:\.\s*(\w+)|\[(.+)\])", target)
        if not match:
            continue   # a global: nothing reads it back
        container = evaluate(match.group(1), lua, context, env)
        key = match.group(2) if match.group(2) else evaluate(match.group(3), lua, context, env)
        if isinstance(container, Region) and isinstance(key, str):
            container.fields[key] = value
        elif isinstance(container, dict):
            container[key] = value


TOKEN = re.compile(r"""\s*(?:(0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')"""
                   r"""|([A-Za-z_]\w*)|(\.\.\.|\.\.|==|~=|<=|>=|\S))""")
BINARY = {"or": 0, "and": 1, "<": 2, ">": 2, "<=": 2, ">=": 2, "~=": 2, "==": 2, "..": 3, "+": 4, "-": 4,
          "*": 5, "/": 5, "%": 5, "^": 7}


class Parser:
    """Evaluates one Lua expression (or a call statement) as it's parsed."""

    def __init__(self, text: str, lua: Lua, context: Context, env: dict, statement: bool = False):
        self.tokens = []   # (kind, value): kind is "number", "string", "name" or "op"
        for match in TOKEN.finditer(text):
            number, string, name, op = match.groups()
            if number is not None:
                self.tokens.append(("number", float(int(number, 16)) if number.startswith("0x") else float(number)))
            elif string is not None:
                self.tokens.append(("string", unescape(string[1:-1])))
            elif name is not None:
                self.tokens.append(("op" if name in LUA_KEYWORDS else "name", name))
            elif op is not None:
                self.tokens.append(("op", op))
        self.i, self.depth = 0, 0
        self.lua, self.context, self.env, self.statement = lua, context, env, statement
        self.whole_call = None   # every value of the call, when the expression is just one call

    def peek(self, offset: int = 0) -> tuple:
        position = self.i + offset
        return self.tokens[position] if position < len(self.tokens) else (None, None)

    def take(self) -> tuple:
        token = self.peek()
        self.i += 1
        return token

    def accept(self, op: str) -> bool:
        if self.peek() == ("op", op):
            self.i += 1
            return True
        return False

    def expression(self, min_precedence: int = 0):
        left = self.unary()
        while True:
            kind, op = self.peek()
            precedence = BINARY.get(op) if kind == "op" else None
            if precedence is None or precedence < min_precedence:
                return left
            self.i += 1
            right = self.expression(precedence if op in ("..", "^") else precedence + 1)
            left = binary(op, left, right)

    def unary(self):
        if self.accept("not"):
            return not truthy(self.expression(6))
        if self.accept("-"):
            value = self.expression(6)
            return -value if is_number(value) else UNKNOWN
        if self.accept("#"):
            self.expression(6)
            return UNKNOWN
        return self.suffixed()

    def suffixed(self):
        start = self.i
        value, path = self.primary()
        while True:
            kind, token = self.peek()
            if (kind, token) == ("op", "."):
                self.i += 1
                name = self.take()[1]
                value = self.field(value, name)
                path = f"{path}.{name}" if path else None
            elif (kind, token) == ("op", "["):
                self.i += 1
                self.depth += 1
                key = self.expression()
                self.depth -= 1
                self.accept("]")
                value, path = self.index(value, key), None
            elif (kind, token) == ("op", ":"):
                self.i += 1
                name = self.take()[1]
                statement = self.statement and self.depth == 0
                args, texts = self.arguments()
                values = self.method(value, name, args, texts, statement)
                value, path = self.called(start, values)
            elif (kind, token) == ("op", "(") or kind == "string" or (kind, token) == ("op", "{"):
                statement = self.statement and self.depth == 0
                args, texts = self.arguments()
                values = self.call(path, args, statement)
                value, path = self.called(start, values)
            else:
                return value

    def called(self, start: int, values: list) -> tuple:
        self.whole_call = values if start == 0 and self.i >= len(self.tokens) else None
        return (values[0] if values else None), None

    def arguments(self) -> tuple[list, list[str]]:
        kind, token = self.peek()
        if kind == "string":
            self.i += 1
            return [token], [repr(token)]
        if (kind, token) == ("op", "{"):
            self.i += 1
            return [self.table()], ["{}"]
        self.i += 1   # (
        self.depth += 1
        args, texts = [], []
        while self.peek()[0] is not None and not self.accept(")"):
            first = self.i
            args.append(self.expression())
            texts.append(" ".join(str(value) for _, value in self.tokens[first:self.i]))
            if self.i == first:   # something it can't parse: skip it
                self.i += 1
            self.accept(",")
        self.depth -= 1
        return args, texts

    def primary(self) -> tuple:
        kind, token = self.take()
        if kind in ("number", "string"):
            return token, None
        if kind == "name":
            return self.name(token), token
        if token == "nil":
            return None, None
        if token in ("true", "false"):
            return token == "true", None
        if token == "(":
            self.depth += 1
            value = self.expression()
            self.depth -= 1
            self.accept(")")
            return value, None
        if token == "{":
            return self.table(), None
        if token == "function":   # an inline function: skip its body
            depth = 1
            while depth and self.peek()[0] is not None:
                kind, word = self.take()
                if kind == "op" and word in ("function", "if", "do", "repeat"):
                    depth += 1
                elif kind == "op" and word in ("end", "until"):
                    depth -= 1
            return UNKNOWN, None
        return UNKNOWN, None

    def table(self) -> dict:
        result, position = {}, 1
        self.depth += 1
        while self.peek()[0] is not None and not self.accept("}"):
            first = self.i
            if self.accept("["):
                key = self.expression()
                self.accept("]")
                self.accept("=")
                result[key] = self.expression()
            elif self.peek()[0] == "name" and self.peek(1) == ("op", "="):
                key = self.take()[1]
                self.i += 1
                result[key] = self.expression()
            else:
                result[position] = self.expression()
                position += 1
            if not (self.accept(",") or self.accept(";")) and self.i == first:
                self.i += 1
        self.depth -= 1
        return result

    def name(self, name: str):
        if name in self.env:
            return self.env[name]
        return self.context.global_value(name, self.lua)

    def field(self, value, name: str):
        if isinstance(value, (Region, dict)):
            return value.get(name)
        if value is GLOBALS:
            return self.context.global_value(name, self.lua)
        return UNKNOWN if value is UNKNOWN else None

    def index(self, value, key):
        if value is GLOBALS and isinstance(key, str):
            return self.context.global_value(key, self.lua)
        if isinstance(value, dict):
            return value.get(key)
        if isinstance(value, Region) and isinstance(key, str):
            return value.get(key)
        return UNKNOWN if value is UNKNOWN else None

    def call(self, path: str | None, args: list, statement: bool) -> list:
        if path is None:
            return [UNKNOWN]
        if path in self.context.api:
            return [self.context.api[path]]
        function = self.lua.function(path)
        if function is None or (statement and not ONLOAD.search(path)):
            return [UNKNOWN]
        if function.method:   # Mixin.Method(self, ...)
            return self.lua.run(path, self.context, args[1:], args[0] if args else None)
        return self.lua.run(path, self.context, args)

    def method(self, value, name: str, args: list, texts: list[str], statement: bool) -> list:
        if not isinstance(value, Region):
            return [UNKNOWN]
        if name in REGION_METHODS:
            return region_method(value, name, args, texts, self.context)
        if value is not self.context.root or (statement and not ONLOAD.search(name)):
            return [UNKNOWN]
        function = self.context.method(name)
        return self.lua.run(function, self.context, args, value) if function else [UNKNOWN]


def binary(op: str, left, right):
    if op == "or":
        return left if truthy(left) else right
    if op == "and":
        return right if truthy(left) else left
    if op == "==":
        return left is not UNKNOWN and right is not UNKNOWN and left == right
    if op == "~=":
        return left is UNKNOWN or right is UNKNOWN or left != right
    if op == "..":
        if isinstance(left, (str, int, float)) and isinstance(right, (str, int, float)) \
                and not isinstance(left, bool) and not isinstance(right, bool):
            return lua_string(left) + lua_string(right)
        return UNKNOWN
    if is_number(left) and is_number(right):
        try:
            return {"<": lambda: left < right, ">": lambda: left > right, "<=": lambda: left <= right,
                    ">=": lambda: left >= right, "+": lambda: left + right, "-": lambda: left - right,
                    "*": lambda: left * right, "/": lambda: left / right, "%": lambda: left % right,
                    "^": lambda: left ** right}[op]()
        except (ZeroDivisionError, OverflowError):
            return UNKNOWN
    return UNKNOWN


def lua_string(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def region_method(region: Region, name: str, args: list, texts: list[str], context: Context) -> list:
    first = args[0] if args else None
    if name == "SetAtlas":
        if isinstance(first, str):
            region.atlas, region.file, region.fdid = first, None, None
            if len(args) > 1 and truthy(args[1]) and "Ignore" not in texts[1]:
                region.size_atlas = first
    elif name == "SetTexture":
        region.atlas = None
        region.file = first if isinstance(first, str) else None
        region.fdid = int(first) if is_number(first) else None
    elif name == "SetTexCoord" and len(args) == 4 and all(is_number(arg) for arg in args):
        region.coords = tuple(args)
    elif name == "SetPoint" and isinstance(first, str):
        set_point(region, args, context)
    elif name == "ClearAllPoints":
        region.anchors, region.all_points = {}, False
    elif name == "SetAllPoints":
        region.anchors = {}
        region.all_points = first if isinstance(first, Region) else True
    elif name in ("Show", "Hide"):
        region.shown = name == "Show"
    elif name == "SetShown":
        region.shown = truthy(first)
    elif name == "SetAlpha" and is_number(first):
        region.alpha = first
    elif name == "SetScale" and is_number(first):
        region.scale = first
    elif name in ("SetSize", "SetWidth", "SetHeight"):
        width, height = region.size
        if name == "SetSize" and len(args) >= 2:
            width, height = args[0], args[1]
        elif name == "SetWidth":
            width = first
        elif name == "SetHeight":
            height = first
        region.size = (width if is_number(width) else None, height if is_number(height) else None)
        region.size_atlas = None
    elif name == "GetName":
        return [region.name]
    elif name == "IsShown":
        return [region.shown]
    elif name == "GetParent":
        return [region.parent]
    return []


def set_point(region: Region, args: list, context: Context) -> None:
    point, rest = args[0].upper(), args[1:]
    relative, relative_point, offsets = None, point, rest
    if rest and not is_number(rest[0]) and rest[0] is not UNKNOWN:
        relative = rest[0]
        if isinstance(relative, str):
            relative = context.root.top().find_name(relative)
        offsets = rest[1:]
        if offsets and isinstance(offsets[0], str) and offsets[0].upper() in POINTS:
            relative_point, offsets = offsets[0].upper(), offsets[1:]
    elif rest and rest[0] is UNKNOWN:
        offsets = rest[1:] if len(rest) > 2 else rest
    x = offsets[0] if offsets and is_number(offsets[0]) else 0.0
    y = offsets[1] if len(offsets) > 1 and is_number(offsets[1]) else 0.0
    anchor = Anchor(point, relative_point, x, y)
    anchor.relative = relative if isinstance(relative, Region) else region.parent
    region.anchors[point] = anchor
    region.all_points = False


class Context:
    """One copy of a frame that code is running on, and the answers to the game API calls that matter."""

    def __init__(self, lua: Lua, root: Region, api: dict):
        self.lua, self.root, self.api = lua, root, api
        self.stack: list[str] = []

    def global_value(self, name: str, lua: Lua):
        if name == "_G":
            return GLOBALS
        if name in lua.tables:
            return lua.tables[name]
        region = self.root.top().find_name(name)
        return region if region is not None else UNKNOWN

    def method(self, name: str) -> str | None:
        """What self:name() runs: the last of the frame's mixins that has it (but not the method
        already running, which is how Classic's boss frames get to TargetFrameMixin:OnLoad)."""
        for mixin in reversed(self.root.mixins):
            full = f"{mixin}:{name}"
            if full not in self.stack and self.lua.has(full):
                return full
        return None

    def call(self, name: str) -> list:
        function = self.method(name)
        if function:
            return self.lua.run(function, self, [], self.root)
        return self.lua.run(name, self, [self.root]) if self.lua.has(name) else []

    def run_script(self, handler: str) -> None:
        script = self.root.scripts.get(handler)
        if script is None:
            return
        if script.get("method"):
            self.call(script.get("method"))
        elif script.get("function"):
            self.lua.run(script.get("function"), self, [self.root])
        elif (script.text or "").strip():
            self.lua.run_snippet(script.text, self)

    def pvp_indicator(self) -> None:
        style = self.lua.tables.get("PvPIndicatorStyle")
        if not style:
            return
        for name in PVP_ELEMENTS:
            returned = self.call(name)
            if returned and isinstance(returned[0], dict):
                elements = returned[0]
                break
        else:
            return
        icon, background = elements.get("pvpIcon"), elements.get("pvpBackground")
        if isinstance(icon, Region) and style.get("allianceIconAtlas"):
            icon.atlas, icon.file, icon.fdid = style["allianceIconAtlas"], None, None
            icon.size_atlas, icon.shown = icon.atlas, True
        if isinstance(background, Region):
            background.shown = truthy(style.get("usesBackground"))
