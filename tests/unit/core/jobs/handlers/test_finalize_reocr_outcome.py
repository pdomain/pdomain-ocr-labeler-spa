"""Unit tests for ``_finalize_reocr_outcome``'s project-pin guard.

Shared by ``reload_ocr``, ``rotate_page``, ``auto_rotate_all`` and
``load_page`` (each imports it from ``core/jobs/handlers/reload_ocr.py``) to
swap a freshly-run OCR outcome into ``ProjectState``. All four run OCR on a
worker thread with no project lock held, so a concurrent ``POST
.../projects/load`` can swap ``ProjectState.loaded_project`` to a different
book before the outcome comes back. Without a pin check, the write is keyed
by page index alone — ``project_state._page_states[page_index]`` — so a job
started against the OLD project lands its result in the NEWLY loaded
project's ``page_states`` at the same index. This mirrors the pin re-check
``propose_regions`` already does in its own lazy-load loop
(``_project_still_pinned`` / ``_refuse_project_changed`` in
``core/jobs/handlers/propose_regions.py``), applied here at the single
shared write site instead of a per-caller re-check.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from pdomain_ocr_labeler_spa.core.jobs.handlers.reload_ocr import _finalize_reocr_outcome
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import ProjectState

if TYPE_CHECKING:
    from pathlib import Path


def _make_project(tmp_path: Path, project_id: str) -> Project:
    root = tmp_path / project_id
    root.mkdir()
    return Project(
        project_id=project_id,
        project_root=root,
        image_paths=[root / "000.png"],
        ground_truth_map={},
        total_pages=1,
    )


def test_drops_the_outcome_when_the_loaded_project_has_changed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``load_page``/``reload_ocr``/rotate job started against project A,
    whose OCR outcome comes back after a ``POST .../load`` swapped in
    project B, must not write into project B's ``page_states`` at the same
    index."""
    project_state = ProjectState()
    project_state.set_loaded_project(_make_project(tmp_path, "book-a"))
    # A project load landed while OCR was in flight, off the project lock.
    project_state.set_loaded_project(_make_project(tmp_path, "book-b"))

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=SimpleNamespace())

    with caplog.at_level(logging.WARNING):
        _finalize_reocr_outcome(
            project_state,
            0,
            outcome,
            page_kind_sent=None,
            page_store=None,
            expected_project_id="book-a",
        )

    pstate = project_state.page_states.get(0)
    assert pstate is None or pstate.page_record is None, (
        "book-a's outcome must not have been written into book-b's page_states"
    )
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING logged for the dropped outcome"
    message = warnings[0].getMessage()
    assert "book-a" in message
    assert "book-b" in message


def test_drops_the_outcome_when_no_project_is_loaded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project can also be unloaded entirely (``clear()``) while OCR runs."""
    project_state = ProjectState()
    project_state.set_loaded_project(_make_project(tmp_path, "book-a"))
    project_state.clear()

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=SimpleNamespace())

    with caplog.at_level(logging.WARNING):
        _finalize_reocr_outcome(
            project_state,
            0,
            outcome,
            page_kind_sent=None,
            page_store=None,
            expected_project_id="book-a",
        )

    assert project_state.page_states.get(0) is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING logged for the dropped outcome"


def test_writes_the_outcome_when_the_project_still_matches(tmp_path: Path) -> None:
    """The common case: no swap happened — the outcome is written normally."""
    project_state = ProjectState()
    project_state.set_loaded_project(_make_project(tmp_path, "book-a"))

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=SimpleNamespace())

    _finalize_reocr_outcome(
        project_state,
        0,
        outcome,
        page_kind_sent=None,
        page_store=None,
        expected_project_id="book-a",
    )

    pstate = project_state.page_states.get(0)
    assert pstate is not None
    assert pstate.page_record is outcome
