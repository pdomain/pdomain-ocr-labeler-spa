"""Unit tests for the propose_regions handler's measurement pass."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion, DetectorInput, RegionDetector


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
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion
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


def test_progress_never_goes_backwards_across_the_two_phases(proposal_run_ready: Any) -> None:
    """A run measures the whole book, then detects over the eligible pages.

    The two phases have different page counts. Reporting each against its own
    denominator made ``progress_total`` change mid-run and ``progress_current``
    reset to zero, so a progress bar went backwards. No single task's review
    could see it: one commit added the measurement phase and another the
    detection phase.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions

    runner, job, _project_state = proposal_run_ready
    seen: list[tuple[int, int]] = []
    original = runner.update_progress

    async def _record(job_id: str, *, current: int, total: int, message: str = "") -> None:
        seen.append((current, total))
        await original(job_id, current=current, total=total, message=message)

    runner.update_progress = _record  # type: ignore[method-assign]
    try:
        asyncio.run(handle_propose_regions(runner, job))
    finally:
        runner.update_progress = original  # type: ignore[method-assign]

    assert seen, "the run reported no progress at all"
    totals = {total for _current, total in seen}
    assert len(totals) == 1, f"progress_total changed mid-run: {sorted(totals)}"
    currents = [current for current, _total in seen]
    assert currents == sorted(currents), f"progress_current went backwards: {currents}"
    assert currents[-1] == totals.pop(), "the run did not finish at its own total"


def test_a_book_fitted_detector_gets_fit_called_once_with_one_input_per_page(
    proposal_run_ready: Any,
) -> None:
    """``BookFittedDetector.fit`` sees the whole book exactly once, before any page is judged."""
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.detector import (
        BookFittedDetector,
    )

    runner, job, _project_state = proposal_run_ready

    fit_calls: list[Sequence[DetectorInput]] = []
    judged: list[DetectorInput] = []

    class _RecordingBookFittedDetector(BookFittedDetector):
        def fit(self, book: Sequence[DetectorInput]) -> RegionDetector:
            fit_calls.append(book)

            def _detect(detector_input: DetectorInput) -> list[DetectedRegion]:
                judged.append(detector_input)
                return []

            return _detect

    detector = _RecordingBookFittedDetector()
    assert isinstance(detector, BookFittedDetector)
    runner.context["region_detector"] = detector
    asyncio.run(handle_propose_regions(runner, job))

    assert len(fit_calls) == 1, "fit must run exactly once per run"
    assert [d.page_index for d in fit_calls[0]] == [0, 1]
    assert [d.page_index for d in judged] == [0, 1]


def test_a_plain_callable_detector_is_called_directly_with_no_fit(proposal_run_ready: Any) -> None:
    """A plain ``RegionDetector`` callable — no ``fit`` — is unaffected by the book-fit seam."""
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.detector import (
        BookFittedDetector,
    )

    runner, job, _project_state = proposal_run_ready
    seen: list[DetectorInput] = []

    def _plain_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
        seen.append(detector_input)
        return []

    assert not isinstance(_plain_detector, BookFittedDetector)
    runner.context["region_detector"] = _plain_detector
    asyncio.run(handle_propose_regions(runner, job))

    assert [d.page_index for d in seen] == [0, 1]


def test_an_object_with_an_unrelated_fit_method_is_not_a_book_fitted_detector(
    proposal_run_ready: Any,
) -> None:
    """Only a subclass of BookFittedDetector takes the book-fit path.

    ``fit`` is the most common method name in machine learning. A callable
    detector that happens to wrap something with ``fit(X, y)`` must be called
    per page as a plain detector, never routed into the book-fit branch, where
    calling its unrelated ``fit`` would fail and the run would propose nothing.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.detector import (
        BookFittedDetector,
    )

    runner, job, _project_state = proposal_run_ready
    judged: list[DetectorInput] = []
    unrelated_fit_calls: list[object] = []

    class _ModelBackedDetector:
        def fit(self, features: object, labels: object) -> None:
            unrelated_fit_calls.append((features, labels))

        def __call__(self, detector_input: DetectorInput) -> list[DetectedRegion]:
            judged.append(detector_input)
            return []

    detector = _ModelBackedDetector()
    assert not isinstance(detector, BookFittedDetector)
    runner.context["region_detector"] = detector
    asyncio.run(handle_propose_regions(runner, job))

    assert unrelated_fit_calls == []
    assert [d.page_index for d in judged] == [0, 1]
