"""Load-page job handler — moves the implicit first page load onto the job system.

Spec authority: ``docs/specs/2026-08-08-page-load-progress-design.md``
"Move page loading onto the job system", and the work item
``docs/issues/2026-08-08-page-load-progress-unbuilt.md``.

Only a genuine store miss reaches this handler. ``GET
/api/projects/{id}/pages/{idx}`` (``api/pages.py::get_page``) does the fast
synchronous check itself first: the in-memory ``PageState``, then
``ensure_page_model(..., allow_ocr=False)`` for the labeled/cached lanes.
Either hit returns the page immediately, with no job and no added latency.
This job is submitted only when both come back empty — the case that used to
block the request for seconds to half a minute with nothing on screen.

Job payload keys
-----------------
``page_index``  int  — 0-based page index to load.

Stage granularity (a deliberate, documented limitation)
--------------------------------------------------------
``pdomain-book-tools``'s ``Document.from_image_ocr_via_doctr`` and the
predictor build behind it (``get_default_doctr_predictor``) take no progress
callback today — the design's open question "Whether ``pdomain-book-tools``
should take a callback or emit structured events" is still open, and this
task deliberately leaves it open rather than reaching into that sibling repo.
Without a callback, this handler cannot observe the boundary between
"predictor built" and "OCR pass started" — both happen inside the one
blocking ``loader.run_ocr`` call it awaits on a worker thread — so they are
reported as ONE stage rather than the design's two ("Preparing the OCR
engine" and "Running OCR"). That is coarser than the design's four-stage
list, but per the design's own framing this is still strictly better than
today's unlabeled multi-second block: the user sees *that* the engine is
loading and OCR is running, and on which device, even without a boundary
between the two.

Stages emitted (see ``_PROGRESS_TOTAL`` / the two ``update_progress`` calls
below):

1. ``current=0`` — "Stored page not found — running OCR." Reported before the
   loader is even built, so the first published event already names a real
   stage (design acceptance criterion "shows a named stage within one
   second") and reports the store miss that triggered this job (acceptance
   criterion "A store miss is visible as its own stage").
2. ``current=1`` — "Preparing the OCR engine and running OCR — {device}."
   One coarse stage covering the predictor build and the OCR pass; the
   device text comes from ``describe_device()`` (already used for the
   ``__main__.py`` boot banner) so a CPU fallback explains a long wait the
   way the design asks for.
3. ``current=2`` (== total) — "Page loaded." on success, via the same
   ``update_progress`` call reload_ocr's handler uses for its own terminal
   stage, so the SSE terminal frame carries a readable message.

Failure semantics, and how this relates to ``PagePayload.page_load_error``
----------------------------------------------------------------------------
Raises on loader failure; ``JobRunner._run_one`` converts that into a
terminal ``error`` job carrying ``error_message = str(exc)`` — the exact
path ``reload_ocr`` already uses, uncurated (unlike the synchronous
``page_load_error.message``, which is curated to the exception type name so
a filesystem path never reaches the direct HTTP response). The two are the
same underlying signal ("this page's OCR failed") surfaced on two different
channels for two different moments:

- ``PagePayload.page_load_error`` — set only by the *synchronous* part of
  ``get_page`` (loader-build failure, or a labeled/cached-lane read that
  raises). It is what a page fetch made *before* this job existed can still
  report, and it is what a plain page-content fetch still gets today.
- This job's terminal ``error`` event / ``error_message`` — set when the
  *OCR itself* fails, now off the synchronous path per this design. The SPA
  learns this from the job stream (``GET /api/jobs/{job_id}/events``) it
  already subscribes to for ``page_load_job_id``, not from
  ``page_load_error`` on a subsequent page fetch (a page GET issued after
  the job errors sees the same store miss again and submits a fresh job,
  matching ``ensure_page_model``'s "the failure is not cached, so the next
  call retries" contract).

A ``NotificationKind.NEGATIVE`` notification is queued on failure, mirroring
``reload_ocr``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ....settings import Settings
from ...device_info import describe_device
from ...notifications import NotificationKind, NotificationQueue
from ...ocr.device_pref import resolve_ocr_device_override
from ...page_state import PageLoadOutcome
from ...project_state import ProjectState
from .reload_ocr import _finalize_reocr_outcome, _get_page_loader, _prior_confirmed_page_kind

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

# Two real stages (store-miss, then the coarse prepare+run stage) plus a
# terminal "done" — see the module docstring "Stage granularity" for why
# there is no finer split between engine prep and the OCR pass itself.
_PROGRESS_TOTAL = 2
_STORE_MISS_MESSAGE = "Stored page not found — running OCR."


def _get_required_context(runner: JobRunner) -> tuple[ProjectState, NotificationQueue]:
    """Pull the required carriers off ``runner.context``; raise if absent."""
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    notification_queue = ctx.get("notification_queue")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("load_page: runner.context['project_state'] is not wired")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("load_page: runner.context['notification_queue'] is not wired")
    return project_state, notification_queue


async def handle_load_page(runner: JobRunner, job: Job) -> None:
    """Run OCR for a page whose in-memory state and store both missed.

    Raises on loader failure; the runner converts that to a terminal
    ``error`` job. See the module docstring for the full stage list and the
    failure-channel relationship to ``PagePayload.page_load_error``.
    """
    payload: dict[str, Any] = job.payload
    page_index: int = int(payload.get("page_index", 0))
    project_id: str = job.project_id or str(payload.get("project_id", ""))

    project_state, notification_queue = _get_required_context(runner)
    settings = runner.context.get("settings")
    if not isinstance(settings, Settings):
        raise RuntimeError(
            "load_page: runner.context['settings'] is not wired; "
            "bootstrap must inject settings before page-load jobs can run"
        )

    log.info(
        "load_page: project=%s page=%d job=%s",
        project_id,
        page_index,
        job.job_id,
    )

    # Stage 1 — the store-miss reason this job exists at all: the
    # synchronous lane check in api.pages.get_page already came back empty
    # before this job was ever submitted.
    await runner.update_progress(job.job_id, current=0, total=_PROGRESS_TOTAL, message=_STORE_MISS_MESSAGE)

    loader = _get_page_loader(
        runner,
        project_state,
        settings,
        job_id=job.job_id,
        page_index=page_index,
    )

    # Stage 2 — predictor build + OCR pass, reported as one coarse stage;
    # see "Stage granularity" above. Names the resolved device so a CPU
    # fallback explains a long wait instead of leaving it a mystery.
    device = describe_device(device_override=resolve_ocr_device_override())
    message = f"Preparing the OCR engine and running OCR — {device}"
    await runner.update_progress(job.job_id, current=1, total=_PROGRESS_TOTAL, message=message)

    # pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
    # "Re-OCR and rotation keep the confirmed kind" — read before the fresh
    # Page replaces this one. A first-ever load has no prior kind, so this
    # is normally None; reusing the shared helper keeps this handler
    # correct if a confirm ever races a first load the same way it can race
    # a reload.
    page_kind = _prior_confirmed_page_kind(project_state, page_index)

    timeout_s = settings.ocr_timeout_s
    try:
        ocr_coro = asyncio.to_thread(loader.run_ocr, page_index, page_kind=page_kind)
        if timeout_s > 0:
            outcome: PageLoadOutcome = await asyncio.wait_for(ocr_coro, timeout=timeout_s)
        else:
            outcome = await ocr_coro
    except TimeoutError as exc:
        # See reload_ocr.handle_reload_ocr for why this re-raises a
        # descriptive TimeoutError rather than letting the bare one from
        # asyncio.wait_for through: JobRunner._run_one stores str(exc) as
        # error_message, and a bare TimeoutError() stringifies to "".
        message = f"OCR timed out for page {page_index + 1} after {timeout_s}s"
        notification_queue.queue(NotificationKind.NEGATIVE, message)
        log.error("load_page: %s project=%s", message, project_id)
        raise TimeoutError(message) from exc
    except Exception as exc:
        notification_queue.queue(
            NotificationKind.NEGATIVE,
            f"OCR failed for page {page_index + 1}: {exc}",
        )
        log.warning(
            "load_page: OCR failed project=%s page=%d",
            project_id,
            page_index,
            exc_info=True,
        )
        raise

    _finalize_reocr_outcome(
        project_state,
        page_index,
        outcome,
        page_kind_sent=page_kind,
        page_store=runner.context.get("page_store"),
    )

    # Stage 3 — terminal "done" message, so the SSE terminal frame reads as
    # something other than the last progress message by coincidence.
    await runner.update_progress(
        job.job_id,
        current=_PROGRESS_TOTAL,
        total=_PROGRESS_TOTAL,
        message="Page loaded.",
    )

    log.info(
        "load_page: complete project=%s page=%d job=%s",
        project_id,
        page_index,
        job.job_id,
    )


__all__ = ["handle_load_page"]
