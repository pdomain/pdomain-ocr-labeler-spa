"""A ``propose_regions`` run with the poetry detector wired: correct
provenance in the journal, and the proposal visible through the real
review-queue route.

Mirrors ``test_region_proposal_run_end_to_end.py``'s pattern (``toolbar_loaded``,
a hand-built ``Page``, a job run through ``handle_propose_regions`` directly)
but swaps in a real ``PoetryDetector`` over a genuinely verse-shaped page,
and a ``propose_regions_measure_fn`` stub that gives ``fit_book_templates`` /
``classify_pages`` (the real functions, not stubbed) enough geometry to fit a
usable ``normal_recto`` template — the poetry detector needs a real template
to measure indent and raggedness against, unlike the header/folio detector
tests, which can get away with an "unavailable" measurement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page
    from pdomain_pgdp_measure.profile_input import ProfileInputPage
    from pdomain_pgdp_measure.profile_models import PageMeasurement

_TEXT_LEFT_PX = 100
_TEXT_RIGHT_PX = 900
_PAGE_WIDTH = 1000
_PAGE_HEIGHT = 1600


def _bbox(left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "top_left": {"x": left, "y": top},
        "bottom_right": {"x": right, "y": bottom},
        "is_normalized": False,
    }


def _word(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(left, top, right, bottom),
    }


def _line(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": [_word(text, left, top, right, bottom)],
        "bounding_box": _bbox(left, top, right, bottom),
    }


def _poetry_page() -> Page:
    """One stanza: indented, ragged right edges, every line capitalized."""
    from pdomain_book_tools.ocr.page import Page

    lines = [
        _line("Roses Are Red,", 200, 100, 500, 125),
        _line("Violets Are Blue,", 200, 130, 650, 155),
        _line("Sugar Is Sweet,", 200, 160, 550, 185),
        _line("And So Are You.", 200, 190, 700, 215),
    ]
    paragraph = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(200, 100, 700, 215),
    }
    return Page.from_dict(
        {
            "width": _PAGE_WIDTH,
            "height": _PAGE_HEIGHT,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, _PAGE_WIDTH, _PAGE_HEIGHT),
            "items": [paragraph],
        }
    )


def _measure_fn(project_id: str, page: ProfileInputPage) -> PageMeasurement:
    """A real, decoded-looking measurement — not the "unavailable" stub the
    furniture-detector tests use — so ``fit_book_templates``/``classify_pages``
    (the real functions ``measure_book`` calls, unstubbed) fit a genuine
    ``normal_recto`` template with ``text_left_px=100``/``text_right_px=900``,
    the same numbers ``_poetry_page`` above was shaped against.
    """
    del project_id
    from pdomain_pgdp_measure.profile_models import CoordinateFrame, InkBand, PageMeasurement

    frame = CoordinateFrame(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    return PageMeasurement(
        page_name=page.name,
        source_path=page.source_path or f"book1/{page.name}",
        sha256="a" * 64,
        source_frame=frame,
        image_mode="L",
        grayscale_threshold=128,
        foreground_pixels=50_000,
        foreground_bounds=(_TEXT_LEFT_PX, 100, _TEXT_RIGHT_PX, 1500),
        margins=(_TEXT_LEFT_PX, 100, frame.width - _TEXT_RIGHT_PX, frame.height - 1500),
        ink_bands=(InkBand(100, 130),),
        page_class="normal_recto",
    )


def test_a_poetry_run_journals_a_proposal_with_provenance_and_the_queue_sees_it(
    toolbar_loaded: Any,
) -> None:
    import asyncio
    from datetime import UTC, datetime

    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.regions.models import (
        FACET_LINE_STRUCTURE,
        FACET_PAGE_IMAGE,
        FACET_WORD_BOXES,
        FACET_WORD_TEXT,
    )
    from pdomain_ocr_labeler_spa.core.regions.poetry import (
        POETRY_DETECTOR_MODEL_ID,
        POETRY_DETECTOR_MODEL_VERSION,
        PoetryDetector,
    )
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, project_state, _original_page = toolbar_loaded
    project = project_state.loaded_project
    assert project is not None

    # Swap the seeded page for a verse-shaped one, the same way the fixture
    # itself seeded page 0 — PageState is a plain mutable dataclass.
    pstate = project_state.page_states[0]
    pstate.page_record = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=_poetry_page())

    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    runner = client.app.state.job_runner
    runner.context["region_detector"] = PoetryDetector()
    runner.context["propose_regions_measure_fn"] = _measure_fn

    job = Job(
        job_id="poetry-e2e-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={
            "project_id": project.project_id,
            "model_id": POETRY_DETECTOR_MODEL_ID,
            "model_version": POETRY_DETECTOR_MODEL_VERSION,
        },
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))

    proposal_log = RegionProposalLog(project.project_root)
    runs = proposal_log.runs()
    assert len(runs) == 1
    run = runs[0]
    assert run.model_id == POETRY_DETECTOR_MODEL_ID
    assert run.model_version == POETRY_DETECTOR_MODEL_VERSION
    # Provenance: a text-reading detector's run must depend on word_text too,
    # or a text-only edit would never mark its own proposals stale.
    assert run.depends_on == frozenset(
        {FACET_WORD_BOXES, FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_TEXT}
    )
    assert 0 in run.page_facet_digests

    proposals = proposal_log.proposals()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.role is RegionRole.POETRY
    assert proposal.run_id == run.run_id
    assert proposal.evidence["decided_by"] == "text"

    # The review queue sees it, through the real route.
    response = client.get(f"/api/projects/{project.project_id}/regions/review-queue", params={"limit": 10})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_undecided"] == 1
    assert body["pages"][0]["page_index"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["role"] == "poetry"
    assert body["items"][0]["proposal_id"] == proposal.proposal_id
