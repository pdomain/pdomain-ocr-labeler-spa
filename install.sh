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

# 2. Resolve the latest tag from the public GitHub API.
LATEST_TAG=$(curl -sSf "https://api.github.com/repos/${REPO}/tags" 2>/dev/null \
    | grep '"name"' | head -1 | sed 's/.*"name": "\([^"]*\)".*/\1/') || true

if [ -z "$LATEST_TAG" ]; then
    echo "Error: could not resolve the latest release tag from GitHub." >&2
    echo "       https://api.github.com/repos/${REPO}/tags returned nothing usable." >&2
    exit 1
fi

echo "Installing pd-ocr-labeler-spa ${LATEST_TAG}..."

# 3. Find the wheel asset attached to the GitHub Release for this tag.
RELEASE_JSON=$(curl -sSf \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/releases/tags/${LATEST_TAG}" 2>/dev/null) || true

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

# 4. Download the wheel to a temp dir and install it as a uv tool.
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
