"""Rotation metadata must surface on the page payload — parity-audit C28 link 3.

The rotate job persists ``rotation_degrees`` / ``rotation_source`` on the
``PageAggregate`` record (durable, verified by ``test_rotate_job.py``), but the
page payload's ``page_record`` is rebuilt fresh by ``page_to_line_matches`` on
every GET — rotation fields stayed at their defaults (``0`` / ``"none"``), so
the SPA rotation badge could never render.

These tests drive the real HTTP path (seeded event store → POST /load →
GET page) and assert the payload carries the aggregate's rotation metadata.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

_PROJECT_ID = "rotbook"


def _make_png(h: int, w: int) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[: h // 2, :] = 128
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 100,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 100),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "bounding_box": _bbox(0, 0, 100, 40),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "bounding_box": _bbox(0, 0, 100, 20),
                        "items": [
                            {
                                "type": "Word",
                                "text": "hello",
                                "ground_truth_text": "hello",
                                "bounding_box": _bbox(0, 0, 50, 20),
                            }
                        ],
                    }
                ],
            }
        ],
    }
    return Page.from_dict(page_dict)


def _make_settings(tmp_path: Path, source_root: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        source_projects_root=source_root,
        mode="api_only",
    )


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    """A project dir with one PNG and a store seeded with rotated-page metadata."""
    source_root = tmp_path / "source"
    proj = source_root / _PROJECT_ID
    proj.mkdir(parents=True)
    (proj / "001.png").write_bytes(_make_png(100, 200))

    from pdomain_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id=_PROJECT_ID,
        project_root=proj,
        image_paths=[proj / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )
    store = LabelerPageStore(project_dir=proj)
    try:
        agg = _ingest_ocr_result(
            page=_make_page(),
            image_bytes=(proj / "001.png").read_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
        agg.rotation_updated(degrees=90, source="manual")
        store.save_page(agg)
    finally:
        store.close()
    return proj


@pytest.mark.integration
def test_get_page_payload_surfaces_rotation_metadata_from_store(tmp_path: Path, seeded_project: Path) -> None:
    """GET page payload must carry the aggregate's rotation_degrees/source.

    C28 link 3: the store had ``rotation_degrees=90, rotation_source="manual"``
    but the API payload stayed ``0/none`` even after POST /load — the rotation
    badge could never render.
    """
    settings = _make_settings(tmp_path, seeded_project.parent)
    app = build_app(settings)
    with TestClient(app) as c:
        r = c.post("/api/projects/load", json={"project_root": str(seeded_project)})
        assert r.status_code == 200, r.text

        r = c.get(f"/api/projects/{_PROJECT_ID}/pages/0")
        assert r.status_code == 200, r.text
        payload = r.json()
        record = payload["page_record"]
        assert record is not None, "page_record missing — labeled lane did not resolve"
        assert record["rotation_degrees"] == 90, (
            f"rotation_degrees not surfaced from the aggregate: got "
            f"{record['rotation_degrees']!r} (store has 90)"
        )
        assert record["rotation_source"] == "manual", (
            f"rotation_source not surfaced from the aggregate: got "
            f"{record['rotation_source']!r} (store has 'manual')"
        )


@pytest.mark.integration
def test_unrotated_page_payload_keeps_default_rotation(tmp_path: Path) -> None:
    """A page with no rotation history keeps rotation 0/none on the payload."""
    source_root = tmp_path / "source"
    proj = source_root / _PROJECT_ID
    proj.mkdir(parents=True)
    (proj / "001.png").write_bytes(_make_png(100, 200))

    from pdomain_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id=_PROJECT_ID,
        project_root=proj,
        image_paths=[proj / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )
    store = LabelerPageStore(project_dir=proj)
    try:
        _ingest_ocr_result(
            page=_make_page(),
            image_bytes=(proj / "001.png").read_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
    finally:
        store.close()

    settings = _make_settings(tmp_path, source_root)
    app = build_app(settings)
    with TestClient(app) as c:
        r = c.post("/api/projects/load", json={"project_root": str(proj)})
        assert r.status_code == 200, r.text
        r = c.get(f"/api/projects/{_PROJECT_ID}/pages/0")
        assert r.status_code == 200, r.text
        record = r.json()["page_record"]
        assert record is not None
        assert record["rotation_degrees"] == 0
        assert record["rotation_source"] == "none"
