# UnitFramesImproved

Restyles Blizzard's default Player, Target, and Focus unit frames with a cleaner look, while
keeping Blizzard's own frame logic (health/mana updates, portraits, PvP/faction icons,
classification handling, combat behavior) fully intact. Built to be a minimal-footprint reskin,
not a replacement unit frame system - no separate options UI, no unnecessary hooks.

## Features
- Custom targeting-frame-style textures for Player, Target, and Focus frames (elite/rare/rare-elite
  variants included).
- Class-colored health bars, with tap-denied targets shown gray.
- Health bar and status text repositioned to match the custom textures, tracked against Blizzard's
  own live frame layout so it keeps working across client UI updates instead of relying on
  hardcoded pixel positions.
- Works alongside Blizzard's Secret Values system and combat-lockdown restrictions without tainting
  execution or erroring in combat.

## Supported Clients
One universal package covers all three:

| Client | TOC file | `AllowLoadGameType` |
|---|---|---|
| Retail | `UnitFramesImproved.toc` | `mainline` |
| Classic progression (currently Mists of Pandaria Classic, and future expansions under the same file) | `UnitFramesImproved_Classic.toc` | `classic` |
| Classic Era / Vanilla | `UnitFramesImproved_Vanilla.toc` | `vanilla` |

## Installation
Install via [CurseForge](https://www.curseforge.com/wow/addons/unitframesimproved) or the
CurseForge app. Manual installation: download a release, and extract the `UnitFramesImproved`
folder into `Interface/AddOns` for the client(s) you play.

## Known Issues
### Classic Era & Classic progression
- Frame scaling has not been re-implemented (yet?).
- Anchoring frames to each other has not been re-implemented (yet?).

## Building From Source
`build.ps1` (PowerShell) is a local stand-in for the CurseForge packager - it fetches the same
Ace3/LibStub externals declared in `.pkgmeta`, deploys the addon straight into a local WoW
install's `Interface/AddOns` for every flavor found (Retail/Classic/Classic Era), and stamps the
`@project-version@`/`@project-date-iso@` TOC tokens from `git describe`. Requires PowerShell and a
local WoW installation; run `.\build.ps1 -?` for parameters (e.g. `-WowInstallPath` if
auto-detection doesn't find your install).

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the addon is structured internally.

## Releasing
[.github/workflows/release.yml](.github/workflows/release.yml) runs the real [CurseForge
packager](https://github.com/BigWigsMods/packager) against `.pkgmeta` - it builds the zip, stamps
a version/date into the TOC files, uploads it to the [CurseForge
project](https://www.curseforge.com/wow/addons/unitframesimproved), and attaches the zip to a
matching GitHub release using `CHANGELOG.md` as the release notes. It's manual-only for now: push
a tag, then trigger it from the Actions tab (Run workflow), picking that tag from the branch/tag
dropdown. Requires a `CF_API_KEY` repository secret (a CurseForge API token, from your [CurseForge
account's API Tokens page](https://www.curseforge.com/account/api-tokens), added under Settings ->
Secrets and variables -> Actions).

## Changelog
See [CHANGELOG.md](CHANGELOG.md).

## License
Public domain - see [LICENSE.txt](LICENSE.txt). Bundled Ace3/LibStub libraries are covered by
[LICENSE-ACE3.txt](LICENSE-ACE3.txt).

## Author
Althalla (Kim Forsberg)
