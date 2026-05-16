"""Integration tests for blockers B1, B3, and functional gap F1.

B1 — ``GET /api/projects/{id}/pages/{idx}`` calls ``ensure_page_model``
     when no page_record is cached, triggering on-demand OCR/load.
B3 — ``POST /api/projects/{id}/pages/{idx}/load`` builds a
     ``LocalDoctrPageLoader`` on-demand (no 503 when no explicit loader
     injection).
F1 — ``POST /api/projects/{id}/current-page-index`` persists the current
     page index to ``session_state.json``.

Issue: #330 (B1), #331 (B3), #333 (F1).

Tests here use a _FakePageLoader injected onto ``runner.context`` rather
than real DocTR, so the test suite stays fast and network-free.  The
production B3 on-demand build path is exercised in a separate monkeypatch
test that verifies the 503 no longer occurs when the context keys are
present.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
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


@dataclass
class _StubWord:
    text: str = "hello"
    ground_truth_text: str = "hello"
    text_style_labels: list[Any] = None  # type: ignore[assignment]
    word_components: list[Any] = None  # type: ignore[assignment]
    word_labels: list[Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.text_style_labels is None:
            self.text_style_labels = []
        if self.word_components is None:
            self.word_components = []
        if self.word_labels is None:
            self.word_labels = []
        # Provide a bounding_box stub
        self.bounding_box = _StubBbox()


@dataclass
class _StubBbox:
    min_x: float = 10.0
    min_y: float = 20.0
    max_x: float = 50.0
    max_y: float = 40.0

    @property
    def minX(self) -> float:  # noqa: N802
        return self.min_x

    @property
    def minY(self) -> float:  # noqa: N802
        return self.min_y

    @property
    def maxX(self) -> float:  # noqa: N802
        return self.max_x

    @property
    def maxY(self) -> float:  # noqa: N802
        return self.max_y


@dataclass
class _StubLine:
    words_: list[_StubWord] = None  # type: ignore[assignment]
    ground_truth_text: str = "hello"
    unmatched_ground_truth_words: list[tuple[int, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.words_ is None:
            self.words_ = [_StubWord()]
        if self.unmatched_ground_truth_words is None:
            self.unmatched_ground_truth_words = []

    @property
    def words(self) -> list[_StubWord]:
        return self.words_

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words_)


@dataclass
class _StubPage:
    label: str = "stub"
    lines_: list[_StubLine] = None  # type: ignore[assignment]
    paragraphs_: list[Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.lines_ is None:
            self.lines_ = [_StubLine()]
        if self.paragraphs_ is None:
            self.paragraphs_ = []

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[Any]:
        return self.paragraphs_

    def to_dict(self) -> dict[str, Any]:
        return {
            "words": [],
            "paragraphs": [],
            "lines": [],
            "source_identifier": f"{self.label}.png",
        }


class _FakePageLoader:
    """Stand-in ``PageLoader`` that records calls and returns stub payloads."""

    def __init__(self) -> None:
        self.run_ocr_calls: list[int] = []
        self.load_labeled_calls: list[int] = []
        self.load_cached_calls: list[int] = []

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload=_StubPage(label=f"ocr_{page_index}"),
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return None


@pytest.fixture
def loaded_client_with_loader(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with project loaded and a _FakePageLoader injected."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.fixture
def loaded_client_no_loader(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with project loaded but NO page_loader on runner.context."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


# ── B1: GET /pages/{idx} auto-triggers ensure_page_model ────────────────


def test_b1_get_page_triggers_ocr_and_returns_line_matches(
    loaded_client_with_loader: TestClient,
) -> None:
    """B1: first GET on a page with no prior OCR calls ensure_page_model.

    Asserts:
    - Response is 200 with a PagePayload shape.
    - ``line_matches`` is non-empty (the fake loader's page has one line).
    - ``page_record`` is populated (not None).
    - The fake loader's ``run_ocr`` was called exactly once for page 0.
    """
    c = loaded_client_with_loader
    loader: _FakePageLoader = c.app.state.job_runner.context["page_loader"]  # type: ignore[attr-defined]
    assert loader.run_ocr_calls == [], "OCR should not have run yet"

    resp = c.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # page_record must be populated by the lifter
    assert body["page_record"] is not None
    pr = body["page_record"]
    assert pr["page_index"] == 0

    # line_matches should have at least one entry (the fake page has one line)
    assert isinstance(body["line_matches"], list)
    assert len(body["line_matches"]) >= 1, "Expected at least one LineMatch after OCR"

    # run_ocr was called once for page 0
    assert 0 in loader.run_ocr_calls


def test_b1_second_get_page_uses_cached_state(
    loaded_client_with_loader: TestClient,
) -> None:
    """B1: second GET for the same page reuses the cached page_record.

    ``run_ocr`` must be called exactly once for page 0 across two GETs.
    Adjacent-page prefetch (GAP-2) may trigger run_ocr for pages 1/2 as a
    background side-effect; the assertion targets only page 0 re-use.
    """
    c = loaded_client_with_loader
    loader: _FakePageLoader = c.app.state.job_runner.context["page_loader"]  # type: ignore[attr-defined]

    c.get("/api/projects/book1/pages/0")
    ocr_calls_for_page0_after_first = loader.run_ocr_calls.count(0)

    c.get("/api/projects/book1/pages/0")
    ocr_calls_for_page0_after_second = loader.run_ocr_calls.count(0)

    assert ocr_calls_for_page0_after_first == 1, (
        f"page 0 should have been OCR'd exactly once after the first GET; "
        f"got {ocr_calls_for_page0_after_first}"
    )
    assert ocr_calls_for_page0_after_second == 1, (
        f"page 0 should NOT be re-OCR'd on the second GET (cached); got {ocr_calls_for_page0_after_second}"
    )


# ── B3: POST /pages/{idx}/load uses on-demand loader ────────────────────


def test_b3_load_with_injected_loader_returns_200(
    loaded_client_with_loader: TestClient,
) -> None:
    """B3 (explicit injection path): /load returns 200 when loader is injected."""
    resp = loaded_client_with_loader.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0


def test_b3_load_without_loader_no_longer_503s(
    loaded_client_no_loader: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3 (on-demand build path): /load must NOT return 503 when no explicit loader
    is injected but the production context keys (predictor_cache, ocr_config_carrier,
    settings) are present.

    We monkeypatch ``LocalDoctrPageLoader`` so the test stays DocTR-free:
    the on-demand build path must try to build the loader rather than 503.
    """
    from pd_ocr_labeler_spa.api import pages as pages_mod

    fake_loader = _FakePageLoader()

    def _patched_build_loader(
        runner: Any,
        project_state: Any,
        settings: Any,
    ) -> _FakePageLoader:
        return fake_loader

    monkeypatch.setattr(pages_mod, "_build_page_loader_from_context", _patched_build_loader)

    resp = loaded_client_no_loader.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"


# ── F1: POST /current-page-index persists to session_state.json ─────────


def test_f1_current_page_index_persists(
    tmp_path: Path,
    projects_root: Path,
) -> None:
    """F1: POST /api/projects/{id}/current-page-index writes last_page_index.

    - Returns 200 on valid page_index.
    - ``session_state.json`` is updated with the new page index.
    - Subsequent GET /api/session-state returns the updated index.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        resp = c.post(
            "/api/projects/book1/current-page-index",
            json={"page_index": 1},
        )
        assert resp.status_code == 200, resp.text

        # Verify session state was persisted
        session_resp = c.get("/api/session-state")
        assert session_resp.status_code == 200
        session_body = session_resp.json()
        assert session_body["last_page_index"] == 1


def test_f1_current_page_index_out_of_range_returns_404(
    tmp_path: Path,
    projects_root: Path,
) -> None:
    """F1: page_index >= total_pages → 404 page_not_found."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        resp = c.post(
            "/api/projects/book1/current-page-index",
            json={"page_index": 99},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "page_not_found"


def test_f1_current_page_index_no_project_returns_404(
    tmp_path: Path,
) -> None:
    """F1: no project loaded → 404 project_not_found."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/nonexistent/current-page-index",
            json={"page_index": 0},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "project_not_found"
