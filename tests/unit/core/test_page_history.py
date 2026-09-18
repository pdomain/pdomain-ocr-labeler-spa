"""Slice H-A — pure version-chain derivation over ``ProvenanceGraph.history``.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` §"Version-chain
derivation (the cursor model)":

- Version node = history entry with non-empty ``blob_refs`` and no
  ``extra.history_op`` marker.
- Changelog-only nodes (empty ``blob_refs``) are skipped.
- A real version after an undo truncates the redo branch (linear undo, U-5).
- ``op=undo`` / ``op=redo`` markers move the cursor to the recorded
  ``restores`` id.
- The OCR root node id appears twice in ``history`` (graph construction +
  ``ocr_completed`` both append it — ``adapters/ocr/local_doctr.py:196-220``);
  consecutive duplicates must be deduped.
- Depth cap: at most ``depth`` undo steps from the newest version (U-8).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pdomain_ops.pages import PageChangeEntry, ProvenanceGraph, ProvenanceNode

from pdomain_ocr_labeler_spa.core.page_history import (
    DEFAULT_UNDO_DEPTH,
    HistoryState,
    build_history_marker_node,
    build_version_list,
    derive_history,
)

# ── Graph builders ───────────────────────────────────────────────────────────


def _version_node(node_id: str, blob: str = "") -> ProvenanceNode:
    return ProvenanceNode(
        id=node_id,
        source="labeler",
        tool="labeler-spa",
        blob_refs=[blob or f"blob-{node_id}"],
    )


def _changelog_node(node_id: str) -> ProvenanceNode:
    return ProvenanceNode(id=node_id, source="labeler", tool="labeler-spa", blob_refs=[])


def _marker_node(node_id: str, *, op: str, restores: str, undoes: str, blob: str) -> ProvenanceNode:
    return ProvenanceNode(
        id=node_id,
        source="labeler",
        tool="labeler-spa",
        blob_refs=[blob],
        extra={"history_op": {"op": op, "restores": restores, "undoes": undoes}},
    )


def _fresh_ocr_graph() -> ProvenanceGraph:
    """Mirror ``_ingest_ocr_result``: the root id lands in history TWICE."""
    root = ProvenanceNode(id="root", source="ocr", tool="doctr", blob_refs=["blob-root", "blob-img"])
    graph = ProvenanceGraph(nodes={root.id: root}, head_id=root.id, history=[root.id])
    # ocr_completed → _apply_node → add_node appends the same id again.
    graph.add_node(root)
    return graph


def _graph_with_edits(n: int) -> ProvenanceGraph:
    graph = _fresh_ocr_graph()
    for i in range(n):
        graph.add_node(_version_node(f"edit-{i}"))
    return graph


# ── Fresh OCR / empty graphs ─────────────────────────────────────────────────


def test_fresh_ocr_graph_tolerates_root_double_entry() -> None:
    state = derive_history(_fresh_ocr_graph(), depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ("root",)
    assert state.cursor == 0
    assert state.undo_available is False
    assert state.redo_available is False


def test_empty_graph_has_no_history() -> None:
    state = derive_history(ProvenanceGraph(), depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ()
    assert state.cursor == -1
    assert state.undo_available is False
    assert state.redo_available is False
    assert state.undo_target() is None
    assert state.redo_target() is None


# ── Linear edits ─────────────────────────────────────────────────────────────


def test_n_edits_cursor_at_end() -> None:
    state = derive_history(_graph_with_edits(3), depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ("root", "edit-0", "edit-1", "edit-2")
    assert state.cursor == 3
    assert state.undo_available is True
    assert state.redo_available is False
    assert state.undo_target() == "edit-1"
    assert state.redo_target() is None


def test_legacy_graph_without_markers_degrades_gracefully() -> None:
    """Graphs written before this spec (no markers): all real versions, cursor at end."""
    state = derive_history(_graph_with_edits(2), depth=DEFAULT_UNDO_DEPTH)
    assert state.cursor == len(state.chain) - 1
    assert state.undo_available is True


# ── Changelog-only nodes ─────────────────────────────────────────────────────


def test_changelog_only_nodes_are_skipped() -> None:
    graph = _graph_with_edits(1)
    graph.add_node(_changelog_node("changelog-1"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ("root", "edit-0")
    assert state.cursor == 1


# ── Undo / redo markers ──────────────────────────────────────────────────────


def test_undo_marker_moves_cursor_to_restores_id() -> None:
    graph = _graph_with_edits(2)  # chain: root, edit-0, edit-1
    graph.add_node(_marker_node("undo-1", op="undo", restores="edit-0", undoes="edit-1", blob="blob-edit-0"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ("root", "edit-0", "edit-1")
    assert state.cursor == 1
    assert state.undo_available is True
    assert state.redo_available is True
    assert state.undo_target() == "root"
    assert state.redo_target() == "edit-1"


def test_redo_marker_moves_cursor_forward() -> None:
    graph = _graph_with_edits(2)
    graph.add_node(_marker_node("undo-1", op="undo", restores="edit-0", undoes="edit-1", blob="blob-edit-0"))
    graph.add_node(_marker_node("redo-1", op="redo", restores="edit-1", undoes="edit-0", blob="blob-edit-1"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    assert state.cursor == 2
    assert state.undo_available is True
    assert state.redo_available is False


def test_marker_with_unknown_restores_is_ignored() -> None:
    """Robustness: a marker pointing outside the active chain leaves the cursor put."""
    graph = _graph_with_edits(1)
    graph.add_node(_marker_node("undo-x", op="undo", restores="nonexistent", undoes="edit-0", blob="b"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    assert state.cursor == 1
    assert state.chain == ("root", "edit-0")


# ── Linear truncation (U-5) ──────────────────────────────────────────────────


def test_real_edit_after_undo_truncates_redo_branch() -> None:
    """Edit A → edit B → undo (back to A) → edit C: B leaves the active chain."""
    graph = _fresh_ocr_graph()
    graph.add_node(_version_node("A"))
    graph.add_node(_version_node("B"))
    graph.add_node(_marker_node("undo-1", op="undo", restores="A", undoes="B", blob="blob-A"))
    graph.add_node(_version_node("C"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    assert state.chain == ("root", "A", "C")
    assert state.cursor == 2
    assert state.redo_available is False
    assert state.undo_target() == "A"


# ── Depth cap (U-8) ──────────────────────────────────────────────────────────


def test_depth_cap_limits_undo_steps() -> None:
    graph = _graph_with_edits(5)  # chain length 6 (root + 5)
    state = derive_history(graph, depth=2)
    assert state.cursor == 5
    assert state.undo_available is True
    # Walk the cursor back the allowed 2 steps: floor reached, undo stops.
    floor_state = HistoryState(chain=state.chain, cursor=3, depth=2)
    assert floor_state.undo_available is False
    assert floor_state.undo_target() is None
    mid_state = HistoryState(chain=state.chain, cursor=4, depth=2)
    assert mid_state.undo_available is True


def test_depth_default_is_50() -> None:
    assert DEFAULT_UNDO_DEPTH == 50


# ── Marker-node builder ──────────────────────────────────────────────────────


def test_build_history_marker_node_shape() -> None:
    node = build_history_marker_node(
        op="undo",
        restores="edit-0",
        undoes="edit-1",
        restored_blob_hash="blob-edit-0",
        parent_id="edit-1",
    )
    assert node.source == "labeler"
    assert node.tool == "labeler-spa"
    assert node.blob_refs == ["blob-edit-0"]
    assert node.extra == {"history_op": {"op": "undo", "restores": "edit-0", "undoes": "edit-1"}}
    assert node.parent_ids == ["edit-1"]
    assert node.timestamp is not None
    assert node.id  # non-empty, unique-ish


def test_build_history_marker_node_ids_are_unique() -> None:
    a = build_history_marker_node(op="redo", restores="x", undoes="y", restored_blob_hash="b", parent_id=None)
    b = build_history_marker_node(op="redo", restores="x", undoes="y", restored_blob_hash="b", parent_id=None)
    assert a.id != b.id
    assert a.parent_ids == []


# ── Round-trip with the builder (marker nodes are not version nodes) ─────────


def test_marker_node_from_builder_is_not_a_version() -> None:
    graph = _graph_with_edits(1)
    marker = build_history_marker_node(
        op="undo", restores="root", undoes="edit-0", restored_blob_hash="blob-root", parent_id="edit-0"
    )
    graph.add_node(marker)
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)
    # The marker re-points the cursor; it must NOT extend the chain.
    assert state.chain == ("root", "edit-0")
    assert state.cursor == 0
    assert state.redo_available is True


# ── jump_target (U-M7 "Jump-to-version semantics") ───────────────────────────


def test_jump_target_accepts_any_chain_member() -> None:
    state = derive_history(_graph_with_edits(3), depth=DEFAULT_UNDO_DEPTH)  # chain: root, edit-0..2
    assert state.jump_target("root") == "root"
    assert state.jump_target("edit-1") == "edit-1"


def test_jump_target_rejects_nodes_outside_the_active_chain() -> None:
    """A truncated (undone-past) version is data but not jump-reachable."""
    graph = _fresh_ocr_graph()
    graph.add_node(_version_node("A"))
    graph.add_node(_version_node("B"))
    graph.add_node(_marker_node("undo-1", op="undo", restores="A", undoes="B", blob="blob-A"))
    graph.add_node(_version_node("C"))
    state = derive_history(graph, depth=DEFAULT_UNDO_DEPTH)  # chain: root, A, C — B truncated
    assert state.chain == ("root", "A", "C")
    assert state.jump_target("B") is None
    assert state.jump_target("nonexistent") is None


# ── build_version_list (U-M7 history panel) ──────────────────────────────────


def _labeler_node_with_changelog(
    node_id: str, *, change_type: str, timestamp: datetime | None = None
) -> tuple[ProvenanceNode, PageChangeEntry]:
    """A real edit version node plus the changelog entry naming its op."""
    node = ProvenanceNode(
        id=node_id,
        source="labeler",
        tool="labeler-spa",
        timestamp=timestamp or datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        blob_refs=[f"blob-{node_id}"],
    )
    entry = PageChangeEntry(provenance_node_id=node_id, changes=[{"type": change_type}])
    return node, entry


def test_build_version_list_labels_root_ocr_with_no_timestamp() -> None:
    """The OCR root never gets a timestamp (adapters/ocr/local_doctr.py never sets one)."""
    versions = build_version_list(_fresh_ocr_graph(), changelog=[], depth=DEFAULT_UNDO_DEPTH)
    assert len(versions) == 1
    assert versions[0].node_id == "root"
    assert versions[0].label == "OCR"
    assert versions[0].timestamp is None
    assert versions[0].is_current is True


def test_build_version_list_derives_labels_from_changelog() -> None:
    graph = _fresh_ocr_graph()
    node, entry = _labeler_node_with_changelog("edit-0", change_type="word_validated")
    graph.add_node(node)
    versions = build_version_list(graph, changelog=[entry], depth=DEFAULT_UNDO_DEPTH)
    assert [v.node_id for v in versions] == ["root", "edit-0"]
    assert versions[1].label == "Word validated"
    assert versions[1].timestamp is not None
    assert versions[1].is_current is True
    assert versions[0].is_current is False


def test_build_version_list_falls_back_when_changelog_entry_missing() -> None:
    """No fabricated label when the changelog entry is absent or empty."""
    graph = _fresh_ocr_graph()
    graph.add_node(_version_node("edit-0"))  # no matching changelog entry passed below
    versions = build_version_list(graph, changelog=[], depth=DEFAULT_UNDO_DEPTH)
    assert versions[-1].label == "Edit"


def test_build_version_list_marks_current_after_undo_and_skips_marker_rows() -> None:
    """U-14: one row per version (plus the OCR root) — undo/redo markers add no row."""
    graph = _fresh_ocr_graph()
    node_a, entry_a = _labeler_node_with_changelog("A", change_type="word_gt")
    node_b, entry_b = _labeler_node_with_changelog("B", change_type="word_validated")
    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(_marker_node("undo-1", op="undo", restores="A", undoes="B", blob="blob-A"))

    versions = build_version_list(graph, changelog=[entry_a, entry_b], depth=DEFAULT_UNDO_DEPTH)
    assert [v.node_id for v in versions] == ["root", "A", "B"], "undo must not add its own row"
    current = [v.node_id for v in versions if v.is_current]
    assert current == ["A"], "the undo marker must move is_current back to A, not add a new row"


def test_build_version_list_respects_truncation() -> None:
    """A version truncated by a real edit after undo (U-5) drops off the list too."""
    graph = _fresh_ocr_graph()
    node_a, entry_a = _labeler_node_with_changelog("A", change_type="word_gt")
    node_b, entry_b = _labeler_node_with_changelog("B", change_type="word_validated")
    node_c, entry_c = _labeler_node_with_changelog("C", change_type="word_rebox")
    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(_marker_node("undo-1", op="undo", restores="A", undoes="B", blob="blob-A"))
    graph.add_node(node_c)

    versions = build_version_list(graph, changelog=[entry_a, entry_b, entry_c], depth=DEFAULT_UNDO_DEPTH)
    assert [v.node_id for v in versions] == ["root", "A", "C"], "B must be gone once C truncates it"
