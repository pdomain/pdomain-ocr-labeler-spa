"""Tests for LabelerPageStore — event store + BlobStore per project."""

from pathlib import Path
from uuid import uuid4

from pdomain_ops.page_aggregate import PageAggregate, ProjectAggregate
from pdomain_ops.pages import PageRecord, ProjectRecord

from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore


def _make_page_record(page_id=None, page_index: int = 0) -> PageRecord:
    return PageRecord(
        page_id=page_id or uuid4(),
        page_index=page_index,
        source="ocr",
    )


def test_save_and_get_page(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    page_id = uuid4()

    record = _make_page_record(page_id=page_id)
    page_agg = PageAggregate(record)
    store.save_page(page_agg)

    loaded = store.get_page(page_id)
    assert loaded.record.page_id == page_id


def test_get_project_returns_aggregate(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    project_id = uuid4()
    page_id = uuid4()

    proj_record = ProjectRecord(project_id=project_id, name="test-proj")
    proj_agg = ProjectAggregate(proj_record)
    proj_agg.add_page(page_id=page_id, page_index=0)
    store.save_project(proj_agg)

    loaded = store.get_project(project_id)
    assert page_id in loaded.record.page_ids


def test_write_and_read_blob(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    data = b"fake image bytes"
    hash_ = store.blobs.write(data)
    assert store.blobs.read(hash_) == data


def test_events_db_created_under_pd_pages(tmp_path: Path) -> None:
    LabelerPageStore(project_dir=tmp_path)
    assert (tmp_path / ".pd-pages" / "events.db").exists()


def test_blobs_dir_created_under_pd_pages(tmp_path: Path) -> None:
    store = LabelerPageStore(project_dir=tmp_path)
    store.blobs.write(b"hello")
    assert (tmp_path / ".pd-pages" / "blobs").exists()
