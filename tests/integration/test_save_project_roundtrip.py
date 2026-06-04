"""Integration: save_project handler must persist page content so a fresh store returns
edited data.

Regression test for the empty-blob-ref head bug: ``save_project`` called
``save_page_to_store`` (no content blob), which advanced the aggregate's provenance
head to a node with no ``blob_refs``. A subsequent fresh-store ``load_page_from_store``
then returned ``None`` because the head had no blob to read — every edit was silently
lost on reload.

This test proves the fix: ``save_project`` must call ``save_page_content_to_store``
so the edited ``Page`` is re-serialized into the blob store and the provenance head
points to it.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord, ProvenanceGraph, ProvenanceNode

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _seed_ocr_page(store: LabelerPageStore, page: Page) -> UUID:
    """Persist page as a fresh OCR aggregate (content blob + head provenance)."""
    page_id = uuid4()
    content_hash = store.blobs.write(json.dumps(page.to_dict()).encode("utf-8"))
    node = ProvenanceNode(id=f"ocr-{page_id}", source="ocr", tool="doctr", blob_refs=[content_hash])
    graph = ProvenanceGraph(nodes={node.id: node}, head_id=node.id, history=[node.id])
    record = PageRecord(page_id=page_id, page_index=0, source="ocr", provenance=graph)
    store.save_page(PageAggregate(record))
    return page_id


def _make_fake_project(project_dir: Path, project_id: str = "test-project") -> Any:
    """Return a minimal Project-like object sufficient for the handler."""
    from pdomain_ocr_labeler_spa.core.models import Project

    return Project(
        project_id=project_id,
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )


def _make_job() -> Job:
    return Job(
        job_id=uuid4().hex,
        job_type="save_project",
        status=JobStatus.QUEUED,
        created_at=datetime.now(UTC),
    )


async def _run_save_project(runner: JobRunner, job: Job) -> None:
    from pdomain_ocr_labeler_spa.core.jobs.handlers.save_project import handle_save_project

    await handle_save_project(runner, job)


# ── Acceptance test ───────────────────────────────────────────────────────────


@pytest.mark.integration
def test_save_project_persists_page_content_for_fresh_store_reload(tmp_path: Path) -> None:
    """Save Project must write a content blob so a fresh store can reload edits.

    RED: before the fix, save_project called save_page_to_store (no blob), so
    load_page_from_store returned None after reopening the store.

    GREEN: after the fix, save_project calls save_page_content_to_store which
    serializes the live Page to a blob, so a fresh store returns the edited content.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    store = LabelerPageStore(project_dir=project_dir)
    try:
        # 1. Seed original page as OCR would write it.
        original_page = _make_page()
        page_id = _seed_ocr_page(store, original_page)

        # 2. Load it back through the store (as the app would on first access).
        loaded_page = load_page_from_store(store, page_id)
        assert loaded_page is not None, "seed failed: could not load page from fresh store"

        # 3. Apply an edit (GT correction + validated label).
        word = loaded_page.lines[0].words[0]
        original_text = word.ground_truth_text
        word.ground_truth_text = "the"
        word.word_labels.append("validated")

        # 4. Wire up a ProjectState / PageState the way the running app would.
        project_state = ProjectState()
        project = _make_fake_project(project_dir)
        project_state.set_loaded_project(project)

        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=loaded_page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        # Mark the page dirty (generation > last_saved_generation).
        pstate.generation = 1
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        # 5. Build a minimal JobRunner with the required context.
        broker = JobEventBroker()
        notification_queue = NotificationQueue()
        # settings only needs to not be None — the handler checks ``settings is None``
        settings = object()
        runner = JobRunner(
            broker,
            context={
                "project_state": project_state,
                "notification_queue": notification_queue,
                "settings": settings,
                "page_store": store,
            },
        )

        job = _make_job()
        runner._jobs[job.job_id] = job

        # 6. Run the save_project handler.
        asyncio.run(_run_save_project(runner, job))

    finally:
        store.close()

    # 7. Open a FRESH store over the same on-disk events.db.
    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        reloaded = load_page_from_store(reopened, page_id)

        # Without the fix: reloaded is None (head blob_refs is empty).
        assert reloaded is not None, (
            "save_project did not persist page content: fresh store returned None. "
            "Edits (GT correction, 'validated' label) were silently lost."
        )

        w = reloaded.lines[0].words[0]
        assert w.ground_truth_text == "the", (
            f"GT correction not persisted: expected 'the', got {w.ground_truth_text!r} "
            f"(was originally {original_text!r})"
        )
        assert "validated" in w.word_labels, f"'validated' label not persisted: word_labels={w.word_labels!r}"
    finally:
        reopened.close()
