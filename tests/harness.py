"""Loads UnitFramesImproved into a stubbed WoW client (tests/wow_stubs.lua) inside Lua 5.1.

Each AddonClient mimics one game client: it sets up that client's Blizzard frame layout, then
loads exactly the files the matching TOC lists, in TOC order, the way the game would. Nothing
here is part of the shipped addon (see tests/README.md).
"""

import pathlib
import re

from lupa.lua51 import LuaRuntime

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
ADDON_NAME = "UnitFramesImproved"

# Every TOC the addon ships, and the client each one is for. "layout" picks the Blizzard frame
# layout wow_stubs.lua builds, which is also what decides the styler file each TOC loads.
# "interface_range" is the ## Interface: range that belongs to that client (the same ranges the
# CurseForge packager uses to tell game versions apart, e.g. 16xxx is WoW Forever).
CLIENTS = {
    "UnitFramesImproved.toc": {"client": "Retail", "layout": "mainline", "has_focus": True, "interface_range": (110000, 999999)},
    "UnitFramesImproved_Camelot.toc": {"client": "WoW Forever", "layout": "mainline", "has_focus": True, "interface_range": (16000, 16999)},
    "UnitFramesImproved_Mists.toc": {"client": "Mists of Pandaria Classic", "layout": "classic", "has_focus": True, "interface_range": (50000, 50999)},
    "UnitFramesImproved_TBC.toc": {"client": "TBC Anniversary", "layout": "classic", "has_focus": True, "interface_range": (20000, 20999)},
    "UnitFramesImproved_Vanilla.toc": {"client": "Classic Era", "layout": "classic", "has_focus": False, "interface_range": (11000, 11999)},
}


def parse_toc(toc_name):
    """Returns (metadata, files) for a TOC file: its ## directives and the files it loads."""
    metadata = {}
    files = []
    for line in (REPO_ROOT / toc_name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^##\s*([^:]+):\s*(.*)$", line)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
        elif not line.startswith("#"):
            files.append(line.replace("\\", "/"))
    return metadata, files


class AddonClient:
    """One stubbed game client with the addon loaded from the given TOC."""

    def __init__(self, toc_name):
        info = CLIENTS[toc_name]
        self.toc_name = toc_name
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.G = self.lua.globals()

        self._run_file(TESTS_DIR / "wow_stubs.lua", "@tests/wow_stubs.lua")
        self.WoWTest = self.G.WoWTest
        self.WoWTest.Setup(info["layout"], info["has_focus"])

        # Every addon file gets (addonName, addonTable) as its varargs, like in game.
        namespace = self.lua.table()
        _, files = parse_toc(toc_name)
        for relative_path in files:
            self._run_file(REPO_ROOT / relative_path, "@" + relative_path, ADDON_NAME, namespace)

        self.addon = self.G.UnitFramesImproved
        self.WoWTest.StartTrackingWrites()

    def _run_file(self, path, chunk_name, *args):
        loader = self.lua.eval(
            "function(code, name) local chunk, err = loadstring(code, name); if not chunk then error(err, 0) end; return chunk end"
        )
        chunk = loader(path.read_text(encoding="utf-8"), chunk_name)
        return chunk(*args)

    # Convenience wrappers around WoWTest.
    def fire(self, event, *args):
        self.WoWTest.FireEvent(event, *args)

    def cvar(self, name):
        return self.G.GetCVar(name)

    def chat_lines(self):
        return list(self.WoWTest.chat.values())

    def calls_named(self, name):
        return [call for call in self.WoWTest.calls.values() if call["name"] == name]

    def field_writes(self):
        return [(write["region"], write["key"]) for write in self.WoWTest.fieldWrites.values()]

    def addon_category(self):
        categories = list(self.WoWTest.settings.addOnCategories.values())
        return categories[0] if len(categories) == 1 else None

    def status_text_setting(self):
        return self.G.Settings.GetSetting("UNITFRAMESIMPROVED_STATUS_TEXT")

    def player_health_bar(self):
        if CLIENTS[self.toc_name]["layout"] == "mainline":
            return self.G.PlayerFrame.PlayerFrameContent.PlayerFrameContentMain.HealthBarsContainer.HealthBar
        return self.G.PlayerFrameHealthBar

    def slash(self, command_line=""):
        self.G.SlashCmdList["UNITFRAMESIMPROVED"](command_line)
