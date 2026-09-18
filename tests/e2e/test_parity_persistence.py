"""M-Final V3 — Save → reload round-trip in the browser.

End-to-end guard of the M0 persistence fix *through the rendered UI*:

  1. Select a word via the hierarchy tree → right-panel WordDetail.
  2. Validate it via ``word-footer-validate``.
  3. Edit its ground-truth text in ``ocr-gt-input`` (commit on Enter).
  4. Click the real ``save-page-button`` button.
  5. Reload the page route (full browser reload).
  6. Re-select the same word and assert the GT edit and validated state
     both survived the round-trip — checked against the server's own page
     payload, not just the rendered screen.

Validate is exercised *before* the GT edit, and this word's per-word
typography review is completed out of band *before the browser ever loads
the page* — see ``_prepare_word_for_validation``'s docstring, Finding 1,
for the reason any other order breaks the validate button for reasons
unrelated to persistence. (Finding 2, the word-identity/ground-truth
divergence that made this worse, is fixed — see
``docs/context/decisions.md`` 2026-09-18 — but Finding 1 alone still
requires this ordering.)

The style-label leg of this round-trip was removed by 6a04cbe (canonical
grapheme review editor): whole-word styling (``style-chip-italics``) was
retired in favor of the typography review workflow, so there is no style
label left to persist here.

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V3
"""

from __future__ import annotations

import time

import httpx
import pytest
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.api.pages import PagePayload
from pdomain_ocr_labeler_spa.core.models import WordMatch
from tests.e2e.exercise_real_project import (
    ExerciseServer,
    _goto_project_page,
    _wait_for_line_cards,
)
from tests.e2e.helpers import require_page_line_matches
from tests.e2e.test_export_manifest_and_trainer import _complete_typography_review_for_word
from tests.e2e.test_ui_coverage import _select_first_word_via_hierarchy

pytestmark = pytest.mark.e2e

_PROJECT_ID = "exercise-fixture"
_PAGE_INDEX = 0
_SUFFIX = "ZZ"  # deterministic GT edit marker


def _read_gt_value(page: Page) -> str:
    return page.evaluate("document.querySelector(\"[data-testid='ocr-gt-input']\")?.value ?? ''")


def _ensure_word_selected(page: Page) -> None:
    selected = _select_first_word_via_hierarchy(page)
    assert selected, "could not select a word node via the hierarchy tree"
    page.locator('[data-testid="ocr-gt-input"]').first.wait_for(state="visible", timeout=10_000)


def _find_word_by_gt(payload_json: object, gt_text: str) -> WordMatch:
    """Locate the word whose ``ground_truth_text`` is ``gt_text`` in a page payload.

    Parses the raw response body through the backend's own ``PagePayload``
    model rather than indexing a ``dict``, so a shape drift in the API fails
    this test with a validation error instead of a silent ``KeyError``.
    """
    page_payload = PagePayload.model_validate(payload_json)
    for line_match in page_payload.line_matches:
        for word_match in line_match.word_matches:
            if word_match.ground_truth_text == gt_text:
                return word_match
    raise AssertionError(f"no word with ground_truth_text={gt_text!r} in page payload")


def _poll_server_word_by_gt(base_url: str, gt_text: str, *, timeout: float = 15.0) -> WordMatch:
    """Poll ``GET .../pages/{page_index}`` until it returns a word matching *gt_text*.

    See ``_wait_for_footer_label``'s Finding 3 — the same transient
    empty-``line_matches`` race can hit a plain ``GET`` issued right after a
    mutation such as ``/save``, not just the browser's own query refetch.
    Reproduces over plain back-to-back HTTP calls with no browser involved,
    so this is a genuine backend race, not something a DOM wait could paper
    over; it is worth reporting rather than fixing here (out of this file's
    scope), and worth not letting fail this test outright on the first
    unlucky read either.
    """
    deadline = time.monotonic() + timeout
    last_error: AssertionError = AssertionError("poll never ran")
    while time.monotonic() < deadline:
        response = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}", timeout=20)
        if response.status_code == 200:
            try:
                return _find_word_by_gt(response.json(), gt_text)
            except AssertionError as exc:
                last_error = exc
        else:
            last_error = AssertionError(f"page re-fetch failed: {response.status_code} {response.text}")
        time.sleep(0.3)
    raise last_error


def _prepare_word_for_validation(base_url: str) -> WordMatch:
    """Fetch the word ``_select_first_word_via_hierarchy`` always lands on
    (line 0, word 0 — see ``_wait_for_line_cards``'s docstring: "the fixture
    pre-validates line 0") and complete its per-word typography review out
    of band, entirely before the browser ever loads the page.

    Finding: ``word-footer-validate`` disables itself
    (``WordFooter.tsx``'s ``!isValidated && !wordTypographyReviewed`` gate)
    for any unvalidated word whose own grapheme-level typography review
    isn't complete. exercise-fixture's word never has one, so clicking
    validate on an unvalidated word times out against a disabled button —
    exactly the "action silently does nothing" trap this test is meant to
    catch, not reproduce.

    Completing the review is a two-part hazard, which is why this runs
    before the browser opens the page at all rather than being satisfied
    lazily once WordFooter needs it:

    1. **Cache staleness.** Completing the review via the real
       ``.../corrections`` API (the same round trip
       ``test_selection_operations_parity.py``'s GRID-3/STB-1 test uses for
       this identical gate) happens over plain HTTP, outside TanStack
       Query's cache. If WordFooter's ``useTypographyHead`` query has
       already fetched and cached ``typography_reviewed=false`` for this
       word — which it does the moment the word is selected in the browser
       — nothing tells that query to refetch, and the button stays
       disabled even though the server-side state is now correct. Running
       this before the word is ever selected avoids the stale-cache read
       entirely: the query's first fetch already sees the completed
       review.
    2. **GT-edit poisoning — fixed 2026-09-18, kept here for history.**
       ``api/typography.py``'s word lookup (``_review_words`` /
       ``_word_text``) used to recompute each word's identity from its
       *current ground-truth text* on every call, while
       ``core/page_to_line_matches.py`` computed the ``word_id`` the
       frontend holds onto from the word's *OCR text*, once. The two agreed
       only while GT and OCR read the same — true here before any edit. The
       moment GT diverged, every ``/typography/words/{word_id}/...`` lookup
       for this word 404d, permanently breaking that word's
       ``word-footer-validate`` button. Word identity is now derived from
       OCR text everywhere, matching ``page_to_line_matches.py`` — see
       ``docs/context/decisions.md`` 2026-09-18 ("word identity diverged
       from OCR text...") and
       ``tests/integration/test_typography_word_id_survives_gt_edit.py``.
       This finding no longer applies; Finding 1 alone is why this function
       still runs before the browser loads the page.
    """
    payload = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}", timeout=20)
    assert payload.status_code == 200, f"page fetch failed: {payload.status_code}"
    page_payload = PagePayload.model_validate(payload.json())
    word = page_payload.line_matches[0].word_matches[0]
    if word.word_id:
        _complete_typography_review_for_word(
            base_url, _PROJECT_ID, page_index=_PAGE_INDEX, word_id=word.word_id
        )
    return word


def _wait_for_footer_label(page: Page, expected_label: str, *, timeout: float = 20.0) -> None:
    """Poll ``word-footer-validate``'s ``aria-label`` until it reads *expected_label*.

    Finding 3: immediately after a per-word mutation (observed after both
    ``/validated`` and ``/save``), the very next ``GET
    .../pages/{page_index}`` can return ``200`` with a transiently empty
    page payload (``line_matches: []``) — reproduces without the browser at
    all (plain back-to-back ``httpx`` calls), so it is a real backend race,
    not a UI rendering artifact. In the browser this shows up as the
    Hierarchy tree reading "No page data" and WordDetail reading "Word not
    found in page data.": the selected word, and its
    ``word-footer-validate`` button, drop out of the DOM entirely for that
    render. A single ``expect(...).to_have_attribute()`` treats a vanished
    locator as a hard failure; this polls instead and, mirroring what an
    actual user would do when the page flickers empty, re-selects the word
    via the Hierarchy tree if it dropped out — the same recovery a person
    clicking through the UI would need. This is a real product bug
    (reported, not fixed here — see this module's docstring and
    ``_prepare_word_for_validation``): a per-word mutation can transiently
    make the whole page look empty to anyone using the app at that moment.

    A related shape of the same race: the button can also get stuck
    *present but stale* — showing the pre-mutation label indefinitely —
    when two mutations fire in quick succession and their invalidation
    refetches resolve out of order, so a late response for the first
    mutation overwrites the cache with data older than the second
    mutation's own response already confirmed. Polling alone cannot fix
    that (nothing else will trigger a further refetch), so past the
    halfway point this forces one full page reload — a real fetch straight
    from the server, the same recovery a stuck user would reach for — and
    keeps polling with the time that remains.
    """
    deadline = time.monotonic() + timeout
    reload_at = time.monotonic() + (timeout / 2)
    reloaded = False
    validate_btn = page.locator('[data-testid="word-footer-validate"]').first
    last_seen: str | None = None
    while time.monotonic() < deadline:
        try:
            if validate_btn.count() == 0:
                _select_first_word_via_hierarchy(page)
            else:
                last_seen = validate_btn.get_attribute("aria-label")
                if last_seen == expected_label:
                    return
        except Exception as _exc:
            # Playwright may throw transiently while React re-renders; ignore and retry.
            _ = _exc
        if not reloaded and time.monotonic() >= reload_at:
            reloaded = True
            page.reload(timeout=20_000)
            page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
            _wait_for_line_cards(page)
            _select_first_word_via_hierarchy(page)
        time.sleep(0.2)
    pytest.fail(
        f"word-footer-validate aria-label never settled on {expected_label!r} "
        f"(last seen {last_seen!r}) within {timeout}s"
    )


def _validate_selected_word(page: Page, expected_gt: str) -> None:
    """Click ``word-footer-validate`` and assert the click actually validated the word.

    Finding: exercise-fixture page 1's line 0 ships pre-validated. The old
    "if already validated, leave it; else click" logic therefore always
    took the already-validated branch and never once clicked
    ``word-footer-validate``: the validate leg of this round-trip proved
    nothing beyond "the fixture starts validated and stays validated", true
    whether or not Save/reload works at all. This forces a known
    unvalidated baseline first so the click path is actually exercised
    before the save/reload the test is meant to prove. See
    ``_prepare_word_for_validation`` for why this word's typography review
    must already be complete by the time this runs.
    """
    validate_btn = page.locator('[data-testid="word-footer-validate"]').first
    validate_btn.wait_for(state="visible", timeout=10_000)
    if validate_btn.get_attribute("aria-label") == "Unvalidate word":
        with page.expect_response(lambda r: r.url.endswith("/validated")) as unvalidate_resp_info:
            validate_btn.click()
        unvalidate_resp = unvalidate_resp_info.value
        assert unvalidate_resp.status == 200, (
            f"Unvalidate request failed: {unvalidate_resp.status} {unvalidate_resp.text()}"
        )
        # Wait for the re-render (query invalidation), not a timer — see
        # ``_wait_for_footer_label``'s docstring for why this polls rather
        # than asserting a single attribute snapshot.
        _wait_for_footer_label(page, "Validate word")
        validate_btn = page.locator('[data-testid="word-footer-validate"]').first

    with page.expect_response(lambda r: r.url.endswith("/validated")) as validate_resp_info:
        validate_btn.click()
    validate_resp = validate_resp_info.value
    assert validate_resp.status == 200, (
        f"Validate request failed: {validate_resp.status} {validate_resp.text()}"
    )
    validated_word = _find_word_by_gt(validate_resp.json(), expected_gt)
    assert validated_word.is_validated, (
        f"Validate response did not mark the word validated: {validated_word!r}"
    )
    _wait_for_footer_label(page, "Unvalidate word")


def test_save_then_reload_persists_gt_and_validation(exercise_server: ExerciseServer, page: Page) -> None:
    """Validate + edit GT → Save Page → reload → both persist, per the server."""
    # The exercise-fixture is deterministically seeded via the event store
    # (invariant since d0c1494). Assert content presence — 0 line_matches is a
    # seeding regression that must fail loudly, not a vacuous-test skip.
    require_page_line_matches(exercise_server.base_url, _PROJECT_ID, _PAGE_INDEX)

    # Complete this word's typography review before the browser ever loads
    # the page — see ``_prepare_word_for_validation``'s docstring.
    prepared_word = _prepare_word_for_validation(exercise_server.base_url)

    page_url = f"{exercise_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1"

    # ── First visit: make the two edits ─────────────────────────────────────
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)
    _ensure_word_selected(page)

    original_gt = _read_gt_value(page)
    assert original_gt == prepared_word.ground_truth_text, (
        f"hierarchy selection landed on a different word than expected: "
        f"UI={original_gt!r} server={prepared_word.ground_truth_text!r}"
    )
    expected_gt = original_gt + _SUFFIX

    # 1. Validate the word via word-footer-validate — see
    # ``_validate_selected_word``'s docstring for why this step used to be a
    # no-op that the old test never noticed, and why it runs before the GT
    # edit below.
    _validate_selected_word(page, original_gt)

    # 2. Edit GT and commit (Enter blurs → onCommitGt → POST .../gt). Wait for
    # the request the commit fires rather than guessing how long the mutation
    # and re-render take, and check the response body actually carries the
    # new text — a fixed sleep here would notice neither a failed POST nor a
    # commit that silently no-opped.
    gt_input = page.locator('[data-testid="ocr-gt-input"]').first
    gt_input.click()
    gt_input.fill(expected_gt)
    with page.expect_response(lambda r: r.url.endswith("/gt")) as gt_resp_info:
        gt_input.press("Enter")
    gt_resp = gt_resp_info.value
    assert gt_resp.status == 200, f"GT commit failed: {gt_resp.status} {gt_resp.text()}"
    committed_word = _find_word_by_gt(gt_resp.json(), expected_gt)
    assert committed_word.is_validated, "GT commit must not have reset the validated state set in step 1"

    # 3. Click the real Save Page button (enabled on a project route). Wait
    # for the save response itself and assert it succeeded, rather than a
    # fixed sleep that never noticed a failed or silently-skipped save.
    save_btn = page.locator('[data-testid="save-page-button"]').first
    save_btn.wait_for(state="visible", timeout=10_000)
    assert save_btn.is_enabled(), "Save page button must be enabled on a project route"
    with page.expect_response(lambda r: r.url.endswith("/save")) as save_resp_info:
        save_btn.click()
    save_resp = save_resp_info.value
    save_body = save_resp.json()
    assert save_resp.status == 200, f"Save request failed: {save_resp.status} {save_resp.text()}"
    assert save_body.get("saved") is True, f"Save response did not report success: {save_body}"

    # ── Confirm persistence against the server, not just the screen ────────
    # Polls rather than a single GET — see ``_poll_server_word_by_gt``'s
    # docstring (Finding 3) for the transient-empty-payload race this
    # guards against.
    server_word = _poll_server_word_by_gt(exercise_server.base_url, expected_gt)
    assert server_word.is_validated, (
        f"server page state after save did not persist validation: {server_word!r}"
    )

    # ── Full browser reload of the page route ──────────────────────────────
    page.goto(page_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    _wait_for_line_cards(page)
    _ensure_word_selected(page)

    # ── Assert both edits survived in the rendered UI too ───────────────────
    persisted_gt = _read_gt_value(page)
    assert persisted_gt == expected_gt, f"GT did not persist: expected {expected_gt!r}, got {persisted_gt!r}"

    _wait_for_footer_label(page, "Unvalidate word")
