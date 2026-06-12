"""Toolbar acceptance — word-scope actions (Lane B / Task B3).

Ported from ``pd-ocr-labeler/tests/browser/test_toolbar_word_actions.py``
to the SPA's HTTP API. Each test POSTs the route the SPA toolbar grid
dispatches for a word-scope cell and asserts the effect on the in-memory
book-tools Page.

Routes exercised:
  - refine/expand   → POST .../refine (scope=word)
  - word→paragraph  → POST .../paragraphs/group-selected-words
  - GT↔OCR          → POST .../lines/copy-gt-batch (scope=word)
  - validate/unval  → POST .../words/validate-batch (scope=word)
  - delete          → POST .../words/delete-batch
  - style/component → POST .../words/{li}/{wi}/style|component (Apply-Style row)
"""

from __future__ import annotations

from typing import Any

_BASE = "/api/projects/book1/pages/0"


def test_word_refine_accepted(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/refine",
        json={"scope": "word", "mode": "refine", "word_indices": [[0, 0]]},
    )
    assert r.status_code != 404
    assert r.status_code in (200, 202), r.text


def test_word_to_paragraph(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.paragraphs)
    r = client.post(
        f"{_BASE}/paragraphs/group-selected-words",
        json={"word_indices": [[0, 0]]},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) > before


def test_word_copy_gt_to_ocr(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    w = page.lines[1].words[0]
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "word", "word_indices": [[1, 0]], "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    assert w.text == w.ground_truth_text


def test_word_copy_ocr_to_gt(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    page.lines[1].words[0].text = "OCRW"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "word", "word_indices": [[1, 0]], "direction": "ocr_to_gt"},
    )
    assert r.status_code == 200, r.text
    assert page.lines[1].words[0].ground_truth_text == "OCRW"


def test_word_validate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "word", "word_indices": [[0, 0]], "validated": True},
    )
    assert r.status_code == 200, r.text
    assert page.lines[0].words[0].is_validated is True
    # Sibling word untouched (validate-batch only sets the attribute on its
    # targets; never-validated words may not carry the attribute at all).
    assert getattr(page.lines[0].words[1], "is_validated", False) is False


def test_word_unvalidate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "word", "word_indices": [[0, 0]], "validated": True},
    )
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "word", "word_indices": [[0, 0]], "validated": False},
    )
    assert r.status_code == 200, r.text
    assert page.lines[0].words[0].is_validated is False


def test_word_delete(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.lines[0].words)
    r = client.post(
        f"{_BASE}/words/delete-batch",
        json={"scope": "word", "word_indices": [[0, 0]]},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.lines[0].words) == before - 1


def test_word_apply_style(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    # Backend uses the book-tools canonical label "italics" (plural). The
    # frontend grid's hardcoded label list uses "italic" (singular) — flagged
    # as a latent parity bug in OPEN_QUESTIONS.
    r = client.post(
        f"{_BASE}/words/0/0/style",
        json={"style": "italics", "scope": "whole"},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    labels = [s.lower() for s in (page.lines[0].words[0].text_style_labels or [])]
    assert "italics" in labels


def test_word_remove_style(toolbar_loaded: Any) -> None:
    """P1.4 (B-39/41/43): ``enabled:false`` removes a style label.

    book-tools' ``apply_style_scope`` is ADD-ONLY; before this slice the
    SPA had no route at all that called ``remove_style_label``, so every
    clear-style surface (toolbar clear-style-button, WordDetail chip
    off-toggle, WordCell tag-x) silently no-oped. Mirrors the component
    route's ``enabled`` flag.
    """
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/0/0/style",
        json={"style": "italics", "scope": "whole"},
    )
    assert r.status_code == 200, r.text
    labels = [s.lower() for s in (page.lines[0].words[0].text_style_labels or [])]
    assert "italics" in labels

    r = client.post(
        f"{_BASE}/words/0/0/style",
        json={"style": "italics", "scope": "whole", "enabled": False},
    )
    assert r.status_code == 200, r.text
    labels = [s.lower() for s in (page.lines[0].words[0].text_style_labels or [])]
    assert "italics" not in labels


def test_word_apply_style_enabled_defaults_true(toolbar_loaded: Any) -> None:
    """Back-compat: bodies without ``enabled`` keep the add semantics."""
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/0/1/style",
        json={"style": "bold", "scope": "whole"},
    )
    assert r.status_code == 200, r.text
    labels = [s.lower() for s in (page.lines[0].words[1].text_style_labels or [])]
    assert "bold" in labels


def test_word_apply_component(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/0/0/component",
        json={"component": "footnote_marker", "enabled": True},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    components = [c.lower() for c in (page.lines[0].words[0].word_components or [])]
    assert any("footnote" in c for c in components)
