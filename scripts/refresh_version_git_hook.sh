#!/usr/bin/env bash
# Centralised body for the git hooks that keep the editable install's
# `__version__` in sync with the current HEAD/tag state (hatch-vcs only
# re-derives the version on (re)install).
#
# Wired by `.pre-commit-config.yaml` into three pre-commit hook stages:
#
#   * post-commit   — fires after `git commit` (closes B-11).
#   * post-rewrite  — fires after `git commit --amend` and `git rebase`.
#   * post-checkout — fires after `git checkout`/`git switch` and after
#                     `git cherry-pick` if it leaves HEAD on a different
#                     sha. Also runs after `git clone`.
#
# All three converge on `just refresh-version` so a contributor never
# has to remember which git op invalidates the editable install. See
# B-17 in `docs/BUGS_FOUND.md` for context — without post-rewrite +
# post-checkout, the post-commit hook silently no-ops on rebase/amend
# /cherry-pick and `__version__` drifts back to a stale value.
#
# Failure mode is intentionally non-fatal — pre-commit hooks should
# never block a checkout or refuse a rebase because of a missing
# toolchain. `just refresh-version` itself absorbs missing-uv errors.

set -u

# Find repo root irrespective of cwd; pre-commit invokes hooks at the
# repo top, but `git checkout` hooks are sometimes called from worktrees.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "${REPO_ROOT}" ]; then
    # Not inside a git tree — nothing to refresh against.
    exit 0
fi

cd "${REPO_ROOT}" || exit 0

# Some hook stages pass arguments (post-checkout: prev_head new_head
# branch_flag; post-rewrite: amend|rebase). We don't currently
# differentiate — the refresh is idempotent — but accept and ignore
# them so the hook stays compatible if pre-commit changes its
# convention.

if command -v just >/dev/null 2>&1; then
    just --quiet refresh-version || true
else
    echo "[refresh_version_git_hook] just not on PATH; skipping refresh." >&2
fi

exit 0
