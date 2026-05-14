"""Auto-rotate-all job handler.

Spec authority:
- ``docs/specs/2026-05-12-auto-rotation-design.md §Auto-rotate (M9.2)``
- Issue #264 acceptance criteria.

Handler entry-point: ``handle_auto_rotate_all(runner, job)`` — registered in
``core/jobs/runner._HANDLERS["auto_rotate_all"]``.

Job payload keys
----------------
``project_id``     str        — project identifier.
``method``         str | None — "gt-best-match", "layout", "auto", or None
                                (uses config default, treated as "auto").
``overwrite_manual`` bool     — when False, skip pages with rotation_source="manual".
``page_count``     int        — total pages (for progress reporting).

The handler performs:

1. Iterate all pages in the project.
2. For each unrotated (or overwrite_manual) page:
   a. Load the page image.
   b. Call ``pd_book_tools.ocr.rotation.detect_best_rotation`` with the
      page's OCR engine.
   c. If the best rotation has confidence ≥ 0.6 and degrees != 0,
      enqueue a ``rotate_page`` job (manual=False).
3. Report progress after each page.

For M9.2, steps 2b-2c are stubbed: the page is yielded without
OCR-engine wiring (same stub-first pattern as M9.1 ``rotate_page``).
The endpoint and job plumbing — including the 503 graceful-degradation
path in ``api/projects.py`` — are the M9.2 deliverable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


async def handle_auto_rotate_all(runner: JobRunner, job: Job) -> None:
    """Auto-rotate all pages in a project.

    Issue #264 — M9.2 auto-rotate endpoint + job scaffold. The OCR-engine
    wiring (loading predictor + calling detect_best_rotation) is a stub here;
    the 202+job plumbing and graceful-degradation path are the deliverables.

    Full implementation connects to the M3 predictor cache and calls
    ``detect_best_rotation`` per page.
    """
    payload: dict[str, Any] = job.payload
    project_id: str = str(payload.get("project_id", ""))
    method: str | None = payload.get("method")
    overwrite_manual: bool = bool(payload.get("overwrite_manual", False))
    page_count: int = int(payload.get("page_count", 0))

    log.info(
        "auto_rotate_all: project=%s method=%r overwrite_manual=%s pages=%d",
        project_id,
        method,
        overwrite_manual,
        page_count,
    )

    # Stub: iterate pages and report progress without actual OCR.
    # Full implementation: load predictor from cache, call detect_best_rotation,
    # enqueue rotate_page jobs for pages with confidence >= 0.6.
    for page_idx in range(page_count):
        await asyncio.sleep(0)  # yield to event loop between pages
        await runner.update_progress(
            job.job_id,
            current=page_idx + 1,
            total=page_count,
            message=f"Processed page {page_idx + 1}/{page_count}",
        )

    log.info("auto_rotate_all: complete project=%s", project_id)
