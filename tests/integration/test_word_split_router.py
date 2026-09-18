"""Integration tests for ``POST .../words/{li}/{wi}/split`` sidecar handling.

Spec authority: same family as ``test_word_merge_router.py`` — the 2026-09-18
sidecar-reindex sweep. Word split was left out of the word-merge and
line-merge reindex fixes because it replaces the split word with two brand
new ``Word`` objects: neither an offset formula (word merge) nor an
identity-snapshot diff (line/paragraph merge) can describe what a *new*
object's sidecar entry should become, so a split is refused outright when
the word carries any sidecar entry — same shape of error as word merge.
Every later word in the line still shifts by one index, and its sidecar
entries must follow it, same as word merge and delete.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.typography import GRAPHEME_SEGMENTATION_VERSION, TypographyCorrection
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.core.typography_review import (
    TypographyBinding,
    TypographyCorrectionLog,
    stable_page_id,
    stable_word_id,
)
from pdomain_ocr_labeler_spa.settings import Settings

_PROJECT_ID = "book1"


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / _PROJECT_ID
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x00")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / _PROJECT_ID)})
        assert resp.status_code == 200, resp.text
        yield c


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str, bbox: dict[str, object], *, gt: str | None = None) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt if gt is not None else text,
        "bounding_box": bbox,
    }


def _make_page() -> Page:
    """One line: ["cat", "dog", "bird"] — every word is >= 2 chars (split needs that)."""
    page_dict: dict[str, object] = {
        "width": 200,
        "height": 100,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 100),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "block_category": "PARAGRAPH",
                "bounding_box": _bbox(0, 0, 200, 100),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "block_category": "LINE",
                        "bounding_box": _bbox(0, 0, 100, 20),
                        "items": [
                            _word("cat", _bbox(0, 0, 30, 10)),
                            _word("dog", _bbox(30, 0, 60, 10)),
                            _word("bird", _bbox(60, 0, 100, 10)),
                        ],
                    },
                ],
            }
        ],
    }
    return Page.from_dict(page_dict)


def _seed_page(client: TestClient) -> tuple[PageState, Page]:
    live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_page()
    page_id = uuid4()
    live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate
    return pstate, page


def _split(client: TestClient, line_index: int, word_index: int, x_fraction: float = 0.5) -> object:
    return client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/words/{line_index}/{word_index}/split",
        json={"x_fraction": x_fraction, "direction": "horizontal"},
    )


# ── refusal: splitting a word that carries durable per-word state ─────────


def test_split_word_refused_for_char_bboxes(loaded_client: TestClient) -> None:
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_0"] = [{"x": 0, "y": 0, "width": 5, "height": 5}]

    resp = _split(loaded_client, 0, 0)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "word_split_would_orphan_annotations"
    assert body["details"]["kind"] == "char_bbox"
    assert body["details"]["line_index"] == 0
    assert body["details"]["word_index"] == 0

    # Refused — the word must survive untouched, not be silently split.
    assert [w.text for w in page.lines[0].words] == ["cat", "dog", "bird"]


def test_split_word_refused_for_glyph_annotations(loaded_client: TestClient) -> None:
    pstate, page = _seed_page(loaded_client)
    # Presence alone counts — an explicitly-empty review still blocks.
    pstate.glyph_annotations_map["0_0"] = {}

    resp = _split(loaded_client, 0, 0)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "word_split_would_orphan_annotations"
    assert body["details"]["kind"] == "glyph_annotation"
    assert body["details"]["word_index"] == 0
    assert [w.text for w in page.lines[0].words] == ["cat", "dog", "bird"]


def _typography_binding() -> TypographyBinding:
    text_sha = hashlib.sha256(b"cat").hexdigest()
    return TypographyBinding(
        page_sha256="a" * 64,
        image_sha256="b" * 64,
        text_sha256=text_sha,
        page_head_sha256="a" * 64,
        word_revision=0,
    )


def _typography_correction(word_id: str) -> TypographyCorrection:
    text_sha = hashlib.sha256(b"cat").hexdigest()
    return TypographyCorrection.model_validate(
        {
            "correction_id": "correction-1",
            "word_id": word_id,
            "revision": 1,
            "supersedes_id": None,
            "base_page_sha256": "a" * 64,
            "base_image_sha256": "b" * 64,
            "base_text_sha256": text_sha,
            "base_word_revision": 0,
            "replacement_text_sha256": text_sha,
            "replacement_page_sha256": "e" * 64,
            "replacement_image_sha256": "f" * 64,
            "replacement_page_head_sha256": "1" * 64,
            "replacement_word_revision": 1,
            "taxonomy_version": "launch-1",
            "taxonomy_hash": "2" * 64,
            "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
            "page_head_sha256": "a" * 64,
            "labeler_id": "reviewer@example.test",
            "decision": "approved_edit",
            "replacement": {
                "word_id": word_id,
                "text": "cat",
                "text_sha256": text_sha,
                "page_content_sha256": "e" * 64,
                "image_artifact_sha256": "f" * 64,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "taxonomy_version": "launch-1",
                "taxonomy_hash": "2" * 64,
                "label_states": {"italic": "positive"},
                "spans": [
                    {
                        "span_id": "span-1",
                        "label": "italic",
                        "start": 0,
                        "end": 3,
                        "label_source": "human",
                        "confidence_tier": "gold",
                        "alignment_evidence_id": "human-review",
                    }
                ],
                "source_evidence_ids": ["human-review"],
                "whole_word_labels": ["italic"],
                "word_revision": 1,
                "review_state": "reviewed",
            },
        }
    )


def test_split_word_refused_for_typography_correction(loaded_client: TestClient, projects_root: Path) -> None:
    _seed_page(loaded_client)

    logical_page_id = stable_page_id(project_id=_PROJECT_ID, page_index=0)
    # Word 0 on line 0 is "cat" at reading_order=0 (page-wide, word-by-word).
    word_id = stable_word_id(project_id=_PROJECT_ID, page_id=logical_page_id, reading_order=0, text="cat")
    log = TypographyCorrectionLog(projects_root / _PROJECT_ID, corpus_root=projects_root)
    log.append(
        _typography_correction(word_id),
        logical_page_id=logical_page_id,
        current=_typography_binding(),
    )

    resp = _split(loaded_client, 0, 0)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "word_split_would_orphan_annotations"
    assert body["details"]["kind"] == "typography_correction"
    assert body["details"]["word_index"] == 0


# ── word-index shift bookkeeping ─────────────────────────────────────────


def test_split_word_reindexes_sidecar_maps_for_later_words(loaded_client: TestClient) -> None:
    """Splitting word 0 ("cat") into two words shifts "dog" from word_index 1
    to 2 and "bird" from word_index 2 to 3 — their sidecar entries must move
    with them, not stay keyed to their old positions.
    """
    pstate, page = _seed_page(loaded_client)
    pstate.glyph_annotations_map["0_1"] = {"marks": ["ligature"]}
    pstate.char_bboxes_map["0_2"] = [{"x": 1, "y": 1, "width": 2, "height": 2}]

    resp = _split(loaded_client, 0, 0)
    assert resp.status_code == 200, resp.text
    assert [w.text for w in page.lines[0].words] == ["ca", "t", "dog", "bird"]

    assert "0_1" not in pstate.char_bboxes_map
    assert pstate.glyph_annotations_map["0_2"] == {"marks": ["ligature"]}
    assert pstate.char_bboxes_map["0_3"] == [{"x": 1, "y": 1, "width": 2, "height": 2}]


def test_split_word_persists_through_save_page_content_to_store(tmp_path: Path, projects_root: Path) -> None:
    """Split must go through ``save_page_content_to_store`` — the single
    choke point — so a fresh-process store reload sees the split structure.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)

    page_id: UUID = uuid4()
    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(projects_root / _PROJECT_ID)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
        page = _make_page()
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = client.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        resp = _split(client, 0, 0)
        assert resp.status_code == 200, resp.text

        store_project_dir = projects_root / _PROJECT_ID

    fresh = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None, "split did not persist through save_page_content_to_store"
        assert [w.text for w in reloaded.lines[0].words] == ["ca", "t", "dog", "bird"]
    finally:
        fresh.close()
