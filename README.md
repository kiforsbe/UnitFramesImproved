# UnitFramesImproved

*"Improve upon the standard Blizzard unit frames, without going beyond the boundaries they set."*

A minimal-footprint reskin of Blizzard's own Player, Target, and Focus unit frames - not a
replacement unit frame system. UnitFramesImproved keeps Blizzard's own frame logic (health/mana
updates, portraits, PvP/faction icons, classification handling, combat behavior) fully intact and
only changes how the frames look. Nothing to set up - it just works.

## Key Features
- Class-colored health bars, with tap-denied targets shown gray.
- Status text (numbers, percentages, or both) follows the game's own Status Text setting, with large
  numbers abbreviated automatically (e.g. "12.4k/45.3k"). On clients that don't show that setting,
  like WoW Forever, it's available under Options -> AddOns -> UnitFramesImproved.
- Built to work reliably with Blizzard's newest protections - no errors or glitches in combat.

### On Classic (Classic Era & Classic progression)
- Custom targeting-frame-style textures for the Player, Target, and Focus frames, including
  elite/rare/rare-elite border variants.
- Health bar and status text repositioned to match the custom textures, staying lined up correctly
  even after Blizzard UI updates.

## Platform Support
One download works for Retail, WoW Forever, Classic (currently Mists of Pandaria Classic), Wrath
(Titan Reforged), TBC Anniversary, and Classic Era.

## Installation
Install via [CurseForge](https://www.curseforge.com/wow/addons/unitframesimproved) or the
CurseForge app. Manual installation: download a release, and extract the `UnitFramesImproved`
folder into `Interface/AddOns` for the client(s) you play.

## Configuration
How it looks is how it looks, by design. The one option is **Status Text** (Numeric Value /
Percentage / Both / None) under Options -> AddOns -> UnitFramesImproved, or `/ufi` (or
`/unitframesimproved`) to open it. It's the same setting as the game's own Status Text option, so
changing either one changes both - it's there mainly because WoW Forever has no visible option for
showing health and mana numbers. A change made in combat applies as soon as combat ends.

The frame-scale and frame-anchoring settings from older versions were removed since Blizzard's
default UI already covers them.

## Known Issues
### Classic Era & Classic progression
- Frame scaling has not been re-implemented (yet?).
- Anchoring frames to each other has not been re-implemented (yet?).

## For Developers
See [DEVELOPMENT.md](DEVELOPMENT.md) for building from source and cutting a release, and
[ARCHITECTURE.md](ARCHITECTURE.md) for how the addon is structured internally.

## Changelog
See [CHANGELOG.md](CHANGELOG.md).

## License
Public domain - see [LICENSE.txt](LICENSE.txt).

