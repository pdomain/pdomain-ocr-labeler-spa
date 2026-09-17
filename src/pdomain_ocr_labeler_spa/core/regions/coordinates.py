"""Convert a region box between source pixels and a page's storage convention.

The API always speaks source pixels: ``RegionProposal.box``, the ``BBox``
request bodies ``api/regions.py`` accepts, and every confirmed
``RegionView.box`` it serves. A confirmed region's stored
``Block.bounding_box`` matches whatever convention the page's own word boxes
use — normalized (0-to-1) on a page DocTR OCR'd today, pixel-space on an
older page. Convert at the boundary: the write routes convert an incoming
pixel box down to the page's convention before building or editing a
``Block``; the read path (``block_adapter.confirmed_regions_from_page``)
converts a stored box back up to pixels before it reaches ``RegionView``.
Mirrors the rule ``core/page_to_line_matches.py``'s ``_bbox_to_model``
already applies to words.
"""

from __future__ import annotations

from pdomain_book_contracts.geometry.bounding_box import BoundingBox


def normalized_to_pixels(
    box: tuple[float, float, float, float], *, page_width: int, page_height: int
) -> tuple[float, float, float, float]:
    """Scale a 0-to-1 box up to source pixels. Callers round to ``int`` themselves.

    Shared by the ``Block``-box conversion below and the furniture detector's
    word-box conversion (``core/regions/furniture.py``), which scales against
    the measurement's ``source_frame`` rather than a ``Block``.
    """
    left, top, right, bottom = box
    return (
        left * page_width,
        top * page_height,
        right * page_width,
        bottom * page_height,
    )


def pixel_box_to_bounding_box(
    box: tuple[int, int, int, int],
    *,
    page_width: int,
    page_height: int,
    is_normalized: bool,
) -> BoundingBox:
    """Convert a source-pixel box to a ``BoundingBox`` in the page's storage convention.

    On a pixel-space page the box is stored as-is. On a normalized page it is
    divided by the page's own width and height, matching the convention its
    word boxes already carry.

    Raises ``ValueError`` for a box that cannot be represented in the target
    convention — either because the page reports a zero or negative
    dimension, or because ``BoundingBox`` itself rejects the result (a
    normalized box whose projection lands outside ``[0, 1]``, i.e. the
    source box reached past the edge of the page). Callers map that to a 400
    distinct from an invalid role, since the two have nothing to do with each
    other.
    """
    left, top, right, bottom = box
    if not is_normalized:
        return BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=False)
    if page_width <= 0 or page_height <= 0:
        raise ValueError(
            f"cannot convert a pixel box to normalized coordinates: page dimensions "
            f"are {page_width}x{page_height}"
        )
    return BoundingBox.from_ltrb(
        left / page_width,
        top / page_height,
        right / page_width,
        bottom / page_height,
        is_normalized=True,
    )


def bounding_box_to_pixels(
    box: BoundingBox, *, page_width: int, page_height: int
) -> tuple[int, int, int, int]:
    """Convert a stored box back to source pixels, rounding each edge to the nearest pixel.

    A pixel-space box round-trips exactly. A normalized box is scaled up by
    the page's own width and height — the inverse of
    :func:`pixel_box_to_bounding_box` — confirmed on a real 1166x1779 page
    round-tripping the pixel box ``(442, 110, 653, 139)`` back to itself.
    """
    left, top, right, bottom = box.to_ltrb()
    if not box.is_normalized:
        return round(left), round(top), round(right), round(bottom)
    s_left, s_top, s_right, s_bottom = normalized_to_pixels(
        (left, top, right, bottom), page_width=page_width, page_height=page_height
    )
    return round(s_left), round(s_top), round(s_right), round(s_bottom)


__all__ = [
    "bounding_box_to_pixels",
    "normalized_to_pixels",
    "pixel_box_to_bounding_box",
]
