# Agent Instructions

For AI coding agents working in this repository. [DEVELOPMENT.md](DEVELOPMENT.md) covers building,
testing and releasing, and [ARCHITECTURE.md](ARCHITECTURE.md) how the addon is structured.

## Releases: Refresh the Art Comparison
Whenever you prepare a release or a tag, refresh the art comparison that [README.md](README.md)
shows, `docs/unitframe-art-comparison.png`, so that it shows the release being made. Do it even when
the release doesn't touch the art: the sheet also draws the current game builds, which change on
their own.

1. Commit everything else that goes into the release first (code, `CHANGELOG.md`). The sheet is
   stamped with the commit it was drawn from, and `--publish` refuses to run while there are
   uncommitted changes.
2. From the repo root, run `python tools/compare_unitframe_art.py --publish`
   (`python -m pip install -r tools/requirements.txt` first, if needed). It draws the sheet into
   `tools/out/` and copies it to `docs/unitframe-art-comparison.png`. It reads the game files from
   the local World of Warcraft install and downloads what's missing from wago.tools.
3. Check the sheet before committing it. Look at the image for cells that show an error instead of
   art, or columns that say a version couldn't be loaded. Read the script's output for anything new
   in its "not followed" lines (addon code the tool couldn't run). If something is wrong, tell the
   user instead of publishing the sheet.
4. Commit the image by itself ("Update the art comparison for <version>"), and tag that commit, so
   the README at the tag shows that release.
5. Check that README.md still shows `docs/unitframe-art-comparison.png` (under "How It Looks"), and
   put the section back if it's gone.

The image goes to GitHub with the repo, but must never ship inside the addon. `docs/` is in the
`.pkgmeta` ignore list, and `build.ps1` only copies the files it lists. Keep it that way if you move
the image or add files next to it.
