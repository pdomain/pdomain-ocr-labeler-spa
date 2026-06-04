"""Integration: forced re-OCR must update pstate.page_id so post-re-OCR edits persist.

Finding F investigation result: R2 is CORRECT.

Page.page_id is a random uuid4 per Page instance
(pdomain_book_tools/ocr/page.py:103 — `page_id: UUID = field(default_factory=uuid4)`).
Every call to run_ocr produces a new Page with a fresh UUID.  _ingest_ocr_result
uses page.page_id as the PageAggregate id and also updates
ProjectAggregate.page_ids[index] to point at the new id.

BUT both ensure_page_model (core/page_state.py:251) and the reload_ocr handler
(core/jobs/handlers/reload_ocr.py:272) guarded the page_id stamp with:

    if labeler_page_id is not None and existing.page_id is None:
        existing.page_id = labeler_page_id

After the FIRST OCR existing.page_id was set (non-None), so a FORCED re-OCR's new
page_id was never stamped on pstate.  Post-re-OCR edits were saved onto the OLD
(now-superseded) PageAggregate.  After restart, load_labeled resolves the NEW
page_id from the ProjectAggregate and found no labeled blob there — it fell
through to re-OCR, and the post-re-OCR edits (saved on first_page_id) were lost.

The actual data loss manifest: the restart reload returns the UNEDITED second-OCR
content (from the new page_id's fresh OCR blob) rather than the post-re-OCR edited
content (which was written to the stale first_page_id by save_page_content_to_store).

TDD protocol — the test drives the REAL ``ensure_page_model`` guard (it does
NOT hand-stamp ``PageState.page_id``):
  RED  — with the broken ``and existing.page_id is None`` guard restored,
         ``ensure_page_model(..., force_ocr=True)`` leaves ``pstate.page_id`` at
         the stale first_page_id; the Phase-2 assertion
         ``pstate.page_id == new_page_id`` fails.
  GREEN — after fix (always stamp page_id from the latest OCR result, removing
          the "if None" guard): ``pstate.page_id`` is refreshed to new_page_id,
          edits are saved to the correct aggregate, and survive restart.

Files changed by the fix:
  - src/pdomain_ocr_labeler_spa/core/page_state.py (ensure_page_model)
  - src/pdomain_ocr_labeler_spa/core/jobs/handlers/reload_ocr.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    LocalDoctrPageLoader,
    _ingest_ocr_result,
    _project_uuid_for,
)
from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.core.models import PageSource, Project
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pdomain_ocr_labeler_spa.core.page_state import (
    PageLoadOutcome,
    ensure_page_model,
    save_page_content_to_store,
)
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

# ── Shared builders ────────────────────────────────────────────────────────────


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
        "items": [_para([_line([_word("teh"), _word("cat")])])],
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
    """LocalDoctrPageLoader whose run_ocr raises — proves reload came from event store."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.run_ocr_calls: int = 0

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> Any:
        self.run_ocr_calls += 1
        raise AssertionError(
            f"run_ocr called on restart read for page {page_index} — "
            "post-re-OCR edits were not persisted onto the correct page_id."
        )


class _ReocrLoader(LocalDoctrPageLoader):
    """LocalDoctrPageLoader whose ``run_ocr`` runs the REAL event-store ingest path.

    This is deliberately *not* a hand-rolled pstate stamp.  It mirrors the
    store-side of the production ``LocalDoctrPageLoader.run_ocr``
    (``adapters/ocr/local_doctr.py:502-522``) verbatim — call the real
    ``_ingest_ocr_result`` (which assigns a fresh ``page_id`` to a new
    ``PageAggregate`` AND advances ``ProjectAggregate.page_ids[index]``), then
    ``object.__setattr__(page, "_labeler_page_id", agg.record.page_id)`` — but
    skips the torch/doctr image-OCR machinery that the production method runs
    first.  The fresh ``Page`` is supplied by the test (a real ``Page`` with a
    fresh uuid4 ``page_id``), standing in for what doctr would have produced.

    Crucially, this loader does **not** touch ``PageState.page_id``.  That stamp
    is left entirely to the guard inside the real ``ensure_page_model``
    (``core/page_state.py:255``) — which is the code under test.
    """

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.run_ocr_calls: int = 0
        self.last_page_id: UUID | None = None

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> PageLoadOutcome:
        self.run_ocr_calls += 1
        # Real ingest: new PageAggregate (fresh uuid4 page_id) + ProjectAggregate
        # page_ids[index] update. Mirrors local_doctr.run_ocr's store branch.
        fresh_page = _make_page()
        assert self.store is not None
        agg = _ingest_ocr_result(
            page=fresh_page,
            image_bytes=b"reocr-bytes",
            page_index=page_index,
            store=self.store,
            project=self.project,
        )
        object.__setattr__(fresh_page, "_labeler_page_id", agg.record.page_id)
        self.last_page_id = agg.record.page_id
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=fresh_page)


# ── Prerequisite: confirm re-OCR produces a distinct page_id ──────────────────


@pytest.mark.integration
def test_reocr_produces_new_page_id(tmp_path: Path) -> None:
    """_ingest_ocr_result for the same index twice yields distinct page_ids.

    This is the root-cause invariant: Page.page_id is uuid4 (random), so
    each OCR run creates a new PageAggregate under a different id.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    store = LabelerPageStore(project_dir=project_dir)
    try:
        project = _make_project(project_dir)
        agg1 = _ingest_ocr_result(
            page=_make_page(), image_bytes=b"a", page_index=0, store=store, project=project
        )
        agg2 = _ingest_ocr_result(
            page=_make_page(), image_bytes=b"b", page_index=0, store=store, project=project
        )
        assert agg1.record.page_id != agg2.record.page_id, (
            "re-OCR must produce a new page_id (Page.page_id is uuid4); "
            "if this fails, Finding F's root-cause assumption is wrong."
        )
        proj_agg = store.get_project(_project_uuid_for("book1"))
        assert proj_agg.record.page_ids[0] == agg2.record.page_id, (
            "ProjectAggregate.page_ids[0] must be updated to the new page_id after re-OCR."
        )
    finally:
        store.close()


# ── Main finding ───────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_post_reocr_edits_persist_after_fix(tmp_path: Path) -> None:
    """After the fix, post-re-OCR edits must survive a restart reload.

    This drives the REAL ``ensure_page_model`` guard
    (``core/page_state.py:255``).  The test loader's ``run_ocr`` only mirrors
    the production loader's *store-side* ingest (real ``_ingest_ocr_result`` +
    ``_labeler_page_id`` stamp on the ``Page``); it does **not** touch
    ``PageState.page_id``.  Whether ``pstate.page_id`` is refreshed to the new
    page_id is decided entirely by the guard inside ``ensure_page_model`` — so
    this test exercises the fix instead of bypassing it.

    Phase 2 directly asserts the guard's effect:
        ensure_page_model(..., force_ocr=True) → pstate.page_id == new_page_id
    With the broken ``and existing.page_id is None`` guard restored, pstate
    already holds first_page_id (non-None), so the stamp is skipped and the
    assertion fails (RED).  With the fix (unconditional stamp), it passes
    (GREEN).

    Phase 3-5 then prove the downstream consequence: the post-re-OCR edit is
    saved to whichever page_id pstate now holds.  Under the fix that is
    new_page_id, which is what ``load_labeled`` resolves on restart, so the
    edit survives; run_ocr is never called on the restart read.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    store = LabelerPageStore(project_dir=project_dir)
    try:
        project = _make_project(project_dir)

        # Phase 1: initial OCR — wire pstate with first_page_id (non-None), the
        # precondition that makes the "if None" guard the thing under test.
        agg1 = _ingest_ocr_result(
            page=_make_page(), image_bytes=b"first-ocr", page_index=0, store=store, project=project
        )
        first_page_id: UUID = agg1.record.page_id
        project_state = ProjectState()
        project_state.set_loaded_project(project)
        initial_loaded = load_page_from_store(store, first_page_id)
        assert initial_loaded is not None
        initial_outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=initial_loaded)
        pstate = PageState(page_index=0, page_record=initial_outcome)
        pstate.page_id = first_page_id
        pstate.generation = 1
        project_state._page_states[0] = pstate

        # Phase 2: forced re-OCR through the REAL ensure_page_model guard.
        # The loader's run_ocr ingests a new aggregate (new page_id) but leaves
        # pstate.page_id alone; only the guard inside ensure_page_model can
        # update it.
        reocr_loader = _ReocrLoader(
            project=project,
            predictor_cache=PredictorCache(),
            detection_key="det",
            recognition_key="rec",
            hf_revision=None,
            store=store,
        )
        reocr_outcome = ensure_page_model(project_state, 0, loader=reocr_loader, force_ocr=True)
        assert reocr_loader.run_ocr_calls == 1, "forced re-OCR must call run_ocr exactly once"
        assert reocr_outcome is not None
        new_page_id = reocr_loader.last_page_id
        assert new_page_id is not None
        assert first_page_id != new_page_id, "re-OCR must produce a new page_id"

        # The guard under test: ensure_page_model must refresh pstate.page_id to
        # the NEW page_id even though it was already set to first_page_id.
        # RED (broken guard): pstate.page_id stays first_page_id → this fails.
        # GREEN (fix): pstate.page_id == new_page_id.
        assert pstate.page_id == new_page_id, (
            "ensure_page_model did not refresh pstate.page_id after forced re-OCR "
            f"(got {pstate.page_id}, expected {new_page_id}). "
            "The stale 'if existing.page_id is None' guard skipped the stamp."
        )

        # Phase 3: edit the post-re-OCR page and save to store using whatever
        # page_id pstate now holds (the route layer would use pstate.page_id).
        post_reocr_page = pstate.page_record.payload  # type: ignore[union-attr]
        word = post_reocr_page.lines[0].words[0]
        word.ground_truth_text = "after_reocr"
        word.word_labels.append("validated")
        save_page_content_to_store(
            page_id=pstate.page_id,
            page=post_reocr_page,
            store=store,
        )
    finally:
        store.close()

    # Phase 4: restart — fresh store + fresh state.
    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        fresh_project = _make_project(project_dir)
        fresh_state = ProjectState()
        fresh_state.set_loaded_project(fresh_project)
        fresh_loader = _ExplodingLoader(
            project=fresh_project,
            predictor_cache=PredictorCache(),
            detection_key="det",
            recognition_key="rec",
            hf_revision=None,
            store=reopened,
        )

        # Phase 5: live restart path must return post-re-OCR edited content.
        outcome = ensure_page_model(fresh_state, 0, loader=fresh_loader)

        assert fresh_loader.run_ocr_calls == 0, (
            "run_ocr called on restart — edits were not persisted to the correct page_id."
        )
        assert outcome is not None, "ensure_page_model returned None on restart"
        assert outcome.source == PageSource.FILESYSTEM, (
            f"expected FILESYSTEM (event store), got {outcome.source!r}"
        )
        w = outcome.payload.lines[0].words[0]  # type: ignore[union-attr]
        assert w.ground_truth_text == "after_reocr", (
            f"post-re-OCR GT edit lost on restart: expected 'after_reocr', got {w.ground_truth_text!r}. "
            "Likely cause: pstate.page_id was not updated after re-OCR (stale 'if None' guard)."
        )
        assert "validated" in w.word_labels, (
            f"'validated' label lost on restart: word_labels={w.word_labels!r}"
        )
    finally:
        reopened.close()
