"""Unit tests for the append-only typography-review-counts rollup journal.

Spec authority: docs/issues/2026-09-18-typography-numerator-needs-a-per-
page-rollup.md. Mirrors ``tests/unit/core/test_review_counts.py``'s
conventions for a journal of this shape, plus the compaction contract this
journal shares with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.core.typography_review_counts import (
    PageTypographyCounts,
    TypographyReviewCountsJournal,
)


def _counts(
    logical_page_id: str = "page-0",
    *,
    total: int = 10,
    reviewed: int = 3,
) -> PageTypographyCounts:
    return PageTypographyCounts(
        logical_page_id=logical_page_id,
        total_words=total,
        typography_reviewed_words=reviewed,
    )


def test_a_fresh_journal_is_empty_and_does_not_raise(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    assert journal.latest_by_page() == {}


def test_appending_never_rewrites_an_existing_record(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0"))
    first = journal.path.read_bytes()

    journal.append(_counts("page-1"))
    second = journal.path.read_bytes()

    assert second.startswith(first)


def test_newest_row_wins_per_page(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0", total=10, reviewed=1))
    journal.append(_counts("page-0", total=10, reviewed=5))
    journal.append(_counts("page-1", total=4, reviewed=4))

    latest = journal.latest_by_page()

    assert set(latest) == {"page-0", "page-1"}
    assert latest["page-0"].typography_reviewed_words == 5
    assert latest["page-1"].typography_reviewed_words == 4


def test_newest_row_can_report_fewer_reviewed_words_than_the_prior_row(tmp_path: Path) -> None:
    """A revision that un-reviews a previously-reviewed word must lower the
    rolled-up count — this journal recomputes fresh at every write rather
    than maintaining a running delta, so the newest row can legitimately
    report less than the one before it.
    """
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0", total=1, reviewed=1))
    journal.append(_counts("page-0", total=1, reviewed=0))

    latest = journal.latest_by_page()

    assert latest["page-0"].typography_reviewed_words == 0


def test_latest_by_page_reads_the_journal_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0"))
    journal.append(_counts("page-1"))

    read_calls = 0
    original_read = TypographyReviewCountsJournal._read_locked

    def _counting_read(self: TypographyReviewCountsJournal) -> list[PageTypographyCounts]:
        nonlocal read_calls
        read_calls += 1
        return original_read(self)

    monkeypatch.setattr(TypographyReviewCountsJournal, "_read_locked", _counting_read)
    latest = journal.latest_by_page()

    assert read_calls == 1
    assert set(latest) == {"page-0", "page-1"}


def test_a_malformed_line_is_skipped_rather_than_failing_the_read(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0"))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    latest = journal.latest_by_page()

    assert set(latest) == {"page-0"}


def test_a_line_missing_a_required_field_is_skipped_rather_than_raising(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    journal.append(_counts("page-0"))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"logical_page_id": "page-1"}\n')

    latest = journal.latest_by_page()

    assert set(latest) == {"page-0"}


# ── Compaction ────────────────────────────────────────────────────────────


def test_compaction_does_not_trigger_at_or_below_ten_rows_for_one_page(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    for i in range(10):
        journal.append(_counts("page-0", reviewed=i))

    journal.latest_by_page()

    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 10


def test_compaction_triggers_past_ten_rows_for_one_page_and_keeps_the_newest(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts("page-0", reviewed=i))

    latest = journal.latest_by_page()

    assert latest["page-0"].typography_reviewed_words == 10
    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 1


def test_compaction_keeps_the_newest_row_per_distinct_page(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts("page-0", reviewed=i))
    for i in range(11):
        journal.append(_counts("page-1", reviewed=i))

    latest = journal.latest_by_page()

    assert latest["page-0"].typography_reviewed_words == 10
    assert latest["page-1"].typography_reviewed_words == 10
    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 2


def test_a_read_after_compaction_still_returns_the_right_answer(tmp_path: Path) -> None:
    journal = TypographyReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts("page-0", reviewed=i))
    journal.latest_by_page()  # triggers compaction

    # A fresh journal handle reading the now-compacted file gets the same answer.
    reread = TypographyReviewCountsJournal(tmp_path).latest_by_page()
    assert reread["page-0"].typography_reviewed_words == 10
