"""``_best_carry_match`` picks one confirmed region deterministically."""

from __future__ import annotations

from pdomain_book_contracts.annotation import RegionRole

from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import _best_carry_match
from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal, ResolvedRegion


def _confirmed(region_id: str, box: tuple[int, int, int, int]) -> ResolvedRegion:
    return ResolvedRegion(
        role=RegionRole.POETRY,
        box=box,
        confirmed=True,
        confidence=None,
        proposal_id=None,
        region_id=region_id,
    )


def _proposal(box: tuple[int, int, int, int]) -> RegionProposal:
    return RegionProposal(
        proposal_id="p",
        run_id="r",
        page_index=0,
        role=RegionRole.POETRY,
        box=box,
        confidence=0.5,
        evidence={},
    )


def test_an_exact_iou_tie_keeps_the_earlier_region() -> None:
    confirmed = [_confirmed("first", (0, 0, 100, 100)), _confirmed("second", (0, 0, 100, 100))]

    match = _best_carry_match(_proposal((0, 0, 100, 100)), confirmed)

    assert match is not None
    assert match.region_id == "first"


def test_the_higher_iou_wins_regardless_of_order() -> None:
    confirmed = [_confirmed("looser", (0, 0, 100, 110)), _confirmed("tighter", (0, 0, 100, 100))]

    match = _best_carry_match(_proposal((0, 0, 100, 100)), confirmed)

    assert match is not None
    assert match.region_id == "tighter"


def test_a_match_exactly_at_the_threshold_counts() -> None:
    # IoU 70/100 = 0.7, the threshold itself.
    confirmed = [_confirmed("edge", (0, 0, 100, 70))]

    match = _best_carry_match(_proposal((0, 0, 100, 100)), confirmed)

    assert match is not None
    assert match.region_id == "edge"
