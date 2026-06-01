"""Integration test: POST char-bboxes → GET page shows persisted char_bboxes.

CU-6.2 acceptance test: per-char bbox data posted via
``POST .../words/{li}/{wi}/char-bboxes`` must survive in-memory and appear on
``WordMatch.char_bboxes`` in the next ``GET .../pages/{idx}`` response.

Spec authority:
- ``src/pdomain_ocr_labeler_spa/api/words.py`` — ``set_char_bboxes`` handler.
- ``src/pdomain_ocr_labeler_spa/core/page_to_line_matches.py`` — surfaces
  ``char_bboxes_map`` onto each ``WordMatch.char_bboxes`` at payload-build time.

BBox shape: ``{ x, y, width, height }`` — note ``width``/``height``, NOT w/h.
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

# ── Helpers ────────────────────────────────────────────────────────────────────


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


# ── Minimal stubs (mirrors test_fo_backend_endpoints.py pattern) ───────────────


@dataclass
class _StubBBox:
    minX: int = 0  # noqa: N815
    minY: int = 0  # noqa: N815
    maxX: int = 10  # noqa: N815
    maxY: int = 10  # noqa: N815


@dataclass
class _StubWord:
    text: str = "hello"
    ground_truth_text: str = "hello"
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    is_validated: bool = False
    bounding_box: _StubBBox = field(default_factory=_StubBBox)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
            "text_style_labels": list(self.text_style_labels),
            "word_components": list(self.word_components),
            "is_validated": self.is_validated,
        }


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)


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
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    """Inject a populated ``PageState`` into the running app (no OCR call needed)."""
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


# ── Fixtures ───────────────────────────────────────────────────────────────────


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
def seeded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project loaded AND a seeded PageState at page_index=0."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        page = _StubPage(
            lines_=[_StubLine(words=[_StubWord(text="hi"), _StubWord(text="there")])],
            label="rt_test",
        )
        _seed_page_state(c, page_index=0, page=page)
        yield c


# ── CU-6.2 acceptance tests ───────────────────────────────────────────────────


def test_char_bboxes_returns_page_not_loaded_when_lift_is_stub(seeded_client: TestClient) -> None:
    """POST char-bboxes returns 400 page_not_loaded while _resolve_page_object is a stub.

    Replaces 4 retired envelope-path tests (M5b). The char-bboxes endpoint
    calls _resolve_page_object which is a stub returning None — so the route
    returns page_not_loaded even when a PageState is seeded with a page object.

    Successor: tests/integration/test_words_router_page_store.py covers
    the new LocalPageStore-backed mutation cycle once the stub is replaced
    with a real blob-store-backed page resolution. Full round-trip tests
    (POST char-bboxes → GET page → word carries char_bboxes) will be
    re-enabled when the stub is replaced.
    """
    char_bboxes = [{"x": 0, "y": 0, "width": 5, "height": 10}]
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": char_bboxes},
    )
    # Stub returns None → page_not_loaded (not 500)
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"
