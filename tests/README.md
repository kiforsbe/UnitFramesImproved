# Tests

Regression tests that run UnitFramesImproved outside the game, against a stubbed WoW client.
Nothing in this folder ships with the addon: no TOC file lists it, `.pkgmeta` ignores it, and
`build.ps1` only copies the files it lists explicitly.

## Running

Needs Python 3.9+ and [lupa](https://pypi.org/project/lupa/), which bundles a real Lua 5.1 runtime
(the Lua version WoW uses), so no separate Lua install is needed:

```sh
pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

## How it works

| File | Role |
|---|---|
| `wow_stubs.lua` | Minimal WoW client: regions/frames, event dispatch, CVars, combat lockdown and addon restrictions, `C_Timer`, the `Settings` API, `SlashCmdList`, global strings, and the Blizzard unit frames for both frame layouts (Mainline for Retail/Forever, flat globals for the Classic family) |
| `harness.py` | `AddonClient(toc)`: a fresh Lua runtime per client that sets up that client's frame layout, then loads exactly the files the TOC lists, in order, with `(addonName, addonTable)` varargs like the game does |
| `test_addon.py` | The tests: TOC/packaging checks, loading and event handling on every client, styling, the Status Text option, and the slash command |

`harness.CLIENTS` maps every shipped TOC to its client. Adding a TOC without adding it there fails
`test_every_shipped_toc_is_covered`.

The stubs are strict where the real client is: unstubbed methods don't exist (calling one errors),
`RegisterEvent` rejects unknown events (add new ones to `KNOWN_EVENTS` in `wow_stubs.lua`), and
`SetCVar` fires `CVAR_UPDATE` synchronously. On Blizzard-owned frames they also record every field
the addon writes after setup (`WoWTest.fieldWrites`) - on Retail/Forever such a write taints the
frame, so the tests assert it never happens there.

## What this can't catch

The stubs model the API surface the addon uses, not the real client. Visual layout (textures,
atlas names, anchor offsets lining up with the art), real taint/secret-value behavior, and
anything Blizzard changes in a client patch still need an in-game check - see the build/deploy
steps in [DEVELOPMENT.md](../DEVELOPMENT.md).
