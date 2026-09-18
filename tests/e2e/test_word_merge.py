"""Browser Verification — word-level merge (``toolbar-word-merge``).

Drives rulings 1-2 of ``docs/issues/2026-09-18-the-word-edit-dialog-the-
driver-contract-documents-does-not-exist.md`` end to end through the
rendered UI: Ctrl-click two adjacent same-line words, click
``toolbar-word-merge``, and confirm the surviving word's OCR text is the
no-separator concatenation, with one fewer word left in that line — both
in the DOM (``ocr-gt-ocr-well``) and via the API the UI itself renders
from.

Fixture: reuses ``test_selection_operations_parity``'s sel-fixture page
dict — block 0's line 0 has two adjacent words, "Hello" and "World" — but
through its own freshly seeded, function-scoped server. Word merge is a
destructive structural mutation, so this test does not share the
module-scoped ``sel_server`` (mirrors that module's own ``mut_server``).

Run with:   make e2e AI=1
Or inline:  uv run --group e2e pytest tests/e2e/test_word_merge.py -v
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.test_selection_operations_parity import (
    _PROJECT_ID,
    SelServer,
    _fetch_encoded_dims,
    _goto_project_page,
    _sel_server_ctx,
    _verify_fixture_two_blocks,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def word_merge_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SelServer]:
    """Function-scoped isolated server — merge is destructive (mirrors ``mut_server``)."""
    with _sel_server_ctx(tmp_path_factory, "word-merge") as srv:
        yield srv


def _click_toolbar_cell(page: Page, testid: str) -> None:
    """Click a toolbar grid cell, falling back to a JS click when it lives in
    the hidden driver-contract stub container (mirrors test_parity_grid_actions.py).
    """
    cell = page.locator(f'[data-testid="{testid}"]').first
    assert cell.count() > 0, f"{testid} must be in the DOM"
    if cell.is_visible():
        cell.click()
    else:
        page.evaluate(f"document.querySelector('[data-testid=\"{testid}\"]')?.click()")


def test_toolbar_word_merge_concatenates_adjacent_words(
    word_merge_server: SelServer,
    page: Page,
) -> None:
    """Ctrl-click two adjacent same-line words, click ``toolbar-word-merge``.

    Acceptance:
    - ``toolbar-word-merge`` is enabled (not a stub, not disabled) once
      exactly two adjacent same-line words are selected.
    - After the click, the surviving word's OCR text — read from the
      right panel's ``ocr-gt-ocr-well`` — is "HelloWorld" (no separator).
    - The page payload the UI renders from confirms line 0 now has exactly
      one word, whose ``ocr_text`` is "HelloWorld".
    """
    lm0, _lm1 = _verify_fixture_two_blocks(word_merge_server.base_url)
    display_width, scale = _fetch_encoded_dims(word_merge_server.base_url)
    bbox0 = lm0["word_matches"][0]["bbox"]  # "Hello"
    bbox1 = lm0["word_matches"][1]["bbox"]  # "World"

    _goto_project_page(page, word_merge_server.project_url)

    # ── Ctrl-click select word 0 then word 1 (same line, same block) ───────
    konva_content = page.locator(".konvajs-content").first
    konva_content.wait_for(state="visible", timeout=10_000)
    pre_box = konva_content.bounding_box()
    assert pre_box is not None, "konvajs-content must have an on-screen bounding box"

    def _offset(elem_box: dict, bbox: dict) -> tuple[float, float]:
        fs = elem_box["width"] / display_width
        return (
            (bbox["x"] * scale + bbox["width"] * scale / 2) * fs,
            (bbox["y"] * scale + bbox["height"] * scale / 2) * fs,
        )

    ox0, oy0 = _offset(pre_box, bbox0)
    page.mouse.click(pre_box["x"] + ox0, pre_box["y"] + oy0)
    time.sleep(0.5)

    post_box = konva_content.bounding_box()
    assert post_box is not None, "konvajs-content must still have a bounding box after step 1"
    ox1, oy1 = _offset(post_box, bbox1)
    konva_content.click(position={"x": ox1, "y": oy1}, modifiers=["Control"])
    time.sleep(0.5)

    multi = page.locator('[data-testid="multi-word-detail"]').first
    multi.wait_for(state="visible", timeout=8_000)

    # ── toolbar-word-merge must be live and enabled for this selection ─────
    merge_btn = page.locator('[data-testid="toolbar-word-merge"]').first
    merge_btn.wait_for(state="attached", timeout=5_000)
    assert merge_btn.get_attribute("data-testid-stub") is None, (
        "toolbar-word-merge must not be a stub — word merge has a live home now"
    )
    assert not merge_btn.is_disabled(), (
        "toolbar-word-merge should be enabled for two adjacent same-line words"
    )

    _click_toolbar_cell(page, "toolbar-word-merge")

    # ── The merged word becomes the sole selection — RightPanel switches ───
    # back to the single-word WordDetail view, showing the concatenated text.
    page.wait_for_function(
        "document.querySelector('[data-testid=\"ocr-gt-ocr-well\"]')?.textContent?.includes('HelloWorld')",
        timeout=10_000,
    )

    # ── Same story from the API the UI itself renders from ─────────────────
    # Real OCR words only — the page's GT source text still reads "Hello
    # World" (two tokens) against one merged OCR word, so rematch also
    # emits an ``unmatched_ground_truth_words`` placeholder entry
    # (``word_index: null``) alongside the real word; that placeholder is
    # this test fixture's GT-source artifact, not part of the merge itself.
    r = httpx.get(f"{word_merge_server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    r.raise_for_status()
    payload = r.json()
    line0 = next(lm for lm in payload["line_matches"] if lm["line_index"] == 0)
    real_words = [w for w in line0["word_matches"] if w["word_index"] is not None]
    assert len(real_words) == 1, f"line 0 should have exactly 1 real word after merge, got {real_words}"
    assert real_words[0]["ocr_text"] == "HelloWorld"
