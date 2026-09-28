"""Reads files out of World of Warcraft clients, by FileDataID, for the scripts in this folder.

Two sources:
- A local installation. Every installed version (Retail, Classic, Classic Era, Anniversary, WoW
  Forever, PTRs...) shares one Data folder under the World of Warcraft folder, and .build.info
  names the build each one runs.
- wago.tools, which mirrors Blizzard's CDN for every build it has processed. Used for versions that
  aren't installed (e.g. the China-only Titan client) and for files a local install hasn't
  downloaded yet.

Also reads DB2 tables (WDC3-5), with column layouts taken from WoWDBDefs.

The formats follow wow.export's readers (github.com/Kruithne/wow.export, MIT): casc-source.js,
casc-source-local.js, blte-reader.js and db/WDCReader.js.
"""

from __future__ import annotations

import json
import os
import re
import struct
import urllib.error
import urllib.request
import zlib
from array import array
from bisect import bisect_left, bisect_right
from itertools import accumulate
from pathlib import Path
from string import ascii_uppercase

WAGO = "https://wago.tools"
WOWDBDEFS = "https://raw.githubusercontent.com/wowdev/WoWDBDefs/master/definitions/{table}.dbd"

LOCALE_ENUS = 0x2
CONTENT_LOW_VIOLENCE = 0x80
CONTENT_NO_NAME_HASH = 0x10000000


class MissingFile(Exception):
    """The file isn't in this build, or this copy of it can't be read."""


def http_get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "UnitFramesImproved-tools"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# --- BLTE: the container every CASC file is stored in ------------------------------------------

class Blte:
    """Random access into a BLTE-encoded file, decoding only the chunks a read touches."""

    def __init__(self, path: Path, offset: int, size: int):
        self.path, self.offset, self.size = path, offset, size
        header = self._raw(0, min(size, 8))
        if header[:4] != b"BLTE":
            raise MissingFile("not stored locally (the data there is blank)")
        header_size = struct.unpack_from(">I", header, 4)[0]

        self.chunks = []  # (encoded offset, encoded size, decoded offset, decoded size)
        if header_size == 0:
            self.chunks.append((8, size - 8, 0, None))
        else:
            table = self._raw(8, header_size - 8)
            count = int.from_bytes(table[1:4], "big")
            encoded, decoded = header_size, 0
            for i in range(count):
                enc_size, dec_size = struct.unpack_from(">II", table, 4 + i * 24)
                self.chunks.append((encoded, enc_size, decoded, dec_size))
                encoded += enc_size
                decoded += dec_size
        self._starts = [chunk[2] for chunk in self.chunks]
        self._cache: dict[int, bytes] = {}

    def _raw(self, start: int, length: int) -> bytes:
        with open(self.path, "rb") as f:
            f.seek(self.offset + start)
            return f.read(length)

    def _chunk(self, index: int) -> bytes:
        if index not in self._cache:
            enc_offset, enc_size, _, dec_size = self.chunks[index]
            if len(self._cache) > 8:
                self._cache.clear()
            self._cache[index] = decode_chunk(self._raw(enc_offset, enc_size), dec_size)
        return self._cache[index]

    def read(self, start: int, length: int) -> bytes:
        out = bytearray()
        index = bisect_right(self._starts, start) - 1
        while len(out) < length and index < len(self.chunks):
            chunk = self._chunk(index)
            skip = start + len(out) - self.chunks[index][2]
            out += chunk[skip:skip + length - len(out)]
            index += 1
        return bytes(out)

    def read_all(self) -> bytes:
        return b"".join(self._chunk(i) for i in range(len(self.chunks)))


def decode_chunk(chunk: bytes, decoded_size: int | None) -> bytes:
    mode = chunk[:1]
    if mode == b"N":
        return chunk[1:]
    if mode == b"Z":
        return zlib.decompress(chunk[1:])
    if mode == b"E" and decoded_size is not None:
        # Encrypted, usually content that isn't released yet (DB2 tables carry it in their own
        # sections). Like wow.export, leave it zeroed: the DB2 reader skips zeroed sections.
        return bytes(decoded_size)
    raise MissingFile(f"can't decode BLTE chunk mode {mode!r}")


# --- Local installation ---------------------------------------------------------------------------

def find_wow_dir() -> Path | None:
    candidates = [os.environ.get("WOW_DIR")]
    for drive in ascii_uppercase:
        root = f"{drive}:\\"
        if not os.path.exists(root):
            continue
        for sub in ("World of Warcraft", "Blizzard\\World of Warcraft", "Games\\World of Warcraft",
                    "Program Files (x86)\\World of Warcraft", "Program Files\\World of Warcraft"):
            candidates.append(root + sub)
    for candidate in candidates:
        if candidate and (Path(candidate) / ".build.info").is_file():
            return Path(candidate)
    return None


class LocalInstall:
    def __init__(self, root: Path):
        self.root = root
        self.data_dir = root / "Data" / "data"
        self._indexes: dict[int, tuple[bytes, int, int]] | None = None

        lines = (root / ".build.info").read_text(encoding="utf-8").splitlines()
        columns = [column.split("!")[0] for column in lines[0].split("|")]
        self.builds = {}
        for line in lines[1:]:
            if line.strip():
                info = dict(zip(columns, line.split("|")))
                self.builds.setdefault(info["Product"], LocalBuild(self, info))

    def config(self, key: str) -> dict[str, str]:
        path = self.root / "Data" / "config" / key[:2] / key[2:4] / key
        pairs = (line.split(" = ", 1) for line in path.read_text(encoding="utf-8").splitlines() if " = " in line)
        return {name: value for name, value in pairs}

    def _load_indexes(self) -> dict[int, tuple[bytes, int, int]]:
        # Data/data/XXyyyyyyyy.idx: bucket XX, version yyyyyyyy. Entries are 18 bytes: the first 9
        # bytes of the encoding key, 5 bytes of archive number + offset, and a 4 byte size.
        if self._indexes is None:
            newest: dict[int, Path] = {}
            for path in self.data_dir.glob("*.idx"):
                bucket = int(path.name[:2], 16)
                if bucket not in newest or path.name > newest[bucket].name:
                    newest[bucket] = path
            self._indexes = {}
            for bucket, path in newest.items():
                data = path.read_bytes()
                hash_size = struct.unpack_from("<I", data, 0)[0]
                start = (8 + hash_size + 0x0F) & ~0x0F
                length = struct.unpack_from("<I", data, start)[0]
                self._indexes[bucket] = (data, start + 8, start + 8 + length)
        return self._indexes

    def _locate(self, ekey: bytes) -> tuple[int, int, int]:
        key = ekey[:9]
        mixed = 0
        for byte in key:
            mixed ^= byte
        bucket = (mixed & 0x0F) ^ (mixed >> 4)
        indexes = self._load_indexes()
        for index in [bucket] + [b for b in indexes if b != bucket]:
            data, start, end = indexes[index]
            pos = data.find(key, start, end)
            while pos != -1:
                if (pos - start) % 18 == 0:
                    high = data[pos + 9]
                    low = struct.unpack_from(">I", data, pos + 10)[0]
                    size = struct.unpack_from("<I", data, pos + 14)[0]
                    return (high << 2) | (low >> 30), low & 0x3FFFFFFF, size
                pos = data.find(key, pos + 1, end)
        raise MissingFile(f"encoding key {ekey.hex()} isn't in the local indexes")

    def blte(self, ekey: bytes) -> Blte:
        archive, offset, size = self._locate(ekey)
        # Each entry starts with a 30 byte header (key, size, flags, checksums) before the BLTE data.
        return Blte(self.data_dir / f"data.{archive:03d}", offset + 30, size - 30)


class LocalBuild:
    def __init__(self, install: LocalInstall, info: dict[str, str]):
        self.install = install
        self.product = info["Product"]
        self.version = info["Version"]
        self.build_key = info["Build Key"]
        self._config: dict[str, str] | None = None
        self._encoding: Encoding | None = None
        self._root: bytes | None = None
        self._ckeys: dict[int, bytes] = {}

    @property
    def config(self) -> dict[str, str]:
        if self._config is None:
            self._config = self.install.config(self.build_key)
        return self._config

    @property
    def name(self) -> str:
        return self.config.get("build-name", "")

    def _ekey(self, ckey: bytes) -> bytes:
        if self._encoding is None:
            self._encoding = Encoding(self.install.blte(bytes.fromhex(self.config["encoding"].split()[1])))
        return self._encoding.ekey(ckey)

    def _find_ckeys(self, fdids: set[int]) -> None:
        wanted = fdids - self._ckeys.keys()
        if not wanted:
            return
        if self._root is None:
            self._root = self.install.blte(self._ekey(bytes.fromhex(self.config["root"]))).read_all()
        self._ckeys.update(scan_root(self._root, wanted))

    def files(self, fdids) -> dict[int, bytes | MissingFile]:
        """The files with these IDs, or the MissingFile error for each one that can't be read."""
        fdids = set(fdids)
        self._find_ckeys(fdids)
        out: dict[int, bytes | MissingFile] = {}
        for fdid in fdids:
            try:
                if fdid not in self._ckeys:
                    raise MissingFile(f"file {fdid} isn't in {self.product} {self.version}")
                out[fdid] = self.install.blte(self._ekey(self._ckeys[fdid])).read_all()
            except MissingFile as error:
                out[fdid] = error
        return out


class Encoding:
    """The encoding table: content key (hash of a file) -> encoding key (where it's stored)."""

    def __init__(self, blte: Blte):
        self.blte = blte
        header = blte.read(0, 22)
        if header[:2] != b"EN":
            raise MissingFile("bad encoding table")
        self.ckey_size, self.ekey_size = header[3], header[4]
        self.page_size = struct.unpack_from(">H", header, 5)[0] * 1024
        page_count = struct.unpack_from(">I", header, 9)[0]
        spec_size = struct.unpack_from(">I", header, 18)[0]

        entry = self.ckey_size + 16  # first key of the page + page checksum
        index = blte.read(22 + spec_size, page_count * entry)
        self.first_keys = [index[i * entry:i * entry + self.ckey_size] for i in range(page_count)]
        self.pages_start = 22 + spec_size + page_count * entry

    def ekey(self, ckey: bytes) -> bytes:
        page_index = bisect_right(self.first_keys, ckey) - 1
        if page_index >= 0:
            page = self.blte.read(self.pages_start + page_index * self.page_size, self.page_size)
            pos = 0
            while pos + 6 + self.ckey_size <= len(page) and page[pos]:
                key_count = page[pos]
                key_start = pos + 6  # key count (1) + file size (5)
                if page[key_start:key_start + self.ckey_size] == ckey:
                    ekey_start = key_start + self.ckey_size
                    return page[ekey_start:ekey_start + self.ekey_size]
                pos = key_start + self.ckey_size + self.ekey_size * key_count
        raise MissingFile(f"content key {ckey.hex()} isn't in the encoding table")


def scan_root(root: bytes, wanted: set[int]) -> dict[int, bytes]:
    """Content keys of the wanted FileDataIDs, from a root file in the 8.2+ MFST format."""
    if root[:4] != b"TSFM":
        raise MissingFile("root files older than 8.2 aren't supported")
    header_size, version = struct.unpack_from("<II", root, 4)
    if header_size == 0x18:  # 10.1.7+
        total, named = struct.unpack_from("<II", root, 12)
    else:
        total, named, header_size, version = header_size, version, 12, 0
    allow_nameless = total != named

    found: dict[int, bytes] = {}
    view = memoryview(root)
    pos = header_size
    while pos < len(root) and len(found) < len(wanted):
        count = struct.unpack_from("<I", root, pos)[0]
        if version == 2:
            locale, flags1, flags2 = struct.unpack_from("<III", root, pos + 4)
            content = flags1 | flags2 | (root[pos + 16] << 17)
            pos += 17
        else:
            content, locale = struct.unpack_from("<II", root, pos + 4)
            pos += 12

        deltas = array("i")
        deltas.frombytes(view[pos:pos + 4 * count])
        pos += 4 * count
        ckeys_start = pos
        pos += 16 * count
        if not (allow_nameless and content & CONTENT_NO_NAME_HASH):
            pos += 8 * count

        if not locale & LOCALE_ENUS or content & CONTENT_LOW_VIOLENCE:
            continue
        # Each ID is the previous one + 1 + its delta, so ID i = (sum of deltas up to i) + i.
        sums = list(accumulate(deltas))
        for fdid in wanted - found.keys():
            i = bisect_left(range(count), fdid, key=lambda n: sums[n] + n)
            if i < count and sums[i] + i == fdid:
                found[fdid] = root[ckeys_start + 16 * i:ckeys_start + 16 * (i + 1)]
    return found


# --- wago.tools -----------------------------------------------------------------------------------

class WagoBuild:
    def __init__(self, product: str, version: str):
        self.product, self.version = product, version
        self.name = f"{product} {version} from wago.tools"

    def files(self, fdids) -> dict[int, bytes | MissingFile]:
        out: dict[int, bytes | MissingFile] = {}
        for fdid in set(fdids):
            try:
                out[fdid] = http_get(f"{WAGO}/api/casc/{fdid}?version={self.version}")
            except (urllib.error.URLError, TimeoutError) as error:
                out[fdid] = MissingFile(f"wago.tools: {error}")
        return out


_wago_builds: dict | None = None


def wago_latest(product: str) -> str | None:
    global _wago_builds
    if _wago_builds is None:
        try:
            _wago_builds = json.loads(http_get(f"{WAGO}/api/builds"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            _wago_builds = {}
    builds = _wago_builds.get(product) or []
    return builds[0]["version"] if builds else None


# --- DB2 tables -----------------------------------------------------------------------------------

def dbd_columns(table: str, layout_hash: str, cache_dir: Path) -> list[tuple[str, str, int, bool]]:
    """(name, type, bits, signed) of each column stored in the record, in record order."""
    cached = cache_dir / f"{table}.dbd"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(http_get(WOWDBDEFS.format(table=table)))
    blocks = cached.read_text(encoding="utf-8").split("\n\n")

    types = {}
    for line in blocks[0].splitlines()[1:]:
        match = re.match(r"(\w+)(?:<[^>]*>)?\s+(\w+)", line.strip())
        if match:
            types[match.group(2)] = match.group(1)

    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not any(line.startswith("LAYOUT") and layout_hash in line for line in lines):
            continue
        columns = []
        for line in lines:
            if line.startswith(("LAYOUT", "BUILD", "COMMENT")):
                continue
            match = re.match(r"(?:\$([\w,]+)\$)?(\w+)(?:<(u?)(\d+)>)?(?:\[(\d+)\])?", line.strip())
            if not match:
                continue
            annotations, name, unsigned, bits, _ = match.groups()
            if "noninline" in (annotations or "").split(","):
                continue
            columns.append((name, types.get(name, "int"), int(bits or 32), not unsigned))
        return columns
    raise MissingFile(f"WoWDBDefs has no {table} layout {layout_hash}")


def read_db2(data: bytes, table: str, cache_dir: Path) -> list[dict]:
    """All rows of a WDC3/WDC4/WDC5 table (records that aren't sparse or encrypted)."""
    magic = data[:4]
    if magic not in (b"WDC3", b"WDC4", b"WDC5"):
        raise MissingFile(f"{table}: unsupported DB2 format {magic!r}")
    pos = 4 + (132 if magic == b"WDC5" else 0)  # WDC5: version + schema string
    (record_count, _field_count, record_size, _string_size, _table_hash, layout_hash, _min_id, _max_id,
     _locale, flags, id_index, total_fields, _bitpacked_offset, _lookup_columns, field_info_size,
     _common_size, _pallet_size, section_count) = struct.unpack_from("<9I2H7I", data, pos)
    pos += 68
    if flags & 1:
        raise MissingFile(f"{table}: sparse tables aren't supported")
    columns = dbd_columns(table, f"{layout_hash:08X}", cache_dir)

    sections = []
    for _ in range(section_count):
        sections.append(struct.unpack_from("<Q8I", data, pos))
        pos += 40
    pos += 4 * total_fields

    fields = []  # (offset bits, size bits, extra data size, compression, packing 1-3)
    for _ in range(field_info_size // 24):
        fields.append(struct.unpack_from("<HHIIIII", data, pos))
        pos += 24
    if magic != b"WDC3":  # IDs of encrypted records, one list per section after the first
        for _ in range(section_count - 1):
            pos += 4 + 4 * struct.unpack_from("<I", data, pos)[0]

    pallets, commons = {}, {}
    for i, field in enumerate(fields):
        if field[3] in (3, 4):
            pallets[i] = array("I", data[pos:pos + field[2]])
            pos += field[2]
    for i, field in enumerate(fields):
        if field[3] == 2:
            commons[i] = {struct.unpack_from("<I", data, pos + j)[0]: struct.unpack_from("<I", data, pos + j + 4)[0]
                          for j in range(0, field[2], 8)}
            pos += field[2]

    # String fields hold offsets relative to their own position, as if all sections' records came
    # first and all their string tables followed.
    string_tables = []  # (start in the combined string tables, file offset, size)
    combined = 0
    for section in sections:
        file_offset, count, string_size = section[1], section[2], section[3]
        string_tables.append((combined, file_offset + count * record_size, string_size))
        combined += string_size

    def read_string(index: int) -> str:
        for start, offset, size in string_tables:
            if start <= index < start + size:
                begin = offset + index - start
                return data[begin:data.index(b"\0", begin)].decode("utf-8")
        return ""

    def value(record: int, i: int, record_id: int) -> int:
        offset_bits, size_bits, _, compression, packing, _, _ = fields[i]
        if compression == 0:
            return int.from_bytes(data[record + offset_bits // 8:record + (offset_bits + size_bits) // 8], "little")
        if compression == 2:
            return commons[i].get(record_id, packing)
        raw = int.from_bytes(data[record + offset_bits // 8:record + offset_bits // 8 + 8].ljust(8, b"\0"), "little")
        raw = (raw >> (offset_bits & 7)) & ((1 << size_bits) - 1)
        if compression in (3, 4):
            return pallets[i][raw * (fields[i][6] if compression == 4 else 1)]
        if compression == 5 and raw >> (size_bits - 1):
            raw -= 1 << size_bits
        return raw

    rows, copies, records_before = [], {}, 0
    for section, (_, strings_offset, string_size) in zip(sections, string_tables):
        tact_key, file_offset, count, _, _, id_list_size, relationship_size, offset_map_count, copy_count = section
        after = strings_offset + string_size
        ids = array("I", data[after:after + id_list_size])
        after += id_list_size
        for j in range(copy_count):
            new_id, old_id = struct.unpack_from("<II", data, after + 8 * j)
            copies[new_id] = old_id
        records = data[file_offset:file_offset + count * record_size]
        if tact_key and not any(records):
            records_before += count * record_size
            continue

        for r in range(count):
            record = file_offset + r * record_size
            record_id = ids[r] if ids else value(record, id_index, 0)
            row = {}
            for i, (name, kind, bits, signed) in enumerate(columns):
                if kind in ("string", "locstring"):
                    pos_in_record = fields[i][0] // 8
                    offset = value(record, i, record_id)
                    index = records_before + r * record_size - record_count * record_size + pos_in_record + offset
                    row[name] = read_string(index) if offset else ""
                else:
                    number = value(record, i, record_id) & ((1 << bits) - 1)
                    row[name] = number - (1 << bits) if signed and number >> (bits - 1) else number
            if ids:
                row["ID"] = record_id
            rows.append(row)
        records_before += count * record_size

    by_id = {row["ID"]: row for row in rows}
    rows += [dict(by_id[old_id], ID=new_id) for new_id, old_id in copies.items() if old_id in by_id]
    return rows
