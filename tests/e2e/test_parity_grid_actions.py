"""M-Final V2 — Grid/word actions round-trip in the browser with DOM-state proof.

Unlike the legacy ``exercise_real_project`` smoke tests (which only assert a
testid stays present), V2 asserts the *observable DOM state changes* that a
real reviewer would see:

  - page/line validate  → the always-visible worklist (default "unvalidated"
    filter) drains to zero rows once every word is validated.
  - paragraph merge      → after ``para-merge`` the page reports one fewer
    paragraph (read back through the API the UI itself drives).
  - word style apply     → the right-panel ``style-chip-italics`` flips to
    ``aria-pressed="true"`` after the chip is clicked and the page query
    re-fetches.

These exercise the real Lane A–E wiring end-to-end through the rendered UI.

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V2
"""

from __future__ import annotations

import time

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.exercise_real_project import (
    ExerciseServer,
    _goto_project_page,
    _wait_for_line_cards,
)
from tests.e2e.helpers import page_line_match_count
from tests.e2e.test_ui_coverage import _select_first_word_via_hierarchy

pytestmark = pytest.mark.e2e

_PROJECT_ID = "exercise-fixture"


def _require_word_content(base_url: str, page_index: int = 0) -> None:
    """Skip the test when the loaded page has no OCR line/word structure.

    See ``helpers.page_line_match_count`` — environments without real OCR
    output on the synthetic fixture images load empty pages, where a word-level
    parity assertion would be vacuous. We skip (honestly) rather than weaken
    the assertion; the test still runs fully wherever the fixture carries
    real word content (CI with seeded OCR / a GPU box).
    """
    n = page_line_match_count(base_url, _PROJECT_ID, page_index)
    if n == 0:
        pytest.skip(
            "page has 0 line_matches — fixture lacks OCR word content in this "
            "environment (no real OCR output on synthetic images); "
            "word-level parity assertion would be vacuous"
        )


def _click_toolbar_cell(page: Page, testid: str) -> None:
    """Click a toolbar grid cell, falling back to a JS click when it lives in
    the hidden driver-contract stub container (IS-4)."""
    cell = page.locator(f'[data-testid="{testid}"]').first
    assert cell.count() > 0, f"{testid} must be in the DOM"
    if cell.is_visible():
        cell.click()
    else:
        page.evaluate(f"document.querySelector('[data-testid=\"{testid}\"]')?.click()")


def _worklist_unvalidated_count(page: Page) -> int:
    """Number of rows in the (default 'unvalidated' filter) worklist queue."""
    return page.locator('[data-testid^="worklist-row-"]').count()


# ---------------------------------------------------------------------------
# V2a — page validate drains the unvalidated worklist to zero
# ---------------------------------------------------------------------------


def test_page_validate_drains_unvalidated_worklist(exercise_server: ExerciseServer, page: Page) -> None:
    """Clicking toolbar-page-validate validates every word → unvalidated worklist empties.

    The worklist defaults to the "unvalidated" filter and is always visible
    (no virtualizer), so a transition from >0 rows to 0 rows is a faithful
    DOM proof that validation took effect — not just a network 200.
    """
    _require_word_content(exercise_server.base_url, page_index=2)
    # Page 3 (index 2) ships unvalidated mismatches, so the worklist starts non-empty.
    _goto_project_page(page, exercise_server.base_url, 3)
    _wait_for_line_cards(page)

    before = _worklist_unvalidated_count(page)
    assert before > 0, f"expected unvalidated rows on page 3, got {before}"

    _click_toolbar_cell(page, "toolbar-page-validate")

    # The unvalidated worklist must drain to zero once all words are validated.
    page.wait_for_function(
        "document.querySelectorAll('[data-testid^=\"worklist-row-\"]').length === 0",
        timeout=15_000,
    )
    assert _worklist_unvalidated_count(page) == 0


# ---------------------------------------------------------------------------
# V2b — paragraph merge reduces the paragraph count
# ---------------------------------------------------------------------------


def _paragraph_count(base_url: str, page_index: int) -> int:
    """Count distinct paragraph indices in the page payload the UI renders from."""
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/{page_index}", timeout=10)
    r.raise_for_status()
    payload = r.json()
    para_ids: set[int] = set()
    for lm in payload.get("line_matches", []):
        pidx = lm.get("paragraph_index")
        if pidx is not None:
            para_ids.add(pidx)
    return len(para_ids)


def test_paragraph_merge_reduces_paragraph_count(exercise_server: ExerciseServer, page: Page) -> None:
    """Selecting a paragraph and clicking para-merge merges it with the next one.

    We drive the real right-panel ``para-merge`` button (it merges paragraph
    ``p`` with ``p+1``) and assert the page the UI renders from now has one
    fewer paragraph.  We only run the merge when the page has >= 2 paragraphs.
    """
    _require_word_content(exercise_server.base_url, page_index=0)
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)

    before = _paragraph_count(exercise_server.base_url, 0)
    if before < 2:
        pytest.skip(f"page 1 has {before} paragraph(s); need >= 2 to merge")

    # Select a paragraph node via the hierarchy tree → right panel ParagraphDetail.
    page.locator('[data-testid="drawer-tab-hierarchy"]').first.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=5_000)
    time.sleep(0.3)
    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > 0:
        block_nodes.first.click()
        block_nodes.first.press("ArrowRight")
        time.sleep(0.3)
    para_nodes = page.locator('[data-testid^="hierarchy-node-para-"]')
    assert para_nodes.count() >= 1, "expected at least one paragraph node in the hierarchy"
    para_nodes.first.click()
    time.sleep(0.4)

    # ParagraphDetail must be visible with its merge button.
    merge_btn = page.locator('[data-testid="para-merge"]').first
    merge_btn.wait_for(state="visible", timeout=10_000)
    merge_btn.click()

    # Paragraph count drops by one once the merge mutation settles.
    deadline = time.monotonic() + 15
    after = before
    while time.monotonic() < deadline:
        after = _paragraph_count(exercise_server.base_url, 0)
        if after < before:
            break
        time.sleep(0.3)
    assert after == before - 1, f"paragraph count {before} -> {after} (expected one fewer)"


# ---------------------------------------------------------------------------
# V2c — word style apply flips the right-panel style chip to active
# ---------------------------------------------------------------------------


def test_word_style_apply_marks_chip_active(exercise_server: ExerciseServer, page: Page) -> None:
    """Apply 'italics' to a word via the right-panel StylePalette; the chip
    flips to aria-pressed='true' once the page query re-fetches.

    This is the visible DOM proof that the apply-style round-trip
    (POST .../style → page invalidation → re-render with the new label)
    completed — not merely a network 200.
    """
    _require_word_content(exercise_server.base_url, page_index=0)
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)

    selected = _select_first_word_via_hierarchy(page)
    assert selected, "could not select a word node via the hierarchy tree"

    chip = page.locator('[data-testid="style-chip-italics"]').first
    chip.wait_for(state="visible", timeout=10_000)

    # If the word is already italic (fixture state), this assertion is still
    # meaningful: we toggle and assert the resulting on-state.
    if chip.get_attribute("aria-pressed") == "true":
        # Toggle to mixed then off then back on to leave a deterministic state.
        chip.click()  # on -> mixed
        time.sleep(0.4)
        chip.click()  # mixed -> off
        time.sleep(0.4)

    chip.click()  # -> on
    page.wait_for_selector(
        '[data-testid="style-chip-italics"][aria-pressed="true"]',
        timeout=15_000,
    )
    assert chip.get_attribute("aria-pressed") == "true"
