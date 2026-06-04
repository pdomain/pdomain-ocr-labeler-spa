"""Lane A / Task A2 — scope-batch routes matching the toolbarMapping contract.

The frontend ``frontend/src/lib/toolbarMapping.ts`` references batch routes
that previously did not exist (404):

- ``lines/copy-gt-batch``       (page / paragraph / line / word scopes)
- ``paragraphs/delete-batch``
- ``lines/delete-batch``
- ``words/delete-batch``
- ``paragraphs/split-selected``
- ``paragraphs/group-selected-words``

Each test asserts the route exists (not 404) and that the underlying
operation actually happened on the in-memory page.
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

# ── Page builders (real book-tools Page) ───────────────────────────────


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str, gt: str | None = None) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt if gt is not None else text,
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


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(0, 0, 100, 40),
    }


def _make_page() -> Page:
    """Two paragraphs, each with two lines, each line two words."""
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            _para([_line([_word("one"), _word("two")]), _line([_word("three"), _word("four")])]),
            _para([_line([_word("five"), _word("six")]), _line([_word("seven"), _word("eight")])]),
        ],
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


def _seed_page_in_store(store: LabelerPageStore, page_id: Any, page_index: int) -> None:
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=page_index, source="ocr")))


@pytest.fixture
def loaded(tmp_path: Path) -> Any:
    """Return (client, project_state, page) with a project loaded and a
    real book-tools Page seeded into PageState + the event store."""
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

    store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_page()
    page_id = uuid4()
    _seed_page_in_store(store, page_id, 0)

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate

    yield client, project_state, page
    client.__exit__(None, None, None)


_BASE = "/api/projects/book1/pages/0"


# ── lines/copy-gt-batch ────────────────────────────────────────────────


def test_copy_gt_batch_line_scope_gt_to_ocr(loaded: Any) -> None:
    client, _ps, page = loaded
    # Make GT differ from OCR on line 0 words.
    page.lines[0].words[0].ground_truth_text = "GT0"
    page.lines[0].words[1].ground_truth_text = "GT1"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "line", "line_indices": [0], "direction": "gt_to_ocr"},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    assert page.lines[0].words[0].text == "GT0"
    assert page.lines[0].words[1].text == "GT1"


def test_copy_gt_batch_page_scope_ocr_to_gt(loaded: Any) -> None:
    client, _ps, page = loaded
    page.lines[0].words[0].text = "OCRX"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "page", "direction": "ocr_to_gt"},
    )
    assert r.status_code == 200, r.text
    assert page.lines[0].words[0].ground_truth_text == "OCRX"


def test_copy_gt_batch_paragraph_scope(loaded: Any) -> None:
    client, _ps, page = loaded
    para_words = page.paragraphs[0].words
    para_words[0].ground_truth_text = "PG"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "paragraph", "paragraph_indices": [0], "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    assert para_words[0].text == "PG"


def test_copy_gt_batch_word_scope(loaded: Any) -> None:
    client, _ps, page = loaded
    page.lines[1].words[0].ground_truth_text = "WG"
    r = client.post(
        f"{_BASE}/lines/copy-gt-batch",
        json={"scope": "word", "word_indices": [[1, 0]], "direction": "gt_to_ocr"},
    )
    assert r.status_code == 200, r.text
    assert page.lines[1].words[0].text == "WG"


# ── delete-batch routes ────────────────────────────────────────────────


def test_paragraphs_delete_batch(loaded: Any) -> None:
    client, _ps, page = loaded
    before = len(page.paragraphs)
    r = client.post(
        f"{_BASE}/paragraphs/delete-batch",
        json={"scope": "paragraph", "paragraph_indices": [0]},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    assert len(page.paragraphs) == before - 1


def test_lines_delete_batch(loaded: Any) -> None:
    client, _ps, page = loaded
    before = len(page.lines)
    r = client.post(
        f"{_BASE}/lines/delete-batch",
        json={"scope": "line", "line_indices": [0]},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    assert len(page.lines) == before - 1


def test_words_delete_batch(loaded: Any) -> None:
    client, _ps, page = loaded
    before = len(page.lines[0].words)
    r = client.post(
        f"{_BASE}/words/delete-batch",
        json={"scope": "word", "word_indices": [[0, 0]]},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    assert len(page.lines[0].words) == before - 1


# ── paragraphs/split-selected ──────────────────────────────────────────


def test_paragraphs_split_selected(loaded: Any) -> None:
    client, _ps, page = loaded
    before = len(page.paragraphs)
    r = client.post(
        f"{_BASE}/paragraphs/split-selected",
        json={"paragraph_indices": [0]},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    # Paragraph 0 had two lines → splitting yields one paragraph per line.
    assert len(page.paragraphs) > before


# ── paragraphs/group-selected-words ────────────────────────────────────


def test_paragraphs_group_selected_words(loaded: Any) -> None:
    client, _ps, page = loaded
    before = len(page.paragraphs)
    r = client.post(
        f"{_BASE}/paragraphs/group-selected-words",
        json={"word_indices": [[0, 0]]},
    )
    assert r.status_code != 404, "route missing (404)"
    assert r.status_code == 200, r.text
    # Grouping selected words creates a new paragraph.
    assert len(page.paragraphs) > before
