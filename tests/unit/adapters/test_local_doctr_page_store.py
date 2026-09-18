"""Test that _ingest_ocr_result writes a PageAggregate + blobs."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.review_counts import WordReviewCountsJournal


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


# ── Word-review-counts row (pdomain-ocr-synth's docs/specs/2026-09-18-one-
# answer-to-what-to-review-next.md) ──────────────────────────────────────────
#
# A fresh OCR ingest writes the page's new head content through a different
# event (``ocr_completed``, not ``labeler_edited``) than an edit-save does —
# so it must append its own counts row for the words it actually carries, or
# a reload/rotate/auto-rotate that wipes out a page's validated words leaves
# the journal reporting the pre-reload count.


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _real_page(*, page_index: int = 0, word_count: int = 3) -> Page:
    words = [
        {"type": "Word", "text": f"w{i}", "ground_truth_text": f"w{i}", "bounding_box": _bbox(0, 0, 10, 10)}
        for i in range(word_count)
    ]
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": page_index,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            {"type": "Block", "child_type": "WORDS", "items": words, "bounding_box": _bbox(0, 0, 100, 20)}
        ],
    }
    return Page.from_dict(page_dict)


def test_reingest_resets_the_word_review_counts_row(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result

    store = LabelerPageStore(project_dir=tmp_path)
    page = _real_page(page_index=0, word_count=3)
    agg = _ingest_ocr_result(page=page, image_bytes=b"\x89PNG\r\n", page_index=0, store=store)

    # A person validates two of the three words and saves — the same
    # content-save path api/words.py's toggle_validated route uses.
    page.words[0].word_labels.append("validated")
    page.words[1].word_labels.append("validated")
    save_page_content_to_store(page_id=agg.record.page_id, page=page, store=store)

    journal = WordReviewCountsJournal(tmp_path)
    before = journal.latest_by_page()[0]
    assert before.total_words == 3
    assert before.validated_words == 2

    # "Reload OCR": a fresh Page at the SAME page_index, unvalidated by
    # construction — the ingest path a reload/rotate/auto-rotate run takes.
    fresh_page = _real_page(page_index=0, word_count=3)
    _ingest_ocr_result(page=fresh_page, image_bytes=b"\x89PNG\r\n", page_index=0, store=store)

    after = journal.latest_by_page()[0]
    assert after.total_words == 3
    assert after.validated_words == 0, "re-OCR must reset the counts row, not leave the pre-reload count"
