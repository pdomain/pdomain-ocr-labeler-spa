"""Test that save_page_to_store fires LabelerEdited event — persists across reload."""

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


def test_labeler_edited_event_persists_across_store_reload(tmp_path: Path) -> None:
    """LabelerEdited event survives a full store close/reopen (reload persistence).

    Task 3 audit: verifies that save_page_to_store is genuinely event-backed
    and that the changes are durable — a new LabelerPageStore pointed at the
    same directory replays the event and exposes the changelog entry.
    """
    from pdomain_ocr_labeler_spa.core.page_state import save_page_to_store

    project_dir = tmp_path / "proj"
    store = LabelerPageStore(project_dir=project_dir)
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)

    changes = [{"type": "word_text", "word_id": "w1", "from": "teh", "to": "the"}]
    save_page_to_store(page_id=page_id, changes=changes, store=store)
    store.close()

    # Re-open a fresh store at the same path — event replay must surface the change.
    store2 = LabelerPageStore(project_dir=project_dir)
    reloaded = store2.get_page(page_id)
    assert len(reloaded.record.changelog) == 1, (
        "LabelerEdited event did not survive store close/reopen — "
        "save_page_to_store is not event-backed as required."
    )
    assert reloaded.record.changelog[0].changes == changes
    store2.close()


def test_page_aggregate_set_extension_persists_across_reload(tmp_path: Path) -> None:
    """PageAggregate.set_extension fires an ExtensionSet event — persists across reload.

    Task 3 audit: the ops 0.7.1 method PageAggregate.set_extension is available
    and its event survives store close/reopen. Verifies the new API works as
    documented before any labeler code migrates to it.
    """
    from pdomain_ocr_labeler_spa.core.labeler_extension import LabelerPageExtension

    project_dir = tmp_path / "proj2"
    store = LabelerPageStore(project_dir=project_dir)
    page_id = uuid4()
    record = PageRecord(page_id=page_id, page_index=0, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)

    # Use the event-backed instance method (not the free helper)
    ext = LabelerPageExtension(page_number=3, page_source="ocr")
    agg.set_extension("labeler", ext)
    store.save_page(agg)
    store.close()

    # Re-open — extension should survive
    store2 = LabelerPageStore(project_dir=project_dir)
    reloaded = store2.get_page(page_id)
    ext_data = reloaded.record.extensions.get("labeler")
    assert ext_data is not None, (
        "PageAggregate.set_extension did not persist labeler extension across store close/reopen."
    )
    assert ext_data.get("page_number") == 3
    store2.close()
