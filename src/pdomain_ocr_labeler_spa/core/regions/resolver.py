"""The one read path both the labeler and the execution engine use.

Callers never touch the three stores directly. They ask for a page's resolved
regions and get confirmed regions if any exist on that page — a page with a
confirmed region has been reviewed, and proposals are the pre-review view, not
a supplement to it. Failing that, proposals above a confidence threshold.
Failing that, nothing.

The labeler passes a threshold of zero and renders proposals visibly differently.
The execution engine passes a real threshold and takes the result as the answer.
Because there is one function, there is no second pipeline to keep in step.

A returned proposal also carries whether it is stale: whether the facets its
run actually depended on have since changed on the page. Staleness never
suppresses a proposal — it is a fact a caller (chiefly the labeler) renders,
not a filter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pdomain_ocr_labeler_spa.core.regions.models import Disposition, ResolvedRegion

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionDecision, RegionProposal


def resolve_regions(
    confirmed: Sequence[ResolvedRegion],
    proposals: Sequence[RegionProposal],
    decisions: Mapping[str, RegionDecision],
    runs: Mapping[str, ProposalRun],
    *,
    threshold: float,
    current_facet_digests: Mapping[str, str],
) -> list[ResolvedRegion]:
    """Resolve one page's regions from the three stores.

    Args:
        confirmed: Regions a person put there, already lifted from the page.
        proposals: What a machine said about this page.
        decisions: The decision for each proposal id, where one exists. A
            proposal absent from this mapping is unreviewed, which is a
            different fact from a recorded rejection.
        runs: The `ProposalRun` each proposal in `proposals` belongs to,
            keyed by run_id, so staleness can be judged against what that
            run actually depended on. A proposal whose run is missing from
            this mapping is treated as not stale — there is nothing to
            compare against.
        threshold: Minimum confidence a proposal needs to stand in for a missing
            confirmed region. Zero shows everything, which is what the labeler
            wants.
        current_facet_digests: The page's facet digests as of right now,
            keyed by facet name (`word_boxes`, `line_structure`, `page_image`,
            `word_text`). Compared only against the facets a proposal's run
            named in `depends_on` — a run that never read `word_text` is
            never invalidated by a text-only edit.

    Returns:
        The confirmed regions, in the order given, if any exist on this page —
        proposals are not shown once a page has been reviewed. Otherwise the
        surviving proposals, in the order given: not rejected, not already
        promoted into a confirmed region by an earlier decision, and at or
        above `threshold`.
    """
    if confirmed:
        # A page with any confirmed regions has been reviewed by a person.
        # Proposals are the pre-review view; once confirmed regions exist,
        # they are what a caller sees, not a mix of the two.
        return list(confirmed)

    resolved: list[ResolvedRegion] = []

    for proposal in proposals:
        decision = decisions.get(proposal.proposal_id)
        if decision is not None and decision.disposition is Disposition.REJECTED:
            # A refusal is a fact. Never fall back to a proposal a person
            # already looked at and turned down.
            continue
        if decision is not None and decision.region_id is not None:
            # Already promoted into a confirmed region, which is in `confirmed`.
            continue
        if proposal.confidence < threshold:
            continue

        run = runs.get(proposal.run_id)
        stale = False
        if run is not None:
            proposal_digests = run.page_facet_digests.get(proposal.page_index, {})
            stale = any(
                current_facet_digests.get(facet) != proposal_digests.get(facet) for facet in run.depends_on
            )

        resolved.append(
            ResolvedRegion(
                role=proposal.role,
                box=proposal.box,
                confirmed=False,
                confidence=proposal.confidence,
                proposal_id=proposal.proposal_id,
                region_id=None,
                stale=stale,
            )
        )

    return resolved
