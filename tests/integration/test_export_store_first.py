"""Store-first export resolution — PARITY-GAP P1.2 / P1.5 (sweep C35-C37, C40).

The export handler historically scanned only the retired ``labeled-projects/``
lane while Save writes only the event store (``save_page_content_to_store``),
so every UI-driven export exported 0 pages. These tests pin the CT-approved
design: **export reads the event-store head**, with the legacy
``labeled-projects/`` envelope as a per-page fallback ONLY when no store head
exists for that page (C56 compat).

Covers:
- store-only page → exported (crops + labels on disk)          [C35/C36]
- legacy-only page → exported via fallback                      [C56]
- mixed: store head wins over a stale legacy envelope           [design]
- style endpoint lists real styles from store-saved pages       [C37]
- canonical cancel route ``POST /api/jobs/{id}/cancel`` exists  [C40]
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.settings import Settings

# ── Real book-tools Page builders (pixel-space bboxes inside a 200x300 image) ──


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


def _make_page_dict(words: list[dict[str, object]]) -> dict[str, object]:
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
    return {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [para],
    }


def _make_page() -> Page:
    return Page.from_dict(_make_page_dict([_word("teh", 10, 8), _word("cat", 60, 8)]))


def _write_real_png(path: Path, *, width: int = 200, height: int = 300) -> None:
    """A real decodable PNG — cv2.imread must succeed on it for crop export."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), "white").save(path)


def _make_project(project_dir: Path, project_id: str = "book1") -> Project:
    return Project(
        project_id=project_id,
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )


def _seed_store_saved_page(
    project_dir: Path,
    project: Project,
    *,
    gt_text: str = "the",
    style_label: str | None = "italics",
) -> None:
    """OCR-ingest page 0 into the project's event store, then save an edited,
    fully-validated version of it via ``save_page_content_to_store`` — the
    exact write path the Save button exercises."""
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
        words = loaded.words
        words[0].ground_truth_text = gt_text
        for w in words:
            w.word_labels.append("validated")
        if style_label is not None:
            words[0].text_style_labels.append(style_label)
        save_page_content_to_store(page_id=page_id, page=loaded, store=store)
    finally:
        store.close()


def _plant_legacy_envelope(
    data_root: Path,
    project_id: str,
    page_index: int,
    *,
    gt_text: str = "legacy",
) -> None:
    """Write a legacy ``labeled-projects/`` envelope + sibling PNG (C56 lane)."""
    project_dir = data_root / "labeled-projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{project_id}_{page_index:03d}"

    _write_real_png(project_dir / f"{stem}.png")

    words = [_word(gt_text, 10, 8), _word("dog", 60, 8)]
    for w in words:
        w["word_labels"] = ["validated"]
    envelope = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "payload": {"page": _make_page_dict(words)},
    }
    (project_dir / f"{stem}.json").write_text(json.dumps(envelope), encoding="utf-8")


# ── Fake runner (handler-level harness, no FastAPI boot) ────────────────────────


class _FakeRunner:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context
        self._jobs: dict[str, Job] = {}
        self.updates: list[dict[str, Any]] = []

    async def update_progress(
        self,
        job_id: str,
        *,
        current: int = 0,
        total: int = 0,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        self.updates.append(
            {
                "job_id": job_id,
                "current": current,
                "total": total,
                "message": message,
                "result": result,
            }
        )


def _make_runner(
    *,
    data_root: Path,
    project: Project | None,
    project_dir: Path | None,
) -> tuple[_FakeRunner, LabelerPageStore | None]:
    """Runner context mirroring bootstrap wiring: settings + project_state (+ store)."""
    project_state = ProjectState()
    store: LabelerPageStore | None = None
    if project is not None:
        project_state.set_loaded_project(project)
    if project_dir is not None:
        store = LabelerPageStore(project_dir=project_dir)
    context: dict[str, Any] = {
        "settings": SimpleNamespace(data_root=data_root),
        "project_state": project_state,
        "page_store": store,
    }
    return _FakeRunner(context), store


def _make_job(project_id: str, **payload_overrides: Any) -> Job:
    from datetime import UTC, datetime

    payload: dict[str, Any] = {"scope": "all_validated"}
    payload.update(payload_overrides)
    return Job(
        job_id="export-test-job",
        job_type="export",
        status=JobStatus.RUNNING,
        project_id=project_id,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def _run_export(runner: _FakeRunner, job: Job) -> None:
    asyncio.run(handle_export(runner, job))  # type: ignore[arg-type]


def _recognition_labels(data_root: Path, project_id: str, subfolder: str = "all") -> dict[str, Any]:
    labels_path = data_root / "doctr-export" / project_id / subfolder / "recognition" / "labels.json"
    assert labels_path.exists(), f"recognition labels.json missing at {labels_path}"
    return json.loads(labels_path.read_text(encoding="utf-8"))


# ── Acceptance: store-only page exports crops + labels (C35/C36) ───────────────


@pytest.mark.integration
def test_export_store_saved_page_produces_crops(tmp_path: Path) -> None:
    """A page saved ONLY via the event store (no labeled-projects file) must
    export real recognition crops + labels — the P1.2 acceptance gate."""
    project_dir = tmp_path / "book1"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_real_png(project_dir / "001.png")

    project = _make_project(project_dir)
    _seed_store_saved_page(project_dir, project, gt_text="the")

    runner, store = _make_runner(data_root=data_root, project=project, project_dir=project_dir)
    try:
        _run_export(runner, _make_job("book1"))
    finally:
        if store is not None:
            store.close()

    labels = _recognition_labels(data_root, "book1")
    assert len(labels) == 2, f"expected 2 word crops, got {len(labels)}: {labels}"
    assert sorted(labels.values()) == ["cat", "the"], (
        f"expected the store-saved (edited) GT values, got {sorted(labels.values())}"
    )

    images_dir = data_root / "doctr-export" / "book1" / "all" / "recognition" / "images"
    crops = list(images_dir.glob("*.png"))
    assert len(crops) == 2, f"expected 2 crop images, got {[p.name for p in crops]}"

    detection_labels = data_root / "doctr-export" / "book1" / "all" / "detection" / "labels.json"
    assert detection_labels.exists(), "detection labels.json missing"

    terminal = runner.updates[-1]
    assert terminal["result"] is not None
    assert terminal["result"]["words_exported_recognition"] == 2


@pytest.mark.integration
def test_export_current_scope_resolves_store_page(tmp_path: Path) -> None:
    """``scope=current`` must resolve the store head too (no legacy file needed)."""
    project_dir = tmp_path / "book1"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_real_png(project_dir / "001.png")

    project = _make_project(project_dir)
    _seed_store_saved_page(project_dir, project)

    runner, store = _make_runner(data_root=data_root, project=project, project_dir=project_dir)
    try:
        _run_export(runner, _make_job("book1", scope="current", page_index=0))
    finally:
        if store is not None:
            store.close()

    labels = _recognition_labels(data_root, "book1")
    assert len(labels) == 2


# ── Acceptance: legacy-only page still exports via fallback (C56) ──────────────


@pytest.mark.integration
def test_export_legacy_only_page_falls_back(tmp_path: Path) -> None:
    """A page with NO store head but a legacy envelope must still export."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _plant_legacy_envelope(data_root, "book1", 0, gt_text="legacy")

    # No project loaded, no store — pure legacy lane.
    runner, _store = _make_runner(data_root=data_root, project=None, project_dir=None)
    _run_export(runner, _make_job("book1"))

    labels = _recognition_labels(data_root, "book1")
    assert sorted(labels.values()) == ["dog", "legacy"]


# ── Acceptance: store head wins over a stale legacy envelope ───────────────────


@pytest.mark.integration
def test_export_store_head_wins_over_legacy_file(tmp_path: Path) -> None:
    """When BOTH a store head and a legacy envelope exist for the same page,
    the store head (what Save wrote) is exported — the legacy file is stale."""
    project_dir = tmp_path / "book1"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_real_png(project_dir / "001.png")

    project = _make_project(project_dir)
    _seed_store_saved_page(project_dir, project, gt_text="store-gt")
    _plant_legacy_envelope(data_root, "book1", 0, gt_text="stale-gt")

    runner, store = _make_runner(data_root=data_root, project=project, project_dir=project_dir)
    try:
        _run_export(runner, _make_job("book1"))
    finally:
        if store is not None:
            store.close()

    labels = _recognition_labels(data_root, "book1")
    values = sorted(labels.values())
    assert "store-gt" in values, f"store head content not exported: {values}"
    assert "stale-gt" not in values, f"stale legacy envelope was exported over the store head: {values}"


# ── Acceptance: style endpoint lists real styles from the store (C37) ──────────


def _make_settings(tmp_path: Path, *, projects_root: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


@pytest.mark.integration
def test_export_styles_endpoint_reads_store(tmp_path: Path) -> None:
    """GET /export/styles must list styles found in store-saved validated pages."""
    projects_root = tmp_path / "projects"
    project_dir = projects_root / "book1"
    _write_real_png(project_dir / "001.png")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(project_dir)})
        assert resp.status_code == 200, f"load failed: {resp.text}"

        live_store = app.state.page_store
        assert live_store is not None

        # Seed THROUGH the live store (the one the route reads).
        page = _make_page()
        project = app.state.project_state.loaded_project
        agg = _ingest_ocr_result(
            page=page,
            image_bytes=(project_dir / "001.png").read_bytes(),
            page_index=0,
            store=live_store,
            project=project,
        )
        loaded = load_page_from_store(live_store, agg.record.page_id)
        assert loaded is not None
        for w in loaded.words:
            w.word_labels.append("validated")
        loaded.words[0].text_style_labels.append("italics")
        loaded.words[1].text_style_labels.append("small caps")
        save_page_content_to_store(page_id=agg.record.page_id, page=loaded, store=live_store)

        resp = client.get("/api/projects/book1/export/styles")
        assert resp.status_code == 200
        assert resp.json() == ["italics", "small caps"], (
            f"style endpoint must surface store-saved styles, got {resp.json()}"
        )


# ── Acceptance: canonical cancel route (C40 backend half) ──────────────────────


@pytest.mark.integration
def test_cancel_route_is_canonical_jobs_cancel(tmp_path: Path) -> None:
    """``POST /api/jobs/{id}/cancel`` is the canonical cancel route (200 while
    the job is live, 409 if it already finished — never 404/405)."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as client:
        resp = client.post(
            "/api/projects/book1/export",
            json={"scope": "all_validated"},
        )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]

        cancel = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancel.status_code in (200, 409), (
            f"canonical cancel route regressed: {cancel.status_code} {cancel.text}"
        )

        # The project-scoped variant the old frontend posted to must NOT exist.
        wrong = client.post(f"/api/projects/book1/jobs/{job_id}/cancel")
        assert wrong.status_code in (404, 405), (
            "project-scoped cancel route unexpectedly exists — frontend must use /api/jobs/{id}/cancel"
        )
