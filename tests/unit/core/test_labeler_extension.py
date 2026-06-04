from uuid import uuid4

from pdomain_ops.pages import PageRecord, get_extension, set_extension

from pdomain_ocr_labeler_spa.core.labeler_extension import LabelerPageExtension


def _make_record() -> PageRecord:
    return PageRecord(page_id=uuid4(), page_index=0)


def test_labeler_extension_defaults() -> None:
    ext = LabelerPageExtension()
    assert ext.page_number == 0
    assert ext.page_source == "ocr"
    assert ext.payload_error is None
    assert ext.selection_mode == "word"
    assert ext.line_filter == "all"
    # Lane C / Task C2: edited-image presence indicator defaults to False so
    # the frontend "Reload OCR (Edited)" button stays disabled until an erase
    # has actually persisted an edited-image blob.
    assert ext.has_edited_image is False


def test_labeler_extension_has_edited_image_round_trip() -> None:
    record = _make_record()
    set_extension(record, "labeler", LabelerPageExtension(has_edited_image=True))
    recovered = get_extension(record, "labeler", LabelerPageExtension)
    assert recovered is not None
    assert recovered.has_edited_image is True


def test_labeler_extension_round_trip_via_page_record() -> None:
    record = _make_record()
    ext = LabelerPageExtension(page_number=5, page_source="cached_ocr", payload_error=None)
    set_extension(record, "labeler", ext)
    recovered = get_extension(record, "labeler", LabelerPageExtension)
    assert recovered is not None
    assert recovered.page_number == 5
    assert recovered.page_source == "cached_ocr"


def test_labeler_extension_payload_error_survives_round_trip() -> None:
    record = _make_record()
    ext = LabelerPageExtension(payload_error="corrupt saved data: missing lines key")
    set_extension(record, "labeler", ext)
    recovered = get_extension(record, "labeler", LabelerPageExtension)
    assert recovered is not None
    assert recovered.payload_error == "corrupt saved data: missing lines key"


def test_labeler_extension_model_dump_is_json_safe() -> None:
    import json

    ext = LabelerPageExtension(page_number=3, page_source="filesystem")
    dumped = ext.model_dump(mode="json")
    round_tripped = json.loads(json.dumps(dumped))
    assert round_tripped["page_number"] == 3
    assert round_tripped["page_source"] == "filesystem"
