"""Toolbar acceptance — paragraph-scope actions (Lane B / Task B3).

Ported from ``pd-ocr-labeler/tests/browser/test_toolbar_paragraph_actions.py``
to the SPA's HTTP API. Each test POSTs the route the SPA toolbar grid
dispatches for a paragraph-scope cell and asserts the effect on the
in-memory book-tools Page.

Routes exercised:
  - merge          → POST .../paragraphs/merge
  - refine/expand  → POST .../refine (scope=paragraph)
  - split-after    → POST .../paragraphs/{pi}/split-after-line
  - split-selected → POST .../paragraphs/split-selected
  - GT↔OCR         → POST .../lines/copy-gt-batch (scope=paragraph)
  - validate/unval → POST .../words/validate-batch (scope=paragraph)
  - delete         → POST .../paragraphs/delete-batch
"""

from __future__ import annotations

from typing import Any

_BASE = "/api/projects/book1/pages/0"


def test_paragraph_merge(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.paragraphs)
    r = client.post(f"{_BASE}/paragraphs/merge", json={"paragraph_indices": [0, 1]})
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) == before - 1


def test_paragraph_refine_accepted(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/refine",
        json={"scope": "paragraph", "mode": "refine", "paragraph_indices": [0]},
    )
    assert r.status_code != 404
    assert r.status_code in (200, 202), r.text


def test_paragraph_split_after_line(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.paragraphs)
    # Split paragraph 0 after its first line → one extra paragraph.
    r = client.post(
        f"{_BASE}/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 0},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) > before


def test_paragraph_split_selected(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.paragraphs)
    r = client.post(f"{_BASE}/paragraphs/split-selected", json={"paragraph_indices": [0]})
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) > before


def test_paragraph_copy_gt_to_ocr(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    para_words = page.paragraphs[0].words
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    for w in para_words:
        assert w.text == w.ground_truth_text


def test_paragraph_copy_ocr_to_gt(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    page.paragraphs[0].words[0].text = "OCRP"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "direction": "ocr_to_gt"},
    )
    assert r.status_code == 200, r.text
    assert page.paragraphs[0].words[0].ground_truth_text == "OCRP"


def test_paragraph_validate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "validated": True},
    )
    assert r.status_code == 200, r.text
    assert all(w.is_validated for w in page.paragraphs[0].words)
    # Paragraph 1 untouched.
    assert all(not getattr(w, "is_validated", False) for w in page.paragraphs[1].words)


def test_paragraph_unvalidate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "validated": True},
    )
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "validated": False},
    )
    assert r.status_code == 200, r.text
    assert all(not w.is_validated for w in page.paragraphs[0].words)


def test_paragraph_delete(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.paragraphs)
    r = client.post(
        f"{_BASE}/paragraphs/delete-batch",
        json={"scope": "paragraph", "paragraph_indices": [0]},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) == before - 1
