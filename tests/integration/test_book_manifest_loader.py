"""End-to-end lazy opening for producer-shaped PGDP book materializations."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings
from tests.unit.core.persistence.test_book_labeling_session import _write_book


def _settings(tmp_path: Path, projects_root: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        no_prefetch=True,
        source_projects_root=projects_root,
    )


def test_loads_and_navigates_a_lazy_319_page_pgdp_book(tmp_path: Path) -> None:
    """Loading pins book metadata; requests open only their verified page lease."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    book_root = projects_root / "projectID643ab41f2b9e6"
    manifest = _write_book(book_root, page_count=319, valid_images=True)
    app = build_app(_settings(tmp_path, projects_root))

    with TestClient(app) as client:
        response = client.post("/api/projects/load", json={"project_root": str(book_root)})
        assert response.status_code == 200, response.text
        project = response.json()["project"]
        assert project["total_pages"] == 319
        assert len(project["image_paths"]) == 319

        state = app.state.project_state
        assert state.labeling_bundle is not None
        assert state.labeling_bundle.bundle_id == manifest.pages[0].labeling_bundle_id
        assert state.book_page_cache_size == 1

        page_zero_image = client.get(f"/api/projects/{project['project_id']}/pages/0/image")
        assert page_zero_image.status_code == 200, page_zero_image.text
        assert page_zero_image.headers["content-type"] == "image/jpeg"
        page_zero_bundle_id = state.labeling_bundle.bundle_id

        page_one_image = client.get(f"/api/projects/{project['project_id']}/pages/1/image")
        assert page_one_image.status_code == 200, page_one_image.text
        assert page_one_image.headers["content-type"] == "image/jpeg"
        assert state.labeling_bundle is not None
        assert state.labeling_bundle.bundle_id == manifest.pages[1].labeling_bundle_id
        assert state.labeling_bundle.bundle_id != page_zero_bundle_id
        assert page_zero_image.content != page_one_image.content
        assert state.book_page_cache_size <= 3

        worklist = client.get(f"/api/projects/{project['project_id']}/pages/1/typography/worklist")
        assert worklist.status_code == 200, worklist.text
        assert worklist.json()["bundle_id"] == manifest.pages[1].labeling_bundle_id

        tampered_page = book_root / manifest.pages[2].materialization_relative_path / "materialization.json"
        tampered_page.write_bytes(b"{}\n")
        invalid_page = client.get(f"/api/projects/{project['project_id']}/pages/2/image")
        assert invalid_page.status_code == 422
        assert invalid_page.json()["error"] == "invalid_labeling_page"
        assert state.labeling_bundle is not None
        assert state.labeling_bundle.bundle_id == manifest.pages[1].labeling_bundle_id
        assert client.get(f"/api/projects/{project['project_id']}/pages/1/image").status_code == 200
