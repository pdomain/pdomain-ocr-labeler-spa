"""Integration tests for the ``rotate_page`` job handler — S8.2.

Spec: ``docs/plans/2026-06-06-parity-gap-completion.md §S8.2``
Acceptance criteria:
  (a) The on-disk source image has transposed dimensions after a 90° rotate
      (width and height swap).
  (b) ``page_record.rotation_degrees == 90`` persisted in the PageAggregate.
  (c) The fake loader's ``run_ocr`` was invoked (re-OCR happened).

Seeding mirrors ``test_reload_ocr_job.py``: inject a ``_FakePageLoader`` on
``runner.context`` so no real DocTR is needed; use a real PNG on disk so the
cv2 round-trip can be verified.

For (b), we use a richer fake loader (``_FakePageLoaderWithIngest``) that calls
``_ingest_ocr_result`` so the returned ``PageLoadOutcome`` carries a real
``_labeler_page_id`` — this lets ``_apply_reocr_outcome`` stamp the pstate, so
the rotate handler can subsequently call ``rotation_updated`` on the aggregate.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
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
    """Return a real PNG with the given height×width so cv2 can decode it."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[: h // 2, :] = 128  # top half gray
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _make_fake_page() -> Any:
    """Minimal Page-like object usable with _ingest_ocr_result."""
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


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    # A rectangular image (height=100, width=200) so rotation transposes dims.
    (proj / "001.png").write_bytes(_make_png(100, 200))
    (proj / "002.png").write_bytes(_make_png(100, 200))
    return root


class _FakePageLoader:
    """Simple fake ``PageLoader``; records ``run_ocr`` calls, no store ingest."""

    def __init__(self, *, raise_on_run: Exception | None = None) -> None:
        self.calls: list[int] = []
        self._raise = raise_on_run

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.calls.append(page_index)
        if self._raise is not None:
            raise self._raise
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload={"fake": "page", "idx": page_index},
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


class _FakePageLoaderWithIngest:
    """Fake loader that also calls _ingest_ocr_result so page_id is stamped.

    This lets the rotate handler find a real page_id on pstate and call
    ``rotation_updated`` on the aggregate — needed to verify (b).
    """

    def __init__(self, store: LabelerPageStore, project: Project) -> None:
        self.calls: list[int] = []
        self._store = store
        self._project = project
        self.last_page_id: UUID | None = None

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
        self.last_page_id = agg.record.page_id
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


def _wrap_broker_publish(broker: JobEventBroker, sink: list[dict[str, Any]]) -> None:
    """Patch ``broker.publish`` to append every event to ``sink``."""
    original = broker.publish

    async def recording_publish(job_id: str, event: dict[str, Any]) -> None:
        sink.append({"job_id": job_id, **event})
        await original(job_id, event)

    broker.publish = recording_publish  # type: ignore[method-assign]


def _wait_for_terminal(events: list[dict[str, Any]], *, timeout: float = 10.0) -> None:
    """Spin until a terminal event lands in ``events``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(e.get("type") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.05)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


@pytest.fixture
def loaded_client_with_loader(
    tmp_path: Path, projects_root: Path
) -> Iterator[tuple[TestClient, _FakePageLoader, list[dict[str, Any]], Path]]:
    """Loaded project + simple fake page_loader + broker event recorder + image path."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    recorded: list[dict[str, Any]] = []
    image_path = projects_root / "book1" / "001.png"
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c, loader, recorded, image_path


def test_rotate_90_transposes_image_dimensions(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]], Path],
) -> None:
    """(a) After a 90° rotate, the source image on disk has transposed dims."""
    c, _loader, events, image_path = loaded_client_with_loader

    # Original: height=100, width=200
    orig = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    assert orig.shape[:2] == (100, 200), f"expected (100,200) got {orig.shape[:2]}"

    resp = c.post(
        "/api/projects/book1/pages/0/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 202, resp.text

    _wait_for_terminal(events)
    assert events[-1].get("type") == "complete", events[-1]

    # After 90° rotate: dims should be transposed to height=200, width=100
    rotated = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    assert rotated.shape[:2] == (200, 100), (
        f"expected transposed (200,100) after 90° rotate, got {rotated.shape[:2]}"
    )


def test_rotate_triggers_reocr(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]], Path],
) -> None:
    """(c) The fake loader's run_ocr was called (re-OCR happened after rotation)."""
    c, loader, events, _image_path = loaded_client_with_loader

    resp = c.post(
        "/api/projects/book1/pages/0/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 202, resp.text

    _wait_for_terminal(events)
    assert events[-1].get("type") == "complete", events[-1]

    assert loader.calls == [0], f"expected run_ocr called with page=0, got {loader.calls}"


def test_rotate_updates_rotation_degrees_in_aggregate(tmp_path: Path, projects_root: Path) -> None:
    """(b) rotation_degrees == 90 persisted in PageAggregate after rotate job.

    Uses ``_FakePageLoaderWithIngest`` so the OCR outcome carries a real
    ``_labeler_page_id`` — required for the rotate handler to stamp pstate
    and call ``rotation_updated`` on the aggregate.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        # Swap to the ingest-capable loader so page_id gets stamped.
        project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
        page_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        project = project_state.loaded_project
        assert project is not None
        loader_with_ingest = _FakePageLoaderWithIngest(store=page_store, project=project)
        c.app.state.job_runner.context["page_loader"] = loader_with_ingest  # type: ignore[attr-defined]

        resp2 = c.post(
            "/api/projects/book1/pages/0/rotate",
            json={"degrees": 90, "manual": True},
        )
        assert resp2.status_code == 202, resp2.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        # Check that page_id was stamped and aggregate has rotation_degrees == 90.
        pstate = project_state.page_states.get(0)
        assert pstate is not None, "page_state for index 0 not set"
        page_id: UUID | None = pstate.page_id
        assert page_id is not None, (
            "page_id not stamped on pstate — _FakePageLoaderWithIngest may not have "
            "produced a _labeler_page_id on the payload"
        )

        agg = page_store.get_page(page_id)
        assert agg.record.rotation_degrees == 90, (
            f"expected rotation_degrees=90 on aggregate, got {agg.record.rotation_degrees}"
        )
        assert str(agg.record.rotation_source) == "manual", (
            f"expected rotation_source='manual', got {agg.record.rotation_source}"
        )


def test_rotate_path_traversal_rejected(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]], Path],
) -> None:
    """Security: rotate job must fail (error terminal) if path points outside project root."""
    c, _loader, events, _image_path = loaded_client_with_loader

    project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
    proj = project_state.loaded_project
    assert proj is not None
    original_paths = proj.image_paths[:]
    # Point page 0's image path to something outside project_root
    evil_path = proj.project_root.parent.parent / "evil.png"
    patched = proj.model_copy(update={"image_paths": [evil_path, *original_paths[1:]]})
    project_state.set_loaded_project(patched)

    resp = c.post(
        "/api/projects/book1/pages/0/rotate",
        json={"degrees": 90, "manual": True},
    )
    assert resp.status_code == 202, resp.text

    _wait_for_terminal(events)
    terminal = events[-1]
    assert terminal.get("type") == "error", f"expected error terminal for path-traversal, got {terminal}"


def test_rotate_ccw_transposes_image_dimensions(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]], Path],
) -> None:
    """CCW rotation (degrees=-90) must succeed and transpose image dimensions.

    Regression test for: rotate_image only accepts {0,90,180,270}; -90 raises
    ValueError causing the job to terminate with an error event and leaving
    the image unchanged.  After the fix, -90 must be normalised to 270
    (equivalent CCW quarter-turn) before calling rotate_image.

    Assertions:
    - Terminal event is "complete" (no error).
    - On-disk image dimensions are transposed (height/width swapped) — same
      geometry as a CCW quarter-turn.
    - page_record.rotation_degrees is the normalised value 270 (not -90).
    """
    c, _loader, events, image_path = loaded_client_with_loader

    # Original: height=100, width=200
    orig = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    assert orig.shape[:2] == (100, 200), f"precondition: expected (100,200) got {orig.shape[:2]}"

    resp = c.post(
        "/api/projects/book1/pages/0/rotate",
        json={"degrees": -90, "manual": True},
    )
    assert resp.status_code == 202, resp.text

    _wait_for_terminal(events)
    assert events[-1].get("type") == "complete", (
        f"CCW rotate (-90) produced a terminal error — expected complete; last event={events[-1]}"
    )

    # After a CCW (270°) rotate: dims transposed to height=200, width=100
    rotated = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    assert rotated.shape[:2] == (200, 100), (
        f"expected transposed (200,100) after CCW rotate (-90/270°), got {rotated.shape[:2]}"
    )


def test_rotate_ccw_persists_normalised_rotation_degrees(
    tmp_path: Path,
    projects_root: Path,
) -> None:
    """rotation_degrees persisted as 270 (not -90) after a CCW rotate job.

    Uses _FakePageLoaderWithIngest so the aggregate path is exercised.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
        page_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        project = project_state.loaded_project
        assert project is not None
        loader_with_ingest = _FakePageLoaderWithIngest(store=page_store, project=project)
        c.app.state.job_runner.context["page_loader"] = loader_with_ingest  # type: ignore[attr-defined]

        resp2 = c.post(
            "/api/projects/book1/pages/0/rotate",
            json={"degrees": -90, "manual": True},
        )
        assert resp2.status_code == 202, resp2.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        pstate = project_state.page_states.get(0)
        assert pstate is not None
        page_id: UUID | None = pstate.page_id
        assert page_id is not None

        agg = page_store.get_page(page_id)
        assert agg.record.rotation_degrees == 270, (
            f"expected normalised rotation_degrees=270 after CCW (-90) rotate, "
            f"got {agg.record.rotation_degrees}"
        )


__all__: list[str] = []
