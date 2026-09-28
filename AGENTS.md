# Agent Instructions

For AI coding agents working in this repository. [DEVELOPMENT.md](DEVELOPMENT.md) covers building,
testing and releasing, [ARCHITECTURE.md](ARCHITECTURE.md) how the addon is structured, and
[tests/README.md](tests/README.md) what the offline tests do and don't cover.

## Changelog
`CHANGELOG.md` is written by hand, and keeping it up to date is your job. It follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and players read it: `.pkgmeta` makes the
packager ship it in the zip and use it as the CurseForge changelog and the GitHub release notes.

- Add the entry in the same commit as the change, under `## [Unreleased]`, in `### Added`,
  `### Changed`, `### Fixed` or `### Removed`. Everything players notice gets an entry, and so do
  notable changes to how the addon is built, tested or released (as `tests/` and `build.ps1` did in
  4.1.0).
- Say what changed for the player first, then why if it isn't obvious. Name the clients it applies
  to (Retail, WoW Forever, Mists, Wrath, TBC, Classic Era) when it isn't all of them.
- Don't rewrite the entries of a version that's been released.

## What Ships
Two lists decide what goes into the addon, and they must agree:

- `build.ps1` (the local build and deploy) copies only the files in its `$SourceItems`.
- The CurseForge packager (the release workflow) copies every tracked file except what `.pkgmeta`
  ignores. Files and folders whose names start with a dot are left out on their own.

A new file or folder the addon loads goes in `$SourceItems`. A new tracked file or folder that isn't
part of the addon (docs, tools, agent files) goes in the `.pkgmeta` ignore list. A new TOC also goes
in `CLIENTS` in `tests/harness.py`. `tests/test_addon.py` checks some of this.

## TOC Files
- `## Interface:` must be the first line. With anything before it, even a comment, the client
  ignores the TOC.
- Leave `@project-version@` and `@project-date-iso@` as they are. The packager fills them in from
  the tag, and `build.ps1` from `git describe`. There's no version to bump in the TOCs.
- The `## Interface:` number must be at least that of the client it's for, or the game lists the
  addon as out of date. It's the client version as major × 10000 + minor × 100 + patch: 12.1.0 is
  `120100`, 1.15.9 is `11509`, 3.80.2 is `38002`. The art comparison prints each current client's
  version, which makes this easy to check.

## Making a Release
Do these in order. If a step fails, stop and tell the user instead of working around it.

1. **Start clean.** Everything that goes into the release is committed, and `git status` shows
   nothing.
2. **Check the TOCs.** Compare each `## Interface:` with its current client (see TOC Files). If one
   is behind, update it, add a changelog entry, and commit that first.
3. **Run the tests:** `python -m unittest discover -s tests -v` (after
   `python -m pip install -r tests/requirements.txt`, if needed). All must pass. List every failing
   test by name.
4. **Offer an in-game check.** If the release changes how the frames look or behave, remind the
   user that the offline tests can't catch layout, taint or client patch problems, and offer
   `.\build.ps1 -DeployToWow` so they can check in game before you go on.
5. **Refresh the art comparison** that README.md shows, `docs/unitframe-art-comparison.png`. Do it
   even when the release doesn't touch the art: the sheet also draws the current game builds, which
   change on their own.
   - From the repo root, run `python tools/compare_unitframe_art.py --publish` (after
     `python -m pip install -r tools/requirements.txt`, if needed). It reads the game files from the
     local World of Warcraft install and downloads what's missing from wago.tools.
   - It refuses to run while there are uncommitted changes. The sheet is stamped with the commit it
     was drawn from. The release commit only adds the changelog and the image, so that commit has
     the same addon code as the release.
   - It draws the sheet into `tools/out/` and copies it to `docs/unitframe-art-comparison.png`.
   - Then check it:
     - look at the image for cells that show an error instead of art, and for columns that say a
       version couldn't be loaded;
     - read the script's output for new "not followed" lines (addon code the tool couldn't run).

     If something is wrong, tell the user instead of releasing with it.
6. **Pick the version**, `<major>.<minor>.<patch>-universal`. The suffix says it's one package for
   every client.
   - Patch: fixes only.
   - Minor: new features or newly supported clients.
   - Major: changes that break something players rely on.

   Ask the user if it isn't clear. Never put "alpha" or "beta" in it, or the packager uploads the
   release as an alpha or beta.
7. **Update the changelog.**
   - Rename `## [Unreleased]` to `## [<version>] - <YYYY-MM-DD>` with today's date, and add a new,
     empty `## [Unreleased]` above it.
   - At the bottom, point the `[Unreleased]` link at `compare/<version>...HEAD`, and add a
     `[<version>]` link that compares the previous release with this one.
   - Read the new section as a player would: it's the release notes.
8. **Update README.md** if the release changes what it describes: features, supported clients,
   options, known issues. Check that it still shows `docs/unitframe-art-comparison.png` (under "How
   It Looks"), and put the section back if it's gone.
9. **Commit the release.** Put `CHANGELOG.md`, `docs/unitframe-art-comparison.png` and any README
   change in one commit, named `Release <version>: <what's in it, in a few words>`.
10. **Tag that commit** with an annotated tag whose message is the version:
    `git tag -a <version> -m "<version>"`.
11. **Hand over.** Don't push the commits or the tag, and don't run the release workflow, unless the
    user asks: that publishes the release to CurseForge and GitHub. Tell the user it's ready.
    Publishing means pushing the commits and the tag, then running "Package and Release" from the
    Actions tab and picking the tag.

The art comparison goes to GitHub with the repo, but it must never ship in the addon. `docs/` is in
the `.pkgmeta` ignore list, and `build.ps1` doesn't list it. Keep it that way if you move the image.
