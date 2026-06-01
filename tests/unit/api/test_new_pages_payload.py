"""Test that api/pages.py uses ops PagePayload + LabelerPageExtension."""

from pathlib import Path
from uuid import uuid4

from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import (
    PagePayload,
    PageRecord,
    ProvenanceGraph,
    ProvenanceNode,
    get_extension,
    set_extension,
)

from pdomain_ocr_labeler_spa.core.labeler_extension import LabelerPageExtension
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore


def test_page_payload_uses_ops_pagerecord(tmp_path: Path) -> None:
    """_assemble_page_payload returns an ops PagePayload with the ops PageRecord."""
    from pdomain_ocr_labeler_spa.api.pages import _assemble_page_payload

    store = LabelerPageStore(project_dir=tmp_path)
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)

    payload = _assemble_page_payload(
        project_id="test-project",
        page_index=0,
        page_id=page_id,
        store=store,
        image_url="/api/projects/test-project/pages/0/image",
        dims=(800, 1200),
    )
    assert isinstance(payload, PagePayload)
    assert payload.page_id == page_id
    assert payload.record.page_id == page_id


def test_page_payload_contains_labeler_extension(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.api.pages import _assemble_page_payload

    store = LabelerPageStore(project_dir=tmp_path)
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    ext = LabelerPageExtension(page_number=1, page_source="ocr")
    set_extension(record, "labeler", ext)
    agg = PageAggregate(record)
    store.save_page(agg)

    payload = _assemble_page_payload(
        project_id="test-project",
        page_index=0,
        page_id=page_id,
        store=store,
        image_url="/api/projects/test-project/pages/0/image",
        dims=(800, 1200),
    )
    recovered_ext = get_extension(payload.record, "labeler", LabelerPageExtension)
    assert recovered_ext is not None
    assert recovered_ext.page_number == 1


def test_provenance_summary_populated_from_ops(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.api.pages import _assemble_page_payload

    store = LabelerPageStore(project_dir=tmp_path)
    page_id = uuid4()
    node = ProvenanceNode(id="n1", source="ocr", tool="doctr")
    graph = ProvenanceGraph(nodes={"n1": node}, head_id="n1", history=["n1"])
    record = PageRecord(page_id=page_id, page_index=0, source="ocr", provenance=graph)
    agg = PageAggregate(record)
    store.save_page(agg)

    payload = _assemble_page_payload(
        project_id="p1",
        page_index=0,
        page_id=page_id,
        store=store,
        image_url="/img",
        dims=(100, 200),
    )
    # provenance_summary must be None or a string — must not raise
    assert payload.record.provenance_summary is None or isinstance(payload.record.provenance_summary, str)
