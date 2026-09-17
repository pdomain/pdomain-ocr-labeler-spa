"""Unit tests for the propose_regions handler's measurement pass."""

from __future__ import annotations

from typing import Any


def test_the_handler_hands_the_detector_one_input_per_eligible_page(
    proposal_run_ready: Any,
) -> None:
    """The detector sees the page, its index, its classification, and the book.

    ``proposal_run_ready`` is defined in this file's sibling conftest and yields
    ``(runner, job, project_state)`` with two pages loaded, both carrying a
    confirmed page kind, and a stub measure function wired into
    ``runner.context``.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    runner, job, _project_state = proposal_run_ready
    seen: list[DetectorInput] = []

    def _recording_detector(detector_input: DetectorInput) -> list[Any]:
        seen.append(detector_input)
        return []

    runner.context["region_detector"] = _recording_detector
    asyncio.run(handle_propose_regions(runner, job))

    assert [d.page_index for d in seen] == [0, 1]
    assert all(d.classification is not None for d in seen)
    assert all(d.templates is not None for d in seen)
    assert all(d.measurement.page_name for d in seen)


def test_a_detected_region_becomes_a_proposal_in_the_journal(proposal_run_ready: Any) -> None:
    import asyncio

    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion, DetectorInput
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    runner, job, project_state = proposal_run_ready

    def _one_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
        del detector_input
        return [
            DetectedRegion(
                role=RegionRole.PAGE_HEADER,
                box=(10, 20, 190, 40),
                confidence=0.75,
                evidence={"signal": "test"},
            )
        ]

    runner.context["region_detector"] = _one_region_detector
    asyncio.run(handle_propose_regions(runner, job))

    project = project_state.loaded_project
    assert project is not None
    log = RegionProposalLog(project.project_root)
    runs = log.runs()
    assert len(runs) == 1
    # RegionProposalLog exposes proposals_for_page, not proposals_for_run —
    # the run-scoped accessor is PageKindProposalLog's, a different class.
    proposals = [p for idx in (0, 1) for p in log.proposals_for_page(idx, run_id=runs[0].run_id)]
    assert len(proposals) == 2
    assert {p.page_index for p in proposals} == {0, 1}
    assert all(p.role is RegionRole.PAGE_HEADER for p in proposals)
    assert all(p.confidence == 0.75 for p in proposals)
