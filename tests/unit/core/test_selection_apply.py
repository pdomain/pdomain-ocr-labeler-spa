"""Unit tests for ``core/selection.apply_selection`` — spec-23-E (§10).

Verifies the three set operations the selection endpoint composes on
top of ``Selection``:

- ``replace`` — output equals the delta (mode included).
- ``remove`` — set-difference per index family; current's
  ``selection_mode`` preserved.
- ``toggle`` — symmetric-difference per index family; current's
  ``selection_mode`` preserved.

Plus invariants:

- Returns a new ``Selection`` instance (no in-place mutation).
- Unknown modes raise ``ValueError``.
"""

from __future__ import annotations

import pytest

from pd_ocr_labeler_spa.core.models import Selection
from pd_ocr_labeler_spa.core.selection import apply_selection


def _make(
    *,
    mode: str = "word",
    paragraphs: set[int] | None = None,
    lines: set[int] | None = None,
    words: set[tuple[int, int]] | None = None,
) -> Selection:
    return Selection(
        selection_mode=mode,  # type: ignore[arg-type]
        selected_paragraphs=set(paragraphs or set()),
        selected_lines=set(lines or set()),
        selected_words=set(words or set()),
    )


# ── replace ──────────────────────────────────────────────────────────────


def test_replace_returns_delta_contents() -> None:
    current = _make(mode="line", paragraphs={1, 2}, lines={5}, words={(0, 0)})
    delta = _make(mode="word", paragraphs={9}, lines={3, 4}, words={(1, 2)})

    out = apply_selection(current, "replace", delta)

    assert out.selection_mode == "word"
    assert out.selected_paragraphs == {9}
    assert out.selected_lines == {3, 4}
    assert out.selected_words == {(1, 2)}


def test_replace_with_empty_delta_clears_selection() -> None:
    current = _make(paragraphs={1}, lines={2}, words={(0, 0), (1, 1)})
    delta = _make(mode="paragraph")

    out = apply_selection(current, "replace", delta)

    assert out.selection_mode == "paragraph"
    assert out.selected_paragraphs == set()
    assert out.selected_lines == set()
    assert out.selected_words == set()


# ── remove ───────────────────────────────────────────────────────────────


def test_remove_subtracts_per_family() -> None:
    current = _make(
        mode="word",
        paragraphs={1, 2, 3},
        lines={4, 5, 6},
        words={(0, 0), (0, 1), (1, 0)},
    )
    delta = _make(
        paragraphs={2, 4},  # 4 not in current — no-op
        lines={5},
        words={(0, 1), (9, 9)},  # (9,9) not in current — no-op
    )

    out = apply_selection(current, "remove", delta)

    assert out.selected_paragraphs == {1, 3}
    assert out.selected_lines == {4, 6}
    assert out.selected_words == {(0, 0), (1, 0)}


def test_remove_preserves_current_selection_mode() -> None:
    current = _make(mode="paragraph", paragraphs={1, 2})
    delta = _make(mode="word", paragraphs={1})

    out = apply_selection(current, "remove", delta)

    assert out.selection_mode == "paragraph"


# ── toggle ───────────────────────────────────────────────────────────────


def test_toggle_is_symmetric_difference_per_family() -> None:
    current = _make(
        paragraphs={1, 2},
        lines={3, 4},
        words={(0, 0), (0, 1)},
    )
    delta = _make(
        paragraphs={2, 3},
        lines={4, 5},
        words={(0, 1), (1, 0)},
    )

    out = apply_selection(current, "toggle", delta)

    assert out.selected_paragraphs == {1, 3}
    assert out.selected_lines == {3, 5}
    assert out.selected_words == {(0, 0), (1, 0)}


def test_toggle_preserves_current_selection_mode() -> None:
    current = _make(mode="line", lines={1})
    delta = _make(mode="word", lines={2})

    out = apply_selection(current, "toggle", delta)

    assert out.selection_mode == "line"
    assert out.selected_lines == {1, 2}


# ── purity / errors ──────────────────────────────────────────────────────


def test_apply_selection_does_not_mutate_inputs() -> None:
    current = _make(paragraphs={1}, lines={2}, words={(0, 0)})
    delta = _make(paragraphs={1}, lines={3}, words={(0, 0), (1, 1)})

    snapshot_current = (
        set(current.selected_paragraphs),
        set(current.selected_lines),
        set(current.selected_words),
        current.selection_mode,
    )
    snapshot_delta = (
        set(delta.selected_paragraphs),
        set(delta.selected_lines),
        set(delta.selected_words),
        delta.selection_mode,
    )

    apply_selection(current, "toggle", delta)
    apply_selection(current, "remove", delta)
    apply_selection(current, "replace", delta)

    assert (
        set(current.selected_paragraphs),
        set(current.selected_lines),
        set(current.selected_words),
        current.selection_mode,
    ) == snapshot_current
    assert (
        set(delta.selected_paragraphs),
        set(delta.selected_lines),
        set(delta.selected_words),
        delta.selection_mode,
    ) == snapshot_delta


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="unknown selection mode"):
        apply_selection(_make(), "intersect", _make())  # type: ignore[arg-type]
