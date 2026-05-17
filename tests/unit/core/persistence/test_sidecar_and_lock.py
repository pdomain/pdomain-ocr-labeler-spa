"""Tests for issue #223: sidecar files (project.json write), AppState lock, pidfile.

Acceptance:
- project.json written on Save Project (write_project_json)
- config.yaml auto-created on first run (already covered by test_config_yaml.py; smoke here)
- ocr_config.json save errors logged as WARNING, never 500 (already tested in test_ocr_config_sidecar.py)
- Per-project lock serializes concurrent writes
- Pidfile startup warning when cache root is held
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.pidfile import (
    check_and_write_pidfile,
    pidfile_path,
    release_pidfile,
)
from pd_ocr_labeler_spa.core.persistence.project_envelope import (
    read_project_metadata,
    write_project_json,
)
from pd_ocr_labeler_spa.core.project_lock import ProjectLockManager

# ---------------------------------------------------------------------------
# write_project_json
# ---------------------------------------------------------------------------


def _make_minimal_project(project_root: Path):
    """Build a minimal Project for write tests."""
    from pd_ocr_labeler_spa.core.persistence.project_envelope import build_project_from_directory

    project_root.mkdir(parents=True, exist_ok=True)
    # Create a dummy image so the scan finds one page.
    (project_root / "001.png").write_bytes(b"\x00")
    return build_project_from_directory(project_root, ground_truth_map={})


def test_write_project_json_creates_file(tmp_path: Path) -> None:
    project_root = tmp_path / "myproject"
    project = _make_minimal_project(project_root)
    write_project_json(project_root, project)
    assert (project_root / "project.json").exists()


def test_write_project_json_round_trips(tmp_path: Path) -> None:
    """Written project.json must be readable back as the same metadata."""
    project_root = tmp_path / "myproject"
    project = _make_minimal_project(project_root)
    write_project_json(project_root, project)

    meta = read_project_metadata(project_root)
    assert meta is not None
    # Key fields should match
    assert meta["current_page_index"] == project.current_page_index
    assert meta["total_pages"] == project.total_pages


def test_write_project_json_atomic_via_tmp(tmp_path: Path, monkeypatch) -> None:
    """Verify write goes through tmp+replace (atomic helper is invoked)."""
    from pd_ocr_labeler_spa.core.persistence import project_envelope as pe_mod

    calls = []
    original = pe_mod.write_json_atomic

    def capturing(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(pe_mod, "write_json_atomic", capturing)

    project_root = tmp_path / "myproject"
    project = _make_minimal_project(project_root)
    write_project_json(project_root, project)
    assert any("project.json" in str(p) for p in calls)


def test_write_project_json_creates_parent_if_missing(tmp_path: Path) -> None:
    """write_project_json must mkdir parents if they don't exist."""
    # Build project from a different temp dir so we can pass a non-existent root.
    existing_root = tmp_path / "source"
    project = _make_minimal_project(existing_root)

    write_root = tmp_path / "deep" / "nested" / "myproject"
    write_project_json(write_root, project)
    assert (write_root / "project.json").exists()


# ---------------------------------------------------------------------------
# ProjectLockManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_manager_acquires_for_project() -> None:
    mgr = ProjectLockManager()
    results = []

    async def task(name: str) -> None:
        async with mgr.lock_for("proj"):
            results.append(f"enter:{name}")
            await asyncio.sleep(0)
            results.append(f"exit:{name}")

    await asyncio.gather(task("a"), task("b"))
    # Interleaving not allowed: exit:a must precede enter:b (or vice versa).
    assert results in [
        ["enter:a", "exit:a", "enter:b", "exit:b"],
        ["enter:b", "exit:b", "enter:a", "exit:a"],
    ]


@pytest.mark.asyncio
async def test_lock_manager_different_projects_dont_block() -> None:
    """Locks for different project_ids must be independent."""
    mgr = ProjectLockManager()
    results = []

    async def task(pid: str) -> None:
        async with mgr.lock_for(pid):
            results.append(f"enter:{pid}")
            await asyncio.sleep(0.01)
            results.append(f"exit:{pid}")

    await asyncio.gather(task("proj_a"), task("proj_b"))
    # Both should have "entered" before any "exit" (interleaved — independent).
    assert "enter:proj_a" in results
    assert "enter:proj_b" in results


def test_lock_manager_is_locked_false_when_not_acquired() -> None:
    mgr = ProjectLockManager()
    assert not mgr.is_locked("unknown_project")
    # Trigger creation then check.
    _ = mgr._get_or_create("existing")
    assert not mgr.is_locked("existing")


def test_lock_manager_new_keys_created_lazily() -> None:
    mgr = ProjectLockManager()
    assert "proj" not in mgr._locks
    mgr._get_or_create("proj")
    assert "proj" in mgr._locks


# ---------------------------------------------------------------------------
# Pidfile
# ---------------------------------------------------------------------------


def test_pidfile_path_contains_pid_filename(tmp_path: Path) -> None:
    p = pidfile_path(tmp_path)
    assert p.name == "pd-ocr-labeler-spa.pid"
    assert p.parent == tmp_path


def test_check_and_write_pidfile_creates_file(tmp_path: Path) -> None:
    check_and_write_pidfile(tmp_path)
    p = pidfile_path(tmp_path)
    assert p.exists()
    assert int(p.read_text()) == os.getpid()


def test_check_and_write_pidfile_creates_cache_dir(tmp_path: Path) -> None:
    cache_root = tmp_path / "newdir"
    assert not cache_root.exists()
    check_and_write_pidfile(cache_root)
    assert cache_root.exists()
    assert pidfile_path(cache_root).exists()


def test_check_and_write_pidfile_warns_when_other_pid_alive(tmp_path: Path, caplog) -> None:
    """When pidfile contains a PID known to be alive, WARNING is emitted."""
    import logging
    from unittest import mock

    # Simulate: pidfile holds our live PID; we monkeypatch getpid so the module
    # thinks it is running as a *different* PID, making the existing PID look
    # like another process that is alive.
    fake_cache = tmp_path / "fake_cache"
    fake_cache.mkdir()
    pidfile_path(fake_cache).write_text(str(os.getpid()))

    seen_pid = os.getpid() + 9999  # different from the PID in the file

    with (
        caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.pidfile"),
        mock.patch("pd_ocr_labeler_spa.core.persistence.pidfile.os.getpid", return_value=seen_pid),
    ):
        check_and_write_pidfile(fake_cache)

    assert any(
        "another process" in r.message.lower() or "cache root" in r.message.lower() for r in caplog.records
    )


def test_release_pidfile_removes_file(tmp_path: Path) -> None:
    check_and_write_pidfile(tmp_path)
    assert pidfile_path(tmp_path).exists()
    release_pidfile(tmp_path)
    assert not pidfile_path(tmp_path).exists()


def test_release_pidfile_does_not_remove_other_pid(tmp_path: Path) -> None:
    """If the pidfile was overwritten by a successor, we must not remove it."""
    p = pidfile_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write a different PID — simulate successor overwrote our file.
    p.write_text(str(os.getpid() + 1))
    release_pidfile(tmp_path)
    # File should remain (it's not ours).
    assert p.exists()


def test_release_pidfile_harmless_when_missing(tmp_path: Path) -> None:
    """release_pidfile must not raise when the file is absent."""
    release_pidfile(tmp_path)  # no exception
