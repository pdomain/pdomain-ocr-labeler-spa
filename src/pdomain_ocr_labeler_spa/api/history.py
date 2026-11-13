"""``.../undo|redo|jump`` + ``.../history/versions`` — per-page undo/redo/jump.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` (slice H-B,
U-M7 "history panel + jump-to-version").

Undo/redo/jump are all blob-version restore: each operation APPENDS a new
``LabelerEdited`` event whose provenance node re-points the head at an
existing content blob (``core/page_history.build_history_marker_node``).
No event is ever deleted or rewritten — the head always moves forward
while content moves backward. Cross-session durability falls out for
free: the marker node's ``blob_refs[0]`` is what the restart read path
(``api/_page_content.py`` → ``head.blob_refs[0]``) resolves.

``GET .../history/versions`` is the read-only counterpart: it derives the
same active chain undo/redo/jump already agree on
(``core/page_history.build_version_list``) and never mutates anything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_tools.ocr.page import Page
from pydantic import BaseModel

from ..core.labeler_sidecars import LabelerSidecars, apply_sidecars_to_page_state
from ..core.models import PageSource
from ..core.page_history import HistoryOp, build_history_marker_node, build_version_list, derive_history
from ..core.page_kind.reviewed_store import PageKindReviewedStore
from ..core.page_lineage import lineage_of, lineage_step_id, project_uuid_for
from ..core.page_state import PageLoadOutcome
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..core.review_counts import append_word_review_counts_best_effort
from ..settings import Settings
from .dependencies import (
    bind_page_labeling_lease,
    get_app_config,
    get_page_store_optional,
    get_project_state,
    get_settings,
)
from .middleware.error_handler import ApiError
from .pages import (
    PagePayload,
    _check_project_and_page,
    _page_payload,
    _resolve_page_object_for_pages,
    _resolve_undo_depth,
)

if TYPE_CHECKING:
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import ProvenanceGraph

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/pages",
    tags=["pages"],
    dependencies=[Depends(bind_page_labeling_lease)],
)


class HistoryVersionInfo(BaseModel):
    """One row of the U-M7 history panel — spec §"API surface".

    Read-only wire shape for ``GET .../history/versions``; mirrors
    ``core.page_history.VersionEntry`` field-for-field. ``timestamp`` is
    ``None`` only for the OCR-ingest root row — see ``VersionEntry``.
    """

    node_id: str
    label: str
    timestamp: datetime | None
    is_current: bool


class JumpRequest(BaseModel):
    """Body of ``POST .../jump`` — spec §"Jump-to-version semantics"."""

    node_id: str


def _history_conflict(error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ApiError(error=error, message=message).model_dump(),
    )


def _read_restored_page(
    store: LabelerPageStore,
    restored_hash: str,
    *,
    op: HistoryOp,
    page_index: int,
) -> tuple[Page, LabelerSidecars] | JSONResponse:
    """Read a content blob into a ``Page`` plus its sidecar payload."""
    try:
        from ..core.labeler_sidecars import parse_content_blob, stamp_sidecars_on_page

        page_bytes = store.blobs.read(restored_hash)
        page_dict, restored_sidecars = parse_content_blob(page_bytes)
        restored_page = Page.from_dict(page_dict)
        stamp_sidecars_on_page(restored_page, restored_sidecars)
    except Exception as exc:
        log.exception("%s: restore blob read failed for page=%d", op, page_index)
        return JSONResponse(
            status_code=500,
            content=ApiError(
                error="restore_failed",
                message=f"failed to read restored content for page {page_index}: {exc}",
            ).model_dump(),
        )
    return restored_page, restored_sidecars


def _path_within(child: Path, parent: Path) -> bool:
    """Return True when *child* is *parent* or a file inside it."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _boundary_op(aggregate: PageAggregate) -> str | None:
    lineage = lineage_of(aggregate)
    if lineage is None:
        return None
    return lineage.boundary_op


def _crossing_restores_image(op: HistoryOp, current_agg: PageAggregate, target_agg: PageAggregate) -> bool:
    """Restore the source image only for the rotation boundary this step crosses.

    Undo leaves the current aggregate, so that aggregate's ``boundary_op``
    decides. Redo enters the target, so the target's ``boundary_op`` decides.
    A re-OCR step does not rewrite the file, even when its neighbor was born
    from a rotation.
    """
    if op == "undo":
        return _boundary_op(current_agg) == "rotate"
    if op == "redo":
        return _boundary_op(target_agg) == "rotate"
    return False


def _generation_image_hash(graph: ProvenanceGraph | None) -> str | None:
    """Return the OCR image hash for one aggregate.

    An edit after OCR stores only the page JSON on the new head. The image
    hash stays on the ingest node (``blob_refs[1]``).
    """
    if graph is None:
        return None
    fallback: str | None = None
    for node in graph.nodes.values():
        refs = node.blob_refs
        if len(refs) < 2:
            continue
        if node.source == "ocr":
            return refs[1]
        if fallback is None:
            fallback = refs[1]
    return fallback


def _write_bytes_atomically(path: Path, data: bytes) -> None:
    """Replace *path* with *data*. The previous file stays until the replace."""
    temporary = path.with_name(f".{path.name}.labeler-restore")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _replace_image_then(path: Path, data: bytes, save: Callable[[], None]) -> None:
    """Write *data* to *path*, run *save*, and put the old bytes back if *save* fails."""
    previous = path.read_bytes() if path.is_file() else None
    _write_bytes_atomically(path, data)
    try:
        save()
    except Exception:
        try:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                _write_bytes_atomically(path, previous)
        except Exception:
            log.exception("rotate image rollback failed for %s", path)
        raise


def _restore_failed(page_index: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiError(
            error="restore_failed",
            message=f"failed to restore the rotated image for page {page_index}: {detail}",
        ).model_dump(),
    )


def _restore_rotate_image(
    *,
    store: LabelerPageStore,
    image_hash: str,
    image_path: Path,
    project_root: Path,
    op: HistoryOp,
    page_index: int,
    save: Callable[[], None],
) -> JSONResponse | None:
    """Write the target aggregate's OCR image blob onto the source path, then save the slot.

    A re-OCR cross does not call this. The image URL is unchanged. If the slot
    save fails, the previous file bytes are written back.
    """
    if image_hash != Path(image_hash).name or image_hash in {"", ".", ".."}:
        log.warning("%s: rotate image hash is not a blob name page=%d", op, page_index)
        return _restore_failed(page_index, "image hash is not a blob name")
    resolved = image_path.resolve()
    root = project_root.resolve()
    if not _path_within(resolved, root):
        log.warning("%s: rotate image path is outside the project page=%d", op, page_index)
        return _restore_failed(page_index, "image path is outside the project")
    try:
        data = store.blobs.read(image_hash)
    except Exception as exc:
        log.exception("%s: rotate image blob read failed page=%d", op, page_index)
        return _restore_failed(page_index, str(exc))
    try:
        _replace_image_then(resolved, data, save)
    except Exception as exc:
        log.exception("%s: rotate image restore failed page=%d", op, page_index)
        return _restore_failed(page_index, str(exc))
    return None


def _restore_lineage_step(
    *,
    store: LabelerPageStore,
    op: HistoryOp,
    project_id: str,
    page_index: int,
    current_page_id: UUID,
    target_page_id: UUID,
    current_agg: PageAggregate,
    image_path: Path | None,
    project_root: Path,
) -> tuple[str, Page, LabelerSidecars, UUID] | JSONResponse:
    """Re-point the project slot at *target_page_id* and load that aggregate's head.

    The content blob is read before ``PageReordered`` is saved. A missing blob
    leaves the slot where it was. The durable record is ``PageReordered``.
    This path does not append a ``labeler_edited`` marker on either aggregate.
    """
    try:
        target_agg = store.get_page(target_page_id)
    except Exception:
        log.debug("%s: lineage aggregate missing page_id=%s", op, target_page_id)
        return _history_conflict(f"{op}_unavailable", f"nothing to {op} for page {page_index}")
    target_graph = target_agg.record.provenance
    head = target_graph.head if target_graph is not None else None
    if head is None or not head.blob_refs:
        return _history_conflict(f"{op}_unavailable", f"nothing to {op} for page {page_index}")
    try:
        project_agg = store.get_project(project_uuid_for(project_id))
    except Exception:
        log.debug("%s: project aggregate missing for lineage cross project=%s", op, project_id)
        return _history_conflict(f"{op}_unavailable", f"nothing to {op} for page {page_index}")
    page_ids = list(project_agg.record.page_ids)
    if current_page_id in page_ids:
        slot = page_ids.index(current_page_id)
    elif 0 <= page_index < len(page_ids):
        slot = page_index
    else:
        return _history_conflict(f"{op}_unavailable", f"nothing to {op} for page {page_index}")
    loaded = _read_restored_page(store, head.blob_refs[0], op=op, page_index=page_index)
    if isinstance(loaded, JSONResponse):
        return loaded
    restored_page, restored_sidecars = loaded
    rotate_cross = _crossing_restores_image(op, current_agg, target_agg)
    image_hash = _generation_image_hash(target_graph) if rotate_cross else None

    def _save_slot() -> None:
        page_ids[slot] = target_page_id
        project_agg.reorder_pages(page_ids)
        store.save_project(project_agg)

    if rotate_cross and image_path is not None and image_hash is not None:
        image_error = _restore_rotate_image(
            store=store,
            image_hash=image_hash,
            image_path=image_path,
            project_root=project_root,
            op=op,
            page_index=page_index,
            save=_save_slot,
        )
        if image_error is not None:
            return image_error
    else:
        if rotate_cross:
            log.warning("%s: rotate boundary has no source image to restore page=%d", op, page_index)
        _save_slot()
    return head.blob_refs[0], restored_page, restored_sidecars, target_page_id


def _execute_history_op(
    *,
    op: HistoryOp,
    project_id: str,
    page_index: int,
    project_state: ProjectState,
    settings: Settings,
    app_config: AppConfig,
    store: LabelerPageStore | None,
    jump_target_node_id: str | None = None,
) -> JSONResponse:
    """Shared undo/redo/jump implementation (spec §"Version-chain derivation").

    1. Derive the version chain + cursor from the aggregate's provenance.
    2. 409 when the requested step is unavailable (bounds / depth / no store;
       for ``jump``, when ``jump_target_node_id`` is not on the active chain
       — U-M7 "409 when the target is not in the active chain").
    3. Read the restored blob, rebuild the ``Page``.
    4. Append the marker ``LabelerEdited`` event (head moves forward,
       content moves backward) — U-9: the changelog records the op.
    5. Swap the in-memory ``PageState`` payload, re-stamp ``_labeler_page_id``,
       bump generations (page + project, so SSE consumers refresh).

    Steps 1-5 all run under this page's lock (spec §13, same discipline as
    ``_confirm_page_kind_locked``): a confirm racing an undo/redo must not
    read ``prior_kind`` or the aggregate mid-restore, and must not land
    between the marker write and the in-memory swap — either of those would
    let the page blob's kind and the latest reviewed marker disagree.
    ``ProjectState.get_page_lock`` is a re-entrant ``threading.RLock`` (it has
    to be — ``_page_payload`` below also takes it), but this block still
    releases it before calling ``_page_payload`` rather than nesting: nothing
    here needs a second acquisition, and doing the restore work itself
    outside the lock would let a concurrent read observe a half-restored
    page.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    if project is None:  # _check_project_and_page guarantees; explicit to survive -O
        raise RuntimeError("project is None after _check_project_and_page passed — invariant violated")

    pstate = project_state.get_page_state(page_index)
    if store is None or pstate is None or pstate.page_id is None:
        return _history_conflict(
            "history_unavailable",
            f"page {page_index} has no event-store history; load the page first",
        )

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        page_id = pstate.page_id
        prior_page = _resolve_page_object_for_pages(pstate)
        prior_kind = prior_page.page_kind if prior_page is not None else None

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
        if op == "undo":
            target = state.undo_target()
        elif op == "redo":
            target = state.redo_target()
        else:
            target = state.jump_target(jump_target_node_id) if jump_target_node_id is not None else None
        lineage_page_id = (
            lineage_step_id(
                lineage_of(agg),
                op=op,
                cursor=state.cursor,
                chain_length=len(state.chain),
            )
            if target is None
            else None
        )
        if target is None and lineage_page_id is None:
            message = (
                f"target {jump_target_node_id!r} is not in the active chain for page {page_index}"
                if op == "jump"
                else f"nothing to {op} for page {page_index}"
            )
            return _history_conflict(f"{op}_unavailable", message)

        if lineage_page_id is not None:
            source_image: Path | None = None
            try:
                source_image = project_state.labeling_image_path(page_index)
            except (ValueError, IndexError, OSError):
                source_image = None
            restored = _restore_lineage_step(
                store=store,
                op=op,
                project_id=project.project_id,
                page_index=page_index,
                current_page_id=page_id,
                target_page_id=lineage_page_id,
                current_agg=agg,
                image_path=source_image,
                project_root=Path(project.project_root),
            )
            if isinstance(restored, JSONResponse):
                return restored
            restored_hash, restored_page, restored_sidecars, active_page_id = restored
        else:
            if target is None:  # pragma: no cover - lineage_page_id covers this
                return _history_conflict(f"{op}_unavailable", f"nothing to {op} for page {page_index}")
            current = state.chain[state.cursor]
            target_node = graph.nodes.get(target)
            if target_node is None or not target_node.blob_refs:  # pragma: no cover - chain invariant
                return _history_conflict(
                    "history_unavailable",
                    f"restore target {target!r} has no content blob",
                )
            restored_hash = target_node.blob_refs[0]
            loaded = _read_restored_page(store, restored_hash, op=op, page_index=page_index)
            if isinstance(loaded, JSONResponse):
                return loaded
            restored_page, restored_sidecars = loaded
            # Append the marker event — the durable record of the revert (U-9).
            # A boundary cross does not: the PageReordered event is that record.
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
            active_page_id = page_id

        # pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
        # review-next.md "A per-page count journal": undo/redo restores an
        # existing blob as the new head without going through
        # ``save_page_content_to_store``, so it must append its own counts
        # row here or the journal's newest row for this page keeps
        # describing content the page no longer has — overstating
        # completion once the restored content has fewer validated words
        # than what was last saved. Counts from ``restored_page`` itself,
        # the content this call just made current.
        append_word_review_counts_best_effort(page=restored_page, store=store, content_hash=restored_hash)

        # pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
        # "An undo or redo that changes the kind writes a marker too": the
        # restored blob can carry an earlier (or no) kind, and without a marker
        # here the reviewed journal would keep the kind the undo just removed.
        # Appended after the page save above succeeds, the order confirm_page_kind
        # already uses. A ``None`` restored kind withdraws the review — see
        # ``PageKindReviewedMarker``. A failed append logs a warning; the page
        # change already happened and this route still returns its result.
        new_kind = restored_page.page_kind
        if new_kind != prior_kind:
            try:
                PageKindReviewedStore(project.project_root).mark_reviewed(
                    page_index,
                    datetime.now(UTC).isoformat(),
                    kind=new_kind,
                    method="history",
                )
            except Exception:
                log.warning(
                    "%s: page-kind reviewed-marker append failed for page=%d", op, page_index, exc_info=True
                )

        # Swap the in-memory payload; re-stamp the aggregate id so subsequent
        # mutations target the aggregate this step landed on (the same stamp
        # discipline as the restart read path). A boundary cross changes that
        # id. Wave 0.1: rehydrate char sidecars from the restored blob so maps
        # never overlay a different content version after undo/redo.
        object.__setattr__(restored_page, "_labeler_page_id", active_page_id)
        pstate.page_id = active_page_id
        pstate.page_record = PageLoadOutcome(
            page_index=page_index,
            source=PageSource.FILESYSTEM,
            payload=restored_page,
        )
        apply_sidecars_to_page_state(pstate, restored_sidecars)
        pstate.generation += 1
    # Bump the project-state generation so SSE consumers refresh. Outside the
    # page lock — ``set_page_state`` only takes the project lock, and no other
    # path takes the project lock before a page lock (see reload_ocr's
    # ``_finalize_reocr_outcome``), so this ordering is deadlock-free either way.
    project_state.set_page_state(page_index, pstate)

    # ``page_store=store`` so ``_page_payload`` both reads the image/rotation/
    # region facets this route was previously (silently) omitting and stamps
    # ``history`` itself, under its own lock acquisition — this call happens
    # after the ``with page_lock:`` block above has already released the
    # lock, so a mutation from another request could land here before this
    # fix; now it can't split word counts from ``history`` in the response
    # (2026-09-18 page-history-consistency fix — same race ``get_page`` had).
    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/{page_index}/undo", response_model=PagePayload)
def undo_page(
    *,
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
    *,
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


@router.post("/{page_index}/jump", response_model=PagePayload)
def jump_page(
    *,
    project_id: str,
    page_index: int,
    body: JumpRequest,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    app_config: AppConfig = Depends(get_app_config),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),  # pyright: ignore[reportCallInDefaultInitializer]
) -> JSONResponse:
    """``POST .../jump`` — restore an arbitrary version on the active chain (U-15).

    Same mechanism as undo/redo (spec §"Jump-to-version semantics"): appends
    a ``history_op`` marker with ``op="jump"``, so it is exactly as
    append-only and auditable as undo/redo — never a rewrite of history.
    409 ``jump_unavailable`` when ``body.node_id`` is not on the active
    chain (truncated by a prior real edit, or never existed).
    """
    return _execute_history_op(
        op="jump",
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        store=store,
        jump_target_node_id=body.node_id,
    )


@router.get("/{page_index}/history/versions", response_model=list[HistoryVersionInfo])
def get_history_versions(
    *,
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),  # pyright: ignore[reportCallInDefaultInitializer]
) -> JSONResponse:
    """``GET .../history/versions`` — read-only version list for the history panel (U-14).

    Never mutates anything: reads the same provenance graph undo/redo/jump
    read, under the same per-page lock (consistency with any concurrent
    mutation), and returns ``[]`` whenever there is nothing to show (no
    project/page mismatch aside — that still 404s) rather than a 409, since
    an empty list is a normal, valid answer for a GET.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    if store is None or pstate is None or pstate.page_id is None:
        return JSONResponse(status_code=200, content=[])

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        try:
            agg = store.get_page(pstate.page_id)
        except Exception:
            log.debug("get_history_versions: aggregate load failed for page_id=%s", pstate.page_id)
            return JSONResponse(status_code=200, content=[])
        graph = agg.record.provenance
        if graph is None:
            return JSONResponse(status_code=200, content=[])
        versions = build_version_list(graph, agg.record.changelog, depth=_resolve_undo_depth(settings))

    body = [
        HistoryVersionInfo(
            node_id=v.node_id,
            label=v.label,
            timestamp=v.timestamp,
            is_current=v.is_current,
        ).model_dump(mode="json")
        for v in versions
    ]
    return JSONResponse(status_code=200, content=body)


def install_history_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the history router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "HistoryVersionInfo",
    "JumpRequest",
    "get_history_versions",
    "install_history_router",
    "jump_page",
    "redo_page",
    "router",
    "undo_page",
]
