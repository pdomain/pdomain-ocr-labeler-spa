"""Auto-rotate-all job handler — S8.3.

Spec authority:
- ``docs/specs/2026-05-12-auto-rotation-design.md §Auto-rotate (M9.2)``
- ``docs/plans/2026-06-06-parity-gap-completion.md §S8.3``
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

The handler:

1. Reads the page image from disk for each page.
2. Calls ``detect_best_rotation`` with an ``ocr_fn`` built from the project's
   predictor cache (or from ``runner.context["auto_rotate_detect_fn"]`` in
   tests — same injection pattern as ``page_loader``).
3. For pages where chosen != 0 and confidence ≥ threshold, applies the SAME
   rotation path as ``handle_rotate_page`` (reuses ``_rotate_png_on_disk``,
   ``_apply_reocr_outcome``, ``_get_page_loader`` — DRY).
4. Honors ``overwrite_manual``: skips pages whose aggregate
   ``rotation_source == "manual"`` unless set.
5. Emits real per-page progress events.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.6


def _load_image_ndarray(src_path: Path) -> np.ndarray:
    """Read a PNG from disk and return it as an ndarray."""
    raw = src_path.read_bytes()
    data = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"cv2.imdecode failed for {src_path}")
    return img


def _build_ocr_fn(runner: JobRunner, project_state: Any, settings: Any) -> Callable[..., Any]:
    """Build an ``ocr_fn`` callable for ``detect_best_rotation``.

    Priority:
    1. ``runner.context["auto_rotate_ocr_fn"]`` — direct injection (test or future wiring).
    2. Production: build from ``predictor_cache`` — wraps the predictor so it returns
       a ``Document`` for each probe image.

    When neither is available a ``RuntimeError`` is raised so the handler reports a
    clear error rather than silently skipping all pages.
    """
    from ....settings import Settings

    # If there's an injected ocr_fn use it (test path and future explicit wiring).
    ocr_fn = runner.context.get("auto_rotate_ocr_fn")
    if ocr_fn is not None:
        return ocr_fn  # type: ignore[return-value]

    # Production path: build from predictor_cache + ocr_config_carrier.
    if isinstance(settings, Settings) and project_state.loaded_project:
        from ...ocr.predictor import PredictorCache

        ctx: dict[str, Any] = runner.context
        predictor_cache: PredictorCache | None = ctx.get("predictor_cache")
        if predictor_cache is not None:
            ocr_carrier = ctx.get("ocr_config_carrier")
            if ocr_carrier is not None:
                detection_key, recognition_key, hf_revision = ocr_carrier.snapshot()
                predictor = predictor_cache.get_or_create(
                    detection_key=detection_key,
                    recognition_key=recognition_key,
                    hf_revision=hf_revision,
                )

                def _ocr_fn_from_predictor(image: np.ndarray) -> Any:
                    return predictor(image)  # type: ignore[call-arg]

                return _ocr_fn_from_predictor

    # Neither injection nor production wiring — fail clearly.
    raise RuntimeError(
        "auto_rotate_all: no usable ocr_fn; "
        "inject runner.context['auto_rotate_detect_fn'] to bypass (test) or "
        "wire predictor_cache + ocr_config_carrier for production use"
    )


async def handle_auto_rotate_all(runner: JobRunner, job: Job) -> None:
    """Auto-rotate all pages in a project — S8.3 real implementation."""
    from ....settings import Settings
    from ...notifications import NotificationKind, NotificationQueue
    from ...project_state import ProjectState
    from ..handlers.reload_ocr import _apply_reocr_outcome, _get_page_loader
    from ..handlers.rotate import _rotate_png_on_disk, _within

    payload: dict[str, Any] = job.payload
    project_id: str = str(payload.get("project_id", ""))
    method: str | None = payload.get("method")
    overwrite_manual: bool = bool(payload.get("overwrite_manual", False))
    page_count: int = int(payload.get("page_count", 0))

    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("auto_rotate_all: runner.context['project_state'] is not wired")

    notification_queue = ctx.get("notification_queue")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("auto_rotate_all: runner.context['notification_queue'] is not wired")

    settings = ctx.get("settings")
    if not isinstance(settings, Settings):
        raise RuntimeError(
            "auto_rotate_all: runner.context['settings'] is not wired; "
            "bootstrap must inject settings before auto-rotate jobs can run"
        )

    project = project_state.loaded_project
    if project is None:
        raise RuntimeError("auto_rotate_all: no project loaded")

    log.info(
        "auto_rotate_all: project=%s method=%r overwrite_manual=%s pages=%d",
        project_id,
        method,
        overwrite_manual,
        page_count,
    )

    # Resolve detect_best_rotation (real or injected for tests).
    detect_fn = ctx.get("auto_rotate_detect_fn")
    if detect_fn is None:
        from pdomain_book_tools.ocr.rotation import detect_best_rotation

        detect_fn = detect_best_rotation

    # Build ocr_fn once for the whole batch.
    ocr_fn = _build_ocr_fn(runner, project_state, settings)
    store = ctx.get("page_store")
    loader = _get_page_loader(runner, project_state, settings)
    project_root = Path(project.project_root).resolve()

    rotated_pages: list[int] = []
    skipped_pages: list[int] = []

    for page_idx in range(page_count):
        src_path = Path(project.image_paths[page_idx]).resolve()

        # Security: skip pages whose image path escapes the project root.
        if not _within(src_path, project_root):
            log.warning(
                "auto_rotate_all: skipping page=%d — path outside project root: %s",
                page_idx,
                src_path,
            )
            skipped_pages.append(page_idx)
            continue

        # Honor overwrite_manual: skip pages already manually rotated.
        if not overwrite_manual and store is not None:
            with project_state._lock:
                pstate = project_state._page_states.get(page_idx)
                page_id = pstate.page_id if pstate is not None else None
            if page_id is not None:
                try:
                    agg = store.get_page(page_id)
                    rotation_source = str(agg.record.rotation_source or "")
                    if rotation_source == "manual":
                        log.debug(
                            "auto_rotate_all: skipping page=%d (manual rotation, overwrite_manual=False)",
                            page_idx,
                        )
                        skipped_pages.append(page_idx)
                        await runner.update_progress(
                            job.job_id,
                            current=page_idx + 1,
                            total=page_count,
                            message=f"Skipped page {page_idx + 1} (manual rotation)",
                        )
                        continue
                except Exception as exc:
                    log.debug(
                        "auto_rotate_all: could not read rotation_source for page=%d: %s",
                        page_idx,
                        exc,
                    )

        # Load image for detection.
        try:
            image = await asyncio.to_thread(_load_image_ndarray, src_path)
        except Exception as exc:
            log.warning(
                "auto_rotate_all: could not load image for page=%d: %s",
                page_idx,
                exc,
            )
            await runner.update_progress(
                job.job_id,
                current=page_idx + 1,
                total=page_count,
                message=f"Failed to load page {page_idx + 1}",
            )
            continue

        # Detect best rotation.
        try:
            chosen, _doc, _probes = await asyncio.to_thread(
                detect_fn,
                image,
                ocr_fn=ocr_fn,
                confidence_threshold=_CONFIDENCE_THRESHOLD,
            )
        except Exception as exc:
            log.warning(
                "auto_rotate_all: detection failed for page=%d: %s",
                page_idx,
                exc,
            )
            await runner.update_progress(
                job.job_id,
                current=page_idx + 1,
                total=page_count,
                message=f"Detection failed for page {page_idx + 1}",
            )
            continue

        if chosen != 0:
            # Apply rotation: rotate on disk, re-OCR, persist metadata.
            log.debug("auto_rotate_all: rotating page=%d by %d°", page_idx, chosen)
            try:
                await asyncio.to_thread(_rotate_png_on_disk, src_path, chosen)

                outcome = await asyncio.to_thread(loader.run_ocr, page_idx)
                _apply_reocr_outcome(project_state, page_idx, outcome)

                if store is not None:
                    with project_state._lock:
                        pstate = project_state._page_states.get(page_idx)
                        page_id = pstate.page_id if pstate is not None else None
                    if page_id is not None:
                        try:
                            agg = store.get_page(page_id)
                            agg.rotation_updated(degrees=chosen, source="auto")
                            store.save_page(agg)
                        except Exception as exc:  # pragma: no cover - defensive
                            log.warning(
                                "auto_rotate_all: failed to persist rotation metadata page_id=%s: %s",
                                page_id,
                                exc,
                            )

                rotated_pages.append(page_idx)
            except Exception as exc:
                log.warning(
                    "auto_rotate_all: rotation failed for page=%d: %s",
                    page_idx,
                    exc,
                )
        else:
            log.debug("auto_rotate_all: page=%d is already upright, skipping", page_idx)

        await runner.update_progress(
            job.job_id,
            current=page_idx + 1,
            total=page_count,
            message=f"Processed page {page_idx + 1}/{page_count}",
        )

    if rotated_pages:
        notification_queue.queue(
            NotificationKind.POSITIVE,
            f"Auto-rotate complete: {len(rotated_pages)} page(s) rotated",
        )
    else:
        notification_queue.queue(
            NotificationKind.INFO,
            "Auto-rotate complete: no pages needed rotation",
        )

    log.info(
        "auto_rotate_all: complete project=%s rotated=%s skipped=%s",
        project_id,
        rotated_pages,
        skipped_pages,
    )


__all__ = ["handle_auto_rotate_all"]
