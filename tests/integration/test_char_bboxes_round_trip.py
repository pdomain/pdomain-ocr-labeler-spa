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


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_char_bboxes_round_trip(seeded_client: TestClient) -> None:
    """POST char-bboxes → GET page → word carries the posted char_bboxes.

    This is the primary CU-6.2 acceptance test: the per-char bbox data
    must survive in-memory and surface on ``WordMatch.char_bboxes`` in the
    next page GET without a server restart.
    """
    char_bboxes = [
        {"x": 0, "y": 0, "width": 5, "height": 10},
        {"x": 5, "y": 0, "width": 5, "height": 10},
    ]
    # 1. POST char-bboxes for word 0/0.
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": char_bboxes},
    )
    assert resp.status_code == 200, f"POST failed: {resp.text}"

    # 2. GET the page payload.
    page_resp = seeded_client.get("/api/projects/book1/pages/0")
    assert page_resp.status_code == 200, f"GET page failed: {page_resp.text}"
    payload = page_resp.json()

    # 3. Locate word 0 in line_matches[0].
    line_matches = payload.get("line_matches", [])
    assert len(line_matches) > 0, "Expected at least one line_match"
    line0 = next((lm for lm in line_matches if lm["line_index"] == 0), None)
    assert line0 is not None, f"line_index=0 not found in {line_matches}"

    word_matches = line0.get("word_matches", [])
    word0 = next((w for w in word_matches if w.get("word_index") == 0), None)
    assert word0 is not None, f"word_index=0 not found in {word_matches}"

    # 4. Assert char_bboxes present and correct.
    assert word0.get("char_bboxes") is not None, f"char_bboxes is None on word0; full word: {word0}"
    stored = word0["char_bboxes"]
    assert len(stored) == 2, f"expected 2 char_bboxes, got {len(stored)}"
    assert stored[0]["x"] == 0
    assert stored[0]["y"] == 0
    assert stored[0]["width"] == 5
    assert stored[0]["height"] == 10
    assert stored[1]["x"] == 5


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_char_bboxes_post_returns_updated_page(seeded_client: TestClient) -> None:
    """The POST response itself contains the updated page payload (no second GET needed).

    ``set_char_bboxes`` calls ``_refresh_payload_response`` — the returned
    body is a full ``PagePayload`` with the new char_bboxes already embedded.
    """
    char_bboxes = [{"x": 10, "y": 20, "width": 8, "height": 12}]
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": char_bboxes},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The response is a PagePayload — it must have line_matches.
    assert "line_matches" in body, f"POST response is not a PagePayload: {list(body)}"

    line0 = next((lm for lm in body["line_matches"] if lm["line_index"] == 0), None)
    assert line0 is not None
    word0 = next((w for w in line0["word_matches"] if w.get("word_index") == 0), None)
    assert word0 is not None
    stored = word0.get("char_bboxes")
    assert stored is not None and len(stored) == 1
    assert stored[0]["x"] == 10
    assert stored[0]["width"] == 8


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_char_bboxes_in_sidecar_map(seeded_client: TestClient) -> None:
    """POST char-bboxes writes directly to ``PageState.char_bboxes_map``.

    The sidecar map is the primary in-memory store; the GET response then
    threads it through the payload builder.
    """
    project_state = seeded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate = project_state.get_page_state(0)
    assert pstate is not None

    char_bboxes = [{"x": 3, "y": 7, "width": 4, "height": 9}]
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": char_bboxes},
    )
    assert resp.status_code == 200, resp.text

    # Check sidecar map directly — key is "{line_index}_{word_index}".
    stored = pstate.char_bboxes_map.get("0_0")
    assert stored is not None, f"char_bboxes_map missing '0_0'; map: {pstate.char_bboxes_map}"
    assert len(stored) == 1
    assert stored[0]["x"] == 3
    assert stored[0]["width"] == 4


@pytest.mark.skip(reason="envelope path retired in M5b; route wiring pending M9")
def test_char_bboxes_overwrite_replaces_previous(seeded_client: TestClient) -> None:
    """A second POST to char-bboxes replaces the first (not appends)."""
    first = [{"x": 0, "y": 0, "width": 5, "height": 10}]
    second = [
        {"x": 1, "y": 1, "width": 3, "height": 8},
        {"x": 4, "y": 1, "width": 3, "height": 8},
        {"x": 7, "y": 1, "width": 3, "height": 8},
    ]

    seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": first},
    )
    seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": second},
    )

    page_resp = seeded_client.get("/api/projects/book1/pages/0")
    payload = page_resp.json()
    line0 = next(lm for lm in payload["line_matches"] if lm["line_index"] == 0)
    word0 = next(w for w in line0["word_matches"] if w.get("word_index") == 0)

    stored = word0.get("char_bboxes", [])
    assert len(stored) == 3, f"expected 3 (second batch), got {len(stored)}: {stored}"
    assert stored[0]["x"] == 1
