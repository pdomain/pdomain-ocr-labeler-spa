"""Integration tests for line/paragraph structural-edit sidecar reindexing.

The defect: ``PageState.char_bboxes_map`` / ``glyph_annotations_map`` /
``glyph_predictions_map`` are keyed ``"{line_index}_{word_index}"``. Deleting
or merging a *line* (or deleting a *paragraph*, which removes several lines
at once) shifts every later line's page-wide index, but none of
``delete_line`` / ``lines/delete-batch`` / ``delete_paragraph`` /
``paragraphs/delete-batch`` / ``lines/merge`` reindexed the sidecar maps —
every later line's words silently inherited another line's char boxes and
glyph annotations.

Mirrors ``tests/integration/test_word_delete_router.py`` /
``test_word_merge_router.py``'s fixtures and structure — those cover the
word-index half of the same bug (fixed 2026-09-18); this covers the
line-index half.
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


def _word(text: str, bbox: dict[str, object]) -> dict[str, object]:
    return {"type": "Word", "text": text, "ground_truth_text": text, "bounding_box": bbox}


def _line(words: list[dict[str, object]], *, y0: int, y1: int) -> dict[str, object]:
    xs = [w["bounding_box"]["top_left"]["x"] for w in words]  # type: ignore[index]
    x1s = [w["bounding_box"]["bottom_right"]["x"] for w in words]  # type: ignore[index]
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "bounding_box": _bbox(min(xs), y0, max(x1s), y1),
        "items": words,
    }


def _paragraph(lines: list[dict[str, object]], *, y0: int, y1: int) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "bounding_box": _bbox(0, y0, 200, y1),
        "items": lines,
    }


def _make_page(paragraphs: list[dict[str, object]]) -> Page:
    page_dict: dict[str, object] = {
        "width": 200,
        "height": 400,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 400),
        "items": paragraphs,
    }
    return Page.from_dict(page_dict)


def _seed_page(client: TestClient, page: Page) -> PageState:
    live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page_id = uuid4()
    live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate
    return pstate


# ── delete_line: a middle line disappears; later lines shift up ──────────


def _three_line_page() -> Page:
    """One paragraph, three lines, two words each: a0/a1, b0/b1, c0/c1."""
    line0 = _line([_word("a0", _bbox(0, 0, 8, 10)), _word("a1", _bbox(10, 0, 18, 10))], y0=0, y1=10)
    line1 = _line([_word("b0", _bbox(0, 20, 8, 30)), _word("b1", _bbox(10, 20, 18, 30))], y0=20, y1=30)
    line2 = _line([_word("c0", _bbox(0, 40, 8, 50)), _word("c1", _bbox(10, 40, 18, 50))], y0=40, y1=50)
    return _make_page([_paragraph([line0, line1, line2], y0=0, y1=50)])


def test_delete_line_reindexes_later_lines_and_drops_deleted_lines_own_entries(
    loaded_client: TestClient,
) -> None:
    """Deleting line 1 (b0/b1) leaves line 2 (c0/c1) as the new line 1.

    Without reindexing, line 2's words silently inherit line 1's old sidecar
    entries (the defect) instead of keeping their own.
    """
    page = _three_line_page()
    pstate = _seed_page(loaded_client, page)
    pstate.char_bboxes_map["0_0"] = [{"tag": "a0"}]  # survives untouched (line 0 unaffected)
    pstate.glyph_annotations_map["1_1"] = {"tag": "b1"}  # deleted line's own entry — must vanish
    pstate.glyph_predictions_map["2_0"] = {"tag": "c0"}  # must follow c0 from "2_0" to "1_0"

    resp = loaded_client.post(f"/api/projects/{_PROJECT_ID}/pages/0/lines/1/delete")
    assert resp.status_code == 200, resp.text

    assert [line[0].text for line in [line.words for line in page.lines]] == ["a0", "c0"]

    assert pstate.char_bboxes_map["0_0"] == [{"tag": "a0"}]
    assert "1_1" not in pstate.glyph_annotations_map
    assert not any(v == {"tag": "b1"} for v in pstate.glyph_annotations_map.values())
    assert "2_0" not in pstate.glyph_predictions_map
    assert pstate.glyph_predictions_map["1_0"] == {"tag": "c0"}


# ── lines/delete-batch: non-adjacent line removal in one call ────────────


def _four_line_page() -> Page:
    """One paragraph, four lines, one word each: a, b, c, d."""
    lines = [
        _line([_word(t, _bbox(0, i * 20, 8, i * 20 + 10))], y0=i * 20, y1=i * 20 + 10)
        for i, t in enumerate(["a", "b", "c", "d"])
    ]
    return _make_page([_paragraph(lines, y0=0, y1=80)])


def test_delete_lines_batch_reindexes_non_adjacent_removal(loaded_client: TestClient) -> None:
    """Deleting lines 1 and 3 in one call is not two independent shifts —
    ``Page.delete_lines`` removes highest-index-first. Surviving lines 0
    (a) and 2 (c) land at new indices 0 and 1.
    """
    page = _four_line_page()
    pstate = _seed_page(loaded_client, page)
    pstate.char_bboxes_map["0_0"] = [{"tag": "a"}]
    pstate.char_bboxes_map["2_0"] = [{"tag": "c"}]
    pstate.glyph_annotations_map["1_0"] = {"tag": "b"}
    pstate.glyph_annotations_map["3_0"] = {"tag": "d"}

    resp = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/lines/delete-batch",
        json={"scope": "line", "line_indices": [1, 3]},
    )
    assert resp.status_code == 200, resp.text

    assert [line.words[0].text for line in page.lines] == ["a", "c"]

    assert pstate.char_bboxes_map["0_0"] == [{"tag": "a"}]
    assert pstate.char_bboxes_map["1_0"] == [{"tag": "c"}]
    assert not any(v == {"tag": "b"} for v in pstate.glyph_annotations_map.values())
    assert not any(v == {"tag": "d"} for v in pstate.glyph_annotations_map.values())


# ── delete_paragraph: removes several lines at once, not necessarily one ──


def _two_paragraph_page() -> Page:
    """Paragraph 0 has lines 0-1 (p0a, p0b); paragraph 1 has lines 2-3 (p1a, p1b)."""
    p0_line0 = _line([_word("p0a", _bbox(0, 0, 8, 10))], y0=0, y1=10)
    p0_line1 = _line([_word("p0b", _bbox(0, 20, 8, 30))], y0=20, y1=30)
    p1_line0 = _line([_word("p1a", _bbox(0, 40, 8, 50))], y0=40, y1=50)
    p1_line1 = _line([_word("p1b", _bbox(0, 60, 8, 70))], y0=60, y1=70)
    return _make_page(
        [
            _paragraph([p0_line0, p0_line1], y0=0, y1=30),
            _paragraph([p1_line0, p1_line1], y0=40, y1=70),
        ]
    )


def test_delete_paragraph_reindexes_all_lines_it_removes(loaded_client: TestClient) -> None:
    """Deleting paragraph 0 removes page-wide lines 0 and 1 together;
    paragraph 1's lines 2/3 become the new lines 0/1.
    """
    page = _two_paragraph_page()
    pstate = _seed_page(loaded_client, page)
    pstate.char_bboxes_map["0_0"] = [{"tag": "p0a"}]  # deleted — must vanish
    pstate.glyph_annotations_map["1_0"] = {"tag": "p0b"}  # deleted — must vanish
    pstate.glyph_predictions_map["2_0"] = {"tag": "p1a"}  # survives -> "0_0"
    pstate.char_bboxes_map["3_0"] = [{"tag": "p1b"}]  # survives -> "1_0"

    resp = loaded_client.post(f"/api/projects/{_PROJECT_ID}/pages/0/paragraphs/0/delete")
    assert resp.status_code == 200, resp.text

    assert [line.words[0].text for line in page.lines] == ["p1a", "p1b"]

    assert not any(v == {"tag": "p0a"} for v in pstate.char_bboxes_map.values())
    assert not any(v == {"tag": "p0b"} for v in pstate.glyph_annotations_map.values())
    assert pstate.glyph_predictions_map["0_0"] == {"tag": "p1a"}
    assert pstate.char_bboxes_map["1_0"] == [{"tag": "p1b"}]


# ── paragraphs/delete-batch: non-contiguous paragraph removal ────────────


def _three_paragraph_page() -> Page:
    """Three paragraphs, one line each (2 words in the first/last): p0, p1, p2."""
    p0_line = _line([_word("p0a", _bbox(0, 0, 8, 10)), _word("p0b", _bbox(10, 0, 18, 10))], y0=0, y1=10)
    p1_line = _line([_word("p1a", _bbox(0, 20, 8, 30))], y0=20, y1=30)
    p2_line = _line([_word("p2a", _bbox(0, 40, 8, 50)), _word("p2b", _bbox(10, 40, 18, 50))], y0=40, y1=50)
    return _make_page(
        [
            _paragraph([p0_line], y0=0, y1=10),
            _paragraph([p1_line], y0=20, y1=30),
            _paragraph([p2_line], y0=40, y1=50),
        ]
    )


def test_delete_paragraphs_batch_reindexes_non_contiguous_removal(loaded_client: TestClient) -> None:
    """Deleting paragraphs 0 and 2 leaves paragraph 1's line — page-wide
    line index 1 before the edit — as the sole survivor, landing at line 0.
    The surviving line was never adjacent to only one of the removed
    paragraphs, so this is not a simple "shift by count" computation.
    """
    page = _three_paragraph_page()
    pstate = _seed_page(loaded_client, page)
    pstate.char_bboxes_map["0_0"] = [{"tag": "p0a"}]  # deleted
    pstate.glyph_annotations_map["0_1"] = {"tag": "p0b"}  # deleted
    pstate.glyph_predictions_map["1_0"] = {"tag": "p1a"}  # survives -> "0_0"
    pstate.char_bboxes_map["2_1"] = [{"tag": "p2b"}]  # deleted

    resp = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/paragraphs/delete-batch",
        json={"scope": "paragraph", "paragraph_indices": [0, 2]},
    )
    assert resp.status_code == 200, resp.text

    assert [w.text for w in page.lines[0].words] == ["p1a"]

    assert pstate.glyph_predictions_map["0_0"] == {"tag": "p1a"}
    assert not any(v == {"tag": "p0a"} for v in pstate.char_bboxes_map.values())
    assert not any(v == {"tag": "p0b"} for v in pstate.glyph_annotations_map.values())
    assert not any(v == {"tag": "p2b"} for v in pstate.char_bboxes_map.values())


# ── lines/merge: the double shift — words move AND later lines renumber ──


def _three_line_page_for_merge() -> Page:
    """Line 0: m0(x=0), m1(x=20). Line 1: n0(x=10), n1(x=30). Line 2: o0.

    Line 0 and line 1's x-positions are chosen to interleave when merged:
    ``Block.merge`` re-sorts the combined word list by x-position rather
    than appending, so the merged line's final word order is
    m0(x0), n0(x10), m1(x20), n1(x30) — NOT "line 0's words, then line 1's
    words" the way a naive "offset by destination length" formula would
    assume.
    """
    line0 = _line([_word("m0", _bbox(0, 0, 8, 10)), _word("m1", _bbox(20, 0, 28, 10))], y0=0, y1=10)
    line1 = _line([_word("n0", _bbox(10, 0, 18, 10)), _word("n1", _bbox(30, 0, 38, 10))], y0=0, y1=10)
    line2 = _line([_word("o0", _bbox(0, 20, 8, 30))], y0=20, y1=30)
    return _make_page([_paragraph([line0, line1, line2], y0=0, y1=30)])


def test_merge_lines_reindexes_interleaved_words_and_shifts_later_lines(
    loaded_client: TestClient,
) -> None:
    """Merging lines 0 and 1: every merged word's sidecar must follow it to
    its ACTUAL post-merge index (which interleaves by x-position), and line
    2 (unrelated to the merge) must shift from index 2 to index 1 with its
    own sidecar intact.
    """
    page = _three_line_page_for_merge()
    pstate = _seed_page(loaded_client, page)
    pstate.char_bboxes_map["0_0"] = [{"tag": "m0"}]
    pstate.char_bboxes_map["0_1"] = [{"tag": "m1"}]
    pstate.glyph_annotations_map["1_0"] = {"tag": "n0"}
    pstate.glyph_annotations_map["1_1"] = {"tag": "n1"}
    pstate.glyph_predictions_map["2_0"] = {"tag": "o0"}

    resp = loaded_client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/lines/merge",
        json={"line_indices": [0, 1]},
    )
    assert resp.status_code == 200, resp.text

    merged_words = [w.text for w in page.lines[0].words]
    assert merged_words == ["m0", "n0", "m1", "n1"], merged_words
    assert [w.text for w in page.lines[1].words] == ["o0"]

    # Each merged word's sidecar must follow it to its real interleaved
    # index, not to "line0's original length" (index 2, which a naive
    # append-offset formula would predict for n0 — wrong: n0 landed at 1).
    assert pstate.char_bboxes_map["0_0"] == [{"tag": "m0"}]
    assert pstate.glyph_annotations_map["0_1"] == {"tag": "n0"}
    assert pstate.char_bboxes_map["0_2"] == [{"tag": "m1"}]
    assert pstate.glyph_annotations_map["0_3"] == {"tag": "n1"}
    # Line 2 shifted from page-wide index 2 to 1; its sidecar followed.
    assert pstate.glyph_predictions_map["1_0"] == {"tag": "o0"}
    assert "2_0" not in pstate.glyph_predictions_map


# ── persistence: all five routes must still reach save_page_content_to_store ─


def _persist_and_reload(
    tmp_path: Path,
    projects_root: Path,
    page: Page,
    request_path: str,
    request_body: dict[str, object],
) -> Page:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    page_id: UUID = uuid4()

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(projects_root / _PROJECT_ID)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = client.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        resp = client.post(f"/api/projects/{_PROJECT_ID}/pages/0{request_path}", json=request_body)
        assert resp.status_code == 200, resp.text

        store_project_dir = projects_root / _PROJECT_ID

    fresh = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None, f"{request_path} did not persist through save_page_content_to_store"
    finally:
        fresh.close()

    journal = WordReviewCountsJournal(store_project_dir)
    latest = journal.latest_by_page()
    assert 0 in latest, f"word-count journal row missing after {request_path}"
    return reloaded


def test_delete_line_persists_through_save_page_content_to_store(tmp_path: Path, projects_root: Path) -> None:
    reloaded = _persist_and_reload(tmp_path, projects_root, _three_line_page(), "/lines/1/delete", {})
    assert [line.words[0].text for line in reloaded.lines] == ["a0", "c0"]


def test_delete_lines_batch_persists_through_save_page_content_to_store(
    tmp_path: Path, projects_root: Path
) -> None:
    reloaded = _persist_and_reload(
        tmp_path,
        projects_root,
        _four_line_page(),
        "/lines/delete-batch",
        {"scope": "line", "line_indices": [1, 3]},
    )
    assert [line.words[0].text for line in reloaded.lines] == ["a", "c"]


def test_delete_paragraph_persists_through_save_page_content_to_store(
    tmp_path: Path, projects_root: Path
) -> None:
    reloaded = _persist_and_reload(tmp_path, projects_root, _two_paragraph_page(), "/paragraphs/0/delete", {})
    assert [line.words[0].text for line in reloaded.lines] == ["p1a", "p1b"]


def test_delete_paragraphs_batch_persists_through_save_page_content_to_store(
    tmp_path: Path, projects_root: Path
) -> None:
    reloaded = _persist_and_reload(
        tmp_path,
        projects_root,
        _three_paragraph_page(),
        "/paragraphs/delete-batch",
        {"scope": "paragraph", "paragraph_indices": [0, 2]},
    )
    assert [w.text for w in reloaded.lines[0].words] == ["p1a"]


def test_merge_lines_persists_through_save_page_content_to_store(tmp_path: Path, projects_root: Path) -> None:
    reloaded = _persist_and_reload(
        tmp_path,
        projects_root,
        _three_line_page_for_merge(),
        "/lines/merge",
        {"line_indices": [0, 1]},
    )
    assert [w.text for w in reloaded.lines[0].words] == ["m0", "n0", "m1", "n1"]
