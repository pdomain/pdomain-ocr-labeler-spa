"""Unit tests for POST /api/projects/{id}/propose-page-kinds."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c


def test_propose_page_kinds_returns_a_job_id(loaded_client: TestClient) -> None:
    resp = loaded_client.post("/api/projects/book1/propose-page-kinds")
    assert resp.status_code == 202, resp.text
    assert "job_id" in resp.json()


def test_propose_page_kinds_404s_when_project_not_loaded(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.post("/api/projects/unknown-book/propose-page-kinds")
        assert resp.status_code == 404
