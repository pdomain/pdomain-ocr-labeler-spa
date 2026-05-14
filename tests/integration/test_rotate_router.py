"""Integration tests for POST /api/projects/{id}/pages/{idx}/rotate.

Spec: docs/specs/2026-05-12-auto-rotation-design.md §Manual rotate (M9.1)
Issue #263

Acceptance:
- 202 response with job_id on valid request
- 404 on unknown project
- 404 on out-of-range page index
- 400 on invalid degrees (e.g. 45)
- RotationSource enum values exported in models
- PageRecord has rotation_degrees + rotation_source fields
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.models import PageRecord, RotationSource
from pd_ocr_labeler_spa.settings import Settings


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
    """Tiny project directory with 3 PNG pages."""
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "test-proj"
    proj.mkdir()
    for i in range(1, 4):
        (proj / f"{i:03d}.png").write_bytes(b"\x89PNG")
    (proj / "pages.json").write_text('{"001.png": "hello", "002.png": "world", "003.png": "foo"}')
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with test-proj loaded."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "test-proj")},
        )
        assert resp.status_code == 200, f"load failed: {resp.text}"
        yield c


def test_rotate_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """POST /rotate with valid degrees returns 202 + job_id."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/0/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert len(body["job_id"]) > 0


def test_rotate_180_accepted(loaded_client: TestClient) -> None:
    """degrees=180 is valid."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/0/rotate",
        json={"degrees": 180, "manual": True},
    )
    assert resp.status_code == 202


def test_rotate_minus90_accepted(loaded_client: TestClient) -> None:
    """degrees=-90 (CCW) is valid."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/0/rotate",
        json={"degrees": -90, "manual": False},
    )
    assert resp.status_code == 202


def test_rotate_invalid_degrees_returns_400(loaded_client: TestClient) -> None:
    """Non-cardinal degrees (e.g. 45) returns 400 invalid_degrees."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/0/rotate",
        json={"degrees": 45, "manual": True},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error") == "invalid_degrees"


def test_rotate_zero_degrees_returns_400(loaded_client: TestClient) -> None:
    """degrees=0 is not a valid rotation — returns 400 invalid_degrees."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/0/rotate",
        json={"degrees": 0, "manual": True},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error") == "invalid_degrees"


def test_rotate_unknown_project_returns_404(loaded_client: TestClient) -> None:
    """Unknown project_id returns 404."""
    resp = loaded_client.post(
        "/api/projects/no-such-project/pages/0/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 404


def test_rotate_out_of_range_page_returns_404(loaded_client: TestClient) -> None:
    """Out-of-range page_index returns 404."""
    resp = loaded_client.post(
        "/api/projects/test-proj/pages/99/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 404


def test_page_record_has_rotation_fields() -> None:
    """PageRecord model has rotation_degrees and rotation_source fields."""
    record = PageRecord(
        page_index=0,
        page_number=1,
        image_path=Path("001.png"),
    )
    assert record.rotation_degrees == 0
    assert record.rotation_source == RotationSource.NONE


def test_page_record_rotation_source_values() -> None:
    """PageRecord accepts all three RotationSource values."""
    for source in (RotationSource.NONE, RotationSource.AUTO, RotationSource.MANUAL):
        record = PageRecord(
            page_index=0,
            page_number=1,
            image_path=Path("001.png"),
            rotation_degrees=90,
            rotation_source=source,
        )
        assert record.rotation_source == source


def test_rotation_source_enum_values() -> None:
    """RotationSource enum has the three expected string values."""
    assert RotationSource.NONE == "none"
    assert RotationSource.AUTO == "auto"
    assert RotationSource.MANUAL == "manual"
