"""Append-only journal recording that a person reviewed one page's kind.

A page has one page kind, so the human's answer replaces the machine's whole
outright — the confirm route never diffs it against
``PageKindProposalLog.latest_proposal_for_page``; nothing at that level needs
to tell an acceptance from a change. This store answers a different question:
whether anyone has looked at all. See pdomain-ocr-synth's docs/specs/2026-09-07-region-provenance-
and-persistence-design.md "Page kind needs a marker, not a decision log".
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageKindReviewedMarker:
    """One record of a person looking at one page's kind."""

    page_index: int
    reviewed_at: str
    actor: str
    note: str | None

    def to_dict(self) -> dict[str, Any]:
        """Render this marker as a JSON-serializable mapping."""
        return {
            "page_index": self.page_index,
            "reviewed_at": self.reviewed_at,
            "actor": self.actor,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageKindReviewedMarker:
        """Restore a marker from the mapping produced by :meth:`to_dict`."""
        return cls(
            page_index=int(d["page_index"]),
            reviewed_at=str(d["reviewed_at"]),
            actor=str(d["actor"]) if d.get("actor") is not None else "default",
            note=str(d["note"]) if d.get("note") is not None else None,
        )


class PageKindReviewedStore:
    """Project-local JSONL journal of per-page review markers."""

    _RELATIVE_PATH: ClassVar[Path] = Path(".pd-pages") / "page-kind-reviewed.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = Path(project_root) / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def mark_reviewed(
        self, page_index: int, reviewed_at: str, *, actor: str = "default", note: str | None = None
    ) -> None:
        """Record that a person looked at this page's kind. Never rewrites a prior mark."""
        marker = PageKindReviewedMarker(
            page_index=page_index, reviewed_at=reviewed_at, actor=actor, note=note
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(marker.to_dict(), sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read(self) -> list[PageKindReviewedMarker]:
        if not self._path.exists():
            return []
        markers: list[PageKindReviewedMarker] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded = json.loads(stripped)
                except json.JSONDecodeError:
                    log.warning("page-kind-reviewed.jsonl: skipping malformed line %d", line_number)
                    continue
                if not isinstance(loaded, dict):
                    continue
                try:
                    markers.append(PageKindReviewedMarker.from_dict(loaded))
                except (KeyError, ValueError, TypeError):
                    log.warning("page-kind-reviewed.jsonl: skipping wrong-shaped line %d", line_number)
                    continue
        return markers

    def latest_for_page(self, page_index: int) -> PageKindReviewedMarker | None:
        """The most recent review marker for one page, or ``None`` if nobody has looked."""
        latest: PageKindReviewedMarker | None = None
        for marker in self._read():
            if marker.page_index == page_index:
                latest = marker
        return latest

    def is_reviewed(self, page_index: int) -> bool:
        """Whether any review marker exists for this page."""
        return self.latest_for_page(page_index) is not None

    def reviewed_page_indices(self) -> frozenset[int]:
        """Every page index carrying at least one review marker, from one read.

        A caller checking many pages (e.g. a book-scoped job walking every
        loaded page) should call this once rather than ``is_reviewed`` per
        page — each ``is_reviewed`` call re-reads and re-parses the whole
        journal, so a per-page loop over it costs one full-file parse per
        page instead of one for the whole loop.
        """
        return frozenset(marker.page_index for marker in self._read())
