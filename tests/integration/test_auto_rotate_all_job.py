"""Integration tests for the ``auto_rotate_all`` job handler — S8.3.

Spec: ``docs/plans/2026-06-06-parity-gap-completion.md §S8.3``
Acceptance criteria:
  - A page whose ocr_fn reports a non-zero best rotation ≥ threshold gets
    rotated (image dims transposed, rotation_degrees set on aggregate).
  - An upright page (best rotation == 0) stays unchanged.
  - Pages with rotation_source="manual" are skipped unless overwrite_manual=True.

These tests inject a stub ``ocr_fn`` via ``runner.context["auto_rotate_ocr_fn"]``
(or via the predictor cache path) so no real DocTR is needed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState
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


def _make_png(h: int, w: int) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[: h // 2, :] = 128
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _make_fake_page() -> Any:
    from pdomain_book_tools.ocr.page import Page

    page_dict = {
        "width": 200,
        "height": 100,
        "page_index": 0,
        "bounding_box": {
            "top_left": {"x": 0, "y": 0},
            "bottom_right": {"x": 200, "y": 100},
            "is_normalized": False,
        },
        "items": [],
    }
    return Page.from_dict(page_dict)


def _wrap_broker_publish(broker: Any, sink: list[dict[str, Any]]) -> None:
    original = broker.publish

    async def recording_publish(job_id: str, event: dict[str, Any]) -> None:
        sink.append({"job_id": job_id, **event})
        await original(job_id, event)

    broker.publish = recording_publish  # type: ignore[method-assign]


def _wait_for_terminal(events: list[dict[str, Any]], *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(e.get("type") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.05)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


def _seed_page_in_store(
    store: LabelerPageStore,
    project: Project,
    page_index: int,
    image_bytes: bytes,
    project_state: ProjectState,
) -> None:
    """Seed a page in the event store and stamp page_id on project_state.

    Mirrors the pattern used in test_save_page_route_roundtrip.py so
    the handler can find a page_id for calling rotation_updated.
    """
    page = _make_fake_page()
    agg = _ingest_ocr_result(
        page=page,
        image_bytes=image_bytes,
        page_index=page_index,
        store=store,
        project=project,
    )
    object.__setattr__(page, "_labeler_page_id", agg.record.page_id)
    outcome = PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.page_id = agg.record.page_id
    with project_state._lock:
        project_state._page_states[page_index] = pstate


class _FakePageLoaderWithIngest:
    """Fake loader that ingests into the store so page_id is stamped."""

    def __init__(self, store: LabelerPageStore, project: Project) -> None:
        self.calls: list[int] = []
        self._store = store
        self._project = project

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.calls.append(page_index)
        page = _make_fake_page()
        agg = _ingest_ocr_result(
            page=page,
            image_bytes=_make_png(100, 200),
            page_index=page_index,
            store=self._store,
            project=self._project,
        )
        object.__setattr__(page, "_labeler_page_id", agg.record.page_id)
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


def _make_sideways_document() -> Any:
    """Return a Document stub with high-confidence 90° rotation."""
    doc = MagicMock()
    doc.pages = [MagicMock()]

    class _FakeProbe:
        def __init__(self, rotation: int, confidence: float) -> None:
            self.rotation = rotation
            self.confidence = confidence

    return doc, [_FakeProbe(90, 0.95)]


def _make_upright_document() -> Any:
    """Return a Document stub indicating 0° best rotation."""
    doc = MagicMock()
    doc.pages = [MagicMock()]

    class _FakeProbe:
        def __init__(self, rotation: int, confidence: float) -> None:
            self.rotation = rotation
            self.confidence = confidence

    return doc, [_FakeProbe(0, 0.99)]


@pytest.fixture
def projects_root_two_pages(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book2"
    proj.mkdir()
    # Two rectangular images
    (proj / "001.png").write_bytes(_make_png(100, 200))
    (proj / "002.png").write_bytes(_make_png(100, 200))
    return root


def test_auto_rotate_rotates_sideways_page(tmp_path: Path, projects_root_two_pages: Path) -> None:
    """A page whose detect_best_rotation returns 90° ≥ threshold gets rotated."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root_two_pages)
    app = build_app(settings)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root_two_pages / "book2")},
        )
        assert resp.status_code == 200, resp.text

        project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
        page_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        project = project_state.loaded_project
        assert project is not None

        # Seed both pages so page_ids are available for rotation metadata.
        image_bytes = _make_png(100, 200)
        _seed_page_in_store(page_store, project, 0, image_bytes, project_state)
        _seed_page_in_store(page_store, project, 1, image_bytes, project_state)

        # Fake loader that ingests new pages on re-OCR.
        loader = _FakePageLoaderWithIngest(store=page_store, project=project)
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

        # Stub detect_best_rotation: page 0 → 90° (sideways), page 1 → 0° (upright).
        sideways_doc, sideways_probes = _make_sideways_document()
        upright_doc, upright_probes = _make_upright_document()
        call_count = [0]

        def fake_detect(image, *, ocr_fn, confidence_threshold=0.6, **kw):  # type: ignore[no-untyped-def]
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return (90, sideways_doc, sideways_probes)
            return (0, upright_doc, upright_probes)

        c.app.state.job_runner.context["auto_rotate_detect_fn"] = fake_detect  # type: ignore[attr-defined]

        image_path_0 = projects_root_two_pages / "book2" / "001.png"
        orig_0 = cv2.imdecode(np.frombuffer(image_path_0.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        assert orig_0.shape[:2] == (100, 200)

        resp2 = c.post(
            "/api/projects/book2/auto-rotate-all",
            json={"overwrite_manual": False},
        )
        assert resp2.status_code == 202, resp2.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        # Page 0 should be rotated (dims transposed).
        rotated_0 = cv2.imdecode(np.frombuffer(image_path_0.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        assert rotated_0.shape[:2] == (200, 100), (
            f"page 0 expected (200,100) after 90° rotate, got {rotated_0.shape[:2]}"
        )

        # Page 1 should NOT be rotated (still 100x200).
        image_path_1 = projects_root_two_pages / "book2" / "002.png"
        untouched_1 = cv2.imdecode(np.frombuffer(image_path_1.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        assert untouched_1.shape[:2] == (100, 200), (
            f"page 1 expected (100,200) unchanged, got {untouched_1.shape[:2]}"
        )


def test_auto_rotate_skips_manual_pages_by_default(tmp_path: Path, projects_root_two_pages: Path) -> None:
    """Pages with rotation_source='manual' are skipped when overwrite_manual=False."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root_two_pages)
    app = build_app(settings)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root_two_pages / "book2")},
        )
        assert resp.status_code == 200, resp.text

        project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
        page_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        project = project_state.loaded_project
        assert project is not None

        # Seed page 0 and mark it with manual rotation in the aggregate.
        image_bytes = _make_png(100, 200)
        _seed_page_in_store(page_store, project, 0, image_bytes, project_state)
        _seed_page_in_store(page_store, project, 1, image_bytes, project_state)

        # Mark page 0 as manually rotated.
        pstate_0 = project_state.page_states[0]
        assert pstate_0.page_id is not None
        agg_0 = page_store.get_page(pstate_0.page_id)
        agg_0.rotation_updated(degrees=90, source="manual")
        page_store.save_page(agg_0)

        loader = _FakePageLoaderWithIngest(store=page_store, project=project)
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

        # detect always returns 90° so both pages would rotate if not skipped.
        def fake_detect(image, *, ocr_fn, confidence_threshold=0.6, **kw):  # type: ignore[no-untyped-def]
            sideways_doc, sideways_probes = _make_sideways_document()
            return (90, sideways_doc, sideways_probes)

        c.app.state.job_runner.context["auto_rotate_detect_fn"] = fake_detect  # type: ignore[attr-defined]

        image_path_0 = projects_root_two_pages / "book2" / "001.png"

        resp2 = c.post(
            "/api/projects/book2/auto-rotate-all",
            # overwrite_manual defaults to False → page 0 (manual) must be skipped
            json={"overwrite_manual": False},
        )
        assert resp2.status_code == 202, resp2.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        # Page 0 should NOT be rotated (manual was skipped).
        result_0 = cv2.imdecode(np.frombuffer(image_path_0.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        assert result_0.shape[:2] == (100, 200), (
            f"page 0 (manual) should be untouched, got {result_0.shape[:2]}"
        )

        # Page 1 should be rotated (no manual flag).
        image_path_1 = projects_root_two_pages / "book2" / "002.png"
        result_1 = cv2.imdecode(np.frombuffer(image_path_1.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        assert result_1.shape[:2] == (200, 100), (
            f"page 1 (not manual) should be rotated to (200,100), got {result_1.shape[:2]}"
        )


__all__: list[str] = []
