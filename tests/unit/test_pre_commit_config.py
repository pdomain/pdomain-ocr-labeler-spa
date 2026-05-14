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


def test_default_install_hook_types_includes_all_refresh_stages(config: dict) -> None:
    """B-11 + B-17: refresh-version hooks only run if they get installed.

    `pre-commit install` (called by `make setup`) defaults to installing
    only the `pre-commit` hook type. `default_install_hook_types`
    extends that so one `pre-commit install` wires up every stage that
    can leave the editable install's `__version__` stale:

    * post-commit  — vanilla `git commit` (B-11).
    * post-rewrite — `git commit --amend`, `git rebase` (B-17).
    * post-checkout — `git switch`/`git checkout`,
      and `git cherry-pick` when it lands HEAD on a different sha (B-17).
    """
    declared = config.get("default_install_hook_types")
    assert isinstance(declared, list), (
        "default_install_hook_types must be a list so `pre-commit install` "
        "wires up every refresh-version stage (B-11 + B-17)"
    )
    required = {"pre-commit", "post-commit", "post-rewrite", "post-checkout"}
    missing = required - set(declared)
    assert not missing, (
        f"default_install_hook_types missing {sorted(missing)} — "
        "without these, the refresh-version hooks are dormant for "
        "amend/rebase/cherry-pick (see B-17)."
    )


# The script all three refresh-version hooks share. Pinning the path
# means the test breaks if a future edit forks the entry per-stage,
# which is exactly the regression mode B-17 is meant to prevent.
REFRESH_HOOK_SCRIPT = "scripts/refresh_version_git_hook.sh"


def test_refresh_version_script_exists_and_is_executable() -> None:
    """B-17: the centralised hook body lives at a known path and is
    executable. pre-commit `language: script` invokes it directly,
    so the +x bit matters at install time."""
    script = REPO_ROOT / REFRESH_HOOK_SCRIPT
    assert script.is_file(), f"missing {REFRESH_HOOK_SCRIPT}"
    import os

    mode = script.stat().st_mode
    assert mode & 0o111, f"{REFRESH_HOOK_SCRIPT} must be executable (chmod +x); current mode is {oct(mode)}"
    # Sanity: the script must call `make refresh-version` so it stays
    # the single source of truth for the refresh path.
    text = script.read_text(encoding="utf-8")
    assert "make" in text and "refresh-version" in text, (
        "refresh hook script must invoke `make refresh-version`"
    )
    # Don't bind os to module scope — only need it for stat above.
    del os


def _refresh_hooks(config: dict) -> list[dict]:
    """Return every local-repo hook that's wired to the refresh script.
    Identified by entry pointing at `scripts/refresh_version_git_hook.sh`,
    not by id, so test stays robust if hook ids are renamed."""
    out: list[dict] = []
    for entry in config["repos"]:
        if entry["repo"] != "local":
            continue
        for hook in entry["hooks"]:
            if REFRESH_HOOK_SCRIPT in (hook.get("entry") or ""):
                out.append(hook)
    return out


def test_refresh_version_hooks_cover_all_three_stages(config: dict) -> None:
    """B-11 + B-17: post-commit catches vanilla commits;
    post-rewrite catches amend/rebase; post-checkout catches
    cherry-pick + branch switch. All three must be wired or
    `__version__` drifts on the missing path."""
    hooks = _refresh_hooks(config)
    assert hooks, f"expected at least one local-repo hook with entry referencing {REFRESH_HOOK_SCRIPT!r}"

    seen_stages: set[str] = set()
    for hook in hooks:
        stages = hook.get("stages") or []
        assert isinstance(stages, list) and len(stages) == 1, (
            f"each refresh hook must declare exactly one stage so the "
            f"binding is unambiguous; got {stages!r} for hook {hook.get('id')!r}"
        )
        seen_stages.add(stages[0])

    required = {"post-commit", "post-rewrite", "post-checkout"}
    missing = required - seen_stages
    assert not missing, (
        f"refresh-version is missing stage coverage for {sorted(missing)} — "
        "without these stages B-17's drift class is open."
    )


def test_refresh_version_hooks_share_single_script_entry(config: dict) -> None:
    """B-17: avoid the 'three copies of `make refresh-version`'
    anti-pattern — every refresh hook must point at the same script
    so a future change to the refresh body lands in one place."""
    hooks = _refresh_hooks(config)
    entries = {hook.get("entry") for hook in hooks}
    assert entries == {REFRESH_HOOK_SCRIPT}, (
        f"all refresh-version hooks must share entry {REFRESH_HOOK_SCRIPT!r}; got {sorted(entries)}"
    )

    for hook in hooks:
        assert hook.get("language") == "script", (
            f"hook {hook.get('id')!r} must use language: script (so pre-commit "
            "invokes the file directly with the post-* hook args)"
        )
        assert hook.get("always_run") is True, (
            f"hook {hook.get('id')!r} doesn't depend on staged files; must always_run"
        )
        assert hook.get("pass_filenames") is False, f"hook {hook.get('id')!r} takes no filename args"


def _local_hook_ids(config: dict) -> list[str]:
    """Return all hook ids from the `local` repo entry."""
    for entry in config["repos"]:
        if entry["repo"] == "local":
            return [h["id"] for h in entry["hooks"]]
    return []


def test_frontend_tsc_hook_present(config: dict) -> None:
    """Issue #279: frontend-tsc hook must be in the local-repo entry.

    Mirrors pd-prep-for-pgdp/.pre-commit-config.yaml. Without this hook
    TypeScript errors only surface in `make lint`, not at commit time.
    """
    ids = _local_hook_ids(config)
    assert "frontend-tsc" in ids, (
        "frontend-tsc hook missing from local repo — add it to mirror pd-prep-for-pgdp"
    )


def test_frontend_eslint_hook_present(config: dict) -> None:
    """Issue #279: frontend-eslint hook must be in the local-repo entry."""
    ids = _local_hook_ids(config)
    assert "frontend-eslint" in ids, (
        "frontend-eslint hook missing from local repo — add it to mirror pd-prep-for-pgdp"
    )


def test_frontend_prettier_hook_present(config: dict) -> None:
    """Issue #279: frontend-prettier hook must be in the local-repo entry."""
    ids = _local_hook_ids(config)
    assert "frontend-prettier" in ids, (
        "frontend-prettier hook missing from local repo — add it to mirror pd-prep-for-pgdp"
    )


def test_frontend_hooks_are_local_system_language(config: dict) -> None:
    """Issue #279: frontend hooks must use `language: system` so they
    resolve `npm`/`npx` from the mise-activated PATH, not a sandboxed
    pre-commit virtualenv where those tools aren't available.
    """
    for entry in config["repos"]:
        if entry["repo"] != "local":
            continue
        for hook in entry["hooks"]:
            if hook.get("id") in ("frontend-tsc", "frontend-eslint", "frontend-prettier"):
                assert hook.get("language") == "system", (
                    f"hook {hook['id']!r} must use language: system; got {hook.get('language')!r}"
                )
                assert hook.get("pass_filenames") is False, (
                    f"hook {hook['id']!r} must not pass filenames (runs over full tree)"
                )


def test_frontend_hooks_have_file_filters(config: dict) -> None:
    """Issue #279: frontend hooks must declare `files:` patterns so they
    only trigger on frontend changes (not on every Python edit).
    """
    for entry in config["repos"]:
        if entry["repo"] != "local":
            continue
        for hook in entry["hooks"]:
            if hook.get("id") in ("frontend-tsc", "frontend-eslint", "frontend-prettier"):
                files_pattern = hook.get("files")
                assert files_pattern, (
                    f"hook {hook['id']!r} must declare a `files:` pattern "
                    "so it only fires on frontend changes"
                )
                assert "frontend/" in files_pattern, (
                    f"hook {hook['id']!r} `files:` pattern must be scoped to the "
                    f"frontend/ directory; got {files_pattern!r}"
                )
