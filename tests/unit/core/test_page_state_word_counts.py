"""``save_page_content_to_store`` — the word-review-counts journal append.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-
what-to-review-next.md "A per-page count journal, written where the page is
already saved":

- the row is appended only after the page's head save has succeeded;
- the append is itself best-effort, in its own try/except, logged and
  swallowed — an unwritable journal must never turn a saved edit into a
  failure the caller sees.

Uses lightweight fakes rather than a real ``LabelerPageStore``/``Page`` —
``tests/integration/test_structural_roundtrip.py`` already covers the real
store + real book-tools ``Page`` round trip; these tests pin the counts-row
contract in isolation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from pdomain_ocr_labeler_spa.core import page_state as page_state_module
from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
from pdomain_ocr_labeler_spa.core.review_counts import WordReviewCountsJournal


class _FakeWord:
    def __init__(self, *, validated: bool) -> None:
        self.word_labels: list[str] = ["validated"] if validated else []


class _FakePage:
    def __init__(self, *, page_index: int, words: list[_FakeWord]) -> None:
        self.page_index = page_index
        self.words = words

    def to_dict(self) -> dict[str, Any]:
        return {"page_index": self.page_index}


class _FakeAgg:
    def labeler_edited(self, *, provenance_node: Any, changes: list[dict[str, Any]]) -> None:
        self.provenance_node = provenance_node
        self.changes = changes


class _FakeBlobs:
    def write(self, data: bytes) -> str:
        return "deadbeef" * 8


class _FakeStore:
    def __init__(self, project_dir: Path, *, fail_save: bool = False) -> None:
        self.project_dir = project_dir
        self.blobs = _FakeBlobs()
        self.saved: list[_FakeAgg] = []
        self._fail_save = fail_save

    def get_page(self, page_id: Any) -> _FakeAgg:
        return _FakeAgg()

    def save_page(self, agg: _FakeAgg) -> None:
        if self._fail_save:
            raise RuntimeError("boom")
        self.saved.append(agg)


def test_appends_a_row_counting_the_pages_words(tmp_path: Path) -> None:
    store = _FakeStore(tmp_path)
    page = _FakePage(
        page_index=3,
        words=[_FakeWord(validated=True), _FakeWord(validated=False), _FakeWord(validated=True)],
    )

    save_page_content_to_store(page_id=uuid4(), page=page, store=store)

    latest = WordReviewCountsJournal(tmp_path).latest_by_page()
    assert latest[3].total_words == 3
    assert latest[3].validated_words == 2


def test_the_appended_row_carries_the_returned_content_hash(tmp_path: Path) -> None:
    store = _FakeStore(tmp_path)
    page = _FakePage(page_index=1, words=[])

    content_hash = save_page_content_to_store(page_id=uuid4(), page=page, store=store)

    latest = WordReviewCountsJournal(tmp_path).latest_by_page()
    assert latest[1].content_hash == content_hash


def test_no_row_is_appended_when_the_head_save_fails(tmp_path: Path) -> None:
    store = _FakeStore(tmp_path, fail_save=True)
    page = _FakePage(page_index=0, words=[_FakeWord(validated=True)])

    with pytest.raises(RuntimeError):
        save_page_content_to_store(page_id=uuid4(), page=page, store=store)

    assert WordReviewCountsJournal(tmp_path).latest_by_page() == {}


def test_journal_append_failure_is_logged_and_swallowed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(self: WordReviewCountsJournal, counts: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(page_state_module.WordReviewCountsJournal, "append", _raise)
    store = _FakeStore(tmp_path)
    page = _FakePage(page_index=0, words=[_FakeWord(validated=True)])

    with caplog.at_level(logging.WARNING):
        content_hash = save_page_content_to_store(page_id=uuid4(), page=page, store=store)

    # The caller's save already succeeded — a broken journal must not surface here.
    assert content_hash
    assert len(store.saved) == 1
    assert any("word-review-counts append failed" in record.message for record in caplog.records)


def test_a_store_without_project_dir_skips_the_append_silently(tmp_path: Path) -> None:
    class _NoProjectDirStore:
        blobs = _FakeBlobs()

        def get_page(self, page_id: Any) -> _FakeAgg:
            return _FakeAgg()

        def save_page(self, agg: _FakeAgg) -> None:
            pass

    page = _FakePage(page_index=0, words=[_FakeWord(validated=True)])

    content_hash = save_page_content_to_store(page_id=uuid4(), page=page, store=_NoProjectDirStore())

    assert content_hash
    assert not (tmp_path / ".pd-pages" / "word-review-counts.jsonl").exists()
