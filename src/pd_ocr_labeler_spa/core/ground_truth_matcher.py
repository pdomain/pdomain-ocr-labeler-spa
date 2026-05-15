"""Ground-truth (re)matching wrapper — spec ``specs/23-page-payload-backend.md §7``.

A thin wrapper over ``pd_book_tools.ocr.ground_truth_matching`` (reached
indirectly via the ``Page.remove_ground_truth`` / ``Page.add_ground_truth``
pair).  Provides one entry point — :func:`rematch_page` — that the
``POST /api/projects/{id}/pages/{idx}/rematch-gt`` endpoint (and any
future internal re-matcher) calls.

Legacy parity:
``pd_ocr_labeler/state/page_state.py:2202`` (``_rematch_page_ground_truth``).
The legacy semantics:

1. Pull GT text for the page (already resolved by the caller — this
   wrapper is intentionally pure).
2. ``page.remove_ground_truth()`` — drops *every* per-word GT edit on
   the page (including any user-typed GT in ``WordCell``).  This is
   how the legacy spec §10 promise of "discards per-word GT edits"
   is implemented: a bulk wipe before the rematch.
3. ``page.add_ground_truth(gt_text)`` — runs the page-level matcher
   (``pd_book_tools.ocr.ground_truth_matching.update_page_with_ground_truth_text``)
   which assigns fresh ``ground_truth_text`` per word via difflib +
   thefuzz word matching.

Returns ``True`` on success, ``False`` when the page lacks the GT
methods (e.g. a stub Page in tests, or a legacy page-dict that was
never wrapped in :class:`pd_book_tools.ocr.page.Page`).  Never raises
— the route layer can decide whether to surface a 400 to the caller.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["rematch_page"]


def rematch_page(page: Any, gt_text: str) -> bool:
    """Wipe per-word GT and re-run the page-level GT matcher.

    Parameters
    ----------
    page :
        A ``pd_book_tools.ocr.page.Page``-shaped object exposing
        ``remove_ground_truth()`` and ``add_ground_truth(text: str)``.
        Test stubs need only those two methods.
    gt_text :
        Source ground-truth text for the page.  The caller is
        responsible for resolving this from
        ``Project.ground_truth_map`` (the rematch wrapper is
        deliberately ignorant of the project graph).

    Returns
    -------
    bool
        ``True`` when both calls succeeded; ``False`` when the page
        type lacks the required methods.  Caller decides whether
        to map the failure to an HTTP error.
    """
    remove_gt = getattr(page, "remove_ground_truth", None)
    add_gt = getattr(page, "add_ground_truth", None)
    if not callable(remove_gt) or not callable(add_gt):
        logger.debug(
            "rematch_page: page type %s lacks remove_ground_truth / add_ground_truth",
            type(page).__name__,
        )
        return False

    # remove_ground_truth() drops every per-word GT edit on the page.
    # This is the legacy "discards per-word GT edits" semantics from
    # spec §7 — bulk wipe before the rematch so add_ground_truth
    # rebuilds GT from the canonical source text only.
    remove_gt()
    add_gt(gt_text)
    return True
