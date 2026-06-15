"""M-Final V4 — Viewport chrome controls work in the browser.

Three independent chrome behaviours:

  V4a — toggling ``rail-layer-word`` off flips the words layer pref so the
        word overlay is no longer rendered (``aria-pressed`` goes "false"; the
        Konva ``BBoxOverlay layer="words"`` receives ``visible={false}``).
        (ImageTabsHeader retired D-050/D-053; control re-homed to Rail.)
  V4b — clicking ``rail-target-para`` activates paragraph mode (``data-active``
        "true") and makes the canvas hit-test resolve paragraphs; selecting a
        paragraph then surfaces the right-panel ``paragraph-detail`` view.
        (``selection-mode-paragraph`` radio retired; Rail target is canonical.)
  V4c — opening the OCR-config modal shows detection/recognition model selects
        that are populated with at least one option each.

V4b drives paragraph selection through the hierarchy tree (a deterministic,
DOM-based selection path).  The pixel-perfect canvas-click variant of paragraph
selection is covered separately by ``test_image_click_selection.py``; we avoid
duplicating its fragile fit-scale coordinate math here.

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V4
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

pytestmark = pytest.mark.e2e

_EXERCISE_ID = "exercise-fixture"


# ---------------------------------------------------------------------------
# V4a — words-layer checkbox toggles the words overlay visibility pref
# ---------------------------------------------------------------------------


def test_words_layer_checkbox_toggles_overlay_visibility(exercise_server: ExerciseServer, page: Page) -> None:
    """Toggling the words-layer rail control flips its pressed state (overlay no longer drawn).

    The viewport-chrome ImageTabsHeader was retired (D-050/D-053); the words-layer
    toggle now lives in the Rail as ``rail-layer-word`` — a real ``<button>`` whose
    ``aria-pressed`` reflects words-layer visibility (LayerToggleRow). That pressed
    state is the DOM-observable proof the words-layer pref flipped; the overlay
    itself is Konva-drawn (no per-word DOM nodes).
    """
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)

    btn = page.locator('[data-testid="rail-layer-word"]').first
    btn.wait_for(state="visible", timeout=10_000)
    # Words layer defaults to on.
    assert btn.get_attribute("aria-pressed") == "true", "words layer should default to visible"

    btn.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='rail-layer-word']\")"
        "?.getAttribute('aria-pressed') === 'false'",
        timeout=10_000,
    )
    assert btn.get_attribute("aria-pressed") == "false", (
        "words layer toggle should read unpressed after toggle"
    )

    # Toggling back restores visibility.
    btn.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='rail-layer-word']\")"
        "?.getAttribute('aria-pressed') === 'true'",
        timeout=10_000,
    )
    assert btn.get_attribute("aria-pressed") == "true"


# ---------------------------------------------------------------------------
# V4b — paragraph selection mode + image click selects a paragraph
# ---------------------------------------------------------------------------


def test_paragraph_mode_selection_opens_paragraph_detail(exercise_server: ExerciseServer, page: Page) -> None:
    """Selecting the paragraph rail target activates it; selecting a paragraph
    surfaces the right-panel paragraph-detail view.

    Switching the rail target to ``para`` is what makes the canvas hit-test
    resolve paragraphs. The viewport-chrome ImageTabsHeader radios were retired
    (D-050/D-053); the selection-mode control now lives in the Rail as
    ``rail-target-para`` — a real ``<button>`` whose ``data-active`` reflects the
    active target. We then select a paragraph via the hierarchy tree — a
    deterministic DOM path — and assert ``paragraph-detail`` renders.
    """
    # The exercise-fixture is deterministically seeded via the event store
    # (invariant since d0c1494). Content presence is asserted, not skipped —
    # 0 line_matches means a seeding regression, which must fail loudly.
    require_page_line_matches(exercise_server.base_url, _EXERCISE_ID, 0)

    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)

    # Enter paragraph selection mode via the canonical rail target cell.
    # Clicking rail-target-para sets railStore.target="para" (canvas hit-test
    # resolves paragraphs) and syncs uiPrefs.selectionMode="paragraph".
    para_target = page.locator('[data-testid="rail-target-para"]')
    para_target.wait_for(state="visible", timeout=10_000)
    para_target.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='rail-target-para']\")"
        "?.getAttribute('data-active') === 'true'",
        timeout=10_000,
    )

    # Select a paragraph node via the hierarchy tree.
    page.locator('[data-testid="drawer-tab-hierarchy"]').first.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=10_000)
    time.sleep(0.3)
    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > 0:
        # Expand the first block to reveal its paragraph children.
        first_block = block_nodes.first
        first_block.wait_for(state="visible", timeout=10_000)
        first_block.click()
        first_block.press("ArrowRight")
    para_nodes = page.locator('[data-testid^="hierarchy-node-para-"]')
    # Paragraph nodes appear once the tree expands (block layer) or immediately
    # (para-rooted tree). Wait for at least one before asserting.
    page.wait_for_selector('[data-testid^="hierarchy-node-para-"]', timeout=10_000)
    assert para_nodes.count() >= 1, "expected at least one paragraph node in the hierarchy"
    first_para = para_nodes.first
    first_para.wait_for(state="visible", timeout=10_000)
    first_para.click()

    # The right-panel paragraph detail must render for the selected paragraph.
    page.wait_for_selector('[data-testid="paragraph-detail"]', timeout=10_000)
    assert page.locator('[data-testid="paragraph-detail"]').count() == 1


# ---------------------------------------------------------------------------
# V4c — OCR-config modal model selects are populated
# ---------------------------------------------------------------------------


def test_ocr_config_model_selects_populated(exercise_server: ExerciseServer, page: Page) -> None:
    """Opening the OCR-config modal shows detection/recognition selects with options."""
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)

    # #405: ocr-config-trigger-button is a real button in PageActionsCompact.
    trigger = page.locator('[data-testid="ocr-config-trigger-button"]:not([data-testid-stub])').first
    trigger.wait_for(state="visible", timeout=10_000)
    trigger.click()

    # Modal mounts. Scope the selects to the open modal — an aria-hidden Radix
    # duplicate of the testid also exists in the DOM, so an unscoped .first can
    # match the wrong (hidden, empty) copy.
    modal = page.locator('[data-testid="ocr-config-modal"]')
    modal.wait_for(state="visible", timeout=10_000)
    det = modal.locator('[data-testid="ocr-detection-model-select"]').first
    reco = modal.locator('[data-testid="ocr-recognition-model-select"]').first
    # The models section lives lower in a scrollable modal body.
    det.scroll_into_view_if_needed()
    det.wait_for(state="visible", timeout=10_000)
    reco.wait_for(state="visible", timeout=10_000)

    # Each select must be populated with at least one <option>.
    det_options = det.locator("option").count()
    reco_options = reco.locator("option").count()
    assert det_options >= 1, f"detection model select has no options ({det_options})"
    assert reco_options >= 1, f"recognition model select has no options ({reco_options})"
    # And carry a non-empty selected value.
    assert (det.input_value() or "").strip() != "", "detection select has empty value"
    assert (reco.input_value() or "").strip() != "", "recognition select has empty value"
    time.sleep(0.1)
