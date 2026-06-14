from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UPDATER_PATH = ROOT / "scripts" / "update_github_actions.py"
spec = importlib.util.spec_from_file_location("update_github_actions", UPDATER_PATH)
assert spec is not None
assert spec.loader is not None
update_github_actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_github_actions)


def test_detects_unmanaged_workflow_action(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: ci\njobs:\n  ci:\n    steps:\n      - uses: example/not-managed@abc123\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="example/not-managed"):
        update_github_actions.verify_managed_actions(workflows)


def test_accepts_local_workflow_call(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "jobs:\n  regen:\n    uses: ./.github/workflows/regen.yml\n",
        encoding="utf-8",
    )

    update_github_actions.verify_managed_actions(workflows)


def test_accepts_quoted_managed_actions_and_local_workflows(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n"
        "  ci:\n"
        "    steps:\n"
        '      - uses: "actions/checkout@abc123"\n'
        "      - uses: './.github/workflows/regen.yml'\n",
        encoding="utf-8",
    )

    update_github_actions.verify_managed_actions(workflows)


def test_current_workflows_use_only_managed_actions() -> None:
    update_github_actions.verify_managed_actions()


def test_update_workflow_refs_updates_quoted_action_refs(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n"
        "  ci:\n"
        "    steps:\n"
        '      - uses: "actions/checkout@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold1"\n'
        "      - uses: 'astral-sh/setup-uv@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold2'\n",
        encoding="utf-8",
    )
    releases = {
        "actions/checkout": update_github_actions.ActionRelease(tag="v-test", sha="a" * 40),
        "astral-sh/setup-uv": update_github_actions.ActionRelease(tag="v-test", sha="b" * 40),
    }

    assert update_github_actions.update_workflow_refs(workflow, releases=releases)
    text = workflow.read_text(encoding="utf-8")
    assert f'uses: "actions/checkout@{"a" * 40}"' in text
    assert f"uses: 'astral-sh/setup-uv@{'b' * 40}'" in text


def test_update_uv_version_refs_updates_quoted_setup_uv(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n"
        "  ci:\n"
        "    steps:\n"
        '      - uses: "astral-sh/setup-uv@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold2"\n'
        "        with:\n"
        '          version: "0.1.0"\n',
        encoding="utf-8",
    )

    assert update_github_actions.update_uv_version_refs(workflow, version="0.11.16")
    assert 'version: "0.11.16"' in workflow.read_text(encoding="utf-8")


def test_update_uv_version_refs_updates_quoted_setup_uv_with_inline_comment(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n"
        "  ci:\n"
        "    steps:\n"
        '      - uses: "astral-sh/setup-uv@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold2"  # v8.1.0\n'
        "        with:\n"
        '          version: "0.1.0"\n',
        encoding="utf-8",
    )

    assert update_github_actions.update_uv_version_refs(workflow, version="0.11.16")
    assert 'version: "0.11.16"' in workflow.read_text(encoding="utf-8")


def test_update_github_actions_does_not_touch_pyproject(tmp_path: Path) -> None:
    """update_github_actions must never rewrite pyproject.toml required-version.

    The dep-refresh job calls ``uv lock --upgrade`` after this script runs.
    If required-version was rewritten to the latest uv release, the running
    uv (which setup-uv installed at job-start) would violate the requirement
    it just wrote, poisoning itself.  The required-version floor is a deliberate
    contributor floor and must not auto-track the latest release.
    """
    import json
    import subprocess

    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "ci.yml"
    workflow.write_text(
        "jobs:\n"
        "  ci:\n"
        "    steps:\n"
        '      - uses: "astral-sh/setup-uv@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold1"\n'
        "        with:\n"
        '          version: "0.1.0"\n'
        '      - uses: "actions/checkout@oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold2"\n',
        encoding="utf-8",
    )
    pyproject = tmp_path / "pyproject.toml"
    original_content = '[tool.uv]\nrequired-version = ">=0.11.16"\n'
    pyproject.write_text(original_content, encoding="utf-8")

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        endpoint = command[-1] if command[0] == "gh" else ""
        if "releases/latest" in endpoint:
            if "astral-sh/uv" in endpoint:
                payload: dict[str, object] = {"tag_name": "0.11.21"}
            else:
                payload = {"tag_name": "v-test"}
        elif "git/ref/tags" in endpoint:
            payload = {"object": {"type": "commit", "sha": "a" * 40}}
        elif "git/tags" in endpoint:
            payload = {"object": {"sha": "a" * 40}}
        else:
            payload = {}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    changed = update_github_actions.update_github_actions(
        workflow_dir=workflows,
        runner=fake_runner,
    )

    # pyproject.toml must NOT appear among changed paths
    assert pyproject not in changed, "update_github_actions must not touch pyproject.toml"
    # pyproject.toml content must be byte-for-byte identical
    assert pyproject.read_text(encoding="utf-8") == original_content, (
        "pyproject.toml required-version was modified; must never be auto-updated"
    )
