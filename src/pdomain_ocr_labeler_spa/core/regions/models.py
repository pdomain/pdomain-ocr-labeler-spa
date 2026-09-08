"""Records that keep a machine's region proposals beside a person's decisions.

Proposals are immutable once written. Decisions join a proposal to what a person
did with it. A run ties a batch of proposals to the model that made them and to
the exact page facets each was computed from, which is what lets a later detector
be scored against this one on identical pages, and lets staleness be judged per
facet rather than by any change anywhere on the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pdomain_book_contracts.annotation import KnowledgeState, RegionRole

#: The four facets a region proposal run can depend on. A geometry proposal
#: depends on the first three; none depend on ``word_text`` — see the spec's
#: "A proposal goes stale per facet, not per page".
FACET_WORD_BOXES = "word_boxes"
FACET_LINE_STRUCTURE = "line_structure"
FACET_PAGE_IMAGE = "page_image"
FACET_WORD_TEXT = "word_text"
ALL_FACETS = frozenset({FACET_WORD_BOXES, FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_TEXT})


class Disposition(StrEnum):
    """What a person did with one proposal, or how an earlier decision reached it."""

    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    CARRIED = "carried"

    @property
    def knowledge_state(self) -> KnowledgeState:
        """The knowledge state this disposition asserts about the proposal."""
        if self is Disposition.REJECTED:
            return KnowledgeState.VERIFIED_NEGATIVE
        return KnowledgeState.POSITIVE


@dataclass(frozen=True)
class RegionProposal:
    """One region a machine proposed. Never edited after it is written."""

    proposal_id: str
    run_id: str
    page_index: int
    role: RegionRole
    box: tuple[int, int, int, int]
    confidence: float
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        left, top, right, bottom = self.box
        if left > right:
            raise ValueError(f"box has L > R ({left} > {right}); require L <= R")
        if top > bottom:
            raise ValueError(f"box has T > B ({top} > {bottom}); require T <= B")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} is outside 0.0 to 1.0")

    def to_dict(self) -> dict[str, Any]:
        """Render this proposal as a JSON-serializable mapping."""
        return {
            "proposal_id": self.proposal_id,
            "run_id": self.run_id,
            "page_index": self.page_index,
            "role": self.role.value,
            "box": list(self.box),
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegionProposal:
        """Restore a proposal from the mapping produced by :meth:`to_dict`."""
        box = d["box"]
        return cls(
            proposal_id=str(d["proposal_id"]),
            run_id=str(d["run_id"]),
            page_index=int(d["page_index"]),
            role=RegionRole(str(d["role"])),
            box=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
            confidence=float(d["confidence"]),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass(frozen=True)
class ProposalRun:
    """One pass of one model over one book, and what it was conditioned on.

    ``page_facet_digests`` replaces a single whole-page hash: fixing a typo
    must not invalidate a geometry proposal that never read the text facet.
    It is keyed by page index, then by facet name (one of ``FACET_WORD_BOXES``,
    ``FACET_LINE_STRUCTURE``, ``FACET_PAGE_IMAGE``, ``FACET_WORD_TEXT``).
    ``depends_on`` names which of those facets this run's proposals were
    actually computed from — the resolver compares only those at read time.
    """

    run_id: str
    model_id: str
    model_version: str
    created_at: str
    page_facet_digests: dict[int, dict[str, str]]
    depends_on: frozenset[str]
    page_kind_decision_ref: str | None
    page_kind_was_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        """Render this run as a JSON-serializable mapping."""
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            # JSON object keys are strings; page indices are restored on read.
            "page_facet_digests": {
                str(index): dict(facets) for index, facets in self.page_facet_digests.items()
            },
            "depends_on": sorted(self.depends_on),
            "page_kind_decision_ref": self.page_kind_decision_ref,
            "page_kind_was_confirmed": self.page_kind_was_confirmed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProposalRun:
        """Restore a run from the mapping produced by :meth:`to_dict`."""
        raw_digests = d.get("page_facet_digests") or {}
        return cls(
            run_id=str(d["run_id"]),
            model_id=str(d["model_id"]),
            model_version=str(d["model_version"]),
            created_at=str(d["created_at"]),
            page_facet_digests={
                int(index): {str(facet): str(digest) for facet, digest in facets.items()}
                for index, facets in raw_digests.items()
            },
            depends_on=frozenset(str(facet) for facet in (d.get("depends_on") or [])),
            page_kind_decision_ref=(
                str(d["page_kind_decision_ref"]) if d.get("page_kind_decision_ref") is not None else None
            ),
            page_kind_was_confirmed=bool(d.get("page_kind_was_confirmed", False)),
        )


@dataclass(frozen=True)
class RegionDecision:
    """What a person decided about one proposal.

    A proposal with no decision is unreviewed. A proposal with a ``REJECTED``
    decision was looked at and refused. Those are opposite facts, and keeping
    them apart is why this record exists at all.
    """

    decision_id: str
    run_id: str
    proposal_id: str
    disposition: Disposition
    region_id: str | None
    actor: str
    decided_at: str
    carried_from_run_id: str | None = None
    carried_from_proposal_id: str | None = None

    def __post_init__(self) -> None:
        if self.disposition is not Disposition.REJECTED and self.region_id is None:
            raise ValueError(f"a {self.disposition.value} decision must name the region_id it produced")
        if self.disposition is Disposition.CARRIED:
            if self.carried_from_run_id is None or self.carried_from_proposal_id is None:
                raise ValueError(
                    "a carried decision must name carried_from_run_id and carried_from_proposal_id"
                )
        elif self.carried_from_run_id is not None or self.carried_from_proposal_id is not None:
            raise ValueError(
                "carried_from_run_id/carried_from_proposal_id are only set on a carried decision"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this decision as a JSON-serializable mapping."""
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "proposal_id": self.proposal_id,
            "disposition": self.disposition.value,
            "region_id": self.region_id,
            "actor": self.actor,
            "decided_at": self.decided_at,
            "carried_from_run_id": self.carried_from_run_id,
            "carried_from_proposal_id": self.carried_from_proposal_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegionDecision:
        """Restore a decision from the mapping produced by :meth:`to_dict`."""
        return cls(
            decision_id=str(d["decision_id"]),
            run_id=str(d["run_id"]),
            proposal_id=str(d["proposal_id"]),
            disposition=Disposition(str(d["disposition"])),
            region_id=str(d["region_id"]) if d.get("region_id") is not None else None,
            actor=str(d.get("actor", "default")),
            decided_at=str(d["decided_at"]),
            carried_from_run_id=(
                str(d["carried_from_run_id"]) if d.get("carried_from_run_id") is not None else None
            ),
            carried_from_proposal_id=(
                str(d["carried_from_proposal_id"]) if d.get("carried_from_proposal_id") is not None else None
            ),
        )


@dataclass(frozen=True)
class ResolvedRegion:
    """One region as a caller sees it, with where it came from.

    ``confirmed`` is True when a person put it there. The labeler renders the
    two differently; the execution engine only ever sees proposals.

    ``member_word_signatures`` names the words the region holds, as stable
    bounding-box signatures — never a line/word ordinal, since line numbering
    is not stable across the band-identification fixes. Populated for a
    confirmed region lifted off a ``Block`` (see the routes plan's
    ``confirmed_regions_from_page``); empty for a region resolved straight
    from a proposal, which carries no membership of its own.

    ``stale`` is True when the run that produced this proposal read facets
    that have since changed on the page. A stale proposal is still returned,
    not suppressed — a person still sees what the model said and judges it
    against the page as it now stands. Always False for a confirmed region.
    """

    role: RegionRole
    box: tuple[int, int, int, int]
    confirmed: bool
    confidence: float | None
    proposal_id: str | None
    region_id: str | None
    member_word_signatures: tuple[tuple[float, float, float, float, bool | None], ...] = ()
    stale: bool = False
