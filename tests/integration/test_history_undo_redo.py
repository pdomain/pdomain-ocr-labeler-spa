"""Slice H-B — undo/redo endpoints + durable round-trip.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` slice H-B:

- ``POST /api/projects/{pid}/pages/{idx}/undo`` restores the prior blob's
  content in the returned payload AND in a fresh ``LabelerPageStore`` read
  (restart simulation — the U-4 contract). ``.../redo`` round-trips.
- 409 at history bounds.
- The marker event lands in the aggregate changelog (U-9).
- In-memory ``PageState`` payload is swapped + generation bumped.
- A re-OCR'd page (new aggregate) reports empty history (U-6 backend half).
- ``PagePayload`` gains a ``history`` field surfaced on ``GET /pages/{idx}``.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

# ── Minimal Page builder (mirrors test_save_page_route_roundtrip.py) ─────────


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(0, 0, 10, 10),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "items": words,
        "bounding_box": _bbox(0, 0, 100, 20),
    }


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "Block", "child_type": "BLOCKS", "items": lines, "bounding_box": _bbox(0, 0, 100, 40)}


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [_para([_line([_word("teh"), _word("cat")]), _line([_word("sat")])])],
    }
    return Page.from_dict(page_dict)


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 300), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


# ── Fixtures: TestClient with a store-seeded project ─────────────────────────


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
        "no_prefetch": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    """Project dir with one real PNG page + event store seeded with its OCR content."""
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(_png_bytes())

    store = LabelerPageStore(project_dir=proj)
    try:
        page = _make_page()
        project = Project(
            project_id="book1",
            project_root=proj,
            image_paths=[proj / "001.png"],
            ground_truth_map={},
            total_pages=1,
        )
        _ingest_ocr_result(
            page=page,
            image_bytes=_png_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
    finally:
        store.close()
    return proj


@pytest.fixture
def client(tmp_path: Path, seeded_project: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=seeded_project.parent)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(seeded_project)})
        assert resp.status_code == 200, resp.text
        yield c


def _get_history(client: TestClient) -> dict[str, object]:
    r = client.get("/api/projects/book1/pages/0")
    assert r.status_code == 200, r.text
    history = r.json().get("history")
    assert history is not None, "PagePayload.history missing from GET /pages/0"
    return history


# ── HTTP round-trip: GET history flags + undo/redo content restore ───────────


@pytest.mark.integration
def test_get_page_history_starts_at_root(client: TestClient) -> None:
    history = _get_history(client)
    assert history["undo_available"] is False
    assert history["redo_available"] is False
    assert history["depth"] == 50


@pytest.mark.integration
def test_undo_redo_http_roundtrip(client: TestClient, seeded_project: Path) -> None:
    # Load the page into memory, then mutate a word's GT (one undo step).
    assert _get_history(client)["undo_available"] is False
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "the"})
    assert r.status_code == 200, r.text
    assert "the" in r.json()["page_text_gt"]

    history = _get_history(client)
    assert history["undo_available"] is True
    assert history["redo_available"] is False

    # Undo → payload shows the pre-mutation GT; redo becomes available.
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "teh" in payload["page_text_gt"]
    assert payload["history"]["redo_available"] is True
    assert payload["history"]["undo_available"] is False

    # Redo → post-mutation GT again.
    r = client.post("/api/projects/book1/pages/0/redo")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "the" in payload["page_text_gt"]
    assert payload["history"]["redo_available"] is False
    assert payload["history"]["undo_available"] is True


@pytest.mark.integration
def test_undo_redo_409_at_bounds(client: TestClient) -> None:
    # Fresh page: cursor at the OCR root — nothing to undo or redo.
    assert _get_history(client)["undo_available"] is False
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "undo_unavailable"
    r = client.post("/api/projects/book1/pages/0/redo")
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "redo_unavailable"


@pytest.mark.integration
def test_undo_404_when_no_project(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        r = c.post("/api/projects/nope/pages/0/undo")
        assert r.status_code == 404


@pytest.mark.integration
def test_undo_survives_restart_and_lands_in_changelog(client: TestClient, seeded_project: Path) -> None:
    """U-4 + U-9: after undo, a FRESH store reads the restored content; the
    marker event is recorded in the aggregate changelog."""
    _get_history(client)  # prime: loads the page into memory
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "the"})
    assert r.status_code == 200, r.text
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 200, r.text

    # Restart simulation: a brand-new store on the same project dir must
    # resolve the restored (pre-edit) content from the head blob.
    fresh = LabelerPageStore(project_dir=seeded_project)
    try:
        proj_agg = fresh.get_project(_project_uuid("book1"))
        page_id = proj_agg.record.page_ids[0]
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None
        assert reloaded.lines[0].words[0].ground_truth_text == "teh", (
            "undo did not move the head to the restored blob — fresh-store read returned post-edit content"
        )
        # U-9: the changelog records the history op.
        agg = fresh.get_page(page_id)
        last_changes = agg.record.changelog[-1].changes
        assert any(c.get("type") == "undo" for c in last_changes), last_changes
    finally:
        fresh.close()


def _project_uuid(project_id: str) -> UUID:
    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _project_uuid_for

    return _project_uuid_for(project_id)


@pytest.mark.integration
def test_new_edit_after_undo_truncates_redo(client: TestClient) -> None:
    """U-5 at the route level: edit A → edit B → undo → edit C → redo 409."""
    _get_history(client)  # prime: loads the page into memory
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "A"})
    assert r.status_code == 200, r.text
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "B"})
    assert r.status_code == 200, r.text
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 200, r.text
    assert "A" in r.json()["page_text_gt"]
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "C"})
    assert r.status_code == 200, r.text
    r = client.post("/api/projects/book1/pages/0/redo")
    assert r.status_code == 409, r.text
    # Undo from C returns to A, not B (U-5).
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 200, r.text
    assert "A" in r.json()["page_text_gt"]


@pytest.mark.integration
def test_generation_bumps_on_undo(client: TestClient) -> None:
    _get_history(client)  # prime: loads the page into memory
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "the"})
    gen_before = r.json()["generation"]
    r = client.post("/api/projects/book1/pages/0/undo")
    assert r.status_code == 200, r.text
    assert r.json()["generation"] > gen_before


# ── U-6 backend half: re-OCR'd page (new aggregate) reports empty history ────


@pytest.mark.integration
def test_reocr_new_aggregate_resets_history(client: TestClient, seeded_project: Path) -> None:
    """Re-OCR replaces the page aggregate; the new aggregate's history is fresh."""
    # Make an edit so the OLD aggregate has undo history.
    _get_history(client)  # prime: loads the page into memory
    r = client.post("/api/projects/book1/pages/0/words/0/0/gt", json={"text": "the"})
    assert r.status_code == 200, r.text
    assert _get_history(client)["undo_available"] is True

    # Simulate the re-OCR boundary the way the reload_ocr handler does it:
    # a NEW aggregate (new page_id) registered at the same slot
    # (core/page_state.py:246-256 re-stamps page_id from the new payload).
    store = LabelerPageStore(project_dir=seeded_project)
    try:
        new_page = _make_page()
        object.__setattr__(new_page, "page_id", uuid4())
        agg = _ingest_ocr_result(
            page=new_page,
            image_bytes=_png_bytes(),
            page_index=0,
            store=store,
            project=Project(
                project_id="book1",
                project_root=seeded_project,
                image_paths=[seeded_project / "001.png"],
                ground_truth_map={},
                total_pages=1,
            ),
        )
        from pdomain_ocr_labeler_spa.core.page_history import derive_history

        graph = agg.record.provenance
        assert graph is not None
        state = derive_history(graph)
        assert state.undo_available is False
        assert state.redo_available is False
    finally:
        store.close()


# ── OpenAPI surface ──────────────────────────────────────────────────────────


@pytest.mark.integration
def test_openapi_has_undo_redo_and_history(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/projects/{project_id}/pages/{page_index}/undo" in paths
    assert "/api/projects/{project_id}/pages/{page_index}/redo" in paths
    payload_props = schema["components"]["schemas"]["PagePayload"]["properties"]
    assert "history" in payload_props
    info_props = schema["components"]["schemas"]["PageHistoryInfo"]["properties"]
    assert set(info_props) >= {"undo_available", "redo_available", "cursor", "depth"}


# Keep ruff happy about unused json import if assertions change later.
_ = json
