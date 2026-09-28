"""Regression tests for UnitFramesImproved, run against stubbed WoW clients.

    pip install -r tests/requirements.txt
    python -m unittest discover -s tests -v

See tests/README.md for what the stubs do and don't cover.
"""

import pathlib
import re
import unittest

from harness import ADDON_NAME, CLIENTS, REPO_ROOT, AddonClient, parse_toc

MAINLINE_TOCS = [toc for toc, info in CLIENTS.items() if info["layout"] == "mainline"]
CLASSIC_TOCS = [toc for toc, info in CLIENTS.items() if info["layout"] == "classic"]


class TocFileTests(unittest.TestCase):
    def test_every_shipped_toc_is_covered(self):
        on_disk = sorted(path.name for path in REPO_ROOT.glob("*.toc"))
        self.assertEqual(on_disk, sorted(CLIENTS))

    def test_interface_line_first_and_in_client_range(self):
        for toc, info in CLIENTS.items():
            with self.subTest(toc=toc):
                first_line = (REPO_ROOT / toc).read_text(encoding="utf-8").splitlines()[0]
                # A TOC that doesn't start with ## Interface: is silently ignored by the client.
                self.assertRegex(first_line, r"^## Interface: \d+(, ?\d+)*$")
                low, high = info["interface_range"]
                for interface in re.findall(r"\d+", first_line):
                    self.assertTrue(low <= int(interface) <= high, f"{toc}: {interface} isn't a {info['client']} interface")

    def test_listed_files_exist_and_no_libraries(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                metadata, files = parse_toc(toc)
                self.assertNotIn("OptionalDeps", metadata)
                self.assertNotIn("Dependencies", metadata)
                for relative_path in files:
                    self.assertTrue((REPO_ROOT / relative_path).is_file(), f"{toc} lists missing file {relative_path}")
                    self.assertFalse(relative_path.startswith("Libs/"), f"{toc} still loads {relative_path}")
                    self.assertFalse(relative_path.startswith("tests/"), f"{toc} loads test code {relative_path}")

    def test_each_toc_loads_the_styler_for_its_frame_layout(self):
        styler = {"mainline": "UnitFramesImproved_Retail.lua", "classic": "UnitFramesImproved_Classic.lua"}
        for toc, info in CLIENTS.items():
            with self.subTest(toc=toc):
                _, files = parse_toc(toc)
                self.assertEqual(
                    files,
                    ["HelperFunctions.lua", "UnitFramesImproved.lua", styler[info["layout"]], "UnitFramesImproved_Options.lua"],
                )

    def test_forever_toc_uses_the_camelot_suffix(self):
        # WoW Forever's game type is "camelot" (Blizzard's own [AllowLoadGameType camelot] TOC
        # tags); the client and the CurseForge packager both pick up <Addon>_Camelot.toc for it.
        metadata, _ = parse_toc("UnitFramesImproved_Camelot.toc")
        self.assertTrue(metadata["Interface"].startswith("16"))


class PackagingTests(unittest.TestCase):
    def test_build_script_ships_everything_the_tocs_load(self):
        build = (REPO_ROOT / "build.ps1").read_text(encoding="utf-8")
        source_items = set(re.findall(r"'([^']+)'", re.search(r"\$SourceItems = @\((.*?)\)", build, re.S).group(1)))
        for toc in CLIENTS:
            self.assertIn(toc, source_items)
            _, files = parse_toc(toc)
            for relative_path in files:
                self.assertIn(relative_path.split("/")[0], source_items, f"build.ps1 doesn't ship {relative_path}")
        self.assertNotIn("tests", source_items)

    def test_pkgmeta_excludes_tests_and_has_no_externals(self):
        pkgmeta = (REPO_ROOT / ".pkgmeta").read_text(encoding="utf-8")
        self.assertRegex(pkgmeta, r"(?m)^\s*-\s*tests\s*$")
        self.assertNotRegex(pkgmeta, r"(?m)^externals:")

    def test_repo_only_files_are_not_packaged(self):
        # docs/ holds the README's art comparison: on GitHub, but not in the addon.
        build = (REPO_ROOT / "build.ps1").read_text(encoding="utf-8")
        source_items = set(re.findall(r"'([^']+)'", re.search(r"\$SourceItems = @\((.*?)\)", build, re.S).group(1)))
        pkgmeta = (REPO_ROOT / ".pkgmeta").read_text(encoding="utf-8")
        for item in ("docs", "AGENTS.md", "CLAUDE.md"):
            self.assertNotIn(item, source_items)
            self.assertRegex(pkgmeta, rf"(?m)^\s*-\s*{re.escape(item)}\s*$")


class LoadTests(unittest.TestCase):
    def test_loads_and_handles_events_on_every_client(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                self.assertIsNone(client.G.LibStub, "LibStub must not be needed")
                client.fire("PLAYER_ENTERING_WORLD", True, False)
                client.fire("PLAYER_TARGET_CHANGED")
                client.fire("PLAYER_FOCUS_CHANGED")
                client.fire("UNIT_TARGET", "target")
                client.fire("UNIT_TARGET", "focus")
                client.fire("PLAYER_REGEN_ENABLED")
                client.fire("PLAYER_ENTERING_WORLD", False, False)

    def test_registers_events_on_its_own_frame(self):
        client = AddonClient("UnitFramesImproved.toc")
        for event in ["PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "PLAYER_TARGET_CHANGED", "PLAYER_FOCUS_CHANGED", "UNIT_TARGET"]:
            with self.subTest(event=event):
                self.assertEqual(client.WoWTest.CountFramesRegisteredFor(event), 1)

    def test_first_load_message_only_once(self):
        client = AddonClient("UnitFramesImproved.toc")
        client.fire("PLAYER_ENTERING_WORLD", True, False)
        client.fire("PLAYER_ENTERING_WORLD", False, False)
        client.fire("PLAYER_REGEN_ENABLED")
        self.assertEqual(client.chat_lines().count("Config loaded."), 1)


class MainlineStylingTests(unittest.TestCase):
    """Retail and WoW Forever share UnitFramesImproved_Retail.lua."""

    def test_never_writes_fields_onto_blizzard_frames(self):
        # On Mainline clients any field the addon writes onto a Blizzard frame taints it, and
        # Blizzard's own later secret-value comparisons on that frame then error - see
        # ARCHITECTURE.md, "Combat lockdown & taint safety".
        for toc in MAINLINE_TOCS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                client.fire("PLAYER_ENTERING_WORLD", True, False)
                client.fire("PLAYER_TARGET_CHANGED")
                client.fire("PLAYER_FOCUS_CHANGED")
                client.fire("UNIT_TARGET", "target")
                client.fire("UNIT_TARGET", "focus")
                client.fire("PLAYER_REGEN_ENABLED")
                self.assertEqual(client.field_writes(), [])

    def test_styles_player_target_focus_and_tot_health_bars(self):
        for toc in MAINLINE_TOCS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                client.fire("PLAYER_ENTERING_WORLD", True, False)
                call_count = client.WoWTest.CallCount
                player_bar = client.G.PlayerFrame.PlayerFrameContent.PlayerFrameContentMain.HealthBarsContainer.HealthBar
                self.assertEqual(call_count(player_bar, "SetStatusBarDesaturated"), 1)
                self.assertEqual(call_count(player_bar, "UpdateTextString"), 1)
                for frame_name in ["TargetFrame", "FocusFrame"]:
                    bar = client.G[frame_name].TargetFrameContent.TargetFrameContentMain.HealthBarsContainer.HealthBar
                    self.assertEqual(call_count(bar.HealthBarTexture, "SetAtlas"), 1, frame_name)
                    tot_bar = client.G[frame_name + "ToT"].HealthBar
                    self.assertEqual(call_count(tot_bar, "SetStatusBarTexture"), 1, frame_name + "ToT")

    def test_unit_target_restyles_only_the_matching_tot_frame(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        target_tot = client.G.TargetFrameToT.HealthBar
        focus_tot = client.G.FocusFrameToT.HealthBar
        client.fire("UNIT_TARGET", "target")
        self.assertEqual(client.WoWTest.CallCount(target_tot, "SetStatusBarTexture"), 1)
        self.assertEqual(client.WoWTest.CallCount(focus_tot, "SetStatusBarTexture"), 0)

    def test_skips_forced_text_update_while_health_is_secret(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        client.lua.execute("issecretvalue = function(value) return true end")
        client.fire("PLAYER_ENTERING_WORLD", True, False)
        player_bar = client.G.PlayerFrame.PlayerFrameContent.PlayerFrameContentMain.HealthBarsContainer.HealthBar
        self.assertEqual(client.WoWTest.CallCount(player_bar, "UpdateTextString"), 0)


class ClassicStylingTests(unittest.TestCase):
    def test_text_status_bar_hook_registered_once(self):
        for toc in CLASSIC_TOCS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                client.fire("PLAYER_ENTERING_WORLD", True, False)
                client.fire("PLAYER_ENTERING_WORLD", False, False)
                client.fire("PLAYER_REGEN_ENABLED")
                hooked = [call[1] for call in client.calls_named("hooksecurefunc")]
                self.assertEqual(hooked.count("UpdateTextStringWithValues"), 1)
                self.assertEqual(hooked.count("PlayerFrame_ToPlayerArt"), 1)

    def test_player_health_bar_offset_does_not_drift(self):
        client = AddonClient("UnitFramesImproved_Vanilla.toc")
        for _ in range(3):
            client.fire("PLAYER_ENTERING_WORLD", False, False)
        point = client.G.PlayerFrameHealthBar.GetPoint(client.G.PlayerFrameHealthBar)
        self.assertEqual((point[3], point[4]), (106, -41 + 18))

    def test_classic_era_has_no_focus_frame(self):
        client = AddonClient("UnitFramesImproved_Vanilla.toc")
        self.assertIsNone(client.G.FocusFrame)
        client.fire("PLAYER_FOCUS_CHANGED")


class StatusTextOptionTests(unittest.TestCase):
    """The Status Text dropdown on Options -> AddOns -> UnitFramesImproved."""

    def test_registered_as_addon_category_on_every_client(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                category = client.addon_category()
                self.assertIsNotNone(category)
                self.assertEqual(category.name, ADDON_NAME)
                initializers = list(category.initializers.values())
                self.assertEqual(len(initializers), 1)
                self.assertEqual(initializers[0].kind, "dropdown")

    def test_dropdown_matches_blizzards_own_status_text_options(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        setting = client.status_text_setting()
        self.assertEqual(setting.GetDefaultValue(setting), "NONE")
        self.assertEqual(setting.name, "Status Text")
        dropdown = list(client.addon_category().initializers.values())[0]
        options = list(dropdown.options().values())
        self.assertEqual([option.value for option in options], ["NUMERIC", "PERCENT", "BOTH", "NONE"])
        self.assertEqual([option.label for option in options], ["Numeric Value", "Percentage", "Both", "None"])

    def test_value_reflects_both_cvars(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        setting = client.status_text_setting()
        set_silently = client.WoWTest.SetCVarSilently
        set_silently("statusText", "0")
        set_silently("statusTextDisplay", "BOTH")
        self.assertEqual(setting.GetValue(setting), "NONE")
        set_silently("statusText", "1")
        self.assertEqual(setting.GetValue(setting), "BOTH")

    def test_selecting_a_mode_writes_the_same_cvars_as_blizzard(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                setting = client.status_text_setting()
                setting.SetValue(setting, "PERCENT")
                self.assertEqual((client.cvar("statusText"), client.cvar("statusTextDisplay")), ("1", "PERCENT"))
                setting.SetValue(setting, "NONE")
                self.assertEqual((client.cvar("statusText"), client.cvar("statusTextDisplay")), ("0", "NONE"))

    def test_unchanged_cvars_are_not_rewritten(self):
        # Every SetCVar fires CVAR_UPDATE synchronously into Blizzard's status bar handlers.
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        client.WoWTest.SetCVarSilently("statusText", "0")
        client.WoWTest.SetCVarSilently("statusTextDisplay", "BOTH")
        setting = client.status_text_setting()
        setting.SetValue(setting, "BOTH")
        self.assertEqual([call[1] for call in client.calls_named("SetCVar")], ["statusText"])

    def test_switching_between_shown_modes_turns_status_text_off_and_on(self):
        # Blizzard's bars only redraw their text for a statusText change - the same as picking None
        # in between, which also doesn't error on secret health the way a direct redraw would.
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        client.WoWTest.SetCVarSilently("statusText", "1")
        client.WoWTest.SetCVarSilently("statusTextDisplay", "NUMERIC")
        setting = client.status_text_setting()
        setting.SetValue(setting, "BOTH")
        writes = [(call[1], call[2]) for call in client.calls_named("SetCVar")]
        self.assertEqual(writes, [("statusTextDisplay", "BOTH"), ("statusText", "0"), ("statusText", "1")])

    def test_every_mode_change_redraws_blizzards_status_bars(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                setting = client.status_text_setting()
                bar = client.player_health_bar()
                redraws = client.WoWTest.CallCount(bar, "UpdateTextString")
                for mode in ["NUMERIC", "BOTH", "PERCENT", "NUMERIC", "NONE"]:
                    setting.SetValue(setting, mode)
                    self.assertGreater(client.WoWTest.CallCount(bar, "UpdateTextString"), redraws, mode)
                    redraws = client.WoWTest.CallCount(bar, "UpdateTextString")

    def test_change_in_combat_waits_for_combat_to_end(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        setting = client.status_text_setting()
        bar = client.player_health_bar()
        client.WoWTest.EnterCombat()
        setting.SetValue(setting, "NUMERIC")
        self.assertEqual(client.WoWTest.SetCVarCallCount(), 0)
        self.assertEqual(client.WoWTest.CallCount(bar, "UpdateTextString"), 0)
        self.assertEqual(setting.GetValue(setting), "NUMERIC")  # the dropdown shows the pending choice
        self.assertTrue(any("once you're out of combat" in line for line in client.chat_lines()))

        client.WoWTest.LeaveCombat()
        client.WoWTest.RunTimers()
        self.assertEqual((client.cvar("statusText"), client.cvar("statusTextDisplay")), ("1", "NUMERIC"))
        # The one-shot retry listener is gone again once applied.
        self.assertEqual(client.WoWTest.CountFramesRegisteredFor("ADDON_RESTRICTION_STATE_CHANGED"), 0)

    def test_change_waits_for_addon_restrictions_to_lift(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        setting = client.status_text_setting()
        client.WoWTest.SetRestriction("Encounter", True)
        setting.SetValue(setting, "BOTH")
        self.assertEqual(client.WoWTest.SetCVarCallCount(), 0)

        # Another restriction starting mid-encounter must not trigger the write early, even though
        # IsAddOnRestrictionActive reports false during that event's dispatch.
        client.WoWTest.SetRestriction("Combat", True)
        client.WoWTest.RunTimers()
        self.assertEqual(client.WoWTest.SetCVarCallCount(), 0)

        client.WoWTest.SetRestriction("Combat", False)
        client.WoWTest.RunTimers()
        self.assertEqual(client.WoWTest.SetCVarCallCount(), 0)

        client.WoWTest.SetRestriction("Encounter", False)
        client.WoWTest.RunTimers()
        self.assertEqual((client.cvar("statusText"), client.cvar("statusTextDisplay")), ("1", "BOTH"))

    def test_last_choice_while_restricted_wins(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        setting = client.status_text_setting()
        client.WoWTest.EnterCombat()
        setting.SetValue(setting, "PERCENT")
        setting.SetValue(setting, "NONE")
        client.WoWTest.LeaveCombat()
        client.WoWTest.RunTimers()
        # Only the last pick (NONE) is applied, and statusText was already off - so the one write is
        # statusTextDisplay, and PERCENT never reaches the CVars at all.
        self.assertEqual([call[2] for call in client.calls_named("SetCVar")], ["NONE"])
        self.assertEqual((client.cvar("statusText"), client.cvar("statusTextDisplay")), ("0", "NONE"))


class SlashCommandTests(unittest.TestCase):
    def test_slash_commands_open_the_options_category(self):
        for toc in CLIENTS:
            with self.subTest(toc=toc):
                client = AddonClient(toc)
                self.assertEqual(client.G.SLASH_UNITFRAMESIMPROVED1, "/ufi")
                self.assertEqual(client.G.SLASH_UNITFRAMESIMPROVED2, "/unitframesimproved")
                client.slash()
                opened = client.calls_named("OpenToCategory")
                self.assertEqual([call[1] for call in opened], [client.addon_category().id])

    def test_slash_command_in_combat_does_not_open_options(self):
        client = AddonClient("UnitFramesImproved_Camelot.toc")
        client.WoWTest.EnterCombat()
        client.slash()
        self.assertEqual(client.calls_named("OpenToCategory"), [])
        self.assertTrue(any("in combat" in line for line in client.chat_lines()))


if __name__ == "__main__":
    unittest.main()
