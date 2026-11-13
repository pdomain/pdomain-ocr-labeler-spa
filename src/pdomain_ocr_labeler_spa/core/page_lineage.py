"""Page-slot lineage across a re-OCR or rotation boundary.

Spec: ``docs/specs/2026-06-12-event-store-undo.md`` section U-M6. The link
lives in ``extensions["labeler.lineage"]``. The view-state namespace
``extensions["labeler"]`` is left alone.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_ops.page_aggregate import PageAggregate

    from .persistence.page_store import LabelerPageStore

log = logging.getLogger(__name__)

LINEAGE_NAMESPACE = "labeler.lineage"
PROJECT_UUID_NAMESPACE = uuid.UUID("6f3c3d2a-1b4e-5a6c-8d7e-9f0a1b2c3d4e")
NIL_PAGE_ID = uuid.UUID(int=0)
BoundaryOp = Literal["reocr", "rotate"]


class PageLineage(BaseModel):
    """Durable link between the aggregate a slot left and the one it points at."""

    model_config = ConfigDict(extra="ignore")

    previous_page_id: str | None = None
    boundary_op: BoundaryOp | None = None
    superseded_by: str | None = None
    linked_at: str | None = None


def project_uuid_for(project_id: str) -> uuid.UUID:
    """Map a labeler project id to the same UUID the OCR ingest path uses."""
    return uuid.uuid5(PROJECT_UUID_NAMESPACE, project_id)


def lineage_of(aggregate: PageAggregate) -> PageLineage | None:
    """Return the lineage extension on *aggregate*, or ``None`` when it has none."""
    data = aggregate.record.extensions.get(LINEAGE_NAMESPACE)
    if not data:
        return None
    try:
        return PageLineage.model_validate(data)
    except ValidationError:
        return None


def _present(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def history_offers(
    *,
    undo_available: bool,
    redo_available: bool,
    cursor: int,
    chain_length: int,
    lineage: PageLineage | None,
) -> tuple[bool, bool]:
    """Add the one boundary step the intra-aggregate cursor cannot see.

    Undo is offered at cursor 0 when ``previous_page_id`` is set. Redo is
    offered at the chain end when ``superseded_by`` is set. An empty chain
    (cursor ``-1``) does not cross.
    """
    undo = undo_available
    redo = redo_available
    if lineage is None:
        return undo, redo
    if cursor == 0 and _present(lineage.previous_page_id) is not None:
        undo = True
    at_end = cursor >= 0 and cursor == chain_length - 1
    if at_end and _present(lineage.superseded_by) is not None:
        redo = True
    return undo, redo


def lineage_step_id(
    lineage: PageLineage | None,
    *,
    op: Literal["undo", "redo", "jump"],
    cursor: int,
    chain_length: int,
) -> uuid.UUID | None:
    """Return the aggregate id one boundary step would re-point at."""
    if lineage is None or op == "jump":
        return None
    if op == "undo":
        if cursor != 0:
            return None
        raw = _present(lineage.previous_page_id)
    else:
        at_end = cursor >= 0 and cursor == chain_length - 1
        if not at_end:
            return None
        raw = _present(lineage.superseded_by)
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def lineage_expired(
    lineage: PageLineage | None,
    *,
    now: datetime,
    retention: timedelta,
) -> bool:
    """Return whether an abandoned aggregate's retention window has closed.

    A missing ``linked_at`` stays inside retention. Prune must not guess.
    """
    if lineage is None or lineage.linked_at is None:
        return False
    try:
        linked = datetime.fromisoformat(lineage.linked_at)
    except ValueError:
        return False
    if linked.tzinfo is None:
        linked = linked.replace(tzinfo=UTC)
    return now >= linked + retention


def link_replacement(
    store: LabelerPageStore,
    *,
    project_id: str,
    new_aggregate: PageAggregate,
    page_index: int,
    boundary_op: BoundaryOp,
    now: datetime | None = None,
) -> None:
    """Link *new_aggregate* to the page aggregate currently in this slot.

    A first OCR, a NIL gap, or a slot that already points at this aggregate
    writes nothing. Replacing the old aggregate's namespace re-stamps
    ``superseded_by`` onto the newest successor and keeps that aggregate's
    own ``previous_page_id``.
    """
    from eventsourcing.application import AggregateNotFoundError

    try:
        project = store.get_project(project_uuid_for(project_id))
    except AggregateNotFoundError:
        return
    page_ids = list(project.record.page_ids)
    if page_index < 0 or page_index >= len(page_ids):
        return
    previous_id = page_ids[page_index]
    new_id = new_aggregate.record.page_id
    if previous_id in (NIL_PAGE_ID, new_id):
        return
    moment = (now if now is not None else datetime.now(UTC)).isoformat()
    try:
        previous = store.get_page(previous_id)
    except Exception:
        return
    previous_lineage = lineage_of(previous) or PageLineage()
    previous.set_extension(
        LINEAGE_NAMESPACE,
        previous_lineage.model_copy(update={"superseded_by": str(new_id), "linked_at": moment}),
    )
    store.save_page(previous)
    new_aggregate.set_extension(
        LINEAGE_NAMESPACE,
        PageLineage(
            previous_page_id=str(previous_id),
            boundary_op=boundary_op,
            linked_at=moment,
        ),
    )
    store.save_page(new_aggregate)


def retag_boundary_op(aggregate: PageAggregate, boundary_op: BoundaryOp) -> bool:
    """Record that an already-linked replacement was a rotation.

    No lineage means this aggregate is the slot's first OCR. The caller
    saves the aggregate after any other events it still has to append.
    """
    current = lineage_of(aggregate)
    if current is None or _present(current.previous_page_id) is None:
        return False
    if current.boundary_op == boundary_op:
        return False
    aggregate.set_extension(
        LINEAGE_NAMESPACE,
        current.model_copy(update={"boundary_op": boundary_op}),
    )
    return True


def walk_lineage(store: LabelerPageStore, start_ids: Sequence[uuid.UUID]) -> list[PageAggregate]:
    """Load every aggregate reachable from *start_ids* by one lineage step at a time."""
    seen: set[uuid.UUID] = set()
    found: list[PageAggregate] = []
    pending = list(start_ids)
    while pending:
        page_id = pending.pop()
        if page_id == NIL_PAGE_ID or page_id in seen:
            continue
        seen.add(page_id)
        try:
            aggregate = store.get_page(page_id)
        except Exception:
            log.debug("lineage walk skipped missing aggregate %s", page_id, exc_info=True)
            continue
        found.append(aggregate)
        lineage = lineage_of(aggregate)
        if lineage is None:
            continue
        for raw in (lineage.previous_page_id, lineage.superseded_by):
            present = _present(raw)
            if present is None:
                continue
            try:
                pending.append(uuid.UUID(present))
            except ValueError:
                continue
    return found
