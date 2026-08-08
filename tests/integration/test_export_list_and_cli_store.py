"""Wave 1: list_exports reads manifest; CLI export is store-first."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from PIL import Image

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _write_export_manifest
from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _run_export
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str, x0: int, y0: int) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(x0, y0, x0 + 40, y0 + 18),
    }


def _make_page() -> Page:
    words = [_word("the", 10, 8), _word("cat", 60, 8)]
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "items": words,
        "bounding_box": _bbox(5, 5, 190, 30),
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "items": [line],
        "bounding_box": _bbox(5, 5, 190, 60),
    }
    return Page.from_dict(
        {
            "width": 200,
            "height": 300,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, 200, 300),
            "items": [para],
        }
    )


def _write_real_png(path: Path, *, width: int = 200, height: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), "white").save(path)


def _make_settings(tmp_path: Path, *, data_root: Path, projects_root: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=data_root,
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


def _seed_store_saved_page(project_dir: Path, project: Project) -> None:
    """OCR-ingest page 0 then save fully-validated content (SPA save path)."""
    store = LabelerPageStore(project_dir=project_dir)
    try:
        page = _make_page()
        agg = _ingest_ocr_result(
            page=page,
            image_bytes=(project_dir / "001.png").read_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
        page_id = agg.record.page_id
        loaded = load_page_from_store(store, page_id)
        assert loaded is not None
        for w in loaded.words:
            labels = list(getattr(w, "word_labels", None) or [])
            if "validated" not in labels:
                labels.append("validated")
            w.word_labels = labels
        save_page_content_to_store(page_id=page_id, page=loaded, store=store)
    finally:
        store.close()


@pytest.mark.integration
def test_list_exports_reads_doctr_manifest(tmp_path: Path) -> None:
    """Wave 1.1: GET .../exports returns remapped row from disk manifest."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    (projects_root / "book1").mkdir()
    (projects_root / "book1" / "001.png").write_bytes(b"\x00")

    export_root = data_root / "doctr-export"
    export_root.mkdir()
    _write_export_manifest(
        export_root=export_root,
        project_id="book1",
        exported_at="2026-07-21T12:00:00+00:00",
        page_count=3,
        task_stats=[
            SimpleNamespace(task="detection", item_count=10),
            SimpleNamespace(task="recognition", item_count=8),
        ],
    )

    settings = _make_settings(tmp_path, data_root=data_root, projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/projects/book1/exports")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        row = body[0]
        assert "2026-07-21" in row["created_at"]
        assert row["page_count"] == 3
        assert row["scope"] == "project"
        assert row["job_id"].startswith("doctr-export:book1:")
        assert row["tasks"]["detection"]["item_count"] == 10

        empty = client.get("/api/projects/other/exports")
        assert empty.status_code == 200
        assert empty.json() == []


@pytest.mark.integration
def test_cli_export_store_first_non_zero_pages(tmp_path: Path) -> None:
    """Wave 1.5: SPA store-only save → CLI export yields non-zero pages."""
    project_dir = tmp_path / "book1"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_real_png(project_dir / "001.png")

    project = Project(
        project_id="book1",
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )
    _seed_store_saved_page(project_dir, project)

    count = asyncio.run(
        _run_export(
            data_root=data_root,
            project_id="book1",
            style_filters=[],
            component_filter=None,
            detection_only=False,
            recognition_only=False,
            classification=False,
            page_index=None,
            project_root=project_dir,
        )
    )
    assert count >= 1, f"CLI store-first exported {count} pages (expected >= 1)"

    manifest = data_root / "doctr-export" / "manifest.json"
    assert manifest.is_file(), "CLI must write doctr-export manifest"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "book1" in data.get("projects", {})
    assert data["projects"]["book1"]["page_count"] >= 1
