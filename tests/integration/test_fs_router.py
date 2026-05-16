"""Integration tests for ``GET /api/fs/ls`` — directory-listing endpoint.

Spec authority: docs/architecture/22-spec-projectpage.md §10 (source-folder
picker); issue #294.

Tests pin:
1. Default (no ``path`` param) → lists home directory.
2. Absolute path → lists real subdirs, excludes hidden and files.
3. Non-existent path → empty entries list (not a 404).
4. Path that is a file (not a dir) → empty entries list.
5. Tilde path (``~/subdir``) → expanduser before resolve.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────
# GET /api/fs/ls
# ──────────────────────────────────────────────────────────────────────


def test_fs_ls_absolute_path_lists_dirs(tmp_path: Path, client: TestClient) -> None:
    """Absolute path → returns sorted subdirectory names, excludes files + hidden."""
    base = tmp_path / "browse"
    base.mkdir()
    (base / "alpha").mkdir()
    (base / "Beta").mkdir()
    (base / ".hidden").mkdir()
    (base / "regular.txt").write_text("ignored")

    resp = client.get("/api/fs/ls", params={"path": str(base)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(base)
    names = [e["name"] for e in body["entries"]]
    assert "alpha" in names
    assert "Beta" in names
    assert ".hidden" not in names
    assert "regular.txt" not in names
    # Sorted alphabetically (case-sensitive per sorted()).
    assert names == sorted(names)


def test_fs_ls_all_entries_are_dirs(tmp_path: Path, client: TestClient) -> None:
    """Every entry in the response has ``is_dir: true``."""
    base = tmp_path / "browse2"
    base.mkdir()
    (base / "sub1").mkdir()
    (base / "sub2").mkdir()

    resp = client.get("/api/fs/ls", params={"path": str(base)})
    body = resp.json()
    assert all(e["is_dir"] is True for e in body["entries"])


def test_fs_ls_nonexistent_path_returns_empty(client: TestClient) -> None:
    """Non-existent path → ``entries: []``, not a 404."""
    resp = client.get("/api/fs/ls", params={"path": "/absolutely/does/not/exist/xyz"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []


def test_fs_ls_file_path_returns_empty(tmp_path: Path, client: TestClient) -> None:
    """Path that points at a regular file → ``entries: []``."""
    f = tmp_path / "regular.txt"
    f.write_text("content")

    resp = client.get("/api/fs/ls", params={"path": str(f)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []


def test_fs_ls_tilde_expands_to_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``path=~/subdir`` expands tilde correctly.

    Root cause of Bug 1: ``Path("~/x").resolve()`` does NOT expand tilde.
    The fix calls ``.expanduser()`` first.  This test exercises the same
    expanduser path through the fs endpoint.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    sub = fake_home / "mybooks"
    sub.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.get("/api/fs/ls", params={"path": "~"})

    assert resp.status_code == 200
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    assert "mybooks" in names


def test_fs_ls_default_path_is_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``GET /api/fs/ls`` with no ``path`` param defaults to ``~`` (home)."""
    fake_home = tmp_path / "defaulthome"
    fake_home.mkdir()
    (fake_home / "projects").mkdir()

    monkeypatch.setenv("HOME", str(fake_home))

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.get("/api/fs/ls")

    assert resp.status_code == 200
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    assert "projects" in names
