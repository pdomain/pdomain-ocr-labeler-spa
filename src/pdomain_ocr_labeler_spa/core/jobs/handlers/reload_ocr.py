"""Reload-OCR job handler — spec-23-B1 / issue #307.

Spec authority:
- ``specs/23-page-payload-backend.md §6`` — fraction-based progress,
  ``LocalDoctrPageLoader.run_ocr`` dispatched via ``asyncio.to_thread``,
  outcome stored on ``ProjectState.page_states[idx].page_record``,
  ``ocr_failed`` notification on exception.
- ``docs/architecture/11-notifications.md §5.1`` — sequence diagram for
  the reload-OCR + SSE flow.

Handler entry-point: ``handle_reload_ocr(runner, job)`` — registered in
``core/jobs/runner._HANDLERS["reload_ocr"]``.

Job payload keys
----------------
``project_id``  str  — project identifier (also on ``job.project_id``).
``page_index``  int  — 0-based page index to (re-)run OCR for.
``force``       bool — when True, bypass cache/labeled lanes; the
                       handler only ever drives the OCR lane, so this
                       flag is forwarded informationally only (kept for
                       wire-shape stability with spec §6).

Runner context keys (read-only)
-------------------------------
``project_state``      ``ProjectState``      — required.
``notification_queue`` ``NotificationQueue`` — required.
``page_loader``        ``PageLoader``        — optional; injected by
                                               tests or by the route
                                               layer (M3 wiring). When
                                               absent the handler falls
                                               through to the production
                                               path below.
``predictor_cache``    ``PredictorCache``    — optional; used by the
                                               production path in
                                               ``_get_page_loader`` to
                                               build
                                               ``LocalDoctrPageLoader``.
                                               If absent and
                                               ``page_loader`` is also
                                               absent, an error follows
                                               when the production path
                                               runs.
``ocr_config_carrier`` ``OCRConfigCarrier``  — optional; supplies
                                               ``snapshot()`` for atomic
                                               model-key read. Same
                                               caveat as
                                               ``predictor_cache``.
``settings``           ``Settings``          — optional; supplies
                                               ``data_root`` /
                                               ``cache_root`` to
                                               ``LocalDoctrPageLoader``.
                                               Same caveat as
                                               ``predictor_cache``.

Progress reporting
------------------
Four ``update_progress`` calls per spec §6 (fractions 0.0 / 0.1 / 0.9 /
1.0). ``JobRunner.update_progress`` accepts integer ``current/total``
counters; we encode the four spec fractions as ``(0,10) (1,10) (9,10)
(10,10)`` so the wire ``current/total`` ratio reproduces the spec
fractions exactly.

Failure semantics
-----------------
The handler raises on loader exceptions; ``JobRunner._run_one`` catches
and transitions the job to ``ERROR`` with the exception text on
``error_message``. Before re-raising, we queue a ``NotificationKind.NEGATIVE``
notification with key ``ocr_failed`` so SPA clients see a banner +
toast independently of the SSE job stream. A ``run_ocr`` call exceeding
``Settings.ocr_timeout_s`` (Task 2, docs/plans/2026-07-14-review-fixes.md)
follows the same path via a re-raised ``TimeoutError``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ....settings import Settings
from ...notifications import NotificationKind, NotificationQueue
from ...ocr.predictor import PredictorCache
from ...page_state import PageLoader, PageLoadOutcome
from ...project_state import PageState, ProjectState

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

# Spec §6 progress fractions, encoded as (current, total) pairs so the
# integer-counter ``update_progress`` API reproduces the fractions.
_PROGRESS_TOTAL = 10
_PROGRESS_STAGES: tuple[tuple[int, str], ...] = (
    (0, "Loading OCR model"),
    (1, "Running OCR"),
    (9, "Persisting cached envelope"),
    (10, "Done"),
)


def _get_required_context(runner: JobRunner) -> tuple[ProjectState, NotificationQueue]:
    """Pull the required carriers off ``runner.context``; raise if absent."""
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    notification_queue = ctx.get("notification_queue")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("reload_ocr: runner.context['project_state'] is not wired")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("reload_ocr: runner.context['notification_queue'] is not wired")
    return project_state, notification_queue


def _get_page_loader(
    runner: JobRunner,
    project_state: ProjectState,
    settings: Settings,
) -> PageLoader:
    """Return the active ``PageLoader``, building one on-demand if needed.

    Priority:
    1. If ``runner.context["page_loader"]`` is already set (test injection
       or explicit route-layer wiring), use it directly — this preserves
       the existing isolation pattern.
    2. Otherwise, build a ``LocalDoctrPageLoader`` from the production
       context keys ``predictor_cache`` / ``ocr_config_carrier``.
       Raises ``RuntimeError`` when the project hasn't been loaded yet.

    The function signature accepts ``project_state`` and ``settings``
    explicitly so callers don't have to pull them a second time off
    ``runner.context`` after ``_get_required_context`` already did so.
    """
    # Fast path: explicit injection (tests + future route-layer wiring).
    loader = runner.context.get("page_loader")
    if loader is not None:
        return loader  # type: ignore[return-value]

    # Production path: build LocalDoctrPageLoader on-demand.
    if project_state.loaded_project is None:
        raise RuntimeError("reload_ocr: no project loaded")

    from ....adapters.ocr.local_doctr import LocalDoctrPageLoader

    ctx: dict[str, Any] = runner.context
    predictor_cache: PredictorCache = ctx["predictor_cache"]
    ocr_carrier = ctx["ocr_config_carrier"]
    detection_key, recognition_key, hf_revision = ocr_carrier.snapshot()

    return LocalDoctrPageLoader(
        project=project_state.loaded_project,
        predictor_cache=predictor_cache,
        detection_key=detection_key,
        recognition_key=recognition_key,
        hf_revision=hf_revision,
        data_root=settings.data_root,
        cache_root=settings.cache_root,
        store=ctx.get("page_store"),  # LabelerPageStore | None
    )


def _read_edited_image_blob(
    runner: JobRunner,
    project_state: ProjectState,
    page_index: int,
) -> bytes | None:
    """Read the persisted post-erase edited-image blob bytes, or ``None``.

    Lane A / Task A4. The erase-pixels route stores the edited PNG bytes in the
    project's ``LabelerPageStore`` blob store and records the content hash on
    ``PageState.edited_image_blob``. This reads that blob back. Returns ``None``
    when no edit has been persisted, no store is wired, or the read fails.
    """
    pstate = project_state.get_page_state(page_index)
    blob_hash = getattr(pstate, "edited_image_blob", None) if pstate is not None else None
    if not blob_hash:
        return None
    store = runner.context.get("page_store")
    if store is None:
        return None
    try:
        return store.blobs.read(blob_hash)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("reload_ocr: failed to read edited-image blob %s: %s", blob_hash, exc)
        return None


def _apply_reocr_outcome(
    project_state: ProjectState,
    page_index: int,
    outcome: PageLoadOutcome,
) -> None:
    """Write an OCR outcome back to ``ProjectState`` in-place.

    Shared by ``handle_reload_ocr`` and ``handle_rotate_page`` so neither
    copies this lock+generation-bump block.  Holds ``project_state._lock``
    for the write only; callers must have run OCR outside the lock.
    """
    with project_state._lock:
        existing = project_state._page_states.get(page_index)
        if existing is None:
            existing = PageState(page_index=page_index)
            project_state._page_states[page_index] = existing
        existing.page_record = outcome
        # Stamp page_id from the OCR result onto PageState so subsequent
        # mutation routes can fire event-store saves (M9 wiring).
        # Always overwrite (no "if None" guard): forced re-OCR produces a NEW
        # page_id (Page.page_id is uuid4); keeping the stale id means saves after
        # re-OCR target the old aggregate while the ProjectAggregate now points
        # at the new one — post-re-OCR edits are silently lost on restart.
        page_payload_obj = getattr(outcome, "payload", None)
        labeler_page_id = getattr(page_payload_obj, "_labeler_page_id", None)
        if labeler_page_id is not None:
            existing.page_id = labeler_page_id
            log.debug(
                "_apply_reocr_outcome: stamped page_id=%s on pstate page=%d",
                labeler_page_id,
                page_index,
            )
        # Per-page generation bump (spec-23-B2 / spec §4 + §8): mark the
        # page dirty so subsequent ``POST .../save`` or ``save_project``
        # passes pick it up.
        existing.generation += 1
        project_state._generation += 1


async def handle_reload_ocr(runner: JobRunner, job: Job) -> None:
    """Run OCR for a single page and store the outcome on ``ProjectState``.

    Spec §6 contract. Raises on loader failure; the runner converts to
    a terminal ``error`` state. Notifications are queued via
    ``NotificationQueue`` per spec 11.
    """
    payload: dict[str, Any] = job.payload
    page_index: int = int(payload.get("page_index", 0))
    project_id: str = job.project_id or str(payload.get("project_id", ""))
    use_edited_image: bool = bool(payload.get("use_edited_image", False))

    project_state, notification_queue = _get_required_context(runner)
    settings = runner.context.get("settings")
    if not isinstance(settings, Settings):
        raise RuntimeError(
            "reload_ocr: runner.context['settings'] is not wired; "
            "bootstrap must inject settings before OCR jobs can run"
        )

    log.info(
        "reload_ocr: project=%s page=%d job=%s",
        project_id,
        page_index,
        job.job_id,
    )

    # Stage 1 — 0.0 / "Loading OCR model".
    current, message = _PROGRESS_STAGES[0]
    await runner.update_progress(job.job_id, current=current, total=_PROGRESS_TOTAL, message=message)

    loader = _get_page_loader(runner, project_state, settings)

    # Stage 2 — 0.1 / "Running OCR".
    current, message = _PROGRESS_STAGES[1]
    await runner.update_progress(job.job_id, current=current, total=_PROGRESS_TOTAL, message=message)

    # Lane A / Task A4: when the caller asks to re-OCR the edited image, read
    # the persisted post-erase blob and hand its bytes to the loader so OCR
    # runs against the erased pixels rather than the pristine on-disk file.
    edited_image_bytes: bytes | None = None
    if use_edited_image:
        edited_image_bytes = _read_edited_image_blob(runner, project_state, page_index)
        if edited_image_bytes is None:
            log.info(
                "reload_ocr: use_edited_image=True but no edited-image blob for page=%d; "
                "falling back to the on-disk source image",
                page_index,
            )

    timeout_s = settings.ocr_timeout_s
    try:
        if edited_image_bytes is not None:
            ocr_coro = asyncio.to_thread(loader.run_ocr, page_index, edited_image_bytes=edited_image_bytes)
        else:
            ocr_coro = asyncio.to_thread(loader.run_ocr, page_index)
        if timeout_s > 0:
            outcome: PageLoadOutcome = await asyncio.wait_for(ocr_coro, timeout=timeout_s)
        else:
            outcome = await ocr_coro
    except TimeoutError as exc:
        # Task 2 (docs/plans/2026-07-14-review-fixes.md): cancelling this
        # await does NOT kill the OS thread running ``run_ocr`` — see
        # ``Settings.ocr_timeout_s`` docstring. Queue a NEGATIVE
        # notification, then re-raise so the runner records the error
        # on the job (same failure path as an OCR exception below).
        # ``asyncio.wait_for`` raises a bare ``TimeoutError()`` with no
        # message, so ``JobRunner._run_one``'s ``str(exc)`` would
        # otherwise store an empty ``error_message`` — re-raise a new
        # ``TimeoutError`` carrying the descriptive message instead.
        message = f"OCR timed out for page {page_index + 1} after {timeout_s}s"
        notification_queue.queue(NotificationKind.NEGATIVE, message)
        log.error("reload_ocr: %s project=%s", message, project_id)
        raise TimeoutError(message) from exc
    except Exception as exc:
        # Spec §6: ``ocr_failed`` notification on exception. Queue first,
        # then re-raise so the runner records the error on the job.
        notification_queue.queue(
            NotificationKind.NEGATIVE,
            f"OCR failed for page {page_index + 1}: {exc}",
        )
        log.exception("reload_ocr: OCR failed project=%s page=%d", project_id, page_index)
        raise

    # Stage 3 — 0.9 / "Persisting cached envelope".
    current, message = _PROGRESS_STAGES[2]
    await runner.update_progress(job.job_id, current=current, total=_PROGRESS_TOTAL, message=message)

    _apply_reocr_outcome(project_state, page_index, outcome)

    # Stage 4 — 1.0 / "Done".
    current, message = _PROGRESS_STAGES[3]
    await runner.update_progress(job.job_id, current=current, total=_PROGRESS_TOTAL, message=message)

    # Success notification (spec 11 §2.2 — kind=positive).
    notification_queue.queue(
        NotificationKind.POSITIVE,
        f"OCR complete for page {page_index + 1}",
    )

    log.info(
        "reload_ocr: complete project=%s page=%d job=%s",
        project_id,
        page_index,
        job.job_id,
    )


__all__ = ["_apply_reocr_outcome", "_get_page_loader", "handle_reload_ocr"]
