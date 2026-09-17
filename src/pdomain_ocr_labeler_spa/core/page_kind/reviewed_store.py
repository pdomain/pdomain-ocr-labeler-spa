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
from typing import Any, ClassVar, Literal

from pdomain_book_contracts.annotation import PageKind

log = logging.getLogger(__name__)

ReviewMethod = Literal["single", "bulk", "history"]


@dataclass(frozen=True)
class PageKindReviewedMarker:
    """One record of a person looking at one page's kind.

    ``kind`` and ``method`` are optional — a marker written before
    pdomain-ocr-synth's 2026-09-17-page-kind-review-design.md has neither.
    ``method`` distinguishes the page route (``single``), the book-wide bulk
    route (``bulk``), and an undo/redo that changed the page's kind
    (``history``). A ``history`` marker whose ``kind`` is ``None`` withdraws
    the review — see ``PageKindReviewedStore.is_reviewed`` — because the undo
    took the page back to before anyone confirmed it.
    """

    page_index: int
    reviewed_at: str
    actor: str
    note: str | None
    kind: PageKind | None = None
    method: ReviewMethod | None = None

    def to_dict(self) -> dict[str, Any]:
        """Render this marker as a JSON-serializable mapping."""
        return {
            "page_index": self.page_index,
            "reviewed_at": self.reviewed_at,
            "actor": self.actor,
            "note": self.note,
            "kind": self.kind.value if self.kind is not None else None,
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageKindReviewedMarker:
        """Restore a marker from the mapping produced by :meth:`to_dict`.

        Old markers carry neither ``kind`` nor ``method`` and still parse —
        both default to ``None``. An unrecognised ``method`` value (should
        never happen from this store's own writes) also falls back to
        ``None`` rather than raising, matching this journal's general
        skip-the-bad-line discipline.
        """
        kind_raw = d.get("kind")
        method_raw = d.get("method")
        method: ReviewMethod | None
        if method_raw == "single":
            method = "single"
        elif method_raw == "bulk":
            method = "bulk"
        elif method_raw == "history":
            method = "history"
        else:
            method = None
        return cls(
            page_index=int(d["page_index"]),
            reviewed_at=str(d["reviewed_at"]),
            actor=str(d["actor"]) if d.get("actor") is not None else "default",
            note=str(d["note"]) if d.get("note") is not None else None,
            kind=PageKind(str(kind_raw)) if kind_raw is not None else None,
            method=method,
        )


def is_marker_reviewed(marker: PageKindReviewedMarker | None) -> bool:
    """Whether ``marker`` counts as a live review, not a withdrawn one.

    A ``history`` marker with no ``kind`` withdraws the review — see
    ``PageKindReviewedMarker``.
    """
    if marker is None:
        return False
    return not (marker.method == "history" and marker.kind is None)


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
        self,
        page_index: int,
        reviewed_at: str,
        *,
        actor: str = "default",
        note: str | None = None,
        kind: PageKind | None = None,
        method: ReviewMethod | None = None,
    ) -> None:
        """Record that a person looked at this page's kind. Never rewrites a prior mark.

        ``kind`` and ``method`` are optional so existing callers that only
        care about "has anyone looked" keep working unchanged. A caller that
        also wants the book route to answer without loading the page, or that
        is recording an undo/redo, passes both.
        """
        marker = PageKindReviewedMarker(
            page_index=page_index,
            reviewed_at=reviewed_at,
            actor=actor,
            note=note,
            kind=kind,
            method=method,
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

    def latest_by_page(self) -> dict[int, PageKindReviewedMarker]:
        """Every page's most recent review marker, from one read.

        A caller that needs every page's marker (e.g. the book-wide
        page-kinds route) should call this once rather than
        ``latest_for_page`` per page — each ``latest_for_page`` call re-reads
        and re-parses the whole journal, so a per-page loop over it costs one
        full-file parse per page instead of one for the whole loop.
        """
        latest: dict[int, PageKindReviewedMarker] = {}
        for marker in self._read():
            latest[marker.page_index] = marker
        return latest

    def is_reviewed(self, page_index: int) -> bool:
        """Whether this page carries a live (non-withdrawn) review marker."""
        return is_marker_reviewed(self.latest_for_page(page_index))

    def reviewed_page_indices(self) -> frozenset[int]:
        """Every page index carrying a live review marker, from one read.

        A caller checking many pages (e.g. a book-scoped job walking every
        loaded page) should call this once rather than ``is_reviewed`` per
        page — each ``is_reviewed`` call re-reads and re-parses the whole
        journal, so a per-page loop over it costs one full-file parse per
        page instead of one for the whole loop.
        """
        return frozenset(idx for idx, marker in self.latest_by_page().items() if is_marker_reviewed(marker))
