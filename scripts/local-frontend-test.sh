#!/usr/bin/env bash
# scripts/local-frontend-test.sh - run Vitest against local sibling pdomain-ui.
#
# `pnpm link` is the right overlay for local dev/build, but linked packages keep
# their own peer dependency graph. For Vitest that can load pdomain-ui's React
# 18 dev install next to this app's React 19 renderer. During tests only, install
# pdomain-ui through the file: protocol so pnpm resolves its peers from this app.
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

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
CANONICAL_REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
WORKSPACE_ROOT="$(dirname "$CANONICAL_REPO_ROOT")"
PROJECT_VENV="$(venv_under "$CANONICAL_REPO_ROOT")"
MARKER="$PROJECT_VENV/.pdomain-local-mode"

SIBLING="$WORKSPACE_ROOT/pdomain-ui"
FRONTEND="$REPO_ROOT/frontend"

say() { echo "[local-frontend-test] $*"; }

if [[ ! -f "$MARKER" ]]; then
  echo "ERROR: not in local-dev mode. Run 'make local-dev' first." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND" ]]; then
  say "no frontend/ directory; nothing to do"
  exit 0
fi

if [[ ! -d "$SIBLING" ]]; then
  echo "ERROR: missing sibling repo: $SIBLING (run 'make local-setup')." >&2
  exit 1
fi

MISE="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
run_pnpm() {
  if [[ -x "$MISE" ]]; then
    (cd "$FRONTEND" && "$MISE" exec -- pnpm "$@")
  elif command -v pnpm >/dev/null 2>&1; then
    (cd "$FRONTEND" && pnpm "$@")
  else
    echo "no pnpm/mise available. Run 'make mise-setup' or install Node." >&2
    exit 1
  fi
}

SNAP_DIR=""
restore_local_links() {
  local rc=$?

  if [[ -n "$SNAP_DIR" && -d "$SNAP_DIR" ]]; then
    cp "$SNAP_DIR/package.json" "$FRONTEND/package.json"
    cp "$SNAP_DIR/pnpm-lock.yaml" "$FRONTEND/pnpm-lock.yaml"
    cp "$SNAP_DIR/pnpm-workspace.yaml" "$FRONTEND/pnpm-workspace.yaml"
    rm -rf "$SNAP_DIR"

    say "restoring pnpm link overlay"
    if ! "$REPO_ROOT/scripts/local-frontend-install.sh"; then
      echo "ERROR: test finished, but restoring local frontend links failed." >&2
      exit 1
    fi
  fi

  exit "$rc"
}
trap restore_local_links EXIT

say "preparing local-linked frontend"
"$REPO_ROOT/scripts/local-frontend-install.sh"

SNAP_DIR="$(mktemp -d)"
cp "$FRONTEND/package.json" "$SNAP_DIR/package.json"
cp "$FRONTEND/pnpm-lock.yaml" "$SNAP_DIR/pnpm-lock.yaml"
cp "$FRONTEND/pnpm-workspace.yaml" "$SNAP_DIR/pnpm-workspace.yaml"

say "using file:../../pdomain-ui for test-time peer resolution"
run_pnpm add "@pdomain/pdomain-ui@file:../../pdomain-ui"

say "running Vitest"
run_pnpm run test "$@"
