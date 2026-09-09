"""Records that keep a book-scoped page-kind classifier's claims beside a
person's confirmed answer.

Page kind is classified per book, proposed here, and confirmed by a human
directly onto ``Page.page_kind``. Unlike regions, page kind needs no decision
log: a page has one kind, so the human's answer replaces the machine's whole.
See pdomain-ocr-synth's docs/specs/2026-09-07-region-provenance-and-persistence-design.md
"Page kind needs a marker, not a decision log".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pdomain_book_contracts.annotation import PageKind


@dataclass(frozen=True)
class PageKindProposalRun:
    """One book-scoped pass of the page-kind classifier."""

    run_id: str
    model_id: str
    model_version: str
    created_at: str
    page_count: int

    def to_dict(self) -> dict[str, Any]:
        """Render this run as a JSON-serializable mapping."""
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "page_count": self.page_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageKindProposalRun:
        """Restore a run from the mapping produced by :meth:`to_dict`."""
        return cls(
            run_id=str(d["run_id"]),
            model_id=str(d["model_id"]),
            model_version=str(d["model_version"]),
            created_at=str(d["created_at"]),
            page_count=int(d["page_count"]),
        )


@dataclass(frozen=True)
class PageKindProposal:
    """One page's proposed kind. Never edited after it is written.

    ``confidence`` is ``None`` for the classifier's own refusal (``kind`` is
    then ``PageKind.UNKNOWN``) — a missing confidence, not a zero one.
    """

    proposal_id: str
    run_id: str
    page_index: int
    kind: PageKind
    confidence: float | None
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} is outside 0.0 to 1.0")

    def to_dict(self) -> dict[str, Any]:
        """Render this proposal as a JSON-serializable mapping."""
        return {
            "proposal_id": self.proposal_id,
            "run_id": self.run_id,
            "page_index": self.page_index,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageKindProposal:
        """Restore a proposal from the mapping produced by :meth:`to_dict`."""
        confidence = d.get("confidence")
        return cls(
            proposal_id=str(d["proposal_id"]),
            run_id=str(d["run_id"]),
            page_index=int(d["page_index"]),
            kind=PageKind(str(d["kind"])),
            confidence=float(confidence) if confidence is not None else None,
            evidence=dict(d.get("evidence") or {}),
        )
