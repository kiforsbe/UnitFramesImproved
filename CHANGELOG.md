# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [4.0.1-universal] - 2026-09-01

### Fixed
- Classic-family TOC files (`_Vanilla`, `_Mists`, `_TBC`) failed to load at all - each started
  with a plain `#` comment line before `## Interface:`, which the client silently treats as an
  unparseable TOC (confirmed by comparing against ~200 real installed addons: only Questie's
  deliberately-broken placeholder TOC shared that pattern, used intentionally to produce this
  exact effect). `## Interface:` is now always the first line.
- `UnitFramesImproved_Classic.toc` renamed to `UnitFramesImproved_Mists.toc` - Mists of Pandaria
  Classic has its own dedicated TOC suffix (confirmed via other installed addons, e.g.
  `TomTom_Mists.toc`, `BetterBags_Mists.toc`); the generic `_Classic` catch-all suffix wasn't being
  reliably matched for it.
- MoP Classic `Interface` declaration corrected and broadened to `50500, 50501, 50502, 50504` -
  `50504` is this client's actual running interface (`/dump select(4, GetBuildInfo())`), which has
  to be present in the list since "out of date" triggers whenever the declared Interface is lower
  than the client's, not merely different from it.
- Removed `## AllowLoadGameType` from all TOC files - redundant with, and murkier than, the
  per-flavor TOC suffix split already in place.

### Added
- `UnitFramesImproved_TBC.toc` for the Burning Crusade Classic Anniversary client (`_anniversary_`,
  product `wow_anniversary`) - a separate product from Classic Era, not a continuation of it.
- `build.ps1` now auto-detects and deploys to a `_anniversary_` install alongside the existing
  `_retail_`/`_classic_`/`_classic_era_` flavors, and ships `CHANGELOG.md` in the built addon
  folder/zip.

## [4.0.0-universal] - 2026-09-01

### Fixed
- Classic: player frame health bar not showing the player's class color - `Style_PlayerFrame` was
  silently erroring on `hooksecurefunc("TextStatusBar_UpdateTextStringWithValues", ...)` on clients
  that have migrated to Blizzard's mixin-based `TextStatusBarMixin` system, aborting the rest of the
  function (including the class-color update) before it ever ran.
- Classic: player frame health bar reverting to Blizzard's default green shortly after showing the
  correct class color - `lockColor` wasn't set, so Blizzard's own native health-bar update kept
  repainting over it on every health change.
- Classic: Player/Target frame health bar X/Y position drift and hardcoded offsets - position is now
  derived from Blizzard's own live anchor plus a fixed, named addon-specific delta, instead of
  hardcoded absolute values or a full copy of Blizzard's live position.
- Classic: Target frame `Background` texture anchored to the wrong corner with stale offsets.
- Retail: Secret Values taint crash in `Style_PlayerFrame` when health/mana is a secret value at the
  moment of a forced text update.
- Potential crash in `UpdateStatusBarColor` when `frame`/`frame.healthbar` is nil (e.g.
  target-of-target frames that may not exist, or lack a `.healthbar` alias, on every client).
- Target frame ending up with a mix of addon and Blizzard styling when switching targets in combat -
  `InCombatLockdown()` guards were narrowed to only the genuinely combat-restricted operation
  (creating new regions); repositioning/recoloring already-existing regions isn't restricted.

### Added
- `PLAYER_REGEN_ENABLED` catch-up that re-applies styling on leaving combat, so anything actually
  skipped by a combat-lockdown guard gets retried instead of staying unstyled for the rest of the
  session.
- Local `build.ps1` script that fetches the same Ace3/LibStub externals `.pkgmeta` declares and
  stages a build for testing without going through the CurseForge packager - defaults to
  `deploy/UnitFramesImproved` only, with `-DeployToWow` (or `-WowInstallPath`/`-TargetPath`) to also
  copy that build into a local WoW install.
- `.github/workflows/release.yml`: manually-triggerable (Actions tab -> Run workflow) packaging and
  CurseForge publishing via the `BigWigsMods/packager` action, which also attaches the built zip to
  a matching GitHub release using this changelog as the release notes.
- `IconTexture` metadata in all three TOC files, so the addon shows an icon in the in-game AddOns
  list instead of the default blank/placeholder icon.
- `build.ps1` now also zips the staged build into `deploy\UnitFramesImproved-<version>.zip`.

### Changed
- Debug "Loading config... / Config loaded." messages now only print on the very first load, not on
  every zone transition or post-combat re-application.
- `UnitFramesImproved_UpdateTextStringWithValues` moved off the global namespace onto
  `UnitFramesImproved.UpdateTextStringWithValues`.
- `README.md` rewritten for players only, in the style of the CurseForge listing description;
  build/release instructions moved to the new `DEVELOPMENT.md`.
- Addon author metadata updated to kiforsbe / KawF.

## [3.0.0-universal] - 2024-08-24
### Added
- Universal package: Retail, Classic (Cata and later progression), and Classic Era/Vanilla now ship
  from one download instead of separate per-flavor packages.

## [2.2.0-retail] - 2024-08-22
### Changed
- Updated for Retail patch 11.0.2.

## [2.1.0-retail] - 2022-12-27
### Changed
- Migrated to the Ace3 addon framework and fixed related taint issues.
- Moved source files to the repo root.

## [2.0.1-retail] - 2022-11-04
### Fixed
- Missing `InCombatLockdown()` checks that could throw errors and disable the addon.

## [2.0.0-retail] - 2022-10-29
- Initial tagged release.

[Unreleased]: https://github.com/kiforsbe/UnitFramesImproved/compare/4.0.1-universal...HEAD
[4.0.1-universal]: https://github.com/kiforsbe/UnitFramesImproved/compare/4.0.0-universal...4.0.1-universal
[4.0.0-universal]: https://github.com/kiforsbe/UnitFramesImproved/compare/3.0.0-universal...4.0.0-universal
[3.0.0-universal]: https://github.com/kiforsbe/UnitFramesImproved/compare/2.2.0-retail...3.0.0-universal
[2.2.0-retail]: https://github.com/kiforsbe/UnitFramesImproved/compare/2.1.0-retail...2.2.0-retail
[2.1.0-retail]: https://github.com/kiforsbe/UnitFramesImproved/compare/2.0.1-retail...2.1.0-retail
[2.0.1-retail]: https://github.com/kiforsbe/UnitFramesImproved/compare/2.0.0-retail...2.0.1-retail
[2.0.0-retail]: https://github.com/kiforsbe/UnitFramesImproved/releases/tag/2.0.0-retail
