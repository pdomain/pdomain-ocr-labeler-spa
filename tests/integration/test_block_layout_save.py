"""Integration test: paragraph layout_type round-trip (FO-1, CU-5).

Verifies that PATCH /api/projects/{id}/pages/{idx}/paragraphs/{pi} with
``layout_type`` persists the attribute on the in-memory paragraph object.

The GET /pages response does NOT currently surface ``layout_type`` on
``LineMatch`` (pdomain-book-tools' ``Block.to_dict`` doesn't serialise it yet
— documented as a round-trip limitation in ``api/lines_paragraphs.py``).
We therefore verify persistence directly via the ``pstate`` in-memory
object, and also confirm the PATCH returns 200 with the correct envelope
shape (project_id, page_index).
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

# ── Test scaffolding ──────────────────────────────────────────────────────────


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
    """TestClient with book1 loaded (2 pages)."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


# ── Minimal stubs — mirrors test_fo_backend_endpoints.py ─────────────────────


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
class _StubParagraph:
    """One paragraph containing one or more stub lines."""

    words: list[_StubWord] = field(default_factory=list)
    lines: list[Any] = field(default_factory=list)
    label: str = "para"


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)
    paragraphs_: list[_StubParagraph] = field(default_factory=list)
    label: str = "stub"

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubParagraph]:
        return self.paragraphs_

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
    """Inject a populated PageState into the running app (mirrors FO test helper)."""
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


# ── CU-5.1: PATCH layout_type round-trip ─────────────────────────────────────


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_patch_paragraph_layout_type_persists_to_memory(loaded_client: TestClient) -> None:
    """PATCH paragraphs/0 with layout_type='Heading' stores the attribute in memory.

    Acceptance: FO-1 / CU-5.1 — the in-memory paragraph object has
    ``layout_type == 'Heading'`` after the PATCH returns 200.
    """
    para = _StubParagraph(words=[_StubWord(text="some text")])
    page = _StubPage(
        lines_=[_StubLine(words=[_StubWord(text="some text")])],
        paragraphs_=[para],
        label="cu5test",
    )
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Heading"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # The PATCH handler stores layout_type as a plain attribute on the paragraph.
    assert getattr(para, "layout_type", None) == "Heading", (
        "layout_type should be stored on the paragraph object in memory"
    )


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_patch_paragraph_layout_type_updates_on_second_call(loaded_client: TestClient) -> None:
    """Two successive PATCHes leave only the last value on the paragraph."""
    para = _StubParagraph(words=[_StubWord(text="hello")])
    page = _StubPage(
        lines_=[_StubLine(words=[_StubWord(text="hello")])],
        paragraphs_=[para],
        label="cu5test2",
    )
    _seed_page_state(loaded_client, page_index=0, page=page)

    r1 = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Footnote"},
    )
    assert r1.status_code == 200
    assert getattr(para, "layout_type", None) == "Footnote"

    r2 = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Caption"},
    )
    assert r2.status_code == 200
    assert getattr(para, "layout_type", None) == "Caption"


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_patch_paragraph_returns_404_for_out_of_range_index(loaded_client: TestClient) -> None:
    """Paragraph index beyond range → 404 paragraph_not_found."""
    para = _StubParagraph(words=[_StubWord(text="hello")])
    page = _StubPage(
        lines_=[_StubLine(words=[_StubWord(text="hello")])],
        paragraphs_=[para],
        label="cu5test3",
    )
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/99",
        json={"layout_type": "Heading"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "paragraph_not_found"


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_patch_paragraph_bumps_generation(loaded_client: TestClient) -> None:
    """A successful PATCH increments PageState.generation."""
    para = _StubParagraph(words=[_StubWord(text="word")])
    page = _StubPage(
        lines_=[_StubLine(words=[_StubWord(text="word")])],
        paragraphs_=[para],
        label="cu5test4",
    )
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    initial_gen = pstate.generation

    loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Body"},
    )

    assert pstate.generation == initial_gen + 1
