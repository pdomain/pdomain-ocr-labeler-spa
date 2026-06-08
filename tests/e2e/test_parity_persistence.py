"""M-Final V3 — Save → reload round-trip in the browser.

End-to-end guard of the M0 persistence fix *through the rendered UI*:

  1. Select a word via the hierarchy tree → right-panel WordDetail.
  2. Edit its ground-truth text in ``ocr-gt-input`` (commit on Enter).
  3. Validate it via ``word-footer-validate``.
  4. Apply the 'italics' style via ``style-chip-italics``.
  5. Click the real ``page-actions-compact-save-page`` button.
  6. Reload the page route (full browser reload).
  7. Re-select the same word and assert the GT edit, validated state, and
     style label all survived the round-trip.

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V3
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page

from tests.e2e.exercise_real_project import (
    ExerciseServer,
    _goto_project_page,
    _wait_for_line_cards,
)
from tests.e2e.helpers import require_page_line_matches
from tests.e2e.test_ui_coverage import _select_first_word_via_hierarchy

pytestmark = pytest.mark.e2e

_PROJECT_ID = "exercise-fixture"
_SUFFIX = "ZZ"  # deterministic GT edit marker


def _read_gt_value(page: Page) -> str:
    return page.evaluate("document.querySelector(\"[data-testid='ocr-gt-input']\")?.value ?? ''")


def _ensure_word_selected(page: Page) -> None:
    selected = _select_first_word_via_hierarchy(page)
    assert selected, "could not select a word node via the hierarchy tree"
    page.locator('[data-testid="ocr-gt-input"]').first.wait_for(state="visible", timeout=10_000)


def test_save_then_reload_persists_gt_validation_and_style(
    exercise_server: ExerciseServer, page: Page
) -> None:
    """Edit GT + validate + style → Save Page → reload → all three persist."""
    # The exercise-fixture is deterministically seeded via the event store
    # (invariant since d0c1494). Assert content presence — 0 line_matches is a
    # seeding regression that must fail loudly, not a vacuous-test skip.
    require_page_line_matches(exercise_server.base_url, _PROJECT_ID, 0)

    page_url = f"{exercise_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1"

    # ── First visit: make the three edits ──────────────────────────────────
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)
    _ensure_word_selected(page)

    original_gt = _read_gt_value(page)
    expected_gt = original_gt + _SUFFIX

    # 1. Edit GT and commit (Enter blurs → onCommitGt → POST + invalidate).
    gt_input = page.locator('[data-testid="ocr-gt-input"]').first
    gt_input.click()
    gt_input.fill(expected_gt)
    gt_input.press("Enter")
    time.sleep(0.6)

    # 2. Validate the word — footer button text flips to "✓ Validated".
    validate_btn = page.locator('[data-testid="word-footer-validate"]').first
    validate_btn.wait_for(state="visible", timeout=10_000)
    if validate_btn.get_attribute("aria-label") == "Unvalidate word":
        # already validated — leave it validated
        pass
    else:
        validate_btn.click()
    page.wait_for_selector(
        '[data-testid="word-footer-validate"][aria-label="Unvalidate word"]',
        timeout=10_000,
    )

    # 3. Apply the italics style chip → aria-pressed=true.
    style_chip = page.locator('[data-testid="style-chip-italics"]').first
    if style_chip.get_attribute("aria-pressed") != "true":
        style_chip.click()
    page.wait_for_selector(
        '[data-testid="style-chip-italics"][aria-pressed="true"]',
        timeout=10_000,
    )

    # 4. Click the real Save Page button (enabled on a project route).
    save_btn = page.locator('[data-testid="page-actions-compact-save-page"]').first
    save_btn.wait_for(state="visible", timeout=10_000)
    assert save_btn.is_enabled(), "Save page button must be enabled on a project route"
    save_btn.click()
    time.sleep(1.0)  # let the save mutation settle

    # ── Full browser reload of the page route ──────────────────────────────
    page.goto(page_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    _wait_for_line_cards(page)
    _ensure_word_selected(page)

    # ── Assert all three edits survived ─────────────────────────────────────
    persisted_gt = _read_gt_value(page)
    assert persisted_gt == expected_gt, f"GT did not persist: expected {expected_gt!r}, got {persisted_gt!r}"

    validate_btn = page.locator('[data-testid="word-footer-validate"]').first
    validate_btn.wait_for(state="visible", timeout=10_000)
    assert validate_btn.get_attribute("aria-label") == "Unvalidate word", (
        "validated state did not persist across reload"
    )

    style_chip = page.locator('[data-testid="style-chip-italics"]').first
    style_chip.wait_for(state="visible", timeout=10_000)
    assert style_chip.get_attribute("aria-pressed") == "true", "italics style did not persist across reload"
