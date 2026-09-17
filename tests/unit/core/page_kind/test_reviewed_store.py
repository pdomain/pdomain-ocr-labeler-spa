"""Unit tests for the per-page page-kind reviewed marker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pdomain_book_contracts.annotation import PageKind


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


def test_a_valid_json_line_of_the_wrong_shape_is_skipped_too(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00")
    path = tmp_path / ".pd-pages" / "page-kind-reviewed.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"foo": 1}\n')
        handle.write("{}\n")

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.reviewed_at == "2026-09-08T10:00:00+00:00"
    assert store.is_reviewed(0) is True


def test_reviewed_page_indices_returns_every_reviewed_page_in_one_read(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00")
    store.mark_reviewed(2, "2026-09-08T10:05:00+00:00")

    assert store.reviewed_page_indices() == frozenset({0, 2})


def test_reviewed_page_indices_is_empty_with_no_journal(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    assert store.reviewed_page_indices() == frozenset()


def test_reviewed_page_indices_counts_a_repeatedly_marked_page_once(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00")
    store.mark_reviewed(0, "2026-09-08T11:00:00+00:00")

    assert store.reviewed_page_indices() == frozenset({0})


def test_an_explicit_null_actor_falls_back_to_default_not_the_string_none(
    tmp_path: Path,
) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    path = tmp_path / ".pd-pages" / "page-kind-reviewed.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"page_index": 0, "reviewed_at": "2026-09-08T10:00:00+00:00", "actor": null, "note": null}\n'
        )

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.actor == "default"


# ── kind + method (pdomain-ocr-synth 2026-09-17-page-kind-review-design.md) ──


def test_a_marker_carries_its_kind_and_method(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.kind == PageKind.BODY
    assert marker.method == "single"


def test_an_old_marker_with_no_kind_or_method_still_parses(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    path = tmp_path / ".pd-pages" / "page-kind-reviewed.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"page_index": 0, "reviewed_at": "2026-09-08T10:00:00+00:00", '
            '"actor": "default", "note": null}\n'
        )

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.kind is None
    assert marker.method is None
    assert store.is_reviewed(0) is True


def test_a_history_marker_with_no_kind_withdraws_the_review(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(0, "2026-09-08T11:00:00+00:00", kind=None, method="history")

    assert store.is_reviewed(0) is False
    assert store.reviewed_page_indices() == frozenset()


def test_a_history_marker_that_still_carries_a_kind_does_not_withdraw(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(0, "2026-09-08T11:00:00+00:00", kind=PageKind.CONTENTS, method="history")

    marker = store.latest_for_page(0)
    assert marker is not None
    assert marker.kind == PageKind.CONTENTS
    assert store.is_reviewed(0) is True
    assert store.reviewed_page_indices() == frozenset({0})


def test_latest_by_page_reads_the_journal_once_and_keeps_the_latest_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    store = PageKindReviewedStore(tmp_path)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(0, "2026-09-08T11:00:00+00:00", kind=PageKind.TITLE_PAGE, method="single")
    store.mark_reviewed(2, "2026-09-08T10:05:00+00:00", kind=PageKind.BODY, method="bulk")

    read_calls = 0
    original_read = PageKindReviewedStore._read

    def _counting_read(self: PageKindReviewedStore) -> list[Any]:
        nonlocal read_calls
        read_calls += 1
        return original_read(self)

    monkeypatch.setattr(PageKindReviewedStore, "_read", _counting_read)
    by_page = store.latest_by_page()

    assert read_calls == 1
    assert set(by_page) == {0, 2}
    assert by_page[0].kind == PageKind.TITLE_PAGE
    assert by_page[2].kind == PageKind.BODY
