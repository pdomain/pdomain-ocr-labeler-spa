"""``POST /api/projects/{project_id}/pages/{page_index}/undo|redo`` — per-page undo/redo.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` (slice H-B).

Undo/redo is blob-version restore: each operation APPENDS a new
``LabelerEdited`` event whose provenance node re-points the head at an
existing content blob (``core/page_history.build_history_marker_node``).
No event is ever deleted or rewritten — the head always moves forward
while content moves backward. Cross-session durability falls out for
free: the marker node's ``blob_refs[0]`` is what the restart read path
(``api/_page_content.py`` → ``head.blob_refs[0]``) resolves.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..core.models import PageSource
from ..core.page_history import HistoryOp, build_history_marker_node, derive_history
from ..core.page_state import PageLoadOutcome
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import (
    get_app_config,
    get_page_store_optional,
    get_project_state,
    get_settings,
)
from .middleware.error_handler import ApiError
from .pages import (
    PagePayload,
    _build_history_info,
    _check_project_and_page,
    _page_payload,
    _resolve_undo_depth,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/pages",
    tags=["pages"],
)


def _history_conflict(error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ApiError(error=error, message=message).model_dump(),
    )


def _execute_history_op(
    *,
    op: HistoryOp,
    project_id: str,
    page_index: int,
    project_state: ProjectState,
    settings: Settings,
    app_config: AppConfig,
    store: LabelerPageStore | None,
) -> JSONResponse:
    """Shared undo/redo implementation (spec §"Version-chain derivation").

    1. Derive the version chain + cursor from the aggregate's provenance.
    2. 409 when the requested step is unavailable (bounds / depth / no store).
    3. Read the restored blob, rebuild the ``Page``.
    4. Append the marker ``LabelerEdited`` event (head moves forward,
       content moves backward) — U-9: the changelog records the op.
    5. Swap the in-memory ``PageState`` payload, re-stamp ``_labeler_page_id``,
       bump generations (page + project, so SSE consumers refresh).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    if store is None or pstate is None or pstate.page_id is None:
        return _history_conflict(
            "history_unavailable",
            f"page {page_index} has no event-store history; load the page first",
        )
    page_id = pstate.page_id

    try:
        agg = store.get_page(page_id)
    except Exception:
        log.debug("%s: aggregate load failed for page_id=%s", op, page_id)
        return _history_conflict(
            "history_unavailable",
            f"page {page_index} has no event-store history; load the page first",
        )
    graph = agg.record.provenance
    if graph is None:
        return _history_conflict(
            "history_unavailable",
            f"page {page_index} has no provenance graph",
        )

    depth = _resolve_undo_depth(settings)
    state = derive_history(graph, depth=depth)
    target = state.undo_target() if op == "undo" else state.redo_target()
    if target is None:
        return _history_conflict(
            f"{op}_unavailable",
            f"nothing to {op} for page {page_index}",
        )
    current = state.chain[state.cursor]

    target_node = graph.nodes.get(target)
    if target_node is None or not target_node.blob_refs:  # pragma: no cover - chain invariant
        return _history_conflict(
            "history_unavailable",
            f"restore target {target!r} has no content blob",
        )
    restored_hash = target_node.blob_refs[0]

    try:
        from pdomain_book_tools.ocr.page import Page

        page_bytes = store.blobs.read(restored_hash)
        restored_page = Page.from_dict(json.loads(page_bytes.decode("utf-8")))
    except Exception as exc:
        log.exception("%s: restore blob read failed for page=%d", op, page_index)
        return JSONResponse(
            status_code=500,
            content=ApiError(
                error="restore_failed",
                message=f"failed to read restored content for page {page_index}: {exc}",
            ).model_dump(),
        )

    # Append the marker event — the durable record of the revert (U-9).
    marker = build_history_marker_node(
        op=op,
        restores=target,
        undoes=current,
        restored_blob_hash=restored_hash,
        parent_id=graph.head_id,
    )
    agg.labeler_edited(
        provenance_node=marker,
        changes=[{"type": op, "restores": target, "undoes": current}],
    )
    store.save_page(agg)

    # Swap the in-memory payload under the per-page lock; re-stamp the
    # aggregate id so subsequent mutations target the same aggregate
    # (same stamp discipline as the restart read path, local_doctr.py:374).
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        object.__setattr__(restored_page, "_labeler_page_id", page_id)
        pstate.page_record = PageLoadOutcome(
            page_index=page_index,
            source=PageSource.FILESYSTEM,
            payload=restored_page,
        )
        pstate.generation += 1
    # Bump the project-state generation so SSE consumers refresh.
    project_state.set_page_state(page_index, pstate)

    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )
    payload.history = _build_history_info(store, page_id, depth=depth)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/{page_index}/undo", response_model=PagePayload)
def undo_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    app_config: AppConfig = Depends(get_app_config),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),  # pyright: ignore[reportCallInDefaultInitializer]
) -> JSONResponse:
    """``POST .../undo`` — restore the previous version (U-1).

    409 ``undo_unavailable`` at the oldest reachable version (bounds or the
    ``PDLABELER_UNDO_DEPTH`` floor); 409 ``history_unavailable`` when no
    event store / aggregate is wired.
    """
    return _execute_history_op(
        op="undo",
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        store=store,
    )


@router.post("/{page_index}/redo", response_model=PagePayload)
def redo_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    app_config: AppConfig = Depends(get_app_config),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),  # pyright: ignore[reportCallInDefaultInitializer]
) -> JSONResponse:
    """``POST .../redo`` — re-apply the next version (U-2).

    409 ``redo_unavailable`` at the newest version.
    """
    return _execute_history_op(
        op="redo",
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        store=store,
    )


def install_history_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the history router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "install_history_router",
    "redo_page",
    "router",
    "undo_page",
]
