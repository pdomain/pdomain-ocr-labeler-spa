"""Pure version-chain derivation over ``ProvenanceGraph.history`` — undo/redo cursor model.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` §"Version-chain
derivation (the cursor model)".

Every page mutation persists a whole-page content blob and advances the
aggregate's provenance head (``core/page_state.py::save_page_content_to_store``).
Undo/redo is therefore *blob-version restore*: this module derives a linear
version chain + cursor from the append-only ``history`` list, and builds the
marker nodes that undo/redo append (head always moves forward; content moves
backward).

Rules:

- **Version node** — a history entry whose node has non-empty ``blob_refs``
  and no ``extra["history_op"]`` marker (the initial OCR root plus every real
  content-bearing edit).
- **Changelog-only nodes** (empty ``blob_refs``) are skipped — not restorable.
- **Real version after an undo truncates** the redo branch from the active
  chain (linear undo, U-5). Truncated nodes remain in the graph as data.
- **Marker ``op=undo`` / ``op=redo``** — cursor moves to the index of the
  recorded ``restores`` id (deterministic replay; no positional guessing).
- The OCR root node id appears **twice** in ``history`` (graph construction +
  ``ocr_completed`` both append it — ``adapters/ocr/local_doctr.py:196-220``);
  consecutive duplicate ids are deduped.
- **Depth cap** (U-8): at most ``depth`` undo steps back from the newest
  version are reachable; older versions remain in the store but stop being
  offered.

Pure functions only — no I/O, no store access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from pdomain_ops.pages import ProvenanceGraph, ProvenanceNode

DEFAULT_UNDO_DEPTH = 50
"""Default maximum number of undo steps offered (``PDLABELER_UNDO_DEPTH``)."""

HistoryOp = Literal["undo", "redo"]


@dataclass(frozen=True)
class HistoryState:
    """Derived linear version chain + cursor for one page aggregate.

    ``chain`` holds the node ids of the restorable versions on the *active*
    chain, oldest first. ``cursor`` indexes the currently-live version
    (``-1`` when the chain is empty). ``depth`` is the configured undo bound.
    """

    chain: tuple[str, ...]
    cursor: int
    depth: int

    @property
    def _floor(self) -> int:
        """Oldest chain index reachable via undo under the depth bound."""
        return max(0, len(self.chain) - 1 - self.depth)

    @property
    def undo_available(self) -> bool:
        return self.cursor > self._floor

    @property
    def redo_available(self) -> bool:
        return 0 <= self.cursor < len(self.chain) - 1

    def undo_target(self) -> str | None:
        """Node id of the version an undo would restore, or ``None``."""
        return self.chain[self.cursor - 1] if self.undo_available else None

    def redo_target(self) -> str | None:
        """Node id of the version a redo would restore, or ``None``."""
        return self.chain[self.cursor + 1] if self.redo_available else None


def _history_op_marker(node: ProvenanceNode) -> dict[str, Any] | None:
    """Return the ``history_op`` marker dict for *node*, or ``None``."""
    extra = node.extra
    if not isinstance(extra, dict):
        return None
    marker = extra.get("history_op")
    return marker if isinstance(marker, dict) else None


def derive_history(graph: ProvenanceGraph, *, depth: int = DEFAULT_UNDO_DEPTH) -> HistoryState:
    """Derive the active version chain + cursor from *graph* (pure, no I/O).

    Processes ``graph.history`` in order, applying the rules in the module
    docstring. Graphs written before this spec (no markers) degrade
    gracefully: every real version is on the chain, cursor at the end.
    """
    chain: list[str] = []
    cursor = -1
    prev_id: str | None = None
    for node_id in graph.history:
        if node_id == prev_id:
            # OCR-root double-entry (graph construction + ocr_completed).
            continue
        prev_id = node_id
        node = graph.nodes.get(node_id)
        if node is None:  # pragma: no cover - defensive
            continue
        marker = _history_op_marker(node)
        if marker is not None:
            restores = marker.get("restores")
            if isinstance(restores, str) and restores in chain:
                cursor = chain.index(restores)
            # Unknown / out-of-chain restores: leave the cursor put (robustness).
            continue
        if not node.blob_refs:
            # Changelog-only node — not a restorable state.
            continue
        # Real version: truncate the redo branch at the cursor, append, advance.
        del chain[cursor + 1 :]
        chain.append(node_id)
        cursor = len(chain) - 1
    return HistoryState(chain=tuple(chain), cursor=cursor, depth=depth)


def build_history_marker_node(
    *,
    op: HistoryOp,
    restores: str,
    undoes: str,
    restored_blob_hash: str,
    parent_id: str | None,
) -> ProvenanceNode:
    """Build the provenance node an undo/redo appends (spec §"Key design choice").

    The node carries ``blob_refs=[restored_blob_hash]`` (content-addressed —
    the hash already exists, zero duplication) so the head read path
    (``api/_page_content.py`` → ``head.blob_refs[0]``) resolves the restored
    content, plus the ``history_op`` marker that makes the derivation replay
    deterministic, plus ``parent_ids=[current head]`` so provenance honestly
    records that the revert happened *after* the state it reverts.
    """
    from pdomain_ops.pages import ProvenanceNode

    return ProvenanceNode(
        id=f"labeler-{op}-{uuid4()}",
        source="labeler",
        tool="labeler-spa",
        timestamp=datetime.now(UTC),
        blob_refs=[restored_blob_hash],
        extra={"history_op": {"op": op, "restores": restores, "undoes": undoes}},
        parent_ids=[parent_id] if parent_id is not None else [],
    )


__all__ = [
    "DEFAULT_UNDO_DEPTH",
    "HistoryOp",
    "HistoryState",
    "build_history_marker_node",
    "derive_history",
]
