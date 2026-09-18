"""Unit tests for the append-only word-review-counts journal.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-
what-to-review-next.md "A per-page count journal, written where the page is
already saved". Mirrors ``tests/unit/core/page_kind/test_proposal_log.py``'s
conventions for a journal of this shape, plus the compaction contract this
journal adds on top of that shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.core.review_counts import PageWordCounts, WordReviewCountsJournal


def _counts(
    page_index: int = 0,
    *,
    content_hash: str = "h0",
    total: int = 10,
    validated: int = 3,
) -> PageWordCounts:
    return PageWordCounts(
        page_index=page_index,
        content_hash=content_hash,
        total_words=total,
        validated_words=validated,
    )


def test_a_fresh_journal_is_empty_and_does_not_raise(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    assert journal.latest_by_page() == {}


def test_appending_never_rewrites_an_existing_record(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    journal.append(_counts(page_index=0, content_hash="h0"))
    first = journal.path.read_bytes()

    journal.append(_counts(page_index=1, content_hash="h1"))
    second = journal.path.read_bytes()

    assert second.startswith(first)


def test_newest_row_wins_per_page(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    journal.append(_counts(page_index=0, content_hash="h0", total=10, validated=1))
    journal.append(_counts(page_index=0, content_hash="h1", total=10, validated=5))
    journal.append(_counts(page_index=1, content_hash="h2", total=4, validated=4))

    latest = journal.latest_by_page()

    assert set(latest) == {0, 1}
    assert latest[0].content_hash == "h1"
    assert latest[0].validated_words == 5
    assert latest[1].content_hash == "h2"


def test_latest_by_page_reads_the_journal_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    journal.append(_counts(page_index=0, content_hash="h0"))
    journal.append(_counts(page_index=1, content_hash="h1"))

    read_calls = 0
    original_read = WordReviewCountsJournal._read_locked

    def _counting_read(self: WordReviewCountsJournal) -> list[PageWordCounts]:
        nonlocal read_calls
        read_calls += 1
        return original_read(self)

    monkeypatch.setattr(WordReviewCountsJournal, "_read_locked", _counting_read)
    latest = journal.latest_by_page()

    assert read_calls == 1
    assert set(latest) == {0, 1}


def test_a_malformed_line_is_skipped_rather_than_failing_the_read(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    journal.append(_counts(page_index=0))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    latest = journal.latest_by_page()

    assert set(latest) == {0}


def test_a_line_missing_a_required_field_is_skipped_rather_than_raising(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    journal.append(_counts(page_index=0))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"page_index": 1}\n')

    latest = journal.latest_by_page()

    assert set(latest) == {0}


# ── Compaction ────────────────────────────────────────────────────────────


def test_compaction_does_not_trigger_at_or_below_ten_rows_for_one_page(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    for i in range(10):
        journal.append(_counts(page_index=0, content_hash=f"h{i}"))

    journal.latest_by_page()

    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 10


def test_compaction_triggers_past_ten_rows_for_one_page_and_keeps_the_newest(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts(page_index=0, content_hash=f"h{i}", validated=i))

    latest = journal.latest_by_page()

    assert latest[0].content_hash == "h10"
    assert latest[0].validated_words == 10
    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 1


def test_compaction_keeps_the_newest_row_per_distinct_page(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts(page_index=0, content_hash=f"a{i}"))
    for i in range(11):
        journal.append(_counts(page_index=1, content_hash=f"b{i}"))

    latest = journal.latest_by_page()

    assert latest[0].content_hash == "a10"
    assert latest[1].content_hash == "b10"
    remaining = [line for line in journal.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 2


def test_a_read_after_compaction_still_returns_the_right_answer(tmp_path: Path) -> None:
    journal = WordReviewCountsJournal(tmp_path)
    for i in range(11):
        journal.append(_counts(page_index=0, content_hash=f"h{i}", validated=i))
    journal.latest_by_page()  # triggers compaction

    # A fresh journal handle reading the now-compacted file gets the same answer.
    reread = WordReviewCountsJournal(tmp_path).latest_by_page()
    assert reread[0].content_hash == "h10"
    assert reread[0].validated_words == 10
