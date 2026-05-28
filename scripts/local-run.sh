#!/usr/bin/env bash
# scripts/local-run.sh — run the SPA against the local-dev workspace.
#
# Requires local-dev mode. Re-applies editable sibling overlays (Python
# + npm), builds the SPA via the local-frontend-* path (which preserves
# `pnpm link` after pnpm install), and launches the app.
#
# Deliberately does NOT delegate to `make run` — that path runs
# `frontend-build` -> `frontend-install` (--frozen-lockfile), which is
# the registry path and would discard the local-link overlay.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"
CANONICAL_REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
# Marker lives in the canonical repo's .venv (shared across worktrees).
MARKER="$CANONICAL_REPO_ROOT/.venv/.pd-local-mode"

if [[ ! -f "$MARKER" ]]; then
  echo "ERROR: not in local-dev mode. Run 'make local-dev' first." >&2
  exit 1
fi

# 1) Re-apply editable Python siblings (uv sync drops them; defensive here).
make -C "$REPO_ROOT" local-setup-py

# 2) Build SPA bundle via local-frontend path (preserves pnpm link).
make -C "$REPO_ROOT" local-frontend-build

# 3) Launch — reproduce `make run`'s launch step inline so we don't
#    trigger the registry-path `frontend-build` dependency chain.
#    --no-sync is REQUIRED: a plain `uv run` re-syncs and reverts the
#    editable pd-* siblings that local-setup-py just installed, breaking
#    editable APIs at runtime.
exec uv run --no-sync --project "$CANONICAL_REPO_ROOT" pd-ocr-labeler-ui
