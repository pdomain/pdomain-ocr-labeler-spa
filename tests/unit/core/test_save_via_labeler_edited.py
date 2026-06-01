"""Test that save_page_to_store fires LabelerEdited event."""

from pathlib import Path
from uuid import uuid4

from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore


def test_save_page_fires_labeler_edited_event(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_state import save_page_to_store

    store = LabelerPageStore(project_dir=tmp_path)
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)

    changes = [{"type": "word_text", "word_id": "w0", "from": "thr", "to": "the"}]
    save_page_to_store(page_id=page_id, changes=changes, store=store)

    reloaded = store.get_page(page_id)
    assert len(reloaded.record.changelog) == 1
    assert reloaded.record.changelog[0].changes == changes
