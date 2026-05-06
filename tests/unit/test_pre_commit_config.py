"""Smoke tests for `.pre-commit-config.yaml`.

We don't try to *run* pre-commit (that needs network + git hook install);
we just assert the YAML parses and carries the hook IDs the workspace
expects, mirroring the peer pd-* convention. Catches accidental drift
during edits and gives the iter-5 reviewer something tangible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def config() -> dict:
    assert CONFIG_PATH.is_file(), f"missing {CONFIG_PATH}"
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    assert isinstance(loaded, dict), "pre-commit config must be a YAML mapping"
    return loaded


def test_config_has_repos_list(config: dict) -> None:
    repos = config.get("repos")
    assert isinstance(repos, list) and repos, "`repos` must be a non-empty list"
    for entry in repos:
        assert isinstance(entry, dict), "each repo entry must be a mapping"
        assert "repo" in entry and "hooks" in entry
        assert isinstance(entry["hooks"], list) and entry["hooks"]


def _hook_ids_for(config: dict, repo_url: str) -> list[str]:
    for entry in config["repos"]:
        if entry["repo"] == repo_url:
            return [h["id"] for h in entry["hooks"]]
    return []


def test_pre_commit_hooks_repo_present(config: dict) -> None:
    """The standard pre-commit-hooks set mirrors pd-prep-for-pgdp."""
    ids = _hook_ids_for(config, "https://github.com/pre-commit/pre-commit-hooks")
    assert ids, "pre-commit/pre-commit-hooks repo entry missing"
    expected = {"trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-json"}
    missing = expected - set(ids)
    assert not missing, f"missing pre-commit-hooks ids: {sorted(missing)}"


def test_ruff_repo_present_with_check_and_format(config: dict) -> None:
    """Ruff is the lint+format toolchain across the workspace."""
    ids = _hook_ids_for(config, "https://github.com/astral-sh/ruff-pre-commit")
    assert ids, "astral-sh/ruff-pre-commit repo entry missing"
    assert "ruff-check" in ids, "ruff-check hook missing"
    assert "ruff-format" in ids, "ruff-format hook missing"


def test_pre_commit_update_repo_present(config: dict) -> None:
    """Optional but matched in peer repos: keeps hook revs current."""
    ids = _hook_ids_for(config, "https://gitlab.com/vojko.pribudic.foss/pre-commit-update")
    assert ids == ["pre-commit-update"], (
        "expected single `pre-commit-update` hook from vojko.pribudic.foss/pre-commit-update"
    )


def test_every_repo_pins_a_rev(config: dict) -> None:
    """Unpinned hook revs lead to silent toolchain drift across machines.

    `local` repos are exempt — they reference scripts in the working tree,
    so there's no upstream rev to pin.
    """
    for entry in config["repos"]:
        if entry["repo"] == "local":
            continue
        rev = entry.get("rev")
        assert isinstance(rev, str) and rev, f"repo {entry['repo']!r} must pin a `rev`"


def test_default_install_hook_types_includes_post_commit(config: dict) -> None:
    """B-11: post-commit refresh-version hook only runs if it gets installed.

    `pre-commit install` (called by `make setup`) defaults to installing
    only the pre-commit hook type. `default_install_hook_types` extends
    that so a single `pre-commit install` also wires up post-commit,
    keeping the developer setup story to one command.
    """
    declared = config.get("default_install_hook_types")
    assert isinstance(declared, list), (
        "default_install_hook_types must be a list so `pre-commit install` "
        "wires up the post-commit refresh-version hook for B-11"
    )
    assert "post-commit" in declared, (
        "post-commit must be in default_install_hook_types or B-11's auto-refresh hook is dormant"
    )
    # Sanity: still installs the pre-commit hook by default.
    assert "pre-commit" in declared


def test_local_refresh_version_post_commit_hook_present(config: dict) -> None:
    """B-11: `make refresh-version` runs after each commit so hatch-vcs
    re-derives `__version__` from the new HEAD instead of staying frozen
    at the last `uv sync`."""
    local_entries = [e for e in config["repos"] if e["repo"] == "local"]
    assert local_entries, "expected a `repo: local` entry hosting refresh-version"

    refresh_hooks = [
        hook for entry in local_entries for hook in entry["hooks"] if hook.get("id") == "refresh-version"
    ]
    assert refresh_hooks, "missing `refresh-version` hook in the local repo"
    assert len(refresh_hooks) == 1, "expected exactly one `refresh-version` hook"

    hook = refresh_hooks[0]
    assert hook.get("stages") == ["post-commit"], (
        "refresh-version must be staged post-commit only — running it "
        "pre-commit would block on `uv pip install` and slow every commit"
    )
    assert hook.get("language") == "system", "refresh-version shells out to make"
    assert "make refresh-version" in (hook.get("entry") or ""), (
        "hook entry must invoke `make refresh-version` (the canonical refresh path)"
    )
    assert hook.get("always_run") is True, "refresh-version doesn't depend on staged files; must always_run"
    assert hook.get("pass_filenames") is False, "make refresh-version takes no file arguments"
