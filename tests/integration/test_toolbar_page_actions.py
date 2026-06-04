"""Toolbar acceptance — page-scope actions (Lane B / Task B3).

Ported from the legacy NiceGUI Playwright suite
``pd-ocr-labeler/tests/browser/test_toolbar_page_actions.py``. The legacy
tests clicked a page-scope toolbar button and asserted a Quasar
notification / DOM change; here we POST the route the SPA toolbar grid
dispatches for that cell (see ``frontend/src/lib/toolbarMapping.ts``) and
assert the same effect on the in-memory book-tools Page.

Routes exercised:
  - page refine            → POST .../refine            (scope=page)
  - page expand+refine     → POST .../refine            (scope=page, mode=expand_then_refine)
  - page GT→OCR / OCR→GT   → POST .../lines/copy-gt-batch (scope=page)
  - page validate / unvalidate → POST .../words/validate-batch (scope=page)
"""

from __future__ import annotations

from typing import Any

_BASE = "/api/projects/book1/pages/0"


def _all_words(page: Any) -> list[Any]:
    return list(getattr(page, "words", []) or [])


# ── refine / expand+refine (async job — assert accepted, not 404) ──────────


def test_page_refine_accepted(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(f"{_BASE}/refine", json={"scope": "page", "mode": "refine"})
    assert r.status_code != 404, "page refine route missing (404)"
    assert r.status_code in (200, 202), r.text


def test_page_expand_refine_accepted(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(f"{_BASE}/refine", json={"scope": "page", "mode": "expand_then_refine"})
    assert r.status_code != 404
    assert r.status_code in (200, 202), r.text


# ── copy GT↔OCR over the whole page ────────────────────────────────────────


def test_page_copy_gt_to_ocr(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "page", "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    # Every word's OCR text now equals its ground truth.
    for w in _all_words(page):
        assert w.text == w.ground_truth_text


def test_page_copy_ocr_to_gt(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    # Make OCR differ from GT, then copy OCR→GT over the whole page.
    page.lines[0].words[0].text = "OCRX"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "page", "direction": "ocr_to_gt"},
    )
    assert r.status_code == 200, r.text
    for w in _all_words(page):
        assert w.ground_truth_text == w.text
    assert page.lines[0].words[0].ground_truth_text == "OCRX"


# ── validate / unvalidate all ──────────────────────────────────────────────


def test_page_validate_all(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "page", "validated": True},
    )
    assert r.status_code == 200, r.text
    words = _all_words(page)
    assert len(words) > 0
    assert all(w.is_validated for w in words)


def test_page_unvalidate_all(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    # Validate first, then unvalidate.
    assert (
        client.post(f"{_BASE}/words/validate-batch", json={"scope": "page", "validated": True}).status_code
        == 200
    )
    r = client.post(
        f"{_BASE}/words/validate-batch",
        json={"scope": "page", "validated": False},
    )
    assert r.status_code == 200, r.text
    assert all(not w.is_validated for w in _all_words(page))
