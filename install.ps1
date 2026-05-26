# pd-ocr-labeler-spa installer (Windows PowerShell)
#
# Usage:
#   irm https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-labeler-spa/main/install.ps1 | iex
#
# Downloads the prebuilt wheel attached to the latest GitHub Release and
# runs `uv tool install` against it. The wheel ships with the React SPA
# already bundled, so end users do NOT need Node, npm, or a JavaScript
# toolchain — only `uv` (which this script will install for you).
#
# PowerShell 5.1+ compatible (the version that ships with Windows 10/11);
# pwsh 7+ also works. Mirrors install.sh; Python 3.13+ is required
# (pyproject.toml requires-python).

$ErrorActionPreference = "Stop"

$repo = "ConcaveTrillion/pd-ocr-labeler-spa"

# B-32: explicit boolean return. The earlier form piped Get-Command
# through ForEach-Object and relied on PowerShell's pipeline-return
# coercion — which is array-shaped, and the callers (`if (-not …)`)
# only worked because `-not` against a non-empty array yields the
# right answer by accident. `$null -ne (...)` is unambiguous: a
# single Boolean leaves the function in both branches.
function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

# 1. Install uv if not already present (provides Python 3.13 too).
#
# Security (F-017 Option B): download from a pinned, immutable GitHub Release
# asset URL rather than piping https://astral.sh/uv/install.ps1 into
# Invoke-Expression. GitHub Release assets at tagged URLs are immutable once
# published; TLS to github.com provides transport integrity. Upstream
# (astral-sh/uv) does not publish a checksum for the installer script itself
# (sha256.sum covers binary tarballs only), so the pinned-tag approach is the
# pragmatic baseline. To upgrade: update $uvVer below.
$uvVer = "0.11.16"
if (-not (Test-Command -Name "uv")) {
    Write-Host "uv not found — installing uv $uvVer from GitHub Releases..."
    $uvInstallerUrl = "https://github.com/astral-sh/uv/releases/download/$uvVer/uv-installer.ps1"
    $uvInstallerTmp = Join-Path ([System.IO.Path]::GetTempPath()) "uv-installer-$([System.Guid]::NewGuid()).ps1"
    Invoke-WebRequest -Uri $uvInstallerUrl -OutFile $uvInstallerTmp -UseBasicParsing
    try { & powershell -NoProfile -ExecutionPolicy Bypass -File $uvInstallerTmp }
    finally { Remove-Item $uvInstallerTmp -ErrorAction SilentlyContinue }
    $env:Path = "$HOME\.local\bin;" + $env:Path
}

# 2. Preflight Python check. `uv tool install` will auto-download Python
#    3.13 if missing, so this is informational, not gating — but it lets
#    the user know up-front whether their system Python is new enough.
#
# B-33: also detect the Microsoft Store stub redirector at
# %LocalAppData%\Microsoft\WindowsApps\python.exe. The stub satisfies
# `Test-Command "python"` (the file exists on PATH) but invoking it
# with arguments emits a "Python was not found" message and exits
# without running. We match the real-Python-version output shape
# (`Python <maj>.<min>[.<patch>][<suffix>]`) and bail with a clear
# message when the stub is detected — uv still handles actual Python
# provisioning, but the user-facing note about a missing real Python
# is what the preflight is for.
#
# B-40: regex anchors only on `Python <maj>.<min>` and tolerates any
# trailing characters. `Python --version` outputs vary:
#   release       -> `Python 3.13.0`
#   pre-release   -> `Python 3.14.0a1`, `Python 3.14.0rc2`
#   pyenv-built   -> `Python 3.13.0+`
# All are real Pythons; the stub on the other hand prints a multi-
# line "Python was not found" reparse-point message that does not
# start with `Python <digit>.<digit>` at all. Loosening the trailing
# match avoids mislabelling pre-release Python users as having a
# Store stub.
if (Test-Command -Name "python") {
    try {
        $pyVersionOutput = (& python --version 2>&1) | Out-String
        $pyVersionOutput = $pyVersionOutput.Trim()
        if ($pyVersionOutput -notmatch '^Python \d+\.\d+(\.\d+)?') {
            Write-Host "Note: `python --version` on PATH did not return the expected `Python <X>.<Y>.<Z>` shape."
            Write-Host "      This usually means the Microsoft Store stub redirector at"
            Write-Host "      %LocalAppData%\Microsoft\WindowsApps\python.exe (Windows 10/11 default when no real Python is installed)."
            Write-Host "      Output was: ${pyVersionOutput}"
            Write-Host "      uv will install Python 3.13 automatically; if you'd rather install Python yourself,"
            Write-Host "      grab it from https://www.python.org/downloads/ or run: winget install Python.Python.3.13"
        } else {
            $sysPy = & python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
            if ($sysPy -and $sysPy -ne "3.13") {
                Write-Host "Note: system python is ${sysPy}; pd-ocr-labeler-spa requires 3.13."
                Write-Host "      uv will download Python 3.13 automatically — no action needed."
            }
        }
    } catch {
        # Non-fatal: uv handles the actual Python provisioning.
    }
}

# 3. Resolve the latest published release from the GitHub API.
#    `/releases/latest` returns the most recent *published* release
#    (ignoring drafts/prereleases) and embeds asset URLs directly, so
#    we save a round-trip vs `/tags` + `/releases/tags/<tag>`. It is
#    also robust to pre-1.0 tag retag flows (this repo retagged
#    v0.0 → v0.0.0 in iter 7) where `/tags` ordering by commit-date
#    can return the wrong "latest". Mirrors install.sh's B-27 fix.
try {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ Accept = "application/vnd.github+json" } -UseBasicParsing
} catch {
    throw "Could not resolve the latest release from https://api.github.com/repos/$repo/releases/latest : $_"
}
if (-not ($release -and $release.tag_name)) {
    throw "Could not resolve the latest release tag from GitHub. (Has a release been published yet?)"
}
$latestTag = $release.tag_name
Write-Host "Installing pd-ocr-labeler-spa $latestTag..."

# 4. Find the wheel asset attached to the latest release.
$wheelAsset = $null
if ($release.assets) {
    $wheelAsset = $release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
}
if (-not $wheelAsset) {
    # Hard-fail rather than fall back to `git+...`. The git+ path requires
    # Node + npm on the user's machine to build the React SPA at install
    # time, which is exactly the requirement this script is designed to
    # avoid. See peer pd-prep-for-pgdp/install.ps1 for the same rationale.
    throw @"
No .whl asset attached to release $latestTag.
Expected a wheel uploaded by .github/workflows/release.yml.
Check https://github.com/$repo/releases/tag/$latestTag — the release
workflow may have failed, or this is an older tag from before wheel
publishing was wired up.
"@
}

# 5. Download the wheel to a temp dir and install it as a uv tool.
$tmpDir = New-Item -ItemType Directory -Path (Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString()))
try {
    $wheelFile = Join-Path $tmpDir.FullName $wheelAsset.name
    Write-Host "Downloading $($wheelAsset.browser_download_url)..."
    Invoke-WebRequest -Uri $wheelAsset.browser_download_url -OutFile $wheelFile -UseBasicParsing

    # uv tool install picks Python 3.13 automatically (downloads it if
    # missing) since pyproject.toml's requires-python is ">=3.13,<4.0".
    & uv tool install --reinstall $wheelFile
} finally {
    Remove-Item -Recurse -Force $tmpDir.FullName -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done! Run: pd-ocr-labeler-ui --help"
Write-Host "If 'pd-ocr-labeler-ui' is not found, add uv's tool bin to your PATH:"
Write-Host "  `$env:Path = `"`$HOME\.local\bin;`" + `$env:Path"
