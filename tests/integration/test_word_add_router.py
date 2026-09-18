"""Integration tests for ``POST .../words/add`` sidecar handling.

Spec authority: same family as ``test_word_split_router.py`` — the
2026-09-18 sidecar-reindex sweep (last route in the family, see
``docs/issues/2026-07-21-sidecar-*``). ``Page.add_word_to_page`` appends the
new word to its target line via ``Block.add_item``, which then re-sorts the
line by x position — so a word added between two existing words shifts every
later word's index by one, same shape of problem as word split's "later
words shift" half. Unlike split, add never replaces an existing ``Word``
object (the new word has no sidecar entries of its own to place, and every
existing word keeps its identity), so the identity-snapshot reindex used by
line/paragraph merge and word split applies here with no refusal needed.
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
    """One line: ["cat", "dog", "bird"] at x-ranges [0,30) [30,60) [60,100)."""
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


def _add_word(client: TestClient, *, x: int, y: int, width: int, height: int, text: str = "new") -> object:
    return client.post(
        f"/api/projects/{_PROJECT_ID}/pages/0/words/add",
        json={"bbox": {"x": x, "y": y, "width": width, "height": height}, "text": text},
    )


# ── word-index shift bookkeeping ─────────────────────────────────────────


def test_add_word_reindexes_sidecar_maps_for_later_words(loaded_client: TestClient) -> None:
    """Adding a word between "cat" and "dog" shifts "dog" from word_index 1
    to 2 and "bird" from word_index 2 to 3 — their sidecar entries must move
    with them, not stay keyed to their old positions (and land on the wrong
    word's char boxes / glyph annotations).
    """
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_0"] = [{"x": 1, "y": 1, "width": 2, "height": 2}]
    pstate.glyph_annotations_map["0_1"] = {"marks": ["ligature"]}
    pstate.char_bboxes_map["0_2"] = [{"x": 9, "y": 9, "width": 2, "height": 2}]

    # top_left.x=15 sorts between cat (x=0) and dog (x=30).
    resp = _add_word(loaded_client, x=15, y=0, width=2, height=10, text="new")
    assert resp.status_code == 200, resp.text
    assert [w.text for w in page.lines[0].words] == ["cat", "new", "dog", "bird"]

    # "cat" (word 0) is untouched by the shift.
    assert pstate.char_bboxes_map["0_0"] == [{"x": 1, "y": 1, "width": 2, "height": 2}]
    # "dog" moved from word 1 to word 2, carrying its glyph annotation.
    assert "0_1" not in pstate.glyph_annotations_map
    assert pstate.glyph_annotations_map["0_2"] == {"marks": ["ligature"]}
    # "bird" moved from word 2 to word 3, carrying its char bboxes.
    assert pstate.char_bboxes_map["0_3"] == [{"x": 9, "y": 9, "width": 2, "height": 2}]
    # The new word (word 1) has no sidecar entries of its own.
    assert "0_1" not in pstate.char_bboxes_map


def test_add_word_appended_last_does_not_disturb_existing_sidecars(loaded_client: TestClient) -> None:
    """Adding a word that sorts after every existing word (the simple,
    append-only path) must not shift any existing word's sidecar entries.
    """
    pstate, page = _seed_page(loaded_client)
    pstate.char_bboxes_map["0_0"] = [{"x": 1, "y": 1, "width": 2, "height": 2}]
    pstate.glyph_annotations_map["0_1"] = {"marks": ["ligature"]}
    pstate.char_bboxes_map["0_2"] = [{"x": 9, "y": 9, "width": 2, "height": 2}]

    # top_left.x=150 sorts after bird (x=60) — last in the line.
    resp = _add_word(loaded_client, x=150, y=0, width=2, height=10, text="new")
    assert resp.status_code == 200, resp.text
    assert [w.text for w in page.lines[0].words] == ["cat", "dog", "bird", "new"]

    assert pstate.char_bboxes_map["0_0"] == [{"x": 1, "y": 1, "width": 2, "height": 2}]
    assert pstate.glyph_annotations_map["0_1"] == {"marks": ["ligature"]}
    assert pstate.char_bboxes_map["0_2"] == [{"x": 9, "y": 9, "width": 2, "height": 2}]
    assert "0_3" not in pstate.char_bboxes_map
    assert "0_3" not in pstate.glyph_annotations_map


def test_add_word_persists_through_save_page_content_to_store(tmp_path: Path, projects_root: Path) -> None:
    """Add must go through ``save_page_content_to_store`` — the single
    choke point — so a fresh-process store reload sees the added word.
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

        resp = _add_word(client, x=15, y=0, width=2, height=10, text="new")
        assert resp.status_code == 200, resp.text

        store_project_dir = projects_root / _PROJECT_ID

    fresh = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None, "add did not persist through save_page_content_to_store"
        assert [w.text for w in reloaded.lines[0].words] == ["cat", "new", "dog", "bird"]
    finally:
        fresh.close()
