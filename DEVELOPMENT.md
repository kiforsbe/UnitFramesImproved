# Development

Building from source and cutting a release for UnitFramesImproved. See [README.md](README.md) for
what the addon does, and [ARCHITECTURE.md](ARCHITECTURE.md) for how the code is structured.

## Building From Source
`build.ps1` (PowerShell) is a local stand-in for the CurseForge packager - it stages a build into
`deploy\UnitFramesImproved`, stamps the
`@project-version@`/`@project-date-iso@` TOC tokens from `git describe`, and zips the result into
`deploy\UnitFramesImproved-<version>.zip` (folder-at-the-root, ready to extract straight into
`Interface\AddOns` or share for manual testing).

```powershell
.\build.ps1                                                                     # deploy\UnitFramesImproved only
.\build.ps1 -DeployToWow                                                       # also copy into every detected local WoW install
.\build.ps1 -WowInstallPath 'D:\Games\World of Warcraft'                       # explicit install root
.\build.ps1 -TargetPath 'E:\...\_classic_\Interface\AddOns\UnitFramesImproved' # exact target only
```

`-DeployToWow` copies into every install flavor it finds under the WoW root: `_retail_`,
`_classic_`, `_classic_era_`, `_anniversary_`, and `_classic_beta_` (the WoW Forever beta). Run
`Get-Help .\build.ps1 -Full` for every parameter and example. The install root can also be set
persistently via the `UFI_WOW_PATH` environment variable instead of passing `-WowInstallPath` every
time. The VS Code "Build & Deploy Addon" launch task (F5) runs `.\build.ps1 -DeployToWow`.

## Testing
`tests/` holds offline regression tests that load the addon into a stubbed WoW client (Lua 5.1 via
Python's `lupa`) once per TOC - Retail, WoW Forever, Mists Classic, TBC Anniversary, Classic Era -
and check loading, event handling, styling, the options page, and packaging. They never ship: no
TOC loads them and both `.pkgmeta` and `build.ps1` leave them out.

```sh
pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

See [tests/README.md](tests/README.md) for how the stubs work and what still needs an in-game check.

## Releasing
[.github/workflows/release.yml](.github/workflows/release.yml) runs the real [CurseForge
packager](https://github.com/BigWigsMods/packager) against `.pkgmeta` - it builds the zip, stamps a
version/date into the TOC files, uploads it to the [CurseForge
project](https://www.curseforge.com/wow/addons/unitframesimproved), and attaches the zip to a
matching GitHub release using `CHANGELOG.md` as the release notes.

It's manual-only for now: push a tag, then trigger the workflow from the Actions tab (Run
workflow), picking that tag from the branch/tag dropdown. Requires a `CF_API_KEY` repository secret
(a CurseForge API token, from your [CurseForge account's API Tokens
page](https://www.curseforge.com/account/api-tokens), added under Settings -> Secrets and
variables -> Actions).
