"""Unit tests for ``POST .../words/{li}/{wi}/gt`` (spec-23-C1, issue #315).

Spec authority:
- ``specs/23-page-payload-backend.md §9`` — word-mutation endpoints,
  per-handler resolve → mutate → bump generation → cached-envelope write
  → refreshed PagePayload.
- ``specs/23-page-payload-backend.md §12`` — autosave + cached lane:
  every mutation writes the cached envelope, best-effort
  (``OSError`` logged not raised).
- ``specs/23-page-payload-backend.md §13`` — per-page locking.

The GT endpoint is the canonical pattern for the spec-23-C1 family
(GT / style / component / validated / validate-batch). The other four
endpoints share the same skeleton (lock → mutate → bump → cache-write →
refresh payload); their happy/error paths are exercised in
``tests/integration/test_words_router.py``.

Pattern (mirrors ``test_save_load.py``):

1. Seed a ``PageState`` with a stub Page exposing ``lines[li].words[wi]``
   and ``to_dict()``.
2. POST the mutation. Assert 200 + payload shape.
3. Assert ``Word.ground_truth_text`` reflects the new text.
4. Assert ``pstate.generation`` incremented.
5. Assert cached envelope file written to
   ``cache_root/page-images/<pid>_<page:03d>_envelope.json``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import cached_envelope_path
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings


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
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


# ── Stub Page / Line / Word ──────────────────────────────────────────


@dataclass
class _StubWord:
    """Minimal Word-like with the mutation surface the route uses.

    Carries the same attribute names the spec maps the route to:
    - ``ground_truth_text`` (settable for GT mutation).
    - ``apply_style_scope(style, scope)`` (style mutation; mirrors
      ``pd_book_tools.ocr.word.Word.apply_style_scope``).
    - ``apply_component(component, *, enabled)`` (component mutation;
      mirrors ``pd_book_tools.ocr.word.Word.apply_component``).
    - ``is_validated`` (per-instance attribute set by the handler;
      tracking issue ConcaveTrillion/pd-book-tools#52 for the proper
      ``Word.set_validated`` setter).
    """

    text: str = "ocr"
    ground_truth_text: str = ""
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    is_validated: bool = False

    def apply_style_scope(self, style: str, scope: str) -> bool:
        self.text_style_labels.append(style)
        return True

    def apply_component(self, component: str, *, enabled: bool) -> bool:
        if enabled and component not in self.word_components:
            self.word_components.append(component)
        elif (not enabled) and component in self.word_components:
            self.word_components.remove(component)
        return True

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
    """Minimal Page-stub exposing ``lines[li].words[wi]`` and ``to_dict()``.

    Built so the route can resolve the target word via
    ``page.lines[line_index].words[word_index]`` exactly as
    ``pd_book_tools.ocr.page.Page`` does.
    """

    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "stub"

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        # Mirrors the Page contract — validate-batch with scope=paragraph
        # walks ``page.paragraphs[pi].words``. For unit-test purposes
        # we treat each line as its own paragraph.
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


def _make_seeded_page() -> _StubPage:
    """A page with line 0 holding two words at indices 0, 1."""
    return _StubPage(
        lines_=[
            _StubLine(words=[_StubWord(text="hello"), _StubWord(text="world")]),
        ],
        label="seeded",
    )


# ── Loaded-project fixture (project + seeded PageState) ──────────────


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    """Inject a populated ``PageState`` for ``page_index`` and return it."""
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


# ── GT happy path ────────────────────────────────────────────────────


def test_update_word_gt_mutates_word_and_writes_cached_envelope(
    loaded_client: TestClient,
) -> None:
    """POST /gt: payload reflects, generation incremented, cache written.

    Asserts (per spec §9 + §12):
    - 200 response with PagePayload shape.
    - Underlying ``Word.ground_truth_text`` updated to body.text.
    - ``pstate.generation`` advanced by exactly 1.
    - Cached envelope file exists on disk at the spec'd path.
    """
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello-edited"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0
    # Generation field on PagePayload echoes ProjectState.generation
    # (not pstate.generation) — see api/pages.py:_page_payload.

    # Word mutation took effect.
    assert page.lines[0].words[0].ground_truth_text == "hello-edited"

    # PageState generation bumped exactly once.
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate_after = project_state.page_states[0]
    assert pstate_after.generation == gen_before + 1

    # Cached envelope written.
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    expected_cache = cached_envelope_path(settings.cache_root, "book1", 0)
    assert expected_cache.exists(), f"cached envelope not written: {expected_cache}"


def test_update_word_gt_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    """Without a seeded PageState, the handler can't resolve the word.

    Mirrors the save_page contract (#308): 400 ``page_not_loaded`` so
    the client knows to load/OCR first.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello-edited"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


def test_update_word_gt_returns_404_for_bad_word_index(
    loaded_client: TestClient,
) -> None:
    """Word-level 404 when (line_index, word_index) falls out of range."""
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/99/gt",
        json={"text": "oops"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "word_not_found"


def test_update_word_gt_returns_400_on_forbidden_codepoint(
    loaded_client: TestClient,
) -> None:
    """Pydantic validator still rejects ligature codepoints (issue #259)."""
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "ofﬁce"},  # U+FB01 fi ligature
    )
    assert resp.status_code == 422 or resp.status_code == 400, resp.text


def test_update_word_gt_cache_write_failure_does_not_break_response(
    loaded_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached-envelope write is best-effort (spec §12): on OSError, the
    handler logs and returns 200. The in-memory mutation must still stick.
    """
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    # Patch the LaneResolver.write_cached symbol the route imports.
    from pd_ocr_labeler_spa.core.persistence import lanes

    def _boom(self, page_index: int, envelope: object) -> None:
        raise OSError("simulated disk-full")

    monkeypatch.setattr(lanes.LaneResolver, "write_cached", _boom)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello-resilient"},
    )
    assert resp.status_code == 200, resp.text
    # Mutation still took effect.
    assert page.lines[0].words[0].ground_truth_text == "hello-resilient"
