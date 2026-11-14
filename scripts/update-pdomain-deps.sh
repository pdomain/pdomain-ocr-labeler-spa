#!/usr/bin/env bash
# scripts/update-pdomain-deps.sh — bump all sibling pd-* deps to registry latest.
#
# Queries pdomain-index-pip (Python) and pdomain-index-npm (npm) for each sibling,
# updates minimum-version pins in pyproject.toml and frontend/package.json,
# then leaves the diff staged for human review. Does NOT commit.
#
# Auto-flips around local-dev mode if the .venv/.pdomain-local-mode marker is set.
# Idempotent: prints "✓ <name> already at <version>" if already at latest.
#
# Usage: just update-pdomain-deps   (or ./scripts/update-pdomain-deps.sh directly)
set -euo pipefail

# uv installs into UV_PROJECT_ENVIRONMENT when that is set and into .venv
# otherwise, so mirror the same rule instead of hardcoding either name. The
# pd-suite devcontainer sets ".venv-container" because the workspace is a bind
# mount shared with the host; a plain checkout outside a container gets .venv.
venv_under() {
  case "${UV_PROJECT_ENVIRONMENT:-}" in
    "") printf '%s/.venv' "$1" ;;
    /*) printf '%s' "$UV_PROJECT_ENVIRONMENT" ;;
    *) printf '%s/%s' "$1" "$UV_PROJECT_ENVIRONMENT" ;;
  esac
}

# ─── Repo-specific config (edit per-repo during M3–M9 rollout) ───────────────
PY_SIBLINGS=(pdomain-book-tools)
NPM_SIBLINGS=(pdomain-ui)   # without @pdomain/ prefix
PD_INDEX_PIP="https://pdomain.github.io/pdomain-index-pip"
PD_INDEX_NPM="https://pdomain.github.io/pdomain-index-npm"
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Edit the checkout this script runs from. A worktree edits itself, not the
# main checkout.
PROJECT_VENV="$(venv_under "$REPO_ROOT")"
MARKER="$PROJECT_VENV/.pdomain-local-mode"

say() { echo "[update-pdomain-deps] $*"; }

# Raises the >= floor of each requirement on one sibling in pyproject.toml.
# It keeps any < cap, leaves exact == pins alone, and refuses a release that
# the cap excludes, because a new 0.x minor may break the API. Prints
# "changed" or "unchanged" on stdout and its notes on stderr.
read -r -d '' BUMP_PIN_PY <<'PY' || true
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

path, name, latest = Path(sys.argv[1]), sys.argv[2], Version(sys.argv[3])
text = path.read_text(encoding="utf-8")
pattern = re.compile(
    '"(' + re.escape(name) + r'(?:\[[^\]]*\])?)(\s*[<>=!~][^";]*)(;[^"]*)?"'
)
changed = False


def note(message):
    print(f"[update-pdomain-deps]    {message}", file=sys.stderr)


def bump(match):
    global changed
    head, spec, marker = match.group(1), match.group(2), match.group(3) or ""
    specifiers = list(Requirement(head + spec).specifier)
    if any(s.operator in ("==", "===") for s in specifiers):
        note(f"{head}{spec} is an exact pin; bump it by hand")
        return match.group(0)
    floors = [s for s in specifiers if s.operator == ">="]
    if len(floors) != 1:
        note(f"{head}{spec} has no single >= floor; left unchanged")
        return match.group(0)
    floor = floors[0]
    if Version(floor.version) >= latest:
        note(f"{head}{spec} already starts at {latest}")
        return match.group(0)
    if not all(s.contains(latest) for s in specifiers if s.operator in ("<", "<=")):
        note(f"{latest} is outside {head}{spec}; check that release, then raise the cap by hand")
        return match.group(0)
    new_spec = re.sub(r">=\s*" + re.escape(floor.version), f">={latest}", spec, count=1)
    note(f"pinning {head}: {spec} -> {new_spec}")
    changed = True
    return f'"{head}{new_spec}{marker}"'


text = pattern.sub(bump, text)
if changed:
    path.write_text(text, encoding="utf-8")
print("changed" if changed else "unchanged")
PY

# ─── Step 1: Detect local-dev mode ───────────────────────────────────────────
LOCAL_DEV_ACTIVE=false
if [[ -f "$MARKER" ]]; then
  LOCAL_DEV_ACTIVE=true
  say "→ local-dev mode detected (marker: $MARKER)"
fi

# ─── Step 2: Flip out of local-dev mode if needed ────────────────────────────
if [[ "$LOCAL_DEV_ACTIVE" == "true" ]]; then
  say "→ flipping out of local-dev mode (registry resolution needed)"
  (cd "$REPO_ROOT" && uv sync --group dev)
fi

# ─── Step 3: Query pdomain-index-pip for each Python sibling ──────────────────────
# Track if any Python dep changed (to avoid redundant uv lock+sync).
PY_CHANGED=false

for sibling in "${PY_SIBLINGS[@]}"; do
  index_url="$PD_INDEX_PIP/simple/$sibling/"
  say "→ querying $index_url"

  # Fetch the PEP 503 simple index page; fail loudly if unreachable/404.
  html=$(curl -sSf "$index_url" 2>&1) || {
    echo "ERROR: could not fetch $index_url" >&2
    echo "       Network issue or sibling not yet seeded in pdomain-index-pip." >&2
    echo "       No changes made." >&2
    exit 1
  }

  # Parse: extract all href filenames, pull version segment, find max.
  # Handles both wheel (<name>-<ver>-py3-none-any.whl) and sdist (<name>-<ver>.tar.gz).
  # Strategy: match <name>-<ver> prefix, then strip everything from the first
  # hyphen or extension that follows the version number.
  pkg_norm="${sibling//-/_}"
  latest=$(
    echo "$html" \
      | grep -oP 'href="[^"]*"' \
      | sed 's/href="//;s/"//' \
      | grep -oP "${pkg_norm}-[0-9][^/\"#]*" \
      | sed "s/${pkg_norm}-//" \
      | uv run python -c "
import sys, re
vers = []
for line in sys.stdin:
  line = line.strip()
  # strip trailing filename junk: everything from first non-version char
  m = re.match(r'^([0-9]+(?:\.[0-9]+)*(?:[._-]?(?:a|b|rc|alpha|beta|dev)[0-9]*)?).*', line)
  if m:
    vers.append(m.group(1))
if vers:
  from packaging.version import Version
  print(str(max(Version(v) for v in vers)))
"
  )

  if [[ -z "$latest" ]]; then
    echo "ERROR: pdomain-index-pip returned a page for $sibling but no wheel/sdist found." >&2
    echo "       Index may not be seeded yet. No changes made." >&2
    exit 1
  fi

  say "   latest $sibling = $latest"

  bump_result=$(uv run python -c "$BUMP_PIN_PY" "$REPO_ROOT/pyproject.toml" "$sibling" "$latest") || {
    echo "ERROR: could not update $sibling in pyproject.toml." >&2
    exit 1
  }
  if [[ "$bump_result" == "changed" ]]; then
    PY_CHANGED=true
  fi
done

# Refresh lockfile + venv only if something changed.
if [[ "$PY_CHANGED" == "true" ]]; then
  say "→ running uv lock"
  (cd "$REPO_ROOT" && uv lock)
  say "→ running uv sync"
  (cd "$REPO_ROOT" && uv sync --group dev)
fi

# ─── Step 4: Query pdomain-index-npm for each npm sibling ─────────────────────────
FRONTEND_DIR="$REPO_ROOT/frontend"
NPM_CHANGED=false

if [[ -d "$FRONTEND_DIR" ]]; then
  for sibling in "${NPM_SIBLINGS[@]}"; do
    pkg="@pdomain/$sibling"
    index_url="$PD_INDEX_NPM/@pdomain/$sibling/"
    say "→ querying $index_url"

    # Fetch npm-style package metadata JSON; fail loudly if unreachable/404.
    meta=$(curl -sSf "$index_url" 2>&1) || {
      echo "ERROR: could not fetch $index_url" >&2
      echo "       Network issue or sibling not yet seeded in pdomain-index-npm." >&2
      echo "       No changes made." >&2
      exit 1
    }

    # dist-tags.latest from JSON.
    latest=$(echo "$meta" | uv run python -c "
import sys, json
try:
  d = json.load(sys.stdin)
  print(d['dist-tags']['latest'])
except Exception as e:
  print('ERROR: ' + str(e), file=sys.stderr)
  sys.exit(1)
" 2>&1) || {
      echo "ERROR: failed to parse dist-tags.latest from $index_url response." >&2
      echo "       Response: $meta" >&2
      echo "       No changes made." >&2
      exit 1
    }

    say "   latest $pkg = $latest"

    # Read current version from frontend/package.json (strips leading ^ or ~).
    current=$(uv run python -c "
import sys, json
with open('$FRONTEND_DIR/package.json') as f:
  d = json.load(f)
deps = {**d.get('dependencies', {}), **d.get('devDependencies', {})}
v = deps.get('$pkg', '')
print(v.lstrip('^~'))
" 2>&1) || {
      echo "ERROR: failed to read $pkg version from $FRONTEND_DIR/package.json" >&2
      exit 1
    }

    if [[ "$current" == "$latest" ]]; then
      say "   ✓ $pkg already at $latest — skipping"
      continue
    fi

    say "   pinning $pkg: $current → ^$latest"
    # Update version in package.json (preserves ^ prefix convention).
    uv run python -c "
import json, sys

with open('$FRONTEND_DIR/package.json') as f:
  d = json.load(f)

pkg = '$pkg'
new_ver = '^$latest'
for section in ('dependencies', 'devDependencies', 'peerDependencies'):
  if section in d and pkg in d[section]:
    d[section][pkg] = new_ver
    break

with open('$FRONTEND_DIR/package.json', 'w') as f:
  json.dump(d, f, indent=2)
  f.write('\n')
"
    NPM_CHANGED=true
  done

  if [[ "$NPM_CHANGED" == "true" ]]; then
    say "→ running pnpm install --no-frozen-lockfile"
    (cd "$FRONTEND_DIR" && pnpm install --no-frozen-lockfile)
  fi
fi

# ─── Step 5: Restore local-dev mode if we flipped out ────────────────────────
if [[ "$LOCAL_DEV_ACTIVE" == "true" ]]; then
  say "→ restoring local-dev mode"
  just --justfile "$REPO_ROOT/justfile" local-dev
fi

# ─── Step 6: Show staged diff summary ────────────────────────────────────────
say ""
say "── diff summary ──────────────────────────────────────────────"
git -C "$REPO_ROOT" diff --stat -- \
  pyproject.toml \
  uv.lock \
  "$FRONTEND_DIR/package.json" \
  "$FRONTEND_DIR/pnpm-lock.yaml" \
  2>/dev/null || true
say "──────────────────────────────────────────────────────────────"
say "Review the diff above, then commit:"
say "  git diff -- pyproject.toml uv.lock frontend/package.json frontend/pnpm-lock.yaml"
say "  git add pyproject.toml uv.lock frontend/package.json frontend/pnpm-lock.yaml"
say "  git commit -m 'chore: bump pd-* sibling deps to registry latest'"
