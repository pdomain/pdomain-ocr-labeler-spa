"""Integration: typography staleness is scoped to structure, not ground truth.

Reproduces and fixes the defect reported 2026-09-18 against the 2026-08-22
"Typography uses current persisted-page epochs" design: ``TypographyBinding.
page_sha256`` was a hash of the *whole page*, including every word's
ground-truth text and bounding box. A typography correction was bound to it,
and a correction whose binding no longer matched the live page was treated as
stale. So correcting any one word's ground truth invalidated every other
word's typography review on the same page — even a word nobody touched.

The 2026-09-18 "Retired: word identity diverged..." entry in
``docs/context/decisions.md`` named this "expected staleness, not a bug." This
file's author disagreed: correcting ground truth is the core activity of this
product, so a page-wide invalidation on every edit makes the per-word
Validate button (``TypographyHeadResponse.typography_reviewed``, gated by
``GET .../typography/words/{word_id}/head``) close to unusable.

Ruling: a typography correction is a statement about a word's own graphemes.
It should go stale when *that word's* own content changes, or when a
structural edit (add/delete/merge/split) shifts reading order — never merely
because *some other* word's ground truth was corrected. ``page_sha256`` is
therefore recomputed from the page's structure alone (ordered line/word
boundaries, word count, and each word's OCR — not ground-truth — text); a
word's own ground-truth staleness is unaffected, since it was always also
carried by the per-word ``text_sha256`` the epoch already checks separately
for append validation and which this fix now also gates reads on.

A correction recorded under the pre-fix whole-page scheme must not be
silently orphaned (treated as permanently stale the moment this ships) or
silently un-staled (treated as safe from a *future* edit it never saw). See
``_legacy_binding`` and ``_current_epoch_migration_aware`` in
``api/typography.py``, and ``test_legacy_page_hash_scheme_is_not_orphaned_on_ship``
below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.api.pages import PagePayload
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings

_PROJECT_ID = "book1"
_PAGE_INDEX = 0


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str, gt: str, *, x0: int = 0) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt,
        "bounding_box": _bbox(x0, 0, x0 + 10, 10),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, 200, 20),
    }


def _page_dict() -> dict[str, object]:
    # Three words, one line, GT == OCR initially so every word starts
    # identical under either the legacy or the structural hash scheme.
    return {
        "width": 400,
        "height": 100,
        "page_index": _PAGE_INDEX,
        "bounding_box": _bbox(0, 0, 400, 100),
        "items": [
            _line(
                [
                    _word("alpha", "alpha", x0=0),
                    _word("beta", "beta", x0=20),
                    _word("gamma", "gamma", x0=40),
                ]
            ),
        ],
    }


@pytest.fixture
def loaded_client(tmp_path: Path) -> Any:
    """TestClient with a real book-tools Page seeded: alpha, beta, gamma."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / _PROJECT_ID
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )
    app = build_app(settings)
    client = TestClient(app)
    client.__enter__()
    resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
    assert resp.status_code == 200, resp.text

    store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = Page.from_dict(_page_dict())
    page_id = uuid4()
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=_PAGE_INDEX, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=_PAGE_INDEX, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=_PAGE_INDEX, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[_PAGE_INDEX] = pstate

    yield client
    client.__exit__(None, None, None)


def _get_payload(client: TestClient) -> PagePayload:
    resp = client.get(f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}")
    assert resp.status_code == 200, resp.text
    return PagePayload.model_validate(resp.json())


def _typography_head(client: TestClient, word_id: str) -> Any:
    return client.get(f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/typography/words/{word_id}/head")


def _edit_ground_truth(client: TestClient, *, line_index: int, word_index: int, text: str) -> Any:
    return client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/words/{line_index}/{word_index}/gt",
        json={"text": text},
    )


def _complete_review(client: TestClient, word_id: str, *, source_evidence_id: str) -> Any:
    """Submit a ``reviewed_regular`` correction against *word_id*'s current head."""
    head_resp = _typography_head(client, word_id)
    assert head_resp.status_code == 200, head_resp.text
    head = head_resp.json()
    taxonomy = head["taxonomy"]
    replacement = {
        "word_id": head["word_id"],
        "text": head["text"],
        "text_sha256": head["text_sha256"],
        "page_content_sha256": head["page_sha256"],
        "image_artifact_sha256": head["image_sha256"],
        "grapheme_map_version": head["grapheme_map_version"],
        "taxonomy_version": taxonomy["version"],
        "taxonomy_hash": taxonomy["taxonomy_hash"],
        "label_states": {label["value"]: "negative" for label in taxonomy["labels"]},
        "spans": [],
        "source_evidence_ids": [source_evidence_id],
        "warnings": [],
        "whole_word_labels": None,
        "word_revision": head["word_revision"] + 1,
        "review_state": "reviewed_regular",
        "metadata": None,
    }
    submission = {
        "expected_head": head["head_token"],
        "correction_id": str(uuid4()),
        "taxonomy_version": taxonomy["version"],
        "taxonomy_hash": taxonomy["taxonomy_hash"],
        "grapheme_map_version": head["grapheme_map_version"],
        "labeler_id": "local",
        "decision": "reviewed_regular",
        "replacement": replacement,
        "replacement_text_sha256": head["text_sha256"],
        "replacement_page_sha256": head["page_sha256"],
        "replacement_image_sha256": head["image_sha256"],
        "replacement_page_head_sha256": head["page_head_sha256"],
        "replacement_word_revision": head["word_revision"] + 1,
        "replacement_artifacts": [],
        "replacement_artifact_payloads": [],
        "model_runs": [],
        "coordinate_transforms": [],
    }
    return client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/typography/words/{word_id}/corrections",
        json=submission,
    )


def _word_id(payload: PagePayload, index: int) -> str:
    word = payload.line_matches[0].word_matches[index]
    assert word.word_id is not None
    return word.word_id


def _find_word_id_by_ocr_text(payload: PagePayload, ocr_text: str) -> str:
    for line_match in payload.line_matches:
        for word in line_match.word_matches:
            if word.ocr_text == ocr_text:
                assert word.word_id is not None
                return word.word_id
    raise AssertionError(f"no word with ocr_text={ocr_text!r} on the page")


def test_ground_truth_edit_on_unrelated_word_does_not_invalidate_review(loaded_client: TestClient) -> None:
    """Complete a review on "alpha", correct "beta"'s ground truth, confirm
    "alpha"'s review — and its Validate button's gate — both survive.

    This is the reported bug's exact repro: reviewing one word and then
    correcting a different word's ground truth used to flip the reviewed
    word back to "not reviewed", because ``page_sha256`` hashed every word's
    ground-truth text, not just the reviewed word's own.
    """
    payload = _get_payload(loaded_client)
    alpha_id = _word_id(payload, 0)

    reviewed = _complete_review(loaded_client, alpha_id, source_evidence_id="seed-alpha")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=1, text="betaX")
    assert edit.status_code == 200, edit.text

    after = _typography_head(loaded_client, alpha_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is True, (
        "correcting an unrelated word's ground truth must not invalidate "
        "this word's already-complete typography review"
    )
    # The Validate button's own gate reads exactly this field — confirm
    # nothing about the CAS head token construction broke either.
    assert after.json()["correction"] is not None


def test_own_ground_truth_edit_still_invalidates_own_review(loaded_client: TestClient) -> None:
    """A word's own ground-truth edit must still stale its own review —
    only *other* words must be unaffected, not the edited word itself.
    """
    payload = _get_payload(loaded_client)
    alpha_id = _word_id(payload, 0)

    reviewed = _complete_review(loaded_client, alpha_id, source_evidence_id="seed-alpha")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=0, text="alphaX")
    assert edit.status_code == 200, edit.text

    after = _typography_head(loaded_client, alpha_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is False, (
        "a word's own ground-truth edit must still invalidate its own "
        "typography review — only unrelated words must be spared"
    )


def test_word_add_invalidates_review(loaded_client: TestClient) -> None:
    """A structural edit (word added earlier in the line) still invalidates
    a later word's review — it genuinely shifts reading order.
    """
    payload = _get_payload(loaded_client)
    gamma_id = _word_id(payload, 2)

    reviewed = _complete_review(loaded_client, gamma_id, source_evidence_id="seed-gamma")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    added = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/words/add",
        json={"line_index": 0, "bbox": {"x": 5, "y": 0, "width": 10, "height": 10}, "text": "new"},
    )
    assert added.status_code == 200, added.text

    refreshed_gamma_id = _find_word_id_by_ocr_text(_get_payload(loaded_client), "gamma")
    after = _typography_head(loaded_client, refreshed_gamma_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is False, (
        "adding a word must still stale a correction whose reading order it shifts"
    )


def test_word_delete_invalidates_review(loaded_client: TestClient) -> None:
    """Deleting a word still invalidates a later word's review."""
    payload = _get_payload(loaded_client)
    gamma_id = _word_id(payload, 2)

    reviewed = _complete_review(loaded_client, gamma_id, source_evidence_id="seed-gamma")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    deleted = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/words/delete-batch",
        json={"scope": "word", "word_indices": [[0, 0]]},
    )
    assert deleted.status_code == 200, deleted.text

    refreshed_gamma_id = _find_word_id_by_ocr_text(_get_payload(loaded_client), "gamma")
    after = _typography_head(loaded_client, refreshed_gamma_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is False, (
        "deleting a word must still stale a correction whose reading order it shifts"
    )


def test_word_merge_invalidates_review(loaded_client: TestClient) -> None:
    """Merging two words still invalidates a later word's review."""
    payload = _get_payload(loaded_client)
    gamma_id = _word_id(payload, 2)

    reviewed = _complete_review(loaded_client, gamma_id, source_evidence_id="seed-gamma")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    merged = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/words/0/0/merge",
        json={"direction": "right"},
    )
    assert merged.status_code == 200, merged.text

    refreshed_gamma_id = _find_word_id_by_ocr_text(_get_payload(loaded_client), "gamma")
    after = _typography_head(loaded_client, refreshed_gamma_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is False, (
        "merging two words must still stale a correction whose reading order it shifts"
    )


def test_word_split_invalidates_review(loaded_client: TestClient) -> None:
    """Splitting a word still invalidates a later word's review."""
    payload = _get_payload(loaded_client)
    gamma_id = _word_id(payload, 2)

    reviewed = _complete_review(loaded_client, gamma_id, source_evidence_id="seed-gamma")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["typography_reviewed"] is True

    split = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/{_PAGE_INDEX}/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "horizontal"},
    )
    assert split.status_code == 200, split.text

    refreshed_gamma_id = _find_word_id_by_ocr_text(_get_payload(loaded_client), "gamma")
    after = _typography_head(loaded_client, refreshed_gamma_id)
    assert after.status_code == 200, after.text
    assert after.json()["typography_reviewed"] is False, (
        "splitting a word must still stale a correction whose reading order it shifts"
    )


def test_legacy_page_hash_scheme_is_not_orphaned_on_ship(loaded_client: TestClient) -> None:
    """A correction recorded under the pre-fix whole-page hash formula is
    not silently orphaned the moment this fix ships.

    Simulates a correction appended by a pre-fix server build — bypassing
    the (already-fixed) ``POST .../corrections`` endpoint — computed with
    ``_legacy_binding``, the exact pre-fix (ground-truth- and
    bbox-inclusive whole-page) formula this fix superseded. Confirms it
    reads as reviewed immediately (not orphaned by the scheme change alone,
    with nothing else edited), continues to survive its *own* word's later
    inspection, but — since a legacy-scheme correction cannot retroactively
    gain the new fine-grained tracking it was never recorded with — still
    goes stale the next time *any* word's ground truth is corrected, same
    as every correction did before this fix. That gap closes permanently
    the moment the word is reviewed again: the new correction is recorded
    under the current (structural-only) scheme, and from then on survives an
    unrelated word's edit exactly like
    ``test_ground_truth_edit_on_unrelated_word_does_not_invalidate_review``
    above.
    """
    from pdomain_book_tools.typography import (
        CorrectionDecision,
        LabelState,
        ReviewState,
        TypographyCorrection,
    )

    from pdomain_ocr_labeler_spa.api import typography as typography_api
    from pdomain_ocr_labeler_spa.core.typography_review import TypographyCorrectionLog

    project = loaded_client.app.state.project_state.loaded_project  # type: ignore[attr-defined]
    state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project is not None

    payload = _get_payload(loaded_client)
    alpha_id = _word_id(payload, 0)
    logical_page_id = typography_api._logical_page_id(project, _PAGE_INDEX, state)
    legacy = typography_api._legacy_binding(project, _PAGE_INDEX, alpha_id, state)
    assert legacy is not None

    taxonomy = typography_api.TYPOGRAPHY_TAXONOMY
    replacement = {
        "word_id": alpha_id,
        "text": "alpha",
        "text_sha256": legacy.text_sha256,
        "page_content_sha256": legacy.page_sha256,
        "image_artifact_sha256": legacy.image_sha256,
        "grapheme_map_version": typography_api.GRAPHEME_SEGMENTATION_VERSION,
        "taxonomy_version": taxonomy.version,
        "taxonomy_hash": taxonomy.taxonomy_hash,
        "label_states": {label.value: LabelState.NEGATIVE.value for label in taxonomy.labels},
        "spans": [],
        "source_evidence_ids": ["legacy-seed"],
        "warnings": [],
        "whole_word_labels": None,
        "word_revision": 1,
        "review_state": ReviewState.REVIEWED_REGULAR.value,
    }
    legacy_correction = TypographyCorrection.model_validate(
        {
            "correction_id": "legacy-correction-1",
            "word_id": alpha_id,
            "revision": 1,
            "supersedes_id": None,
            "base_page_sha256": legacy.page_sha256,
            "base_image_sha256": legacy.image_sha256,
            "base_text_sha256": legacy.text_sha256,
            "base_word_revision": 0,
            "replacement_text_sha256": legacy.text_sha256,
            "replacement_page_sha256": legacy.page_sha256,
            "replacement_image_sha256": legacy.image_sha256,
            "replacement_page_head_sha256": legacy.page_head_sha256,
            "replacement_word_revision": 1,
            "taxonomy_version": taxonomy.version,
            "taxonomy_hash": taxonomy.taxonomy_hash,
            "grapheme_map_version": typography_api.GRAPHEME_SEGMENTATION_VERSION,
            "page_head_sha256": legacy.page_head_sha256,
            "labeler_id": "pre-fix-server",
            "decision": CorrectionDecision.REVIEWED_REGULAR.value,
            "replacement": replacement,
        }
    )
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    log.append(legacy_correction, logical_page_id=logical_page_id, current=legacy)

    # Not orphaned: nothing else has changed, so the legacy-scheme root
    # still matches the page's live state under the legacy formula.
    immediately = _typography_head(loaded_client, alpha_id)
    assert immediately.status_code == 200, immediately.text
    assert immediately.json()["typography_reviewed"] is True, (
        "a correction recorded under the pre-fix whole-page hash scheme must "
        "read as reviewed immediately after this fix ships, with nothing else "
        "edited — it must not be silently orphaned by the scheme change alone"
    )

    # Known, accepted transitional gap: an *unrelated* word's ground-truth
    # edit still stales this legacy-scheme correction, because the legacy
    # formula it was recorded under is itself whole-page. This is not worse
    # than before this fix shipped — it is exactly the pre-fix behavior,
    # confined to corrections nobody has touched since.
    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=1, text="betaX")
    assert edit.status_code == 200, edit.text
    after_unrelated_edit = _typography_head(loaded_client, alpha_id)
    assert after_unrelated_edit.status_code == 200, after_unrelated_edit.text
    assert after_unrelated_edit.json()["typography_reviewed"] is False, (
        "a legacy-scheme correction cannot retroactively gain fine-grained "
        "tracking it was never recorded with — it goes stale on the next "
        "unrelated edit, exactly as it would have before this fix"
    )

    # That gap closes for good once the word is reviewed again: the new
    # correction is recorded under the current (structural-only) scheme and
    # survives a *further* unrelated edit from then on.
    re_reviewed = _complete_review(loaded_client, alpha_id, source_evidence_id="seed-alpha-rereview")
    assert re_reviewed.status_code == 200, re_reviewed.text
    assert re_reviewed.json()["typography_reviewed"] is True

    further_edit = _edit_ground_truth(loaded_client, line_index=0, word_index=1, text="betaY")
    assert further_edit.status_code == 200, further_edit.text
    after_further_edit = _typography_head(loaded_client, alpha_id)
    assert after_further_edit.status_code == 200, after_further_edit.text
    assert after_further_edit.json()["typography_reviewed"] is True, (
        "once re-reviewed under the current scheme, this word's review must "
        "survive a further unrelated word's ground-truth edit"
    )
