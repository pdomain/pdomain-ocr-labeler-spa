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
    """Unpinned hook revs lead to silent toolchain drift across machines."""
    for entry in config["repos"]:
        rev = entry.get("rev")
        assert isinstance(rev, str) and rev, f"repo {entry['repo']!r} must pin a `rev`"
