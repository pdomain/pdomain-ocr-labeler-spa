"""Toolbar acceptance — line-scope actions (Lane B / Task B3).

Ported from ``pd-ocr-labeler/tests/browser/test_toolbar_line_actions.py``
to the SPA's HTTP API. Each test POSTs the route the SPA toolbar grid
dispatches for a line-scope cell and asserts the effect on the in-memory
book-tools Page.

Routes exercised:
  - merge          → POST .../lines/merge
  - refine/expand  → POST .../refine (scope=line)
  - split-after    → POST .../lines/{li}/split-after-word
  - GT↔OCR         → POST .../lines/copy-gt-batch (scope=line)
  - validate/unval → POST .../words/validate-batch (scope=line)
  - delete         → POST .../lines/delete-batch
"""

from __future__ import annotations

from typing import Any

_BASE = "/api/projects/book1/pages/0"


def test_line_merge(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.lines)
    r = client.post(f"{_BASE}/lines/merge", json={"line_indices": [0, 1]})
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.lines) == before - 1


def test_line_refine_accepted(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/refine",
        json={"scope": "line", "mode": "refine", "line_indices": [0]},
    )
    assert r.status_code != 404
    assert r.status_code in (200, 202), r.text


def test_line_split_after_word(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.lines)
    # Line 0 has two words; split after word 0 → one extra line.
    r = client.post(
        f"{_BASE}/lines/0/split-after-word",
        json={"line_index": 0, "word_index": 0},
    )
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.lines) > before


def test_line_copy_gt_to_ocr(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    line_words = page.lines[0].words
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "line", "line_indices": [0], "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    for w in line_words:
        assert w.text == w.ground_truth_text


def test_line_copy_ocr_to_gt(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    page.lines[0].words[0].text = "OCRL"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "line", "line_indices": [0], "direction": "ocr_to_gt"},
    )
    assert r.status_code == 200, r.text
    assert page.lines[0].words[0].ground_truth_text == "OCRL"


def test_line_validate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "line", "line_indices": [0], "validated": True},
    )
    assert r.status_code == 200, r.text
    assert all(w.is_validated for w in page.lines[0].words)
    assert all(not getattr(w, "is_validated", False) for w in page.lines[1].words)


def test_line_unvalidate(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "line", "line_indices": [0], "validated": True},
    )
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "line", "line_indices": [0], "validated": False},
    )
    assert r.status_code == 200, r.text
    assert all(not w.is_validated for w in page.lines[0].words)


def test_line_delete(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    before = len(page.lines)
    r = client.post(f"{_BASE}/lines/delete-batch", json={"scope": "line", "line_indices": [0]})
    assert r.status_code != 404
    assert r.status_code == 200, r.text
    assert len(page.lines) == before - 1
