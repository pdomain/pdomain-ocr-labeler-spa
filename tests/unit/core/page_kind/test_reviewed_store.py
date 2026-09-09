"""Unit tests for the per-page page-kind reviewed marker."""

from __future__ import annotations

from pathlib import Path


def test_a_marker_reads_back(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", note="looks right")

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.reviewed_at == "2026-09-08T10:00:00+00:00"
    assert marker.actor == "default"
    assert marker.note == "looks right"
    assert store.is_reviewed(0) is True


def test_an_unreviewed_page_has_no_marker(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    assert store.latest_for_page(0) is None
    assert store.is_reviewed(0) is False


def test_the_most_recent_mark_wins_and_the_earlier_one_survives(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", note="first pass")
    store.mark_reviewed(0, "2026-09-08T11:00:00+00:00", note="changed my mind")

    current = store.latest_for_page(0)
    assert current is not None
    assert current.note == "changed my mind"


def test_markers_for_different_pages_do_not_collide(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00")

    assert store.is_reviewed(0) is True
    assert store.is_reviewed(1) is False


def test_a_malformed_line_is_skipped_rather_than_failing_the_read(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00")
    path = tmp_path / ".pd-pages" / "page-kind-reviewed.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    assert store.is_reviewed(0) is True
