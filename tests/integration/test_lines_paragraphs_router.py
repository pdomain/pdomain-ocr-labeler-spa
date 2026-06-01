"""Integration tests for ``api/lines_paragraphs.py`` route handlers.

Acceptance criteria for issue #186:
- pytest integration tests for each endpoint (happy path + 404 guard)

Spec authority:
- ``docs/architecture/02-backend.md §5.5`` — line/paragraph endpoint contracts.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


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
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x00")
    (proj / "002.png").write_bytes(b"\x00")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project already loaded (book1, 2 pages)."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.fixture
def bare_client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with no project loaded."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ── copy-line-gt ──────────────────────────────────────────────────────


def test_copy_line_gt_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_copy_line_gt_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_copy_line_gt_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0


# ── delete-scope ──────────────────────────────────────────────────────


def test_delete_scope_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_delete_scope_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_delete_scope_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── merge-scope ───────────────────────────────────────────────────────


def test_merge_scope_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_merge_scope_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_merge_scope_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-paragraph-after-line ────────────────────────────────────────


def test_split_paragraph_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_paragraph_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_paragraph_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-line-after-word ─────────────────────────────────────────────


def test_split_line_after_word_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_line_after_word_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_line_after_word_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-line-with-selected ──────────────────────────────────────────


def test_split_line_with_selected_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_line_with_selected_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_line_with_selected_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── group-into-paragraph ──────────────────────────────────────────────


def test_group_into_paragraph_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_group_into_paragraph_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_group_into_paragraph_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── set-line-gt helpers ───────────────────────────────────────────────────


@dataclass
class _StubWord:
    text: str = "ocr"
    ground_truth_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Word", "text": self.text, "ground_truth_text": self.ground_truth_text}


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"words": [w.to_dict() for w in self.words]}


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "stub"

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [ln.to_dict() for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=PageSource.OCR,
        payload=page,
    )
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[page_index] = pstate
    return pstate


def _make_two_word_line() -> _StubLine:
    return _StubLine(words=[_StubWord(text="hello"), _StubWord(text="world")])


# ── set-line-gt ───────────────────────────────────────────────────────────


def test_set_line_gt_returns_page_not_loaded_when_lift_is_stub(loaded_client: TestClient) -> None:
    """POST .../lines/0/set-gt returns 400 page_not_loaded while _resolve_page_object is a stub.

    Replaces 2 retired envelope-path tests (M5b). The set-gt endpoint calls
    _resolve_page_object which is a stub returning None — so the route returns
    page_not_loaded even when a PageState is seeded with a page object.

    Successor: tests/integration/test_words_router_page_store.py covers
    the new LocalPageStore-backed mutation cycle once the stub is replaced.
    """
    page = _StubPage(lines_=[_make_two_word_line()])
    _seed_page_state(loaded_client, page_index=0, page=page)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/set-gt",
        json={"text": "hello world"},
    )
    # Stub returns None → page_not_loaded (not 500)
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def test_set_line_gt_rejects_ligatures(bare_client: TestClient) -> None:
    """GT text containing ligature codepoints → 400 validation_error.

    The error handler converts ``RequestValidationError`` to 400
    (codebase convention — see ``api/middleware/error_handler.py:100``).
    """
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/set-gt",
        json={"text": "ﬀoo"},  # U+FB00 ff-ligature
    )
    assert resp.status_code in (400, 422)
    assert resp.json()["error"] == "validation_error"


def test_set_line_gt_404_unknown_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/no-such-project/pages/0/lines/0/set-gt",
        json={"text": "x"},
    )
    assert resp.status_code == 404
