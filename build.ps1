<#
.SYNOPSIS
  Builds UnitFramesImproved locally, standing in for the CurseForge packager during
  dev/testing.

.DESCRIPTION
  The repo's Libs/ (LibStub, Ace3) are fetched by the real packager from .pkgmeta's SVN
  externals at release time and are not committed here. This script fetches the same
  externals itself over plain HTTP (repos.wowace.com serves its SVN tree over HTTP GET,
  no svn client required), caches them in the gitignored Libs/ folder so repeat builds
  are instant, then copies addon source + Libs into deploy\UnitFramesImproved (gitignored,
  .pkgmeta-ignored) and stamps the @project-version@ / @project-date-iso@ tokens the
  packager would otherwise fill in. It also zips that folder into
  deploy\UnitFramesImproved-<version>.zip, in the same one-folder-at-the-root layout the
  real CurseForge packager produces, for manual testing/sharing without going through CI.

  By default that's the only output - nothing is copied into a WoW install unless you
  opt in via -DeployToWow, -WowInstallPath, or -TargetPath, so a plain `.\build.ps1` is
  always safe to run without touching a live install. When one of those is given, the
  already-staged deploy\UnitFramesImproved folder is copied as-is into Interface\AddOns
  under every _retail_ / _classic_ / _classic_era_ folder found (or into -TargetPath
  directly) - it's a copy of the one build, not a second independent build.

.PARAMETER DeployToWow
  Also copy the build into every WoW install flavor found via -WowInstallPath, the
  UFI_WOW_PATH environment variable, or auto-detection (see Find-WowInstallRoot below),
  in that order. This is what the "Build & Deploy Addon" F5 task in .vscode/launch.json
  uses, so F5 keeps behaving like a full build+deploy.

.PARAMETER TargetPath
  Also copy the build into exactly this one AddOns folder, bypassing WoW-install
  auto-detection and the -WowInstallPath/UFI_WOW_PATH lookup entirely. Implies
  -DeployToWow.

.PARAMETER WowInstallPath
  The WoW install root (the folder that directly contains _retail_/_classic_/
  _classic_era_ - e.g. 'E:\Blizzard\World of Warcraft'). Takes precedence over the
  UFI_WOW_PATH environment variable and auto-detection. Implies -DeployToWow.

.PARAMETER RefreshLibs
  Re-fetch Libs/ even if already cached (e.g. if wowace revs a library).

.EXAMPLE
  .\build.ps1
  .\build.ps1 -DeployToWow
  .\build.ps1 -WowInstallPath 'D:\Games\World of Warcraft'
  .\build.ps1 -TargetPath 'E:\Blizzard\World of Warcraft\_classic_\Interface\AddOns\UnitFramesImproved'

.NOTES
  Install root can also be set persistently via the UFI_WOW_PATH environment variable,
  e.g. (PowerShell): [Environment]::SetEnvironmentVariable('UFI_WOW_PATH', 'E:\Blizzard\World of Warcraft', 'User')
#>
[CmdletBinding()]
param(
    [string]$TargetPath,
    [string]$WowInstallPath,
    [switch]$DeployToWow,
    [switch]$RefreshLibs
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$LibsCache = Join-Path $RepoRoot 'Libs'

# Mirrors .pkgmeta's externals, plus CallbackHandler-1.0 (see .DESCRIPTION above).
$Externals = [ordered]@{
    'LibStub'             = 'https://repos.wowace.com/wow/libstub/tags/1.0'
    'CallbackHandler-1.0' = 'https://repos.wowace.com/wow/ace3/trunk/CallbackHandler-1.0'
    'AceAddon-3.0'        = 'https://repos.wowace.com/wow/ace3/trunk/AceAddon-3.0'
    'AceConsole-3.0'      = 'https://repos.wowace.com/wow/ace3/trunk/AceConsole-3.0'
    'AceEvent-3.0'        = 'https://repos.wowace.com/wow/ace3/trunk/AceEvent-3.0'
}

# WowAce's SVN host serves its tree over plain HTTP (mod_dav_svn autoindex), so a
# directory listing is just <a href="name">name</a> per entry - subdirs end in "/".
# Recursing over that is a lightweight stand-in for `svn export` without needing svn.
function Get-SvnHttpExport {
    param([string]$Url, [string]$Dest)

    $dirUrl = $Url.TrimEnd('/') + '/'
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null

    $response = Invoke-WebRequest -Uri $dirUrl -UseBasicParsing
    $links = [regex]::Matches($response.Content, '<a href="([^"]+)">') | ForEach-Object { $_.Groups[1].Value }

    foreach ($link in $links) {
        if ($link -eq '../' -or $link -match '^https?://') { continue }  # parent link, or the "Powered by Apache Subversion" footer link

        if ($link.EndsWith('/')) {
            Get-SvnHttpExport -Url "$dirUrl$link" -Dest (Join-Path $Dest $link.TrimEnd('/'))
        } else {
            Invoke-WebRequest -Uri "$dirUrl$link" -OutFile (Join-Path $Dest $link) -UseBasicParsing
        }
    }
}

function Sync-Libs {
    if ($RefreshLibs -and (Test-Path $LibsCache)) {
        Remove-Item $LibsCache -Recurse -Force
    }
    if (Test-Path $LibsCache) {
        return
    }

    Write-Host "Fetching Libs (one-time - cached in Libs/ for future builds)..." -ForegroundColor Cyan
    foreach ($name in $Externals.Keys) {
        Write-Host "  $name"
        Get-SvnHttpExport -Url $Externals[$name] -Dest (Join-Path $LibsCache $name)
    }
}

# Locates the WoW install root - the folder that directly contains _retail_ /
# _classic_ / _classic_era_ - without any parameter or env var override.
function Find-WowInstallRoot {
    # 1. Battle.net Agent's product.db is a protobuf blob, but install paths are
    #    embedded in it as plain readable strings - no protobuf parser needed, just
    #    scan the raw bytes for a drive-letter path ending in "World of Warcraft".
    $productDb = Join-Path $env:ProgramData 'Battle.net\Agent\product.db'
    if (Test-Path $productDb) {
        $bytes = [System.IO.File]::ReadAllBytes($productDb)
        $text = [System.Text.Encoding]::Latin1.GetString($bytes)
        $match = [regex]::Match($text, '[A-Za-z]:[\\/][^\x00-\x1f"]*?World of Warcraft')
        if ($match.Success) {
            return ($match.Value -replace '/', '\')
        }
    }

    # 2. Registry key used by some non-Battle.net / legacy Blizzard installers.
    foreach ($key in @(
        'HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft',
        'HKLM:\SOFTWARE\Blizzard Entertainment\World of Warcraft'
    )) {
        if (Test-Path $key) {
            $installPath = (Get-ItemProperty $key -ErrorAction SilentlyContinue).InstallPath
            if ($installPath) { return $installPath.TrimEnd('\') }
        }
    }

    # 3. Common default install locations, as a last resort.
    $candidates = @(
        "${env:ProgramFiles(x86)}\World of Warcraft",
        "$env:ProgramFiles\World of Warcraft"
    )
    foreach ($drive in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
        $candidates += "$($drive.Root)World of Warcraft"
        $candidates += "$($drive.Root)Games\World of Warcraft"
        $candidates += "$($drive.Root)Battle.net\World of Warcraft"
        $candidates += "$($drive.Root)Blizzard\World of Warcraft"
    }
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    return $null
}

# _retail_/_classic_/_classic_era_ are separate installs sharing one root; deploy to
# every one that's actually present so all flavors stay in sync from one run.
$Flavors = [ordered]@{
    '_retail_'      = 'Retail'
    '_classic_'     = 'Classic'
    '_classic_era_' = 'Classic Era'
}

$DeployDir = Join-Path $RepoRoot 'deploy\UnitFramesImproved'

# Every build always stages into the local, gitignored deploy/ folder (a look at exactly what
# would ship, and something to inspect/zip up without a WoW install at hand). WoW install
# copies are opt-in only (-DeployToWow / -WowInstallPath / -TargetPath) - returns an empty
# array when the caller didn't ask for any of those, so a plain `.\build.ps1` never touches
# a live install.
function Get-WowDeployTargets {
    if ($TargetPath) {
        return @($TargetPath)
    }

    if (-not $DeployToWow -and -not $WowInstallPath) {
        return @()
    }

    $root = $WowInstallPath
    if (-not $root) { $root = $env:UFI_WOW_PATH }
    if (-not $root) { $root = Find-WowInstallRoot }

    if (-not $root) {
        Write-Host "No WoW install found - deploy\UnitFramesImproved was still built. Pass -WowInstallPath, set the UFI_WOW_PATH environment variable, or pass -TargetPath to deploy into a live install." -ForegroundColor Yellow
        return @()
    }
    if (-not (Test-Path $root)) {
        throw "WoW install path '$root' does not exist."
    }

    Write-Host "WoW install root: $root" -ForegroundColor Cyan

    $targets = @()
    foreach ($flavor in $Flavors.Keys) {
        $flavorPath = Join-Path $root $flavor
        if (Test-Path $flavorPath) {
            $targets += Join-Path $flavorPath 'Interface\AddOns\UnitFramesImproved'
            Write-Host "  found $($Flavors[$flavor]) ($flavor)" -ForegroundColor DarkGray
        }
    }

    if ($targets.Count -eq 0) {
        Write-Host "  no _retail_/_classic_/_classic_era_ folder found under '$root'" -ForegroundColor Yellow
    }

    return $targets
}

# What actually ships - source files only, no .git/.claude/.vscode/build.ps1/etc.
$SourceItems = @(
    'HelperFunctions.lua',
    'UnitFramesImproved.lua',
    'UnitFramesImproved.toc',
    'UnitFramesImproved_Retail.lua',
    'UnitFramesImproved_Classic.lua',
    'UnitFramesImproved_Classic.toc',
    'UnitFramesImproved_Vanilla.toc',
    'Textures',
    'LICENSE.txt',
    'LICENSE-ACE3.txt',
    'README.md'
)

# Guards the wipe in Deploy-Addon below: refuses unless the target both looks like a WoW
# AddOns folder (or is the local deploy/ staging folder) for this addon specifically, AND
# every entry already in it is one our own deploy could have produced. A -TargetPath typo
# or a Deploy-Addon caller bug pointing this at, say, a Documents folder must not turn into
# a silent recursive delete.
function Assert-SafeToWipe {
    param([string]$Target)

    if (-not (Test-Path $Target)) {
        return
    }

    if ($Target -ne $DeployDir -and $Target -notmatch '\\Interface\\AddOns\\UnitFramesImproved\\?$') {
        throw "Refusing to wipe '$Target' - doesn't look like a WoW AddOns folder (expected it to end in '...\Interface\AddOns\UnitFramesImproved') or the local deploy folder ('$DeployDir')."
    }

    $knownEntries = @($SourceItems) + 'Libs'
    $unexpected = Get-ChildItem $Target -Name | Where-Object { $_ -notin $knownEntries }
    if ($unexpected) {
        throw "Refusing to wipe '$Target' - it contains entries this script doesn't recognize as part of the addon: $($unexpected -join ', '). Remove them by hand first if that's intentional, in case they're not meant to be deleted."
    }
}

function Deploy-Addon {
    param([string]$Target)

    Write-Host "Deploying to $Target" -ForegroundColor Cyan

    # Wipe first so files removed/renamed on the source side (or left over from an
    # older, unrelated copy of the addon) don't linger next to the current build.
    if (Test-Path $Target) {
        Assert-SafeToWipe -Target $Target
        Remove-Item $Target -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null

    foreach ($item in $SourceItems) {
        $srcPath = Join-Path $RepoRoot $item
        if (-not (Test-Path $srcPath)) { continue }
        Copy-Item -Path $srcPath -Destination (Join-Path $Target $item) -Recurse -Force
    }

    $libsTarget = Join-Path $Target 'Libs'
    New-Item -ItemType Directory -Force -Path $libsTarget | Out-Null
    Copy-Item -Path (Join-Path $LibsCache '*') -Destination $libsTarget -Recurse -Force

    # Stamp the tokens the real packager substitutes at release time.
    $version = git -C $RepoRoot describe --tags --always --dirty 2>$null
    if (-not $version) { $version = 'dev' }
    $dateIso = Get-Date -Format 'yyyy-MM-dd'
    $script:BuildVersion = $version

    Get-ChildItem -Path $Target -Filter '*.toc' | ForEach-Object {
        (Get-Content $_.FullName -Raw) `
            -replace '@project-version@', $version `
            -replace '@project-date-iso@', $dateIso |
            Set-Content -Path $_.FullName -NoNewline
    }

    Write-Host "  version $version ($dateIso)" -ForegroundColor Green
}

# Zips the staged build into deploy\UnitFramesImproved-<version>.zip - the same
# one-folder-at-the-root layout the real CurseForge packager produces, so it's ready to
# manually upload/share or extract straight into Interface\AddOns. Removes any zip left
# over from a previous, differently-versioned build first so they don't pile up.
function New-DeployZip {
    $deployRoot = Split-Path $DeployDir -Parent
    Get-ChildItem -Path $deployRoot -Filter 'UnitFramesImproved-*.zip' -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $zipPath = Join-Path $deployRoot "UnitFramesImproved-$script:BuildVersion.zip"
    Compress-Archive -Path $DeployDir -DestinationPath $zipPath -Force

    Write-Host "  zipped to $zipPath" -ForegroundColor Green
}

# Copies the already-built deploy\UnitFramesImproved folder as-is into a WoW install (or
# -TargetPath) - a copy of the one staged build, not an independent second build, so every
# target ends up byte-for-byte identical.
function Copy-StagedBuildTo {
    param([string]$Target)

    Write-Host "Deploying to $Target" -ForegroundColor Cyan

    if (Test-Path $Target) {
        Assert-SafeToWipe -Target $Target
        Remove-Item $Target -Recurse -Force
    }

    Copy-Item -Path $DeployDir -Destination $Target -Recurse -Force
    Write-Host "  version $script:BuildVersion" -ForegroundColor Green
}

Sync-Libs
Deploy-Addon -Target $DeployDir
New-DeployZip
foreach ($target in (Get-WowDeployTargets)) {
    Copy-StagedBuildTo -Target $target
}
