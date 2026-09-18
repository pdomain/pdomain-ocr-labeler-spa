"""Integration tests for glyph annotation routes — plan Task 2.

Covers the HTTP surface of M11 glyph review:

- ``POST .../words/{li}/{wi}/glyph-annotations`` (set / clear)
- ``POST .../words/{li}/{wi}/accept-prediction``
- ``POST .../pages/{idx}/glyph-bulk-mark`` (dry-run + apply)
- GT update still rejects raw ligature/long-s codepoints (spec §10)

Spec: ``specs/20-glyph-annotations.md`` §6.
Issue: ``docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md``.
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

# ── Stub page (in-session, no durable store needed) ─────────────────────────


@dataclass
class _StubBBox:
    minX: int = 0  # noqa: N815
    minY: int = 0  # noqa: N815
    maxX: int = 10  # noqa: N815
    maxY: int = 10  # noqa: N815


@dataclass
class _StubWord:
    text: str = "word"
    ground_truth_text: str = "word"
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    word_labels: list[str] = field(default_factory=list)
    is_validated: bool = False
    bounding_box: _StubBBox = field(default_factory=_StubBBox)


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[Any]:
        return []


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
    return root


def _seed_stub_page_state(client: TestClient, *, page: _StubPage) -> PageState:
    """Inject a populated in-session ``PageState`` (no durable store)."""
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[0] = pstate
    return pstate


@pytest.fixture
def seeded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with book1 loaded and page 0 seeded: line0 = ['victor', 'plain']."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        page = _StubPage(
            lines_=[
                _StubLine(
                    words=[
                        _StubWord(text="victor", ground_truth_text="victor"),
                        _StubWord(text="plain", ground_truth_text="plain"),
                    ]
                )
            ]
        )
        _seed_stub_page_state(c, page=page)
        yield c


def _word_match(body: dict[str, Any], *, line: int = 0, word: int = 0) -> dict[str, Any]:
    lm = body["line_matches"][line]
    wm: dict[str, Any] = lm["word_matches"][word]
    return wm


_CT_MARK = {
    "annotations": {
        "ligatures": [{"kind": "ct", "char_span": [2, 4]}],
        "long_s_positions": [],
        "swash": False,
        "source": "human",
    }
}


# ── set-glyph-annotations ────────────────────────────────────────────────


def test_set_glyph_annotations_ct_mark_visible_in_response(seeded_client: TestClient) -> None:
    """Setting a CT mark on word 0/0 is visible on the very same response."""
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/glyph-annotations",
        json=_CT_MARK,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    wm = _word_match(body)
    assert wm["glyph_annotations"] is not None
    assert wm["glyph_annotations"]["ligatures"][0]["kind"] == "ct"
    assert wm["glyph_annotations"]["source"] == "human"
    # Untouched sibling word stays unreviewed.
    assert _word_match(body, word=1)["glyph_annotations"] is None
    assert body["generation"] == 2  # bumped from the seeded generation=1


def test_set_glyph_annotations_null_clears_to_unreviewed(seeded_client: TestClient) -> None:
    """``annotations: null`` clears a previously-set mark back to 'not reviewed'."""
    first = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/glyph-annotations",
        json=_CT_MARK,
    )
    assert first.status_code == 200, first.text
    assert _word_match(first.json())["glyph_annotations"] is not None

    cleared = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/glyph-annotations",
        json={"annotations": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert _word_match(cleared.json())["glyph_annotations"] is None


# ── accept-prediction ─────────────────────────────────────────────────────


def test_accept_prediction_returns_400_when_no_predictions(seeded_client: TestClient) -> None:
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/accept-prediction",
        json={},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "no_predictions"


def test_accept_prediction_promotes_predictions_to_human_confirmed(seeded_client: TestClient) -> None:
    """Seeded ``glyph_predictions_map`` promotes to a human_confirmed annotation."""
    project_state = seeded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate = project_state.get_page_state(0)
    pstate.glyph_predictions_map["0_0"] = {
        "ligatures": [{"kind": "ct", "char_span": [2, 4]}],
        "long_s_positions": [],
        "swash": False,
        "source": "predicted",
    }

    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/accept-prediction",
        json={},
    )
    assert resp.status_code == 200, resp.text
    wm = _word_match(resp.json())
    assert wm["glyph_annotations"] is not None
    assert wm["glyph_annotations"]["source"] == "human_confirmed"
    assert wm["glyph_annotations"]["ligatures"][0]["kind"] == "ct"


# ── glyph-bulk-mark ────────────────────────────────────────────────────────


def test_glyph_bulk_mark_dry_run_returns_preview_without_mutating(seeded_client: TestClient) -> None:
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/glyph-bulk-mark",
        json={"recipe": "ct_substring", "dry_run": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["affected_word_ids"] == ["0_0"]
    assert body["skipped_word_ids"] == []
    assert body["page"] is None  # dry-run does not mutate or return a page

    # Confirm no mutation happened: a subsequent GET shows no annotations.
    follow_up = seeded_client.get("/api/projects/book1/pages/0")
    assert follow_up.status_code == 200, follow_up.text
    assert _word_match(follow_up.json())["glyph_annotations"] is None


def test_glyph_bulk_mark_apply_stamps_words_and_bumps_generation(seeded_client: TestClient) -> None:
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/glyph-bulk-mark",
        json={"recipe": "ct_substring", "dry_run": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["affected_word_ids"] == ["0_0"]
    assert body["page"] is not None
    wm = _word_match(body["page"])
    assert wm["glyph_annotations"] is not None
    assert wm["glyph_annotations"]["ligatures"][0]["kind"] == "ct"
    assert body["page"]["generation"] == 2  # bumped from the seeded generation=1


# ── GT update still rejects raw glyph codepoints (spec §10) ────────────────


def test_update_word_gt_rejects_ligature_codepoints(seeded_client: TestClient) -> None:
    """Spec §10: raw ligature codepoints in GT text get 400 ``validation_error``."""
    fi_ligature = chr(0xFB01)  # LATIN SMALL LIGATURE FI — via chr(), see below.
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": f"{fi_ligature}ction"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "validation_error"


def test_update_word_gt_rejects_long_s_codepoint(seeded_client: TestClient) -> None:
    long_s = chr(0x017F)  # LATIN SMALL LETTER LONG S — spelled via chr() to
    # avoid an ambiguous-unicode literal (RUF001) in the source file.
    resp = seeded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": f"plea{long_s}ure"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "validation_error"
