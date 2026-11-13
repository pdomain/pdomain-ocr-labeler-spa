"""U-M6 prune live-set. The clock is injected so retention can expire without sleeping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pdomain_ops.blob_store import BlobStore
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord, ProvenanceGraph, ProvenanceNode

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _project_uuid_for
from pdomain_ocr_labeler_spa.core.page_lineage import LINEAGE_NAMESPACE, PageLineage, project_uuid_for
from pdomain_ocr_labeler_spa.core.page_prune import live_blob_names, prune_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore


def test_project_uuid_matches_the_ingest_namespace() -> None:
    assert project_uuid_for("book1") == _project_uuid_for("book1")


def _aggregate(
    page_id: UUID,
    graph: ProvenanceGraph,
    lineage: PageLineage | None = None,
) -> PageAggregate:
    record = PageRecord(page_id=page_id, page_index=0, provenance=graph)
    if lineage is not None:
        record.extensions[LINEAGE_NAMESPACE] = lineage.model_dump(mode="json")
    return PageAggregate(record)


def test_expired_dead_branch_and_abandoned_version_blobs_leave_the_live_set() -> None:
    current_id = uuid4()
    abandoned_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    v1 = ProvenanceNode(id="v1", source="labeler", tool="labeler-spa", blob_refs=["live-root"], timestamp=old)
    dead = ProvenanceNode(
        id="dead", source="labeler", tool="labeler-spa", blob_refs=["dead-hash"], timestamp=old
    )
    marker = ProvenanceNode(
        id="undo-1",
        source="labeler",
        tool="labeler-spa",
        timestamp=old,
        blob_refs=["live-root"],
        extra={"history_op": {"op": "undo", "restores": "v1", "undoes": "dead"}},
    )
    head = ProvenanceNode(
        id="head",
        source="labeler",
        tool="labeler-spa",
        timestamp=datetime(2020, 2, 1, tzinfo=UTC),
        blob_refs=["live-head", "image-hash"],
    )
    current_graph = ProvenanceGraph(
        nodes={node.id: node for node in (v1, dead, marker, head)},
        head_id="head",
        history=["v1", "dead", "undo-1", "head"],
    )
    abandoned_graph = ProvenanceGraph(
        nodes={
            "old": ProvenanceNode(
                id="old",
                source="ocr",
                tool="doctr",
                blob_refs=["abandoned-version", "abandoned-image"],
                timestamp=old,
            )
        },
        head_id="old",
        history=["old"],
    )
    names = {
        "live-root",
        "dead-hash",
        "live-head",
        "image-hash",
        "abandoned-version",
        "abandoned-image",
        "unknown-file",
    }
    live = live_blob_names(
        blob_names=names,
        current_page_ids={current_id},
        aggregates=[
            _aggregate(current_id, current_graph),
            _aggregate(
                abandoned_id,
                abandoned_graph,
                PageLineage(superseded_by=str(current_id), linked_at="2020-01-01T00:00:00+00:00"),
            ),
        ],
        now=now,
        retention=timedelta(days=30),
        undo_depth=50,
    )
    assert "dead-hash" not in live
    assert "abandoned-version" not in live
    assert "live-root" in live
    assert "live-head" in live
    assert "image-hash" in live
    assert "abandoned-image" in live
    assert "unknown-file" in live

    within = live_blob_names(
        blob_names=names,
        current_page_ids={current_id},
        aggregates=[
            _aggregate(current_id, current_graph),
            _aggregate(
                abandoned_id,
                abandoned_graph,
                PageLineage(superseded_by=str(current_id), linked_at=now.isoformat()),
            ),
        ],
        now=now,
        retention=timedelta(days=30),
        undo_depth=50,
    )
    assert "abandoned-version" in within
    assert "dead-hash" not in within


def _jumped_chain() -> ProvenanceGraph:
    """Four versions, then a jump that leaves the cursor on v1."""
    old = datetime(2020, 1, 1, tzinfo=UTC)
    versions = [
        ProvenanceNode(
            id=node_id,
            source="labeler",
            tool="labeler-spa",
            blob_refs=[digest],
            timestamp=old,
        )
        for node_id, digest in (("v0", "hash-v0"), ("v1", "hash-v1"), ("v2", "hash-v2"), ("v3", "hash-v3"))
    ]
    jump = ProvenanceNode(
        id="jump",
        source="labeler",
        tool="labeler-spa",
        timestamp=old,
        blob_refs=["hash-v1"],
        extra={"history_op": {"op": "jump", "restores": "v1", "undoes": "v3"}},
    )
    nodes = [*versions, jump]
    return ProvenanceGraph(
        nodes={node.id: node for node in nodes},
        head_id="jump",
        history=[node.id for node in nodes],
    )


def test_a_cursor_below_the_undo_floor_keeps_its_blob_and_nonpositive_depth_uses_fifty() -> None:
    current_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    names = {"hash-v0", "hash-v1", "hash-v2", "hash-v3"}
    aggregate = _aggregate(current_id, _jumped_chain())

    shallow = live_blob_names(
        blob_names=names,
        current_page_ids={current_id},
        aggregates=[aggregate],
        now=now,
        retention=timedelta(days=30),
        undo_depth=1,
    )
    assert "hash-v1" in shallow
    assert "hash-v2" in shallow
    assert "hash-v3" in shallow
    assert "hash-v0" not in shallow

    coerced = live_blob_names(
        blob_names=names,
        current_page_ids={current_id},
        aggregates=[aggregate],
        now=now,
        retention=timedelta(days=30),
        undo_depth=0,
    )
    assert names <= coerced


class _ProjectRecord:
    def __init__(self) -> None:
        self.page_ids: list[UUID] = []


class _Project:
    def __init__(self) -> None:
        self.record = _ProjectRecord()


class _Store:
    def __init__(self, project_dir: Path, blobs: BlobStore) -> None:
        self.project_dir = project_dir
        self.blobs = blobs

    def get_project(self, _project_id: UUID) -> _Project:
        return _Project()


def test_prune_store_unlinks_only_snapshot_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blob created while the live set is computed is not a candidate."""
    blobs = BlobStore(tmp_path / ".pd-pages")
    blob_dir = tmp_path / ".pd-pages" / "blobs"
    (blob_dir / "dead-hash").write_bytes(b"dead")
    (blob_dir / "live-hash").write_bytes(b"live")

    def _live(*, blob_names: set[str], **_kwargs: object) -> set[str]:
        (blob_dir / "late-hash").write_bytes(b"late")
        return set(blob_names) - {"dead-hash"}

    monkeypatch.setattr("pdomain_ocr_labeler_spa.core.page_prune.live_blob_names", _live)
    deleted = prune_store(
        cast("LabelerPageStore", _Store(tmp_path, blobs)),
        "book1",
        retention_days=30,
        undo_depth=50,
    )
    assert deleted == ["dead-hash"]
    assert not (blob_dir / "dead-hash").exists()
    assert (blob_dir / "live-hash").is_file()
    assert (blob_dir / "late-hash").is_file()
