"""Append-only per-page typography-review rollup journal.

Spec authority: docs/issues/2026-09-18-typography-numerator-needs-a-per-
page-rollup.md. Mirrors ``core.review_counts.WordReviewCountsJournal`` —
same JSONL-row-per-event shape, same OS append lock, same compacting
``latest_by_page`` reader — built for the identical reason: the
``review-queue`` route's ``typography`` entry used to answer its count by
reading and pydantic-parsing the *whole book's*
``typography-corrections.jsonl`` (``core.typography_review.
TypographyCorrectionLog.records()``), which cost about 80 microseconds a
row and forced a 512 KiB ``available: false`` ceiling once a book's
correction history grew past it (``api/review_queue.py``'s former
``_TYPOGRAPHY_CORRECTIONS_MAX_BYTES``). This journal makes the typography
numerator as cheap to read as the word, region, and page-kind counts: one
small per-page-keyed file, never the whole book's correction history.

``append_typography_review_counts_best_effort`` is called from
``api/typography.py``'s ``append_typography_correction``, right after
``TypographyCorrectionLog.append`` has durably succeeded — a row naming a
count that never actually landed would be untrustworthy — and the append
itself is best-effort: logged at warning and swallowed, exactly like
``core.review_counts.append_word_review_counts_best_effort``, so an
unwritable rollup never turns an already-accepted correction into a failed
request.

One nuance this journal has that ``WordReviewCountsJournal`` does not:
``TypographyCorrectionLog`` is append-only *per word*, not per page, so a
row here cannot be built from "the one thing that just changed" the way a
page-save's word count can. Each row is instead the page's *full* reviewed
count, recomputed from that page's own correction history (one page's
worth of rows — cheap) at the moment of the write, never a running delta
adjusted up or down from the prior row. Recomputing is what makes a
correction that *un-reviews* a previously-reviewed word (a revision whose
replacement fails the completeness bar) show up as a lower count on the
next row, rather than requiring careful, error-prone decrement bookkeeping
alongside every increment.

This rollup preserves the reviewed-count semantics the ``review-queue``
route's ``typography`` entry has always had, before this journal existed:
each word id's *latest-ever* correction on the page (regardless of the
page's current binding epoch), counted reviewed via ``core.
typography_review.typography_reviewed``, with no staleness check against
the live page's current hashes — the same floor-not-ceiling semantics
``core.typography_review``'s now-removed ``reviewed_word_keys`` had.
``api/typography.py``'s ``typography_page_review`` computes a *different*,
staleness-aware count for the page-review UI; this rollup does not change
that endpoint or its meaning.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from .typography_review import TypographyCorrectionLog, typography_reviewed

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from pdomain_book_tools.typography import TypographyCorrection

log = logging.getLogger(__name__)

_COMPACTION_ROWS_PER_PAGE = 10


@dataclass(frozen=True)
class PageTypographyCounts:
    """One page's typography-review counts as of one accepted correction.

    Keyed by ``logical_page_id`` — the same identity
    ``TypographyCorrectionLog`` records under (``api/typography.py``'s
    ``_logical_page_id``: ``stable_page_id`` for an ordinary project, a
    loaded labeling bundle's own ``page_id`` otherwise) — not
    ``page_index``, unlike ``core.review_counts.PageWordCounts``. Typography
    corrections are never addressed by the labeler's own page ordinal, so a
    rollup keyed by ``page_index`` would silently mis-key every
    labeling-bundle project's rows.

    ``total_words`` records the page's active word count at the moment this
    row was written, for parity with ``PageWordCounts``'s own row shape;
    ``api/review_queue.py``'s ``typography`` entry does not read it, using
    the word-review-counts journal's own total instead so both kinds share
    one authoritative denominator.
    """

    logical_page_id: str
    total_words: int
    typography_reviewed_words: int

    def to_dict(self) -> dict[str, Any]:
        """Render this row as a JSON-serializable mapping."""
        return {
            "logical_page_id": self.logical_page_id,
            "total_words": self.total_words,
            "typography_reviewed_words": self.typography_reviewed_words,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PageTypographyCounts:
        """Restore a row from the mapping produced by :meth:`to_dict`."""
        return cls(
            logical_page_id=str(d["logical_page_id"]),
            total_words=int(d["total_words"]),
            typography_reviewed_words=int(d["typography_reviewed_words"]),
        )


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


class TypographyReviewCountsJournal:
    """Project-local JSONL journal of per-page typography-review counts.

    One row per accepted correction. The reader (``latest_by_page``) keeps
    only the newest row for each ``logical_page_id`` and compacts the file
    once it holds more than ``_COMPACTION_ROWS_PER_PAGE`` rows for every
    page it has a row for — see ``core.review_counts.
    WordReviewCountsJournal`` for the full rationale; this journal mirrors
    it exactly, substituting ``logical_page_id`` (a string) for
    ``page_index`` (an int) as the row key.
    """

    _RELATIVE_PATH: ClassVar[Path] = Path(".pd-pages") / "typography-review-counts.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = Path(project_root) / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def append(self, counts: PageTypographyCounts) -> None:
        """Append one row. Never rewrites a prior row."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(counts.to_dict(), sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _parse_rows(self, raw: bytes) -> list[PageTypographyCounts]:
        rows: list[PageTypographyCounts] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                log.warning("typography-review-counts.jsonl: skipping malformed line %d", line_number)
                continue
            if not isinstance(loaded, dict):
                continue
            try:
                rows.append(PageTypographyCounts.from_dict(loaded))
            except (KeyError, ValueError, TypeError):
                log.warning("typography-review-counts.jsonl: skipping wrong-shaped line %d", line_number)
                continue
        return rows

    def _read_locked(self) -> list[PageTypographyCounts]:
        """Read every row under a shared lock — never torn by a concurrent compaction."""
        try:
            fd = os.open(self._path, os.O_RDONLY)
        except FileNotFoundError:
            return []
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            raw = _read_all(fd)
        finally:
            os.close(fd)
        return self._parse_rows(raw)

    def latest_by_page(self) -> dict[str, PageTypographyCounts]:
        """Every page's most recent typography counts row, from one read.

        Compacts the file (see the class docstring) when the read just made
        shows it has grown past the threshold. The caller already gets the
        answer from the read that triggered it — compaction is purely a
        housekeeping side effect, never a second read.
        """
        rows = self._read_locked()
        latest: dict[str, PageTypographyCounts] = {}
        for row in rows:
            latest[row.logical_page_id] = row
        if latest and len(rows) > _COMPACTION_ROWS_PER_PAGE * len(latest):
            self._compact()
        return latest

    def _compact(self) -> None:
        """Rewrite the journal to hold exactly the newest row per page.

        See ``core.review_counts.WordReviewCountsJournal._compact`` for why
        this rewrites the file in place (truncate + write to the same
        descriptor) rather than write-temp-then-rename.
        """
        try:
            fd = os.open(self._path, os.O_RDWR)
        except FileNotFoundError:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = _read_all(fd)
            rows = self._parse_rows(raw)
            latest: dict[str, PageTypographyCounts] = {}
            for row in rows:
                latest[row.logical_page_id] = row
            payload = "".join(
                json.dumps(counts.to_dict(), sort_keys=True) + "\n" for _, counts in sorted(latest.items())
            ).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)


def append_typography_review_counts_best_effort(
    *,
    correction_log: TypographyCorrectionLog,
    logical_page_id: str,
    total_words: int,
    required_labels: Collection[str],
) -> None:
    """Append one rollup row for *logical_page_id*. Best effort.

    Called from ``api/typography.py``'s ``append_typography_correction``,
    right after ``correction_log.append`` has already durably succeeded —
    see the module docstring for why the row is recomputed fresh from that
    page's own correction history rather than adjusted from the prior row.
    ``correction_log`` is the same ``TypographyCorrectionLog`` instance the
    caller just appended through, reused rather than reconstructed.

    Runs in its own try/except, logged at warning and swallowed: a failure
    here must never surface as a failed correction, because the correction
    it would be counting has already landed durably. A row that never gets
    written just makes a later count say "did not see this page" — the
    review-queue route already has a field for that (``pages_not_counted``)
    — rather than reporting an already-accepted correction as failed.
    """
    try:
        latest_by_word: dict[str, TypographyCorrection] = {}
        for record in correction_log.records(logical_page_id):
            latest_by_word[record.correction.word_id] = record.correction
        reviewed_words = sum(
            1
            for correction in latest_by_word.values()
            if typography_reviewed(correction, required_labels=required_labels)
        )
        TypographyReviewCountsJournal(correction_log.project_root).append(
            PageTypographyCounts(
                logical_page_id=logical_page_id,
                total_words=total_words,
                typography_reviewed_words=reviewed_words,
            )
        )
    except Exception:
        log.warning(
            "typography-review-counts append failed for logical_page_id=%s",
            logical_page_id,
            exc_info=True,
        )


__all__ = [
    "PageTypographyCounts",
    "TypographyReviewCountsJournal",
    "append_typography_review_counts_best_effort",
]
