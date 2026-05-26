#!/usr/bin/env bash
# pip-audit-with-manifest.sh — F-021 fix
#
# pip-audit only audits packages it can resolve via PyPI. Dependencies served
# from private registries (pd-index-pip), GitHub Releases, or other non-PyPI
# sources are silently skipped — or cause pip-audit to fail entirely when it
# tries to resolve them.
#
# This script:
#   1. Parses uv.lock to find packages from non-PyPI sources.
#   2. Filters those packages out of the exported requirements before
#      running pip-audit, so the audit completes successfully.
#   3. Prints an explicit manifest of every skipped package with its source
#      URL — so there is NO silent blind spot.
#
# Usage: scripts/pip-audit-with-manifest.sh [--no-dev]
#        Called via `make pip-audit` or `make pip-audit-no-dev`.

set -euo pipefail

NO_DEV=""
if [[ "${1:-}" == "--no-dev" ]]; then
    NO_DEV="--no-dev"
fi

echo "=== pip-audit: scanning dependency lockfile ==="
echo ""

# ---------------------------------------------------------------------------
# Step 1 — identify non-PyPI packages from uv.lock
# ---------------------------------------------------------------------------
# uv.lock format for a PyPI package:
#   source = { registry = "https://pypi.org/simple" }
# For a private-registry package:
#   source = { registry = "https://concavetrillion.github.io/pd-index-pip/simple/" }
# For a git dep or direct URL wheel:
#   source = { git = "..." } or wheel URL not under files.pythonhosted.org
#
# We identify non-PyPI packages by scanning for [[package]] blocks whose
# source registry is NOT pypi.org (or which have no registry at all).

LOCKFILE="uv.lock"
if [[ ! -f "$LOCKFILE" ]]; then
    echo "ERROR: uv.lock not found. Run 'uv lock' first." >&2
    exit 1
fi

# Parse the lockfile with Python for reliability
NON_PYPI_NAMES=$(uv run python3 - <<'PYEOF'
import re, sys

lockfile = open("uv.lock").read()

# Split into [[package]] blocks
blocks = re.split(r'(?=^\[\[package\]\])', lockfile, flags=re.MULTILINE)

skipped = []
for block in blocks:
    if not block.strip().startswith("[[package]]"):
        continue

    name_m = re.search(r'^name = "([^"]+)"', block, re.MULTILINE)
    version_m = re.search(r'^version = "([^"]+)"', block, re.MULTILINE)
    source_m = re.search(r'^source = \{(.+?)\}', block, re.MULTILINE)

    if not (name_m and version_m and source_m):
        continue

    name = name_m.group(1)
    version = version_m.group(1)
    source = source_m.group(1)

    # Editable/local source (e.g. the project itself)
    if "editable" in source:
        continue

    # PyPI is the only auditable source
    if 'registry = "https://pypi.org/simple"' in source:
        continue

    # Everything else — private registry, git URL, direct URL
    skipped.append((name, version, source.strip()))

for name, version, source in sorted(skipped):
    print(f"{name}=={version}\t{source}")
PYEOF
)

if [[ -z "$NON_PYPI_NAMES" ]]; then
    echo "No non-PyPI packages found — all packages are auditable via PyPI."
    echo ""
else
    echo "NON-PyPI packages (EXCLUDED from pip-audit, manual review required):"
    echo "-----------------------------------------------------------------------"
    while IFS=$'\t' read -r pkg source; do
        echo "  SKIP  $pkg"
        echo "        source: $source"
    done <<< "$NON_PYPI_NAMES"
    echo "-----------------------------------------------------------------------"
    echo ""
    echo "Action required for skipped packages:"
    echo "  - pd-book-tools: monitor https://github.com/ConcaveTrillion/pd-book-tools"
    echo "    for security advisories; no PyPI advisory database covers it."
    echo "  - For any other private/git dep: subscribe to upstream release notes"
    echo "    or run 'osv-scanner' against the project when available."
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 2 — build a filtered requirements file
# ---------------------------------------------------------------------------
TMPDIR_AUDIT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_AUDIT"' EXIT

REQUIREMENTS="$TMPDIR_AUDIT/requirements.txt"

# Export all packages (or non-dev), strip editable installs (they cause pip
# resolution failures too), then strip the non-PyPI packages.
SKIP_PATTERN=$(echo "$NON_PYPI_NAMES" | awk -F'==' '{print $1}' | paste -sd'|' -)

if [[ -z "$SKIP_PATTERN" ]]; then
    uv export --frozen ${NO_DEV} --no-hashes \
        | grep -v '^-e ' \
        > "$REQUIREMENTS"
else
    uv export --frozen ${NO_DEV} --no-hashes \
        | grep -v '^-e ' \
        | grep -Eiv "^(${SKIP_PATTERN})==" \
        > "$REQUIREMENTS"
fi

TOTAL_REQS=$(grep -c '==' "$REQUIREMENTS" || true)
SKIPPED_COUNT=$(echo "$NON_PYPI_NAMES" | grep -c '==' || true)
echo "Auditing $TOTAL_REQS PyPI-resolvable packages"
echo "($SKIPPED_COUNT non-PyPI package(s) excluded — see manifest above)"
echo ""

# ---------------------------------------------------------------------------
# Step 3 — run pip-audit against the filtered requirements
# ---------------------------------------------------------------------------
# Use OSV (Google's Open Source Vulnerabilities database) in addition to PyPI's
# own advisory DB. OSV covers more advisories and cross-references CVEs that
# PyPI sometimes lags on.
uvx pip-audit \
    --vulnerability-service osv \
    --requirement "$REQUIREMENTS" \
    --no-deps

echo ""
echo "=== pip-audit complete ==="
if [[ -n "$NON_PYPI_NAMES" ]]; then
    SKIP_COUNT=$(echo "$NON_PYPI_NAMES" | grep -c '.' || true)
    echo "NOTE: $SKIP_COUNT package(s) above require manual advisory monitoring."
fi
