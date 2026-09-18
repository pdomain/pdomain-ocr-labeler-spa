"""Append-only per-page word-review-counts journal.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-
what-to-review-next.md "A per-page count journal, written where the page is
already saved".

``core.page_state.save_page_content_to_store`` appends one row here after a
page's content blob is durably saved — the same point that function already
has the page's fresh content hash to return. A word only counts as reviewed
when ``"validated"`` is in its ``word_labels`` (``api/words.py``'s
``_apply_word_validated``), a fact that otherwise lives only inside the
page's content blob and would cost a full page-blob parse per page to count.
This journal makes counting a book's words as cheap as counting its regions
or page kinds: a read of one small file, never a page load.

Mirrors ``PageKindProposalLog``/``PageKindReviewedStore`` — a JSONL row per
event, an OS append lock, fsync before ``append`` returns, no row ever
rewritten by ``append`` itself. It diverges from those two in one respect:
this is the only one of the three journals whose reader (``latest_by_page``)
can *also* rewrite the file, to compact it once it has grown past ten rows
for every page it holds a row for. Because that rewrite mutates the file
in place rather than only appending to it, reads and the compacting rewrite
both take an explicit lock (shared for a plain read, exclusive for
``append`` and compaction) — plain unlocked reads, safe when the only writer
ever appends, are not safe once a writer can also truncate the file out
from under one.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

log = logging.getLogger(__name__)

_COMPACTION_ROWS_PER_PAGE = 10


@dataclass(frozen=True)
class PageWordCounts:
    """One page's word counts as of one saved content hash.

    ``content_hash`` is what makes a row trustworthy without opening the
    page: a row whose hash does not match the page's current head is
    detectably stale, though the review-queue route (slice 5) does not
    perform that check today — it treats every row it reads as current, the
    same way the region and page-kind journals treat their latest rows.
    """

    page_index: int
    content_hash: str
    total_words: int
    validated_words: int

    def to_dict(self) -> dict[str, Any]:
        """Render this row as a JSON-serializable mapping."""
        return {
            "page_index": self.page_index,
            "content_hash": self.content_hash,
            "total_words": self.total_words,
            "validated_words": self.validated_words,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PageWordCounts:
        """Restore a row from the mapping produced by :meth:`to_dict`."""
        return cls(
            page_index=int(d["page_index"]),
            content_hash=str(d["content_hash"]),
            total_words=int(d["total_words"]),
            validated_words=int(d["validated_words"]),
        )


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


class WordReviewCountsJournal:
    """Project-local JSONL journal of per-page word counts.

    One row per page-save. The reader (``latest_by_page``) keeps only the
    newest row for each page, exactly as ``PageKindProposalLog.latest_by_page``
    and ``PageKindReviewedStore.latest_by_page`` do, and compacts the file
    once it holds more than ``_COMPACTION_ROWS_PER_PAGE`` rows for every page
    it has a row for — generous enough that an ordinary session never
    triggers it, small enough that the file cannot grow indefinitely. The
    comparison is against the number of *distinct pages the journal itself
    has ever counted* (``len(latest)``), not the book's total page count: a
    three-page book that has only ever saved page 0 should not need thirty
    rows of headroom just because the book has three hundred pages.
    """

    _RELATIVE_PATH: ClassVar[Path] = Path(".pd-pages") / "word-review-counts.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = Path(project_root) / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def append(self, counts: PageWordCounts) -> None:
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

    def _parse_rows(self, raw: bytes) -> list[PageWordCounts]:
        rows: list[PageWordCounts] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                log.warning("word-review-counts.jsonl: skipping malformed line %d", line_number)
                continue
            if not isinstance(loaded, dict):
                continue
            try:
                rows.append(PageWordCounts.from_dict(loaded))
            except (KeyError, ValueError, TypeError):
                log.warning("word-review-counts.jsonl: skipping wrong-shaped line %d", line_number)
                continue
        return rows

    def _read_locked(self) -> list[PageWordCounts]:
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

    def latest_by_page(self) -> dict[int, PageWordCounts]:
        """Every page's most recent counts row, from one read.

        Compacts the file (see the class docstring) when the read just made
        shows it has grown past the threshold. The caller already gets the
        answer from the read that triggered it — compaction is purely a
        housekeeping side effect, never a second read.
        """
        rows = self._read_locked()
        latest: dict[int, PageWordCounts] = {}
        for row in rows:
            latest[row.page_index] = row
        if latest and len(rows) > _COMPACTION_ROWS_PER_PAGE * len(latest):
            self._compact()
        return latest

    def _compact(self) -> None:
        """Rewrite the journal to hold exactly the newest row per page.

        Re-reads fresh under the exclusive lock rather than reusing the
        caller's already-parsed rows, so a concurrent append landing between
        the two reads is never lost. Rewrites in place (truncate + write to
        the same file descriptor) rather than write-temp-then-rename: a
        rename would swap the path to a new inode, and a concurrent
        ``append`` that already opened the old path before the rename would
        go on to lock and write to the now-unreachable old inode, silently
        losing that row. Locking in place keeps every opener — appenders and
        this compaction alike — contending for the same inode's lock.
        """
        try:
            fd = os.open(self._path, os.O_RDWR)
        except FileNotFoundError:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = _read_all(fd)
            rows = self._parse_rows(raw)
            latest: dict[int, PageWordCounts] = {}
            for row in rows:
                latest[row.page_index] = row
            payload = "".join(
                json.dumps(counts.to_dict(), sort_keys=True) + "\n" for _, counts in sorted(latest.items())
            ).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)


__all__ = ["PageWordCounts", "WordReviewCountsJournal"]
