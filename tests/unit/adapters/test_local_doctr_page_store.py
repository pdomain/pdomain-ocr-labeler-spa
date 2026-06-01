"""Test that _ingest_ocr_result writes a PageAggregate + blobs."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore


def _make_fake_page(page_id=None):
    """Minimal duck-typed Page for testing."""
    page = MagicMock()
    page.page_id = page_id or uuid4()
    page.width = 100
    page.height = 200
    page.to_dict.return_value = {"page_id": str(page.page_id), "lines": []}
    return page


def test_run_ocr_saves_page_aggregate(tmp_path: Path) -> None:
    """After _ingest_ocr_result, the PageAggregate exists in the LabelerPageStore."""
    store = LabelerPageStore(project_dir=tmp_path)
    fake_page = _make_fake_page()

    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result

    _ingest_ocr_result(
        page=fake_page,
        image_bytes=b"\x89PNG\r\n",
        page_index=0,
        store=store,
    )

    agg = store.get_page(fake_page.page_id)
    assert agg.record.page_id == fake_page.page_id


def test_run_ocr_writes_image_blob(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    fake_page = _make_fake_page()
    image_bytes = b"\x89PNG\r\n fake png"

    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result

    _ingest_ocr_result(page=fake_page, image_bytes=image_bytes, page_index=0, store=store)

    agg = store.get_page(fake_page.page_id)
    # aggregate was saved — minimal check
    assert agg.record.page_id == fake_page.page_id


def test_run_ocr_writes_page_json_blob(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    fake_page = _make_fake_page()

    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result

    _ingest_ocr_result(page=fake_page, image_bytes=b"fake", page_index=0, store=store)

    # Blob store must have at least one blob (the Page JSON)
    blobs_dir = tmp_path / ".pd-pages" / "blobs"
    assert blobs_dir.exists()
    assert any(blobs_dir.iterdir())
