"""Lift confirmed ``Block`` regions off a page into ``ResolvedRegion`` views.

A region is a ``Block`` carrying an explicit ``region_id`` in
``additional_block_attributes`` — the marker that a person created or edited it
through the region routes. A block with a role label but no ``region_id`` is
ordinary paragraph/line structure inherited from OCR or the reorganize
pipeline, not a region under this design. ``additional_block_attributes`` is a
plain ``dict[str, object]`` that ``Block.to_dict``/``from_dict`` already
round-trips, so no new storage is needed to carry it.

Also computes the four facet digests a ``ProposalRun`` names in ``depends_on``
and a caller compares against at read time (spec §"A proposal goes stale per
facet, not per page"). The digest algorithm lives here, alongside the adapter,
because both are read off the same live ``Page``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.block import Block
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.word import Word

from pdomain_ocr_labeler_spa.core.regions.models import ResolvedRegion

_REGION_ID_KEY = "region_id"
_SOURCE_PROPOSAL_ID_KEY = "source_proposal_id"


def _walk_blocks(items: Sequence[Word | Block]) -> Iterator[Block]:
    """Yield every ``Block`` reachable from ``items``, at any nesting depth."""
    for item in items:
        if isinstance(item, Block):
            yield item
            yield from _walk_blocks(item.items)


def find_region_block(page: Page, region_id: str) -> Block | None:
    """Return the ``Block`` carrying ``region_id`` anywhere on ``page``, or ``None``."""
    for block in _walk_blocks(page.items):
        if block.additional_block_attributes.get(_REGION_ID_KEY) == region_id:
            return block
    return None


def confirmed_regions_from_page(page: Page) -> list[ResolvedRegion]:
    """Every region a person confirmed on this page, as ``ResolvedRegion``.

    Skips blocks with no ``region_id`` (ordinary structure) and blocks whose
    first role label is not a recognised ``RegionRole`` value (defensive
    against a future role or a block edited outside this design) rather than
    raising — a page must always render, even with one malformed region.

    ``member_word_signatures`` is read straight off ``block.words`` (which
    recurses through a nesting-capable ``BLOCKS`` container the same as a
    leaf ``WORDS`` block) as stable bounding-box signatures — never a
    line/word ordinal. ``proposal_id`` surfaces whatever the routes stamped
    into ``source_proposal_id`` when the region was created or promoted: a
    real proposal id, the explicit hand-drawn sentinel, or ``None`` for a
    region blob written before this correction landed.
    """
    resolved: list[ResolvedRegion] = []
    for block in _walk_blocks(page.items):
        region_id = block.additional_block_attributes.get(_REGION_ID_KEY)
        if not isinstance(region_id, str) or not region_id:
            continue
        if not block.block_role_labels:
            continue
        try:
            role = RegionRole(block.block_role_labels[0])
        except ValueError:
            continue
        if block.bounding_box is None:
            continue
        left, top, right, bottom = block.bounding_box.to_ltrb()
        source_proposal_id = block.additional_block_attributes.get(_SOURCE_PROPOSAL_ID_KEY)
        member_signatures = tuple(
            sig for sig in (word.bbox_signature for word in block.words) if sig is not None
        )
        resolved.append(
            ResolvedRegion(
                role=role,
                box=(round(left), round(top), round(right), round(bottom)),
                confirmed=True,
                confidence=None,
                proposal_id=source_proposal_id if isinstance(source_proposal_id, str) else None,
                region_id=region_id,
                member_word_signatures=member_signatures,
            )
        )
    return resolved


def _digest_of(payload: object) -> str:
    """Deterministic sha256 hex digest of a JSON-serializable payload."""
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _carries_region_id(block: Block) -> bool:
    """True when ``block`` is a region a person created, not OCR line structure."""
    region_id = block.additional_block_attributes.get(_REGION_ID_KEY)
    return isinstance(region_id, str) and bool(region_id)


def compute_page_facet_digests(page: Page, *, image_digest: str | None) -> dict[str, str]:
    """Digest each facet a proposal run can depend on.

    Recomputed from the live page rather than declared by a mutation route —
    spec §"Facet digests are computed, never declared" — so a change is
    caught no matter which route made it.

    ``line_structure`` skips every block carrying a ``region_id``. A leaf
    region is a ``WORDS``-typed ``Block``, and ``Block.lines`` returns
    ``[self]`` for one, so a confirmed region joins ``page.lines`` — without
    the skip, confirming one proposal would change ``line_structure`` and
    mark every *other* proposal on that page stale against its own run. A
    region is a person's decision layered over the line structure, not part
    of it.

    ``image_digest`` is passed in rather than derived here: the block tree
    carries no reference to the source image blob, only the page's
    content-addressed provenance chain does (``ProvenanceNode.blob_refs[1]``,
    by the convention ``pdomain_ops.page_aggregate`` documents — index 0 is
    the page-content JSON, index 1 the source image). When the caller has no
    image digest the ``page_image`` facet is **omitted** rather than filled
    with a stand-in: the labeler-edit path writes ``blob_refs=[content_hash]``
    alone, so index 0 is the page *content*, and publishing it as
    ``page_image`` would invalidate every geometry proposal on a typo fix —
    exactly what per-facet digests exist to prevent. A missing facet compares
    unequal to a recorded one, so an omitted ``page_image`` reads as stale,
    never as falsely fresh.

    Word-box rows are serialized to strings and sorted as strings — not as
    raw signature tuples — because a signature's trailing ``is_normalized``
    field is ``bool | None``, and ``None``/``bool`` are not orderable.
    """
    word_box_rows = sorted(
        json.dumps(list(sig), default=str)
        for sig in (word.bbox_signature for word in page.words)
        if sig is not None
    )
    word_boxes = _digest_of(word_box_rows)
    line_structure = _digest_of(
        [
            [
                line.block_category.value if line.block_category is not None else None,
                line.override_page_sort_order,
            ]
            for line in page.lines
            if not _carries_region_id(line)
        ]
    )
    word_text = _digest_of([[word.text, word.ground_truth_text] for word in page.words])
    digests = {
        "word_boxes": word_boxes,
        "line_structure": line_structure,
        "word_text": word_text,
    }
    if image_digest:
        digests["page_image"] = image_digest
    return digests


__all__ = ["compute_page_facet_digests", "confirmed_regions_from_page", "find_region_block"]
