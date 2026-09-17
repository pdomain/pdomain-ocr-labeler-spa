"""Unit tests for the propose_regions handler's measurement pass."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion, DetectorInput, RegionDetector


async def _collect_progress(runner: JobRunner, job: Job) -> list[tuple[int, int, str]]:
    """Run the handler, recording every ``update_progress`` call's (current, total, message)."""
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions

    seen: list[tuple[int, int, str]] = []
    original = runner.update_progress

    async def _record(
        job_id: str,
        *,
        current: int,
        total: int,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        seen.append((current, total, message))
        await original(job_id, current=current, total=total, message=message, result=result)

    runner.update_progress = _record  # type: ignore[method-assign]
    try:
        await handle_propose_regions(runner, job)
    finally:
        runner.update_progress = original  # type: ignore[method-assign]
    return seen


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


def test_the_summary_names_pages_skipped_for_no_page_kind(
    proposal_run_one_page_missing_kind: Any,
) -> None:
    """A page with no page-kind state is named in the run's final message, with the hint to fix it.

    ``proposal_run_one_page_missing_kind`` loads two pages but marks only page
    0 reviewed, so page 1 carries no page-kind state at all — the case a
    person hits by clicking "Propose regions" before "Propose page kinds".
    """
    import asyncio

    runner, job, _project_state = proposal_run_one_page_missing_kind
    seen = asyncio.run(_collect_progress(runner, job))

    assert seen, "the run reported no progress at all"
    _current, _total, final_message = seen[-1]
    assert "Skipped 1 page(s)" in final_message
    assert "Propose page kinds" in final_message


def test_the_summary_has_no_skip_clause_when_every_page_has_kind_state(
    proposal_run_ready: Any,
) -> None:
    """With no page skipped for a missing kind, the summary is just the proposal count."""
    import asyncio

    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion

    runner, job, _project_state = proposal_run_ready

    def _one_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
        del detector_input
        return [
            DetectedRegion(
                role=RegionRole.PAGE_HEADER,
                box=(10, 20, 190, 40),
                confidence=0.9,
                evidence={},
            )
        ]

    runner.context["region_detector"] = _one_region_detector
    seen = asyncio.run(_collect_progress(runner, job))

    _current, _total, final_message = seen[-1]
    assert final_message == "Proposed 2 region(s) on 2 page(s)."


def test_the_early_return_message_hints_at_propose_page_kinds(
    proposal_run_no_kind_state: Any,
) -> None:
    """Neither page carries page-kind state, so the run refuses before measuring anything."""
    import asyncio

    runner, job, _project_state = proposal_run_no_kind_state
    seen = asyncio.run(_collect_progress(runner, job))

    assert len(seen) == 1, "the early return should report exactly one progress update"
    _current, _total, message = seen[0]
    assert "Propose page kinds" in message


def test_the_final_progress_update_keeps_current_equal_to_the_combined_total(
    proposal_run_ready: Any,
) -> None:
    """The summary update must report against the same combined total as every prior update.

    See ``test_progress_never_goes_backwards_across_the_two_phases`` above:
    the two-phase run reports both phases against one ``combined_total``, and
    the handler's last update — now a summary message — must not reset or
    exceed it.
    """
    import asyncio

    runner, job, _project_state = proposal_run_ready
    seen = asyncio.run(_collect_progress(runner, job))

    final_current, final_total, _message = seen[-1]
    assert final_current == final_total
    assert final_total == seen[0][1], "total changed across the run"


def test_pages_not_in_memory_are_loaded_and_proposed_over_without_ocr(
    proposal_run_lazy_load: Any,
) -> None:
    """A book with no page in memory: the run loads the two pages with stored
    OCR content, proposes on them, and never calls ``run_ocr``.

    Regression test for a real-book bug: after a server restart (or on a book
    nobody has paged through), every page is absent from
    ``project_state.page_states``, and the handler used to see that as "no
    pages loaded" and do nothing.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions

    runner, job, project_state, loader = proposal_run_lazy_load
    seen: list[DetectorInput] = []

    def _recording_detector(detector_input: DetectorInput) -> list[Any]:
        seen.append(detector_input)
        return []

    runner.context["region_detector"] = _recording_detector
    asyncio.run(handle_propose_regions(runner, job))

    assert loader.run_ocr_calls == [], "propose_regions must never run OCR"
    assert [d.page_index for d in seen] == [0, 2]
    assert project_state.page_states[0].page_record is not None
    assert project_state.page_states[2].page_record is not None
    assert 1 not in project_state.page_states


def test_the_summary_names_pages_skipped_for_no_ocr_yet(proposal_run_lazy_load: Any) -> None:
    """The one page with no stored/cached content is named in the summary."""
    import asyncio

    runner, job, _project_state, loader = proposal_run_lazy_load
    seen = asyncio.run(_collect_progress(runner, job))

    assert loader.run_ocr_calls == []
    _current, _total, final_message = seen[-1]
    assert "1 page(s)" in final_message
    assert "no OCR output yet" in final_message


def test_all_pages_already_loaded_behaves_exactly_as_before(proposal_run_ready: Any) -> None:
    """When every page is already in memory, the lazy-load pass is a no-op.

    ``proposal_run_ready`` wires neither a ``page_loader`` nor the
    production loader context keys, so this only passes if the handler
    never needed a loader for a fully-preloaded book.
    """
    import asyncio

    runner, job, _project_state = proposal_run_ready
    seen = asyncio.run(_collect_progress(runner, job))

    _current, _total, final_message = seen[-1]
    assert final_message == "Proposed 0 region(s) on 0 page(s)."
    assert "no OCR output yet" not in final_message


def test_no_loader_available_falls_back_to_loaded_pages_only(
    proposal_run_no_loader_with_unloaded_page: Any,
    caplog: Any,
) -> None:
    """With no page loader wired, an unloaded page is invisible to the run,
    the same as before this fix — and the fallback is logged.
    """
    import asyncio
    import logging

    runner, job, project_state = proposal_run_no_loader_with_unloaded_page

    with caplog.at_level(logging.INFO, logger="pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions"):
        seen = asyncio.run(_collect_progress(runner, job))

    assert 1 not in project_state.page_states, "the unloaded page must not have been loaded"
    _current, _total, final_message = seen[-1]
    assert "no OCR output yet" not in final_message
    assert any("no page loader available" in record.message for record in caplog.records)


def test_a_project_swap_mid_lazy_load_aborts_before_the_next_page(
    proposal_run_book_swap_mid_load: Any,
) -> None:
    """A concurrent load swapping books mid-loop must not let this run keep
    loading pages — or journal proposals — against the wrong book.

    ``proposal_run_book_swap_mid_load``'s loader swaps
    ``project_state.loaded_project`` to book B while loading book A's
    second page (index 1). The pre-check before the third page must catch
    that and abort before ever asking the loader about it.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    runner, job, project_state, book_b, loader = proposal_run_book_swap_mid_load

    asyncio.run(handle_propose_regions(runner, job))

    assert loader.load_labeled_calls == [0, 1], "the third page must never have been requested"

    reported = runner.get_job(job.job_id)
    assert reported is not None
    assert "book-a" in reported.message
    assert "book-b" in reported.message

    assert RegionProposalLog(book_b.project_root).runs() == [], "no run was journalled for either book"

    # The swapped-in book's page_states were not written by this job after
    # the swap: only the racy in-flight page (index 1, already returned by
    # the loader when the swap happened) landed there.
    assert 2 not in project_state.page_states


def test_a_project_swap_on_the_last_page_is_caught_after_the_loop(
    proposal_run_book_swap_on_last_page: Any,
) -> None:
    """A swap on the very last page has no further loop iteration to catch
    it via the per-page pre-check — the one-time re-check after the loop
    must still catch it before eligibility or journal work proceeds.
    """
    import asyncio

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    runner, job, _project_state, book_b, loader = proposal_run_book_swap_on_last_page

    asyncio.run(handle_propose_regions(runner, job))

    assert loader.load_labeled_calls == [0, 1]

    reported = runner.get_job(job.job_id)
    assert reported is not None
    assert "book-a" in reported.message
    assert "book-b" in reported.message

    assert RegionProposalLog(book_b.project_root).runs() == []


def test_a_legacy_typography_payload_is_skipped_not_fatal(
    proposal_run_legacy_payload: Any,
) -> None:
    """One page's removed-review-data error must not abort the whole run.

    ``LocalDoctrPageLoader.load_labeled`` re-raises
    ``LegacyTypographyPayloadError`` rather than treating it as an ordinary
    cache miss, so ``ensure_page_model`` propagates it too. The lazy-load
    loop must catch it per page, skip that page, and keep going.
    """
    import asyncio

    runner, job, project_state, loader = proposal_run_legacy_payload
    seen = asyncio.run(_collect_progress(runner, job))

    assert loader.run_ocr_calls == []
    assert 1 not in project_state.page_states, "the legacy-payload page must not have loaded"
    assert project_state.page_states[0].page_record is not None
    assert project_state.page_states[2].page_record is not None

    _current, _total, final_message = seen[-1]
    assert "1 page(s)" in final_message
    assert "legacy review data" in final_message
