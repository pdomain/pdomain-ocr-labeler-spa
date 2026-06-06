"""Rotate-page job handler — S8.2.

Spec authority:
- ``docs/specs/2026-05-12-auto-rotation-design.md §Manual rotate (M9.1)``
- ``docs/plans/2026-06-06-parity-gap-completion.md §S8.2``
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

1. Rotate the source image in-place on disk (lossless via cv2 + np.rot90).
2. Re-run OCR using the same path as ``reload_ocr`` (``_get_page_loader`` /
   ``_apply_reocr_outcome`` — DRY, no copy-paste).
3. Persist durable rotation metadata via ``PageAggregate.rotation_updated``.
4. Report progress.

Security: the source image path is resolved and checked to live within
``project.project_root`` before any write (path-containment guard).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


def _within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` is within ``parent`` (including ==)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _rotate_png_on_disk(src_path: Path, degrees: int) -> None:
    """Rotate the PNG at ``src_path`` by ``degrees`` in-place (lossless).

    Uses ``pdomain_book_tools.ocr.rotation.rotate_image`` (np.rot90 under
    the hood) so the rotation is pixel-perfect and reversible.

    Raises ``RuntimeError`` if cv2 cannot re-encode the result.
    """
    import cv2
    import numpy as np
    from pdomain_book_tools.ocr.rotation import rotate_image

    raw = src_path.read_bytes()
    data = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"cv2.imdecode failed for {src_path}")
    rotated = rotate_image(img, degrees)
    ok, buf = cv2.imencode(".png", rotated)
    if not ok:
        raise RuntimeError(f"cv2.imencode failed for {src_path}")
    src_path.write_bytes(buf.tobytes())


async def handle_rotate_page(runner: JobRunner, job: Job) -> None:
    """Rotate a page image, re-run OCR, and persist durable rotation metadata.

    S8.2 real implementation — replaces the M9.1 ``asyncio.sleep(0)`` stub.
    """
    from ....settings import Settings
    from ...notifications import NotificationKind, NotificationQueue
    from ...project_state import ProjectState
    from ..handlers.reload_ocr import _apply_reocr_outcome, _get_page_loader

    payload: dict[str, Any] = job.payload
    project_id: str = str(payload.get("project_id", ""))
    page_index: int = int(payload.get("page_index", 0))
    degrees: int = int(payload.get("degrees", 90))
    manual: bool = bool(payload.get("manual", True))
    source = "manual" if manual else "auto"

    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("rotate_page: runner.context['project_state'] is not wired")

    notification_queue = ctx.get("notification_queue")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("rotate_page: runner.context['notification_queue'] is not wired")

    settings = ctx.get("settings")
    if not isinstance(settings, Settings):
        raise RuntimeError(
            "rotate_page: runner.context['settings'] is not wired; "
            "bootstrap must inject settings before rotate jobs can run"
        )

    project = project_state.loaded_project
    if project is None:
        raise RuntimeError("rotate_page: no project loaded")

    log.info(
        "rotate_page: project=%s page=%d degrees=%d manual=%s",
        project_id,
        page_index,
        degrees,
        manual,
    )

    await runner.update_progress(
        job.job_id,
        current=0,
        total=4,
        message="Rotating image",
    )

    # Step 1: Rotate the source image on disk.
    src_path = Path(project.image_paths[page_index]).resolve()
    project_root = Path(project.project_root).resolve()

    # Security: assert the source path stays within the project root.
    if not _within(src_path, project_root):
        raise RuntimeError(
            f"rotate_page: path-containment violation — {src_path} is outside project root {project_root}"
        )

    await asyncio.to_thread(_rotate_png_on_disk, src_path, degrees)
    log.debug("rotate_page: rotated on-disk image %s by %d°", src_path, degrees)

    await runner.update_progress(
        job.job_id,
        current=1,
        total=4,
        message="Running OCR on rotated image",
    )

    # Step 2: Re-run OCR using the reload_ocr machinery (DRY — shared helper).
    loader = _get_page_loader(runner, project_state, settings)

    try:
        outcome = await asyncio.to_thread(loader.run_ocr, page_index)
    except Exception as exc:
        notification_queue.queue(
            NotificationKind.NEGATIVE,
            f"OCR failed for page {page_index + 1} after rotation: {exc}",
        )
        log.exception("rotate_page: OCR failed project=%s page=%d", project_id, page_index)
        raise

    await runner.update_progress(
        job.job_id,
        current=2,
        total=4,
        message="Persisting OCR result",
    )

    # Write OCR outcome back to project state (shared helper — DRY).
    _apply_reocr_outcome(project_state, page_index, outcome)

    await runner.update_progress(
        job.job_id,
        current=3,
        total=4,
        message="Persisting rotation metadata",
    )

    # Step 3: Persist durable rotation metadata via PageAggregate.
    # Load the page aggregate (page_id may have been updated by _apply_reocr_outcome).
    store = ctx.get("page_store")
    if store is not None:
        with project_state._lock:
            pstate = project_state._page_states.get(page_index)
            page_id = pstate.page_id if pstate is not None else None

        if page_id is not None:
            try:
                agg = store.get_page(page_id)
                agg.rotation_updated(degrees=degrees, source=source)
                store.save_page(agg)
                log.debug(
                    "rotate_page: persisted rotation_updated degrees=%d source=%s page_id=%s",
                    degrees,
                    source,
                    page_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.warning(
                    "rotate_page: failed to persist rotation metadata page_id=%s: %s",
                    page_id,
                    exc,
                )
        else:
            log.debug(
                "rotate_page: no page_id on pstate for page=%d — rotation not persisted to store",
                page_index,
            )
    else:
        log.debug("rotate_page: no page_store wired — rotation metadata not persisted (test mode)")

    await runner.update_progress(
        job.job_id,
        current=4,
        total=4,
        message=f"Page {page_index} rotated {degrees}°",
    )

    notification_queue.queue(
        NotificationKind.POSITIVE,
        f"Page {page_index + 1} rotated {degrees}°",
    )

    log.info("rotate_page: complete project=%s page=%d", project_id, page_index)


__all__ = ["_rotate_png_on_disk", "_within", "handle_rotate_page"]
