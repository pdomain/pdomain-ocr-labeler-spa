#!/usr/bin/env bash
set -euo pipefail

# Install pd-ocr-labeler-spa as a standalone tool using uv.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-labeler-spa/main/install.sh | bash
#
# Downloads the prebuilt wheel attached to the latest GitHub Release and
# runs `uv tool install` against it. The wheel ships with the React SPA
# already bundled, so end users do NOT need Node, npm, or a JavaScript
# toolchain — only `uv` (which this script will install for you).
#
# Mirrors the pd-prep-for-pgdp installer shape; this one is shorter
# because pd-ocr-labeler-spa has no CUDA / GPU extras to negotiate.
# Python 3.13+ is required (pyproject.toml requires-python).

REPO="ConcaveTrillion/pd-ocr-labeler-spa"

# 1. Install uv if not already present (provides Python 3.13 too).
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found — installing uv from https://astral.sh/uv/install.sh ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Preflight Python check. `uv tool install` will auto-download Python
#    3.13 if missing, so this is informational, not gating — but it lets
#    the user know up-front whether their system Python is new enough.
if command -v python3 >/dev/null 2>&1; then
    SYS_PY=$(python3 -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>/dev/null || echo "?")
    if [ "$SYS_PY" != "3.13" ] && [ "$SYS_PY" != "?" ]; then
        echo "Note: system python3 is ${SYS_PY}; pd-ocr-labeler-spa requires 3.13."
        echo "      uv will download Python 3.13 automatically — no action needed."
    fi
fi

# 3. Resolve the latest published release from the GitHub API.
#    `/releases/latest` returns the most recent *published* release
#    (ignoring drafts/prereleases) and embeds asset URLs directly, so
#    we save a round-trip vs `/tags` + `/releases/tags/<tag>`. It is
#    also robust to pre-1.0 tag retag flows (this repo retagged
#    v0.0 → v0.0.0 in iter 7) where `/tags` ordering by commit-date
#    can return the wrong "latest".
RELEASE_JSON=$(curl -sSf \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null) || true

if [ -z "$RELEASE_JSON" ]; then
    echo "Error: could not resolve the latest release from GitHub." >&2
    echo "       https://api.github.com/repos/${REPO}/releases/latest returned nothing usable." >&2
    echo "       (Has a release been published yet?)" >&2
    exit 1
fi

LATEST_TAG=$(printf '%s\n' "$RELEASE_JSON" \
    | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

echo "Installing pd-ocr-labeler-spa ${LATEST_TAG}..."

# 4. Find the wheel asset attached to the latest release.
WHEEL_URL=$(printf '%s\n' "$RELEASE_JSON" \
    | grep '"browser_download_url"' \
    | grep -E '\.whl"' \
    | head -1 \
    | sed 's/.*"browser_download_url": *"\([^"]*\)".*/\1/')

if [ -z "$WHEEL_URL" ]; then
    # Hard-fail rather than fall back to `git+...`. The git+ path requires
    # Node + npm on the user's machine to build the React SPA at install
    # time, which is exactly the requirement this script is designed to
    # avoid. See peer pd-prep-for-pgdp/install.sh for the same rationale.
    echo "Error: no .whl asset attached to release ${LATEST_TAG}." >&2
    echo "       Expected a wheel uploaded by .github/workflows/release.yml." >&2
    echo "       Check https://github.com/${REPO}/releases/tag/${LATEST_TAG}" >&2
    exit 1
fi

# 5. Download the wheel to a temp dir and install it as a uv tool.
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

WHEEL_FILE="${TMPDIR}/$(basename "$WHEEL_URL")"
echo "Downloading ${WHEEL_URL}..."
curl -fsSL -o "$WHEEL_FILE" "$WHEEL_URL"

# uv tool install picks Python 3.13 automatically (downloads it if
# missing) since pyproject.toml's requires-python is ">=3.13,<4.0".
uv tool install --reinstall "$WHEEL_FILE"

echo ""
echo "Done! Run: pd-ocr-labeler-ui --help"
echo "If 'pd-ocr-labeler-ui' is not found, add uv's tool bin to your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
