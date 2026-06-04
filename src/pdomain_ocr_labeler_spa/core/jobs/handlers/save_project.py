"""save_project job handler — spec-23-B2 / issue #308.

Spec authority: ``specs/23-page-payload-backend.md §8``.

The handler iterates over every page in ``ProjectState.page_states``
that has ``generation > last_saved_generation``, calls
``persist_page_to_file`` on each, and reports per-page progress. On
``OSError`` the page is recorded as a ``SaveFailure`` and the loop
continues with the remaining pages — partial-failure semantics per
spec §8 ("emits ``save_project_done`` with ``failures:
list[SaveFailure]``"). Successful pages have their
``last_saved_generation`` advanced to the current ``generation`` so a
re-run is a no-op until the next mutation.

Handler entry-point: ``handle_save_project(runner, job)`` —
registered in ``core/jobs/runner._HANDLERS["save_project"]``.

Notifications side-effects go through ``NotificationQueue`` per spec 11
— one terminal notification (POSITIVE on clean run, NEGATIVE when any
failures are recorded) so the SPA can render a banner / toast without
streaming the per-page progress.

Failures list shape: the handler stashes the list on
``job.payload["failures"]`` so a follow-up ``GET /api/jobs/{id}``
caller can read it; the SSE stream also carries the failures
inline in the terminal event when emitted via
``JobRunner.update_progress`` (the runner's emit shape doesn't include
arbitrary payload fields today; this is documented as a follow-up and
the in-memory ``Job`` instance keeps the full list for any HTTP poller).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...notifications import NotificationKind, NotificationQueue
from ...page_state import (
    persist_page_to_file,
    save_page_content_to_store,
    save_page_to_store,
)
from ...project_state import ProjectState

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


def _get_required_context(
    runner: JobRunner,
) -> tuple[ProjectState, NotificationQueue, object, Any]:
    """Pull required carriers off ``runner.context``; raise if absent.

    Returns ``(project_state, notification_queue, settings, page_store)``.
    ``page_store`` may be ``None`` (no project loaded or store not wired).
    """
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    notification_queue = ctx.get("notification_queue")
    settings = ctx.get("settings")
    page_store = ctx.get("page_store")  # LabelerPageStore | None
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("save_project: runner.context['project_state'] is not wired")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("save_project: runner.context['notification_queue'] is not wired")
    if settings is None:
        raise RuntimeError("save_project: runner.context['settings'] is not wired")
    return project_state, notification_queue, settings, page_store


def _dirty_page_indices(project_state: ProjectState) -> list[int]:
    """Return the sorted list of page indices that need saving.

    A page is "dirty" when ``page_record is not None`` (something has
    been loaded / OCR'd / mutated for it) AND
    ``generation > last_saved_generation`` (it has a change pending
    persistence). Sorted for deterministic progress reporting.
    """
    dirty: list[int] = []
    for idx, pstate in project_state.page_states.items():
        if pstate.page_record is None:
            continue
        if pstate.generation > pstate.last_saved_generation:
            dirty.append(idx)
    dirty.sort()
    return dirty


async def handle_save_project(runner: JobRunner, job: Job) -> None:
    """Persist every dirty page in the active project to the labeled lane.

    Spec §8 contract. Iterates ``ProjectState.page_states``; for each
    dirty page calls ``persist_page_to_file`` and updates
    ``last_saved_generation``. On ``OSError`` the page is added to a
    failures list and the loop continues. The terminal job state is
    always ``complete`` (the runner converts uncaught exceptions to
    ``error``; we catch ``OSError`` per-page so partial failures don't
    abort the whole job).
    """
    project_state, notification_queue, _settings, page_store = _get_required_context(runner)
    project = project_state.loaded_project
    if project is None:
        # No project loaded → nothing to do. Treat as a clean no-op so
        # the job transitions to ``complete``. (The route layer already
        # 404s when no project is loaded, so this path is mostly
        # defensive against an out-of-band cancel/reload race.)
        await runner.update_progress(job.job_id, current=0, total=0, message="No project loaded")
        return

    dirty = _dirty_page_indices(project_state)
    total = len(dirty)

    log.info(
        "save_project: project=%s pages_dirty=%d job=%s",
        project.project_id,
        total,
        job.job_id,
    )

    if total == 0:
        await runner.update_progress(job.job_id, current=0, total=0, message="Nothing to save")
        notification_queue.queue(
            NotificationKind.POSITIVE,
            f"Project {project.project_id}: nothing to save.",
        )
        # Stash an empty failures list for HTTP pollers.
        job.payload["failures"] = []
        return

    failures: list[dict[str, Any]] = []
    completed = 0

    await runner.update_progress(job.job_id, current=0, total=total, message=f"Saving {total} page(s)")

    for page_index in dirty:
        pstate = project_state.page_states.get(page_index)
        if pstate is None or pstate.page_record is None:  # pragma: no cover - race-defense
            continue
        # Event-store save path: persist each dirty page to the store.
        # Skip pages without a registered page_id (not yet in the store —
        # no-op is safe; they'll be saved when OCR writes them to the store).
        if page_store is not None and pstate.page_id is not None:
            try:
                changes = [{"type": "save_project", "page_index": page_index}]
                # Prefer save_page_content_to_store so the edited Page is
                # re-serialized into a content blob.  save_page_to_store only
                # records a changelog entry (no blob_refs), which causes
                # load_page_from_store to return None after a fresh-store
                # reload — the #1 audit finding.  Fall back to
                # save_page_to_store only when no live Page object is
                # available (e.g. the page was marked dirty by a changelog-
                # only path with no cached payload).
                payload = pstate.page_record.payload if pstate.page_record is not None else None
                if payload is not None and callable(getattr(payload, "to_dict", None)):
                    save_page_content_to_store(
                        page_id=pstate.page_id,
                        page=payload,
                        store=page_store,
                        changes=changes,
                    )
                else:
                    # No live Page to re-serialize — record changelog only.
                    log.debug(
                        "save_project: page %d has no serializable payload — "
                        "falling back to changelog-only store write",
                        page_index,
                    )
                    save_page_to_store(
                        page_id=pstate.page_id,
                        changes=changes,
                        store=page_store,
                    )
            except Exception as exc:
                log.warning(
                    "save_project: store persist failed page=%d project=%s: %s",
                    page_index,
                    project.project_id,
                    exc,
                )
                failures.append({"page_index": page_index, "error": str(exc)})
                completed += 1
                await runner.update_progress(
                    job.job_id,
                    current=completed,
                    total=total,
                    message=f"Failed page {page_index + 1}/{total}",
                )
                continue
        elif page_store is None:
            # No store available — treat as clean success (in-memory only session).
            log.debug("save_project: no page_store in context — skipping store write for page %d", page_index)
        else:
            # page_id not set — page not yet registered in store, skip.
            log.debug("save_project: page %d has no page_id — skipping store write", page_index)
        pstate.last_saved_generation = pstate.generation

        completed += 1
        await runner.update_progress(
            job.job_id,
            current=completed,
            total=total,
            message=f"Saved page {page_index + 1}/{total}",
        )

    job.payload["failures"] = failures

    if failures:
        notification_queue.queue(
            NotificationKind.NEGATIVE,
            f"Save complete with {len(failures)} failure(s).",
        )
    else:
        notification_queue.queue(
            NotificationKind.POSITIVE,
            f"Saved {total} page(s) for project {project.project_id}.",
        )

    log.info(
        "save_project: complete project=%s saved=%d failed=%d job=%s",
        project.project_id,
        total - len(failures),
        len(failures),
        job.job_id,
    )


__all__ = ["handle_save_project", "persist_page_to_file"]
