"""Conformance: new PagePayload (ops) contract.

Guards the new API response shape built from ops PagePayload + LabelerPageExtension.
These replace the deleted UserPageEnvelope conformance tests.
"""

import json
from uuid import uuid4

from pdomain_ops.pages import PagePayload, PageRecord, get_extension, set_extension

from pdomain_ocr_labeler_spa.core.labeler_extension import LabelerPageExtension


def _make_payload() -> PagePayload:
    """Minimal valid PagePayload as returned by the new pages API."""
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    ext = LabelerPageExtension(page_number=1, page_source="ocr")
    set_extension(record, "labeler", ext)
    return PagePayload(
        page_id=page_id,
        page_index=0,
        record=record,
        content={"page_id": str(page_id), "lines": []},
        image_url="/api/projects/test/pages/0/image?w=800",
        dims=(800, 1200),
    )


def test_payload_has_required_fields() -> None:
    p = _make_payload()
    assert p.page_id is not None
    assert p.record is not None
    assert p.content is not None


def test_payload_labeler_extension_readable() -> None:
    p = _make_payload()
    ext = get_extension(p.record, "labeler", LabelerPageExtension)
    assert ext is not None
    assert ext.page_number == 1
    assert ext.page_source == "ocr"


def test_payload_round_trips_json() -> None:
    p = _make_payload()
    dumped = p.model_dump(mode="json")
    json_str = json.dumps(dumped)
    parsed = json.loads(json_str)
    assert parsed["page_index"] == 0
    assert "record" in parsed
    assert "extensions" in parsed["record"]
    assert "labeler" in parsed["record"]["extensions"]


def test_payload_image_url_is_string() -> None:
    p = _make_payload()
    assert isinstance(p.image_url, str)
    assert p.image_url.startswith("/api/")
