"""Reading-order stamps that keep a word's published id across a membership move.

``stable_word_id`` hashes a page-wide reading order. ``page.lines`` rebuilds
that order, and a leaf region is itself a line, so moving a word into a region
used to reissue every id on the page. A membership write freezes the order it
found. Later payload and journal lookups read the stamp.
"""

from __future__ import annotations

READING_ORDER_KEY = "labeler_reading_order"


def stamped_reading_order(word: object) -> int | None:
    """Return the frozen reading order stored on *word*, if it has one."""
    keys = getattr(word, "ground_truth_match_keys", None)
    if not isinstance(keys, dict):
        return None
    value: object = keys.get(READING_ORDER_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def identity_reading_order(word: object, live_order: int) -> int:
    """Return the stamp when the word has one, otherwise *live_order*."""
    stamped = stamped_reading_order(word)
    if stamped is None:
        return live_order
    return stamped


def clear_page_reading_orders(page: object) -> None:
    """Drop frozen reading orders so a structural edit publishes the new order.

    Membership writes keep the stamp. Line and word merge, split, and delete
    call this first, so a later word's live index cannot collide with a stamp
    that still names the pre-edit position.
    """
    for line in getattr(page, "lines", None) or []:
        for word in getattr(line, "words", None) or []:
            keys = getattr(word, "ground_truth_match_keys", None)
            if isinstance(keys, dict):
                keys.pop(READING_ORDER_KEY, None)


def stamp_page_reading_orders(page: object) -> None:
    """Freeze each unstamped word's current page-wide reading order.

    The counter matches ``page_to_line_matches``: one step per word on
    ``page.lines``. Words that already carry a stamp keep it, so a second
    membership write does not re-key the page.
    """
    order = 0
    for line in getattr(page, "lines", None) or []:
        for word in getattr(line, "words", None) or []:
            keys = getattr(word, "ground_truth_match_keys", None)
            if isinstance(keys, dict) and READING_ORDER_KEY not in keys:
                keys[READING_ORDER_KEY] = order
            order += 1
