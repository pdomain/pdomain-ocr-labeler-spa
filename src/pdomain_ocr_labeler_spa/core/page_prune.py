"""Conservative blob live-set for the U-M6 maintenance prune.

``BlobStore.prune_orphans`` deletes every file whose name is absent from the
set it is given. This module therefore starts from the files on disk and
subtracts only hashes the undo spec marks dead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .page_history import DEFAULT_UNDO_DEPTH, derive_dead_segments, derive_history
from .page_lineage import NIL_PAGE_ID, lineage_expired, lineage_of, project_uuid_for, walk_lineage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import ProvenanceNode

    from .persistence.page_store import LabelerPageStore


def _marker(node: ProvenanceNode) -> dict[str, object] | None:
    extra = node.extra
    if not isinstance(extra, dict):
        return None
    marker = extra.get("history_op")
    return marker if isinstance(marker, dict) else None


def _resolved_undo_depth(undo_depth: int) -> int:
    """Match undo's depth coercion: a non-positive value is the default of 50."""
    return undo_depth if undo_depth > 0 else DEFAULT_UNDO_DEPTH


def live_blob_names(
    *,
    blob_names: set[str],
    current_page_ids: set[uuid.UUID],
    aggregates: Sequence[PageAggregate],
    now: datetime,
    retention: timedelta,
    undo_depth: int,
) -> set[str]:
    """Return the blob names prune must keep.

    A content hash is dropped only when every node that names it as
    ``blob_refs[0]`` is prunable and the hash is not also an image or
    preprocess ref (``blob_refs[1:]``). Files no scanned node mentions stay.
    """
    image_hashes: set[str] = set()
    flags: dict[str, list[bool]] = {}

    def note_content(digest: str, *, prunable: bool) -> None:
        flags.setdefault(digest, []).append(prunable)

    for aggregate in aggregates:
        graph = aggregate.record.provenance
        if graph is None:
            continue
        is_current = aggregate.record.page_id in current_page_ids
        expired = (not is_current) and lineage_expired(lineage_of(aggregate), now=now, retention=retention)
        if not is_current:
            for node in graph.nodes.values():
                refs = node.blob_refs
                if not refs:
                    continue
                note_content(refs[0], prunable=expired)
                image_hashes.update(refs[1:])
            continue
        state = derive_history(graph, depth=_resolved_undo_depth(undo_depth))
        # Protect from the live cursor when a jump sits below the undo floor.
        # Cursor -1 is an empty chain; do not use chain[-1:].
        protected_from = min(state.cursor, state._floor) if state.cursor >= 0 else state._floor
        protected_chain = set(state.chain[protected_from:])
        below_floor = set(state.chain[:protected_from])
        expired_dead: set[str] = set()
        fresh_dead: set[str] = set()
        for segment in derive_dead_segments(graph, retention=retention, now=now):
            bucket = expired_dead if segment.branch.retain_until <= now else fresh_dead
            bucket.update(segment.node_ids)
        prunable_versions = (below_floor | expired_dead) - protected_chain
        for node_id, node in graph.nodes.items():
            refs = node.blob_refs
            if not refs:
                continue
            image_hashes.update(refs[1:])
            marker = _marker(node)
            if marker is not None:
                restores = marker.get("restores")
                note_content(
                    refs[0],
                    prunable=isinstance(restores, str) and restores in prunable_versions,
                )
                continue
            if node_id in protected_chain or node_id in fresh_dead:
                note_content(refs[0], prunable=False)
            elif node_id in prunable_versions:
                note_content(refs[0], prunable=True)
            else:
                note_content(refs[0], prunable=False)

    candidates = {
        digest for digest, bits in flags.items() if digest not in image_hashes and bool(bits) and all(bits)
    }
    return set(blob_names) - candidates


def _blobs_dir(store: LabelerPageStore) -> Path:
    return store.project_dir / ".pd-pages" / "blobs"


def _blob_names(store: LabelerPageStore) -> set[str]:
    blobs_dir = _blobs_dir(store)
    if not blobs_dir.is_dir():
        return set()
    return {path.name for path in blobs_dir.iterdir() if path.is_file() and not path.name.endswith(".tmp")}


def unlink_named_blobs(blobs_dir: Path, names: set[str]) -> list[str]:
    """Delete only these blob file names.

    A name that is not already a file in *blobs_dir* is left alone. That is
    what keeps a blob written after the candidate snapshot: it was never a
    candidate, so it is not in *names*.
    """
    deleted: list[str] = []
    if not blobs_dir.is_dir():
        return deleted
    for name in sorted(names):
        if name.endswith(".tmp") or name in {"", ".", ".."} or name != Path(name).name:
            continue
        path = blobs_dir / name
        if path.parent != blobs_dir or not path.is_file():
            continue
        path.unlink()
        deleted.append(name)
    return deleted


def prune_store(
    store: LabelerPageStore,
    project_id: str,
    *,
    now: datetime | None = None,
    retention_days: int,
    undo_depth: int,
) -> list[str]:
    """Delete only the hashes ``live_blob_names`` marks dead. Never raises on a missing project."""
    moment = now if now is not None else datetime.now(UTC)
    try:
        project = store.get_project(project_uuid_for(project_id))
    except Exception:
        return []
    snapshot = _blob_names(store)
    start = [page_id for page_id in project.record.page_ids if page_id != NIL_PAGE_ID]
    aggregates = walk_lineage(store, start)
    live = live_blob_names(
        blob_names=snapshot,
        current_page_ids=set(start),
        aggregates=aggregates,
        now=moment,
        retention=timedelta(days=retention_days),
        undo_depth=undo_depth,
    )
    # Unlink only names in the snapshot. ``prune_orphans`` would also delete
    # a blob created while history was replayed, because that name is absent
    # from the keep set.
    return unlink_named_blobs(_blobs_dir(store), snapshot - live)
