"""One measure-and-fit pass over a whole book, shared by both proposal jobs.

``propose_page_kinds`` needs every page measured before it can classify any —
``fit_book_templates`` measures the whole book's first-band geometry before
classifying a single page against it. ``propose_regions`` needs the same three
outputs: each page's measurement, each page's classification, and the book's
fitted templates. Running that pass twice in two files is how the two jobs end
up disagreeing about the same book.

Each page's bytes are read through a verified per-page lease
(``core/jobs/handlers/_labeling_page_lease.leased_labeling_page``), never
``project.image_paths`` directly — on a book-labeling project that path
bypasses the manifest hash pin, so measuring from it would let proposals be
computed from bytes the manifest never authorized. On an ordinary project the
lease is a no-op and ``ProjectState.labeling_image_path`` degrades to the
same on-disk path this loop used to read. A page whose lease fails to verify
is logged and skipped — the run keeps going, and ``page_indices`` records
which original page index each entry in ``measurements`` came from, since a
skip opens a gap that positional recovery below can no longer assume away.

The measurement is not persisted. A region run re-measures rather than reading
a stored result, because the page-kind journal records only ``run_id``,
``model_id``, ``model_version``, ``created_at`` and ``page_count`` — it has no
per-facet staleness machinery, so a stored measurement would need a new record
carrying its own image digest and a rule for what to do when that digest stops
matching. See the design's "The measurement has to reach the run".
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pdomain_pgdp_measure.page_templates import (
    BookTemplates,
    PageClassification,
    classify_pages,
    fit_book_templates,
)
from pdomain_pgdp_measure.profile_input import ProfileInputPage
from pdomain_pgdp_measure.profile_models import PageMeasurement

from .jobs.handlers._labeling_page_lease import leased_labeling_page

if TYPE_CHECKING:
    from .models import Project
    from .project_state import ProjectState

log = logging.getLogger(__name__)


class MeasurePageFn(Protocol):
    """The ``profile_page`` shape, as an injection point for tests."""

    def __call__(self, project_id: str, page: ProfileInputPage) -> PageMeasurement: ...


ProgressFn = Callable[[int, int], Awaitable[None]]
"""Called after each page with ``(pages_done, pages_total)``."""


@dataclass(frozen=True)
class MeasuredBook:
    """One book's measured geometry: per page, and fitted across the whole volume.

    ``page_indices[n]`` is the original page index of ``measurements[n]``. It is
    not always ``n``: a page whose verified lease could not be opened is skipped,
    and the gap that leaves is invisible to positional recovery. Every consumer
    joins through ``page_indices``, never by position.
    """

    measurements: tuple[PageMeasurement, ...]
    classifications: tuple[PageClassification, ...]
    page_indices: tuple[int, ...]
    templates: BookTemplates


async def measure_book(
    project: Project,
    *,
    project_state: ProjectState,
    measure_fn: MeasurePageFn,
    on_page_measured: ProgressFn,
) -> MeasuredBook:
    """Measure every page of ``project`` through a verified lease, fit its
    templates, and classify it.

    Walks ``project.image_paths`` — the same sequence the progress denominator
    comes from, so the two can never disagree. A book-labeling project's bytes
    are only trustworthy behind a verified per-page lease
    (``ProjectState.open_labeling_page`` / ``labeling_image_path``) — reading
    ``image_path`` directly would bypass the manifest hash pin. An ordinary
    project has nothing to lease: ``leased_labeling_page`` is then a no-op and
    ``labeling_image_path`` degrades to ``image_path`` unchanged, so one code
    path serves both project kinds.
    """
    image_paths = list(project.image_paths)
    total = len(image_paths)
    measured: list[PageMeasurement] = []
    measured_page_indices: list[int] = []
    for page_index, image_path in enumerate(image_paths):
        # The lease is entered through an ``ExitStack`` rather than a ``with``
        # inside a ``try``, so only ``open_labeling_page``'s own ``ValueError``
        # is attributed to the lease. A measurement function may raise
        # ``ValueError`` of its own, and reporting that as a failed lease
        # would send the next reader looking at the manifest instead of the
        # measurement.
        stack = ExitStack()
        try:
            stack.enter_context(leased_labeling_page(project_state, page_index))
        except ValueError as exc:
            log.warning(
                "measure_book: skipping page=%d — could not open a verified page lease: %s",
                page_index,
                exc,
            )
            await on_page_measured(page_index + 1, total)
            continue
        with stack:
            input_page = ProfileInputPage(
                name=image_path.name,
                image_path=project_state.labeling_image_path(page_index),
                source_path=f"{project.project_id}/{image_path.name}",
            )
            # ``profile_page`` decodes the image and scans it with numpy —
            # CPU-bound work that would block the one event loop for the whole
            # book. Offload it the way every other image-touching handler does,
            # so the confirm route and the job's own progress stream keep
            # being served. The lease stays bound for the duration of the
            # offloaded call — ``asyncio.to_thread`` propagates the contextvar
            # the binding uses.
            measurement = await asyncio.to_thread(measure_fn, project.project_id, input_page)
        measured.append(measurement)
        measured_page_indices.append(page_index)
        await on_page_measured(page_index + 1, total)

    templates = fit_book_templates(measured)
    # classify_pages preserves input order, so zipping it against
    # measured_page_indices recovers each classification's original page_index
    # without depending on page_name uniqueness. That order-preservation is
    # documented behavior, not a type-checked contract, so this explicit check
    # — written out rather than asserted, to survive -O — is what makes
    # relying on it safe: a future release that filters or reorders results
    # fails loudly here instead of silently attributing every proposal after
    # the first divergence to the wrong page.
    classifications = classify_pages(measured, templates)
    if len(classifications) != len(measured):
        raise RuntimeError(
            "measure_book: classify_pages returned "
            f"{len(classifications)} classification(s) for {len(measured)} measured "
            "page(s) — page_index recovery by position is no longer safe"
        )
    return MeasuredBook(tuple(measured), classifications, tuple(measured_page_indices), templates)


__all__ = ["MeasurePageFn", "MeasuredBook", "ProgressFn", "measure_book"]
