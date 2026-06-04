"""M0.2 live-path gate: edits reload through ``ensure_page_model`` after a restart.

The existing ``test_label_roundtrip`` proves the *helper* (``load_page_from_store``)
round-trips edited content. But nothing exercised the **live page-load path** that a
fresh process actually walks: ``core.page_state.ensure_page_model`` →
``loader.load_labeled`` → fall-through to ``run_ocr``.

At base ``760005d`` that path was broken end-to-end:
``LocalDoctrPageLoader.load_labeled`` was a hard ``return None`` stub, so a fresh
process ALWAYS fell through to ``run_ocr`` and re-OCR'd the page — silently
discarding every stored edit. The OCR write path also never registered the page
into a ``ProjectAggregate``, so there was no index→page_id map to resolve from.

This test is the one M0.2 should have been: it drives ``ensure_page_model``
(not the helper directly) over a fresh store and asserts both that the EDITED
content comes back AND that ``run_ocr`` was never called (proving the data came
from the event store, not a re-OCR).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    LocalDoctrPageLoader,
    _ingest_ocr_result,
    _project_uuid_for,
)
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import (
    PageSource,
    ensure_page_model,
    save_page_content_to_store,
)
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState

# ── Real book-tools Page builders ──────────────────────────────────────────────


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
    return {"type": "Block", "child_type": "WORDS", "items": words, "bounding_box": _bbox(0, 0, 100, 20)}


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


def _make_project(project_dir: Path, project_id: str = "book1") -> Project:
    return Project(
        project_id=project_id,
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )


class _ExplodingLoader(LocalDoctrPageLoader):
    """LocalDoctrPageLoader whose ``run_ocr`` records calls and refuses to run.

    Used to prove the restart read came from the event store: if
    ``load_labeled`` resolves the stored edits, ``run_ocr`` must never fire.
    """

    run_ocr_calls: int = 0

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> Any:
        type(self).run_ocr_calls += 1
        raise AssertionError(
            f"run_ocr was called for page {page_index} on the restart read path — "
            "edits should have been reloaded from the event store, not re-OCR'd."
        )


def _fresh_loader(project: Project, store: LabelerPageStore) -> _ExplodingLoader:
    from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache

    return _ExplodingLoader(
        project=project,
        predictor_cache=PredictorCache(),
        detection_key="det",
        recognition_key="rec",
        hf_revision=None,
        store=store,
    )


# ── Acceptance test (M0.2 live path) ────────────────────────────────────────────


@pytest.mark.integration
def test_edits_reload_via_ensure_page_model_after_restart(tmp_path: Path) -> None:
    """A fresh process loading page 0 must see stored edits, not a re-OCR.

    Steps:
    1. OCR page 0 via ``_ingest_ocr_result`` — this writes the PageAggregate
       AND must register index 0 → page_id in the ProjectAggregate (step A).
    2. Edit the page (GT correction + 'validated' label) and persist content.
    3. Simulate a restart: FRESH store + FRESH loader + FRESH ProjectState over
       the SAME on-disk events.db/blobs.
    4. ``ensure_page_model`` (the live path) must resolve the stored, edited
       page WITHOUT calling ``run_ocr``.
    """
    _ExplodingLoader.run_ocr_calls = 0
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    # ── Phase 1: OCR write (populate store + project aggregate) ──
    store = LabelerPageStore(project_dir=project_dir)
    try:
        page = _make_page()
        project = _make_project(project_dir)
        agg = _ingest_ocr_result(
            page=page,
            image_bytes=b"\x89PNG\r\n fake png bytes",
            page_index=0,
            store=store,
            project=project,
        )
        page_id = agg.record.page_id

        # ── Phase 2: edit + persist content ──
        # Reload through the store so we edit the same content the app would.
        from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store

        loaded = load_page_from_store(store, page_id)
        assert loaded is not None
        word = loaded.lines[0].words[0]
        word.ground_truth_text = "the"
        word.word_labels.append("validated")
        save_page_content_to_store(page_id=page_id, page=loaded, store=store)
    finally:
        store.close()

    # ── Phase 3: simulate restart (fresh everything over same on-disk data) ──
    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        fresh_project = _make_project(project_dir)
        fresh_state = ProjectState()
        fresh_state.set_loaded_project(fresh_project)
        loader = _fresh_loader(fresh_project, reopened)

        # ── Phase 4: live path must reload stored edits, NOT re-OCR ──
        outcome = ensure_page_model(fresh_state, 0, loader=loader)

        assert _ExplodingLoader.run_ocr_calls == 0, (
            "run_ocr was called on the restart read path — the stub load_labeled "
            "fell through to a re-OCR instead of reading the event store."
        )
        assert outcome is not None, "ensure_page_model returned None on restart read"
        assert outcome.source == PageSource.FILESYSTEM, (
            f"expected the reload to be sourced from the event store (FILESYSTEM), got {outcome.source!r}"
        )

        reloaded_page = outcome.payload
        assert isinstance(reloaded_page, Page), (
            f"ensure_page_model payload must be a Page reconstructed from the "
            f"store, got {type(reloaded_page)!r}"
        )
        w = reloaded_page.lines[0].words[0]
        assert w.ground_truth_text == "the", (
            f"GT correction not reloaded on restart: got {w.ground_truth_text!r}"
        )
        assert "validated" in w.word_labels, (
            f"'validated' label not reloaded on restart: word_labels={w.word_labels!r}"
        )

        # The page_id must be stamped so subsequent edits target the same aggregate.
        assert getattr(reloaded_page, "_labeler_page_id", None) == page_id, (
            "reloaded Page is missing the _labeler_page_id stamp needed for subsequent event-store mutations"
        )
    finally:
        reopened.close()


@pytest.mark.integration
def test_ingest_ocr_registers_page_in_project_aggregate(tmp_path: Path) -> None:
    """_ingest_ocr_result must build the index→page_id map in the ProjectAggregate.

    Without this, a fresh ``load_labeled`` has no way to resolve which page_id
    sits at page_index 0.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    store = LabelerPageStore(project_dir=project_dir)
    try:
        project = _make_project(project_dir, project_id="book1")
        agg = _ingest_ocr_result(
            page=_make_page(),
            image_bytes=b"img",
            page_index=0,
            store=store,
            project=project,
        )
        proj_uuid = _project_uuid_for("book1")
        proj_agg = store.get_project(proj_uuid)
        assert agg.record.page_id in proj_agg.record.page_ids
        # page at index 0 resolves to the page we just wrote
        assert proj_agg.record.page_ids[0] == agg.record.page_id
    finally:
        store.close()


def test_project_uuid_is_deterministic() -> None:
    """The project-id→UUID mapping must be stable across processes (uuid5)."""
    from uuid import UUID

    a = _project_uuid_for("book1")
    b = _project_uuid_for("book1")
    assert a == b
    assert isinstance(a, UUID)
    assert _project_uuid_for("book1") != _project_uuid_for("book2")


@pytest.mark.integration
def test_ingest_ocr_idempotent_on_reocr(tmp_path: Path) -> None:
    """Re-OCR of the same index must not duplicate or corrupt the project map.

    The page at a given index is replaced (the project's slot points at the new
    page_id), not appended twice.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    store = LabelerPageStore(project_dir=project_dir)
    try:
        project = _make_project(project_dir, project_id="book1")
        agg1 = _ingest_ocr_result(
            page=_make_page(), image_bytes=b"a", page_index=0, store=store, project=project
        )
        agg2 = _ingest_ocr_result(
            page=_make_page(), image_bytes=b"b", page_index=0, store=store, project=project
        )
        proj_agg = store.get_project(_project_uuid_for("book1"))
        # index 0 now points at the second OCR result; no duplicate slot.
        assert len(proj_agg.record.page_ids) == 1
        assert proj_agg.record.page_ids[0] == agg2.record.page_id
        assert agg1.record.page_id != agg2.record.page_id
    finally:
        store.close()
