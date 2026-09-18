"""Integration tests for ``POST .../words/delete-batch`` sidecar reindexing.

The defect: ``delete_words_batch`` removed a word from a line without
reindexing ``PageState.char_bboxes_map`` / ``glyph_annotations_map`` /
``glyph_predictions_map`` — sidecars keyed ``"{line_index}_{word_index}"``
silently attached to whatever word inherited the deleted word's slot.

Mirrors ``tests/integration/test_word_merge_router.py``'s fixtures — word
merge (2026-09-18) already reindexes sidecar maps after removing a word via
``_reindex_word_sidecar_maps_after_removal``; delete needs the same
treatment.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.core.review_counts import WordReviewCountsJournal
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


def _make_two_line_page() -> Page:
    """One paragraph, two lines: line 0 has 5 words, line 1 has 1 word.

    Line 0's words are spaced 10px apart so the batch-delete tests below can
    pick two non-adjacent indices in the same line.
    """
    line0_words = [_word(f"w{i}", _bbox(i * 10, 0, i * 10 + 8, 10)) for i in range(5)]
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
                        "items": line0_words,
                    },
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "block_category": "LINE",
                        "bounding_box": _bbox(0, 20, 100, 40),
                        "items": [
                            _word("delta", _bbox(0, 20, 15, 30)),
                            _word("echo", _bbox(20, 20, 35, 30)),
                        ],
                    },
                ],
            }
        ],
    }
    return Page.from_dict(page_dict)


def _seed_page(client: TestClient) -> tuple[PageState, Page]:
    live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_two_line_page()
    page_id = uuid4()
    live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate
    return pstate, page


def _delete(client: TestClient, word_indices: list[list[int]]) -> object:
    return client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/words/delete-batch",
        json={"scope": "word", "word_indices": word_indices},
    )


# ── single delete: later words' sidecars must follow them, not stay put ──


def test_delete_word_reindexes_sidecar_maps_for_later_words(loaded_client: TestClient) -> None:
    """Deleting word 0 shifts words 1-4 down by one; their sidecars must move
    with them. This is the core defect: without reindexing, word 1's char
    bboxes silently become attached to the surviving word now sitting at
    index 0 (formerly word 1), etc.
    """
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_1"] = [{"x": 1, "y": 1, "width": 2, "height": 2}]
    pstate.glyph_annotations_map["0_2"] = {"marks": ["ligature"]}
    pstate.glyph_predictions_map["0_3"] = {"marks": ["long_s"], "source": "model"}

    resp = _delete(loaded_client, [[0, 0]])
    assert resp.status_code == 200, resp.text  # type: ignore[attr-defined]

    assert [w.text for w in page.lines[0].words] == ["w1", "w2", "w3", "w4"]

    # Old keys must not remain — they'd misattach to whichever word now sits
    # at that index.
    assert "0_1" not in pstate.char_bboxes_map or pstate.char_bboxes_map["0_1"] != [
        {"x": 1, "y": 1, "width": 2, "height": 2}
    ]
    # Each sidecar must have followed its own word (all shifted down by 1).
    assert pstate.char_bboxes_map["0_0"] == [{"x": 1, "y": 1, "width": 2, "height": 2}]
    assert pstate.glyph_annotations_map["0_1"] == {"marks": ["ligature"]}
    assert pstate.glyph_predictions_map["0_2"] == {"marks": ["long_s"], "source": "model"}


def test_delete_word_drops_its_own_sidecar_entries(loaded_client: TestClient) -> None:
    """The deleted word's own sidecar data must be discarded, not left
    attached at its old index (which now refers to a different word).
    """
    pstate, _page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_2"] = [{"x": 9, "y": 9, "width": 1, "height": 1}]
    pstate.glyph_annotations_map["0_2"] = {"marks": ["swash"]}

    resp = _delete(loaded_client, [[0, 2]])
    assert resp.status_code == 200, resp.text  # type: ignore[attr-defined]

    assert "0_2" not in pstate.char_bboxes_map
    assert "0_2" not in pstate.glyph_annotations_map
    # And it must not have leaked onto the word that now occupies index 2
    # (formerly word 3).
    assert pstate.char_bboxes_map.get("0_2") != [{"x": 9, "y": 9, "width": 1, "height": 1}]


# ── batch delete: multiple removals in one call, including same-line ─────


def test_delete_batch_two_words_same_line_reindexes_correctly(loaded_client: TestClient) -> None:
    """Deleting words 1 and 3 from a 5-word line in one call is not two
    independent single-word shifts — book-tools removes highest-index-first
    per line (``Page.delete_words``), so the reindex must follow the same
    order or the arithmetic comes out wrong.

    Line 0 words (indices 0-4) -> after deleting 1 and 3, survivors are the
    original 0, 2, 4 at new indices 0, 1, 2.
    """
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_0"] = [{"x": 100, "y": 0, "width": 1, "height": 1}]
    pstate.char_bboxes_map["0_2"] = [{"x": 200, "y": 0, "width": 1, "height": 1}]
    pstate.glyph_annotations_map["0_4"] = {"marks": ["ligature"]}

    resp = _delete(loaded_client, [[0, 1], [0, 3]])
    assert resp.status_code == 200, resp.text  # type: ignore[attr-defined]

    assert [w.text for w in page.lines[0].words] == ["w0", "w2", "w4"]

    assert pstate.char_bboxes_map["0_0"] == [{"x": 100, "y": 0, "width": 1, "height": 1}]
    assert pstate.char_bboxes_map["0_1"] == [{"x": 200, "y": 0, "width": 1, "height": 1}]
    assert pstate.glyph_annotations_map["0_2"] == {"marks": ["ligature"]}
    assert "0_3" not in pstate.char_bboxes_map
    assert "0_4" not in pstate.glyph_annotations_map


def test_delete_batch_across_two_lines_keeps_lines_independent(loaded_client: TestClient) -> None:
    """Deleting a word on line 0 and a word on line 1 in the same call must
    reindex each line independently — one line's shift must not bleed into
    the other's key space.
    """
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["1_0"] = [{"x": 1, "y": 1, "width": 1, "height": 1}]
    pstate.char_bboxes_map["0_1"] = [{"x": 2, "y": 2, "width": 2, "height": 2}]

    resp = _delete(loaded_client, [[0, 0], [1, 0]])
    assert resp.status_code == 200, resp.text  # type: ignore[attr-defined]

    assert [w.text for w in page.lines[0].words] == ["w1", "w2", "w3", "w4"]
    # Line 1 had ["delta", "echo"]; deleting word 0 ("delta") leaves "echo"
    # at index 0 on the same line — line 1 itself is not pruned.
    assert [w.text for w in page.lines[1].words] == ["echo"]
    # Line 1's deleted word ("delta") had no sidecar entry of its own, so
    # "1_0" now names "echo" instead — nothing to drop here. The case where
    # the deleted word itself carries a sidecar entry is covered by
    # test_delete_word_drops_its_own_sidecar_entries above.
    assert "1_0" not in pstate.char_bboxes_map
    # Line 0's surviving word (was index 1) shifted down to index 0.
    assert pstate.char_bboxes_map["0_0"] == [{"x": 2, "y": 2, "width": 2, "height": 2}]


# ── persistence: delete must go through save_page_content_to_store ───────


def test_delete_words_batch_persists_and_updates_word_count_journal(
    tmp_path: Path, projects_root: Path
) -> None:
    """Delete must go through ``save_page_content_to_store`` — the single
    choke point that also appends the per-page word-count journal row.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)

    page_id: UUID = uuid4()
    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(projects_root / _PROJECT_ID)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
        page = _make_two_line_page()
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = client.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        resp = _delete(client, [[0, 0]])
        assert resp.status_code == 200, resp.text  # type: ignore[attr-defined]

        store_project_dir = projects_root / _PROJECT_ID

    fresh = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None, "delete did not persist through save_page_content_to_store"
        assert [w.text for w in reloaded.lines[0].words] == ["w1", "w2", "w3", "w4"]
    finally:
        fresh.close()

    journal = WordReviewCountsJournal(store_project_dir)
    latest = journal.latest_by_page()
    assert 0 in latest, "word-count journal row missing after delete"
    assert latest[0].total_words == 6  # was 7 words (w0-w4, delta, echo) before the delete
