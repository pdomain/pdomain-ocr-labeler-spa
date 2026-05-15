"""Pure set-ops for ``Selection`` updates — spec-23-E (``§10``).

The selection endpoint ``POST .../selection`` accepts a ``mode`` of
``replace`` | ``remove`` | ``toggle`` plus a delta ``Selection`` and
folds it into the page's current ``Selection``.

``apply_selection`` is the entire ~40-LOC contract:

- ``replace``: returned selection == delta. Used by the canvas
  drag-to-select gesture without modifier keys — fresh marquee
  replaces whatever was selected before.
- ``remove``: current minus delta (set difference). Used by
  Ctrl-drag to subtract from the existing selection.
- ``toggle``: current XOR delta (symmetric difference). Used by
  Shift-drag and Shift-click — each item flips its membership.

The ``selection_mode`` (paragraph/line/word) is taken from ``delta``
under ``replace`` (the canvas may switch scopes mid-session) and
from ``current`` under ``remove`` / ``toggle`` (the scope is already
established; the delta only contributes index keys).

Pure / side-effect-free — the endpoint handler assigns the return
value back onto ``pstate.selection`` and bumps ``generation``.
"""

from __future__ import annotations

from typing import Literal

from .models import Selection

SelectionMode = Literal["replace", "remove", "toggle"]


def apply_selection(
    current: Selection,
    mode: SelectionMode,
    delta: Selection,
) -> Selection:
    """Fold ``delta`` into ``current`` using ``mode``'s set operation.

    Returns a *new* ``Selection``; neither argument is mutated.

    Spec authority: ``specs/23-page-payload-backend.md §10``.
    """
    if mode == "replace":
        return Selection(
            selection_mode=delta.selection_mode,
            selected_paragraphs=set(delta.selected_paragraphs),
            selected_lines=set(delta.selected_lines),
            selected_words=set(delta.selected_words),
        )
    if mode == "remove":
        return Selection(
            selection_mode=current.selection_mode,
            selected_paragraphs=current.selected_paragraphs - delta.selected_paragraphs,
            selected_lines=current.selected_lines - delta.selected_lines,
            selected_words=current.selected_words - delta.selected_words,
        )
    if mode == "toggle":
        return Selection(
            selection_mode=current.selection_mode,
            selected_paragraphs=current.selected_paragraphs ^ delta.selected_paragraphs,
            selected_lines=current.selected_lines ^ delta.selected_lines,
            selected_words=current.selected_words ^ delta.selected_words,
        )
    raise ValueError(f"unknown selection mode: {mode!r}")


__all__ = ["SelectionMode", "apply_selection"]
