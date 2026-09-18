"""Integration: a word's typography identity must survive a ground-truth edit.

Reproduces the defect: ``core/page_to_line_matches.py`` mints a word's
``word_id`` from its OCR text, once, when building the page payload.
``api/typography.py``'s ``_review_words``/``_word_text`` recomputed the same
word's identity from its *live* ground-truth text, on every call. The two
agreed only while ground truth read the same as OCR — the moment a person
corrected a word's ground truth (the core activity of this product), every
``/typography/words/{word_id}/...`` lookup for that word 404d, permanently,
unless the ground truth was later reverted to exactly match the OCR text.

That 404 fed straight into the per-word Validate button's gate
(``WordFooter``'s ``useTypographyHead`` query reads
``TypographyHeadResponse.typography_reviewed``): once a word's ground truth
was corrected, the word could be unvalidated but never validated again —
reintroducing the exact bug the "Retired: the per-word validate button could
never validate a word" fix (``docs/context/decisions.md``) removed, through a
different door.

Fix: word identity is derived from OCR text everywhere — matching
``page_to_line_matches.py`` and the upstream contract's own stated invariant
(``make_word_id``'s docstring: "Corrections never reissue this ID"). A
correction recorded under the pre-fix (ground-truth-derived) id is still
reachable: ``_canonical_word_id_map`` resolves either id to the same word.
See ``docs/context/decisions.md`` (2026-09-18, word-id/ground-truth
divergence).

Spec: ``tests/e2e/test_parity_persistence.py``'s
``_prepare_word_for_validation`` docstring, Finding 2, documents this same
defect and routes around it; this file proves and fixes it directly.
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


def _word(text: str, gt: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt,
        "bounding_box": _bbox(0, 0, 10, 10),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, 100, 20),
    }


def _page_dict() -> dict[str, object]:
    # Ground truth equals OCR text at the start, matching the common
    # unedited case, so the defect only shows up *after* the GT edit below —
    # not from page load onward.
    return {
        "width": 200,
        "height": 100,
        "page_index": _PAGE_INDEX,
        "bounding_box": _bbox(0, 0, 200, 100),
        "items": [
            _line([_word("teh", "teh"), _word("cat", "cat")]),
        ],
    }


@pytest.fixture
def loaded_client(tmp_path: Path) -> Any:
    """TestClient with a real book-tools Page seeded, GT == OCR initially."""
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
    """Submit a ``reviewed_regular`` correction against *word_id*'s current head.

    Mirrors the round trip ``TypographySection``'s "Reviewed regular" button
    performs (and ``tests/e2e/test_export_manifest_and_trainer.py``'s
    ``_complete_typography_review_for_word``): resolves the current head,
    then submits every taxonomy label as negative with no spans, decided
    ``reviewed_regular``.
    """
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


def test_typography_head_survives_ground_truth_edit(loaded_client: TestClient) -> None:
    """Reads a word's ``word_id`` from the real page payload (as the
    frontend does), confirms the typography head lookup for that id
    succeeds before any edit, edits the word's ground truth so it diverges
    from its OCR text, and confirms the same id still resolves afterward.
    """
    payload = _get_payload(loaded_client)
    word = payload.line_matches[0].word_matches[0]
    assert word.word_id is not None
    assert word.ocr_text == "teh"
    assert word.ground_truth_text == "teh"

    pre_edit = _typography_head(loaded_client, word.word_id)
    assert pre_edit.status_code == 200, pre_edit.text

    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=0, text="the")
    assert edit.status_code == 200, edit.text

    post_edit = _typography_head(loaded_client, word.word_id)
    assert post_edit.status_code == 200, (
        f"typography head 404d for word_id={word.word_id!r} after a ground-truth "
        f"edit changed its ground truth from 'teh' to 'the' while its OCR text "
        f"stayed 'teh' — word identity must survive ground-truth correction, "
        f"the core activity of this product. {post_edit.text}"
    )
    # The word's ``word_id`` in a freshly re-fetched payload must be
    # unchanged too: identity is stable across the edit, not just resolvable
    # via a fallback.
    refreshed = _get_payload(loaded_client)
    refreshed_word = refreshed.line_matches[0].word_matches[0]
    assert refreshed_word.word_id == word.word_id
    assert refreshed_word.ground_truth_text == "the"


def test_typography_review_survives_ground_truth_edit(loaded_client: TestClient) -> None:
    """Review a word, correct its ground truth, and confirm the review is
    still reachable — and the Validate button's gate
    (``TypographyHeadResponse.typography_reviewed``) can still reach
    "reviewed" — afterward.

    Editing *any* word's ground truth changes the page's content hash, which
    invalidates every word's correction epoch (``TypographyBinding.
    page_sha256``, unrelated to word identity and unchanged by this fix) —
    so ``typography_reviewed`` legitimately flips back to ``False`` and asks
    for a fresh review, the same as it would for a genuinely new page
    revision. That is expected, not the bug. The bug was that the lookup
    itself 404d, so the button could *never* move to "reviewed" again no
    matter what — this proves it now can: the head keeps resolving (200, not
    404) through the edit, and a fresh review reaches ``typography_reviewed:
    true`` again.
    """
    payload = _get_payload(loaded_client)
    word = payload.line_matches[0].word_matches[0]
    assert word.word_id is not None
    word_id = word.word_id

    head_resp = _typography_head(loaded_client, word_id)
    assert head_resp.status_code == 200, head_resp.text
    assert head_resp.json()["typography_reviewed"] is False

    first_review = _complete_review(loaded_client, word_id, source_evidence_id="test-seed-1")
    assert first_review.status_code == 200, first_review.text
    assert first_review.json()["typography_reviewed"] is True

    reviewed_head = _typography_head(loaded_client, word_id)
    assert reviewed_head.status_code == 200, reviewed_head.text
    assert reviewed_head.json()["typography_reviewed"] is True

    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=0, text="the")
    assert edit.status_code == 200, edit.text

    post_edit_head = _typography_head(loaded_client, word_id)
    assert post_edit_head.status_code == 200, (
        "the Validate button's gate (GET .../typography/words/{word_id}/head) "
        f"must still resolve after a ground-truth edit — a 404 here is the bug "
        f"this fix closes. {post_edit_head.text}"
    )

    second_review = _complete_review(loaded_client, word_id, source_evidence_id="test-seed-2")
    assert second_review.status_code == 200, second_review.text
    assert second_review.json()["typography_reviewed"] is True, (
        "the Validate button must be able to reach 'reviewed' again after a "
        "ground-truth edit — a review that can never complete again "
        "reintroduces the retired 'validate button could never validate a "
        "word' bug"
    )


def test_correction_recorded_under_legacy_ground_truth_id_still_resolves(loaded_client: TestClient) -> None:
    """A correction filed under the pre-fix (ground-truth-derived) id must
    still be reachable through the current (OCR-derived) id.

    Simulates a correction recorded by a server build that predates this
    fix by appending one directly to the append-only journal — bypassing
    the (already-fixed) ``POST .../corrections`` endpoint entirely — under
    the ground-truth-derived id the old ``_review_words``-based scheme
    would have used. Then confirms the *current* (OCR-derived, page-payload)
    id still resolves it. Proves the fallback (this fix's answer to "what
    happens to corrections recorded under the old id") without depending on
    server-version history or patching internals.
    """
    from pdomain_book_tools.typography import TypographyCorrection

    from pdomain_ocr_labeler_spa.core.typography_review import (
        TypographyBinding,
        TypographyCorrectionLog,
        stable_page_id,
        stable_word_id,
    )

    payload = _get_payload(loaded_client)
    word = payload.line_matches[0].word_matches[0]
    assert word.word_id is not None
    current_word_id = word.word_id

    # Diverge GT from OCR so the legacy (ground-truth-derived) id differs
    # from the current (OCR-derived) id from this point on.
    edit = _edit_ground_truth(loaded_client, line_index=0, word_index=0, text="the")
    assert edit.status_code == 200, edit.text
    page_id = stable_page_id(project_id=_PROJECT_ID, page_index=_PAGE_INDEX)
    legacy_word_id = stable_word_id(project_id=_PROJECT_ID, page_id=page_id, reading_order=0, text="the")
    assert legacy_word_id != current_word_id

    head_resp = _typography_head(loaded_client, current_word_id)
    assert head_resp.status_code == 200, head_resp.text
    head = head_resp.json()
    taxonomy = head["taxonomy"]
    replacement = {
        "word_id": legacy_word_id,
        "text": head["text"],
        "text_sha256": head["text_sha256"],
        "page_content_sha256": head["page_sha256"],
        "image_artifact_sha256": head["image_sha256"],
        "grapheme_map_version": head["grapheme_map_version"],
        "taxonomy_version": taxonomy["version"],
        "taxonomy_hash": taxonomy["taxonomy_hash"],
        "label_states": {label["value"]: "negative" for label in taxonomy["labels"]},
        "spans": [],
        "source_evidence_ids": ["legacy-seed"],
        "warnings": [],
        "whole_word_labels": None,
        "word_revision": 1,
        "review_state": "reviewed_regular",
    }
    legacy_correction = TypographyCorrection.model_validate(
        {
            "correction_id": "legacy-correction-1",
            "word_id": legacy_word_id,
            "revision": 1,
            "supersedes_id": None,
            "base_page_sha256": head["page_sha256"],
            "base_image_sha256": head["image_sha256"],
            "base_text_sha256": head["text_sha256"],
            "base_word_revision": 0,
            "replacement_text_sha256": head["text_sha256"],
            "replacement_page_sha256": head["page_sha256"],
            "replacement_image_sha256": head["image_sha256"],
            "replacement_page_head_sha256": head["page_head_sha256"],
            "replacement_word_revision": 1,
            "taxonomy_version": taxonomy["version"],
            "taxonomy_hash": taxonomy["taxonomy_hash"],
            "grapheme_map_version": head["grapheme_map_version"],
            "page_head_sha256": head["page_head_sha256"],
            "labeler_id": "legacy-server",
            "decision": "reviewed_regular",
            "replacement": replacement,
        }
    )
    current_binding = TypographyBinding(
        page_sha256=head["page_sha256"],
        image_sha256=head["image_sha256"],
        text_sha256=head["text_sha256"],
        page_head_sha256=head["page_head_sha256"],
        word_revision=0,
    )
    project = loaded_client.app.state.project_state.loaded_project  # type: ignore[attr-defined]
    assert project is not None
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    log.append(legacy_correction, logical_page_id=head["logical_page_id"], current=current_binding)

    # Look the review up through the *current* (OCR-derived, page-payload)
    # id — the one the frontend actually holds — and confirm it is found.
    current_head = _typography_head(loaded_client, current_word_id)
    assert current_head.status_code == 200, current_head.text
    assert current_head.json()["typography_reviewed"] is True, (
        "a correction recorded under the legacy ground-truth-derived id must "
        "still be visible through the word's current, OCR-derived id"
    )
