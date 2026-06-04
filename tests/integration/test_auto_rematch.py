"""Lane A / Task A3 — GT auto-rematch after structural edits.

Legacy ``_finalize_structural_edit`` re-runs the GT matcher after every
structural word/line/paragraph mutation so per-word GT tracks the new
structure. The SPA previously did not, so per-word GT and OCR diverged after
edits. These tests assert:

1. After a structural edit, unedited words get their GT (re)filled by the
   page-level matcher.
2. An explicit per-word GT edit survives a subsequent structural edit
   (rematch only fills unedited words).
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

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str, gt: str = "") -> dict[str, object]:
    return {"type": "Word", "text": text, "ground_truth_text": gt, "bounding_box": _bbox(0, 0, 10, 10)}


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, 100, 20),
    }


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(0, 0, 100, 40),
    }


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [_para([_line([_word("hello"), _word("world")]), _line([_word("foo")])])],
    }
    return Page.from_dict(page_dict)


def _make_settings(tmp_path: Path, *, projects_root: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


@pytest.fixture
def loaded(tmp_path: Path) -> Any:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)
    client = TestClient(app)
    client.__enter__()
    resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
    assert resp.status_code == 200, resp.text

    # Inject GT source text for the page so auto-rematch has something to match.
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    project = project_state.loaded_project
    project.ground_truth_map[project.image_paths[0].name] = "hello world"

    store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_page()
    page_id = uuid4()
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate

    yield client, page
    client.__exit__(None, None, None)


_BASE = "/api/projects/book1/pages/0"


def test_structural_edit_refills_unedited_word_gt(loaded: Any) -> None:
    """After deleting an unrelated word, the surviving words get GT filled by
    the page-level matcher (auto-rematch). Before A3 the GT stayed empty."""
    client, page = loaded
    assert page.lines[0].words[0].ground_truth_text == ""

    # Delete "foo" (line 1, word 0) — a structural edit.
    r = client.post(f"{_BASE}/words/delete-batch", json={"scope": "word", "word_indices": [[1, 0]]})
    assert r.status_code == 200, r.text

    # The "hello"/"world" words now carry GT assigned by the rematch.
    assert page.lines[0].words[0].ground_truth_text == "hello"
    assert page.lines[0].words[1].ground_truth_text == "world"


def test_structural_edit_preserves_explicit_gt_edit(loaded: Any) -> None:
    """An explicit per-word GT edit survives a subsequent structural edit;
    rematch only fills words the user did not edit."""
    client, page = loaded

    # User types an explicit GT override on the first word.
    page.lines[0].words[0].ground_truth_text = "CUSTOM"

    # Structural edit elsewhere (delete "foo").
    r = client.post(f"{_BASE}/words/delete-batch", json={"scope": "word", "word_indices": [[1, 0]]})
    assert r.status_code == 200, r.text

    # The explicit edit is preserved; the unedited word is (re)matched.
    assert page.lines[0].words[0].ground_truth_text == "CUSTOM"
    assert page.lines[0].words[1].ground_truth_text == "world"
