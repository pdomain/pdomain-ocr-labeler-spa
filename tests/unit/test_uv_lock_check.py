"""B-23 regression: assert `uv.lock` stays in sync with `pyproject.toml`.

The B-20 fix moved lockfile-drift detection into `docker build` (the
wheel stage runs `uv export --frozen …`). That's the right fail-mode
architecturally but it only fires inside docker, which neither
`make ci` nor `make test` invokes. Without a separate gate, M1+
contributors who add a new dep to `pyproject.toml` without running
`uv lock` would pass all tests and ruff and only learn about the
drift when the release pipeline actually builds an image.

This module pins two invariants:

1. The pre-commit config carries the `uv-lock-check` hook so a
   commit that touches `pyproject.toml` or `uv.lock` is gated on
   `uv lock --check` returning success.
2. The repo's *current* lockfile passes `uv lock --check`, so that
   any commit that introduces drift (whether via the hook firing or
   not — e.g. a CI run on a PR opened from a branch where the
   contributor disabled hooks) is caught by `make test`.

Both pieces matter: the hook gate stops drift from landing locally;
the runtime check stops drift from landing in the repo at all.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"
LOCKFILE = REPO_ROOT / "uv.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _local_repo(config: dict) -> dict:
    """Return the `repo: local` block, asserting it exists."""
    repos = config.get("repos")
    assert isinstance(repos, list) and repos, "config has no repos list"
    locals_ = [r for r in repos if r.get("repo") == "local"]
    assert len(locals_) == 1, (
        "expected exactly one `repo: local` block in .pre-commit-config.yaml"
    )
    return locals_[0]


def test_pre_commit_config_carries_uv_lock_check_hook() -> None:
    """The B-23 gate: a hook named `uv-lock-check` invoking `uv lock --check`.

    If a contributor renames the hook ID, swaps to `--frozen` (which
    has different semantics — it errors if any lock-affecting flag
    is also passed), or drops the hook entirely, this test fails so
    the regression engineer notices the gate is gone.
    """
    assert CONFIG_PATH.is_file(), f"missing {CONFIG_PATH}"
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    local = _local_repo(config)
    hooks = local.get("hooks") or []
    matches = [h for h in hooks if h.get("id") == "uv-lock-check"]
    assert len(matches) == 1, (
        "pre-commit config must carry exactly one `uv-lock-check` hook "
        "(B-23). Other refresh-version hooks are unrelated."
    )
    hook = matches[0]
    entry = (hook.get("entry") or "").strip()
    assert entry == "uv lock --check", (
        f"uv-lock-check hook entry should be `uv lock --check` (B-23 gate); "
        f"got {entry!r}. `--check` exits non-zero on drift without "
        f"modifying the lockfile."
    )
    assert hook.get("language") == "system", (
        "uv-lock-check must run via the system `uv` (the one `make setup` "
        "ensured is on PATH); pre-commit's isolated venvs would not have it."
    )
    assert hook.get("pass_filenames") is False, (
        "`uv lock --check` takes no filename args; passing them would "
        "fail with 'unexpected argument' under pipefail."
    )
    files_pattern = hook.get("files") or ""
    # The pattern must trigger on edits to either pyproject.toml or uv.lock.
    # We don't care about the exact regex shape, only that both filenames
    # match — anything else is wasted work on every commit.
    import re

    pat = re.compile(files_pattern)
    assert pat.search("pyproject.toml"), (
        f"uv-lock-check `files` pattern {files_pattern!r} must match "
        f"`pyproject.toml` so dep edits trigger the gate."
    )
    assert pat.search("uv.lock"), (
        f"uv-lock-check `files` pattern {files_pattern!r} must match "
        f"`uv.lock` so lockfile edits also trigger the gate."
    )


@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="`uv` not on PATH — drift check needs the binary the hook calls",
)
def test_uv_lock_is_in_sync_with_pyproject() -> None:
    """Run `uv lock --check` directly so a stale lockfile fails the suite.

    Belt-and-suspenders to the pre-commit hook: even if a contributor
    bypasses hooks (`git commit --no-verify`) or pushes from a fork
    that lacks them, `make test` still catches the drift. Skipped
    when `uv` is absent so a stripped CI image doesn't fail with a
    tooling error masquerading as a drift error.
    """
    assert PYPROJECT.is_file(), f"missing {PYPROJECT}"
    assert LOCKFILE.is_file(), f"missing {LOCKFILE}"
    completed = subprocess.run(
        ["uv", "lock", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        "uv.lock is out of sync with pyproject.toml — run `uv lock` and "
        f"commit the result. stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
