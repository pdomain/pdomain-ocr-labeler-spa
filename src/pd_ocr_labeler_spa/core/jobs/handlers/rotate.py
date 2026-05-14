"""Rotate-page job handler.

Spec authority:
- ``docs/specs/2026-05-12-auto-rotation-design.md §Manual rotate (M9.1)``
- Issue #263 acceptance criteria.

Handler entry-point: ``handle_rotate_page(runner, job)`` — registered in
``core/jobs/runner._HANDLERS["rotate_page"]``.

Job payload keys
----------------
``project_id``  str  — project identifier (also on ``job.project_id``).
``page_index``  int  — 0-based page index.
``degrees``     int  — rotation in degrees (-90, 90, 180).
``manual``      bool — True for user-initiated rotation.

The handler performs four steps:

1. Emits ``started`` event (done by runner._run_one before calling here).
2. Rotate the source image in-place via ``pd_book_tools.ocr.rotation.rotate_image``.
3. Re-run OCR (delegates to reload_ocr machinery — wired when M3 lands).
4. Update ``PageRecord.rotation_degrees`` / ``rotation_source``, auto-save
   envelope.

For M9.1 steps 2-4 are stubs; the 202+job plumbing is the deliverable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


async def handle_rotate_page(runner: JobRunner, job: Job) -> None:
    """Rotate a page image and re-run OCR.

    Issue #263 — M9.1 manual rotate (202+job pattern).  Steps 2-4 are
    stubbed for M9.1; the real image-rotate + OCR + save pipeline lands
    once the M3 OCR plumbing is wired.
    """
    payload: dict[str, Any] = job.payload
    project_id: str = str(payload.get("project_id", ""))
    page_index: int = int(payload.get("page_index", 0))
    degrees: int = int(payload.get("degrees", 90))
    manual: bool = bool(payload.get("manual", True))

    log.info(
        "rotate_page: project=%s page=%d degrees=%d manual=%s",
        project_id,
        page_index,
        degrees,
        manual,
    )

    # Steps 2-4 stub: yield to event loop so the runner stays responsive.
    # Full implementation: rotate image via pd_book_tools.ocr.rotation,
    # re-run OCR, update PageRecord.rotation_degrees + rotation_source,
    # auto-save envelope.
    await asyncio.sleep(0)

    await runner.update_progress(
        job.job_id,
        current=1,
        total=1,
        message=f"Page {page_index} rotated {degrees} degrees",
    )

    log.info("rotate_page: complete project=%s page=%d", project_id, page_index)
