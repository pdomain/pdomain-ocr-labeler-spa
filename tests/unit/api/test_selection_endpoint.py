"""Unit tests for ``POST /api/projects/{id}/pages/{idx}/selection`` — spec-23-E.

Spec authority:
- ``specs/23-page-payload-backend.md §10`` — endpoint signature, body
  shape, ``apply_selection`` integration, generation bump, return shape.
- ``specs/23-page-payload-backend.md §13`` — per-page lock discipline.

Endpoint contract under test:

1. Body ``{mode: "replace"|"remove"|"toggle", selection: Selection}``.
2. ``pstate.selection = apply_selection(pstate.selection, mode, body.selection)``.
3. ``pstate.generation += 1``.
4. Returns the spec-23-A populated ``PagePayload`` with the **updated**
   selection echoed on ``payload.selection``.
5. 404 ``project_not_found`` on missing project; 404 ``page_not_found``
   on out-of-range page index.
6. Works even when no ``PageState`` exists yet (selection is a UI
   carrier — does not require OCR to have run).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings

TINY_FIXTURE = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "projects" / "tiny-fixture"


def _make_settings(tmp_path: Path, source_projects_root: Path | None = None) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=source_projects_root,
    )


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "tiny-fixture"
    proj.mkdir()
    for src in sorted(TINY_FIXTURE.glob("*.png")):
        (proj / src.name).write_bytes(src.read_bytes())
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "tiny-fixture")},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _project_state(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.project_state  # type: ignore[attr-defined]


# ── replace ──────────────────────────────────────────────────────────────


def test_replace_sets_selection_and_bumps_generation(loaded_client: TestClient) -> None:
    ps = _project_state(loaded_client)
    gen_before = ps.get_page_state(0).generation if ps.get_page_state(0) is not None else 0

    body = {
        "mode": "replace",
        "selection": {
            "selection_mode": "word",
            "selected_paragraphs": [],
            "selected_lines": [3],
            "selected_words": [[0, 1], [2, 4]],
        },
    }
    resp = loaded_client.post("/api/projects/tiny-fixture/pages/0/selection", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    sel = payload["selection"]
    assert sel["selection_mode"] == "word"
    assert sorted(sel["selected_lines"]) == [3]
    # Lists-of-lists over JSON; compare as sorted tuples.
    word_pairs = sorted(tuple(w) for w in sel["selected_words"])
    assert word_pairs == [(0, 1), (2, 4)]

    pstate = ps.get_page_state(0)
    assert pstate is not None
    assert pstate.selection.selected_words == {(0, 1), (2, 4)}
    assert pstate.selection.selected_lines == {3}
    assert pstate.generation == gen_before + 1


# ── remove (set-difference) ──────────────────────────────────────────────


def test_remove_subtracts_from_existing_selection(loaded_client: TestClient) -> None:
    # Seed an initial selection via a replace call.
    loaded_client.post(
        "/api/projects/tiny-fixture/pages/0/selection",
        json={
            "mode": "replace",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [[0, 0], [0, 1], [1, 0]],
            },
        },
    )
    pstate = _project_state(loaded_client).get_page_state(0)
    assert pstate is not None
    gen_after_seed = pstate.generation

    # Now remove a subset.
    resp = loaded_client.post(
        "/api/projects/tiny-fixture/pages/0/selection",
        json={
            "mode": "remove",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [[0, 1], [9, 9]],  # (9,9) is a no-op
            },
        },
    )
    assert resp.status_code == 200, resp.text

    assert pstate.selection.selected_words == {(0, 0), (1, 0)}
    assert pstate.generation == gen_after_seed + 1


# ── toggle (symmetric-difference) ────────────────────────────────────────


def test_toggle_flips_membership(loaded_client: TestClient) -> None:
    # Seed selection {(0,0), (0,1)}.
    loaded_client.post(
        "/api/projects/tiny-fixture/pages/0/selection",
        json={
            "mode": "replace",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [[0, 0], [0, 1]],
            },
        },
    )
    # Toggle with {(0,1), (1,0)} -> {(0,0), (1,0)}.
    resp = loaded_client.post(
        "/api/projects/tiny-fixture/pages/0/selection",
        json={
            "mode": "toggle",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [[0, 1], [1, 0]],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    pstate = _project_state(loaded_client).get_page_state(0)
    assert pstate is not None
    assert pstate.selection.selected_words == {(0, 0), (1, 0)}


# ── pre-load (no PageState yet) ──────────────────────────────────────────


def test_selection_works_before_page_loaded(loaded_client: TestClient) -> None:
    """Selection is UI state — must work before OCR has run.

    Asserts the endpoint auto-creates a ``PageState`` carrier on first
    use and stores the selection on it.
    """
    ps = _project_state(loaded_client)
    assert ps.get_page_state(1) is None  # never touched

    resp = loaded_client.post(
        "/api/projects/tiny-fixture/pages/1/selection",
        json={
            "mode": "replace",
            "selection": {
                "selection_mode": "line",
                "selected_paragraphs": [],
                "selected_lines": [7],
                "selected_words": [],
            },
        },
    )
    assert resp.status_code == 200, resp.text

    pstate = ps.get_page_state(1)
    assert pstate is not None
    assert isinstance(pstate, PageState)
    assert pstate.selection.selected_lines == {7}
    assert pstate.selection.selection_mode == "line"


# ── errors ───────────────────────────────────────────────────────────────


def test_unknown_project_returns_404(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/does-not-exist/pages/0/selection",
        json={
            "mode": "replace",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [],
            },
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_page_index_out_of_range_returns_404(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/tiny-fixture/pages/99/selection",
        json={
            "mode": "replace",
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [],
            },
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_invalid_mode_is_rejected(loaded_client: TestClient) -> None:
    """Pydantic literal validation — unknown modes never reach the route.

    The repo's validation-error middleware converts FastAPI's 422 into a
    400 ``ApiError`` envelope (see ``api/middleware/error_handler.py``);
    the route never sees an ``"intersect"`` value.
    """
    resp = loaded_client.post(
        "/api/projects/tiny-fixture/pages/0/selection",
        json={
            "mode": "intersect",  # not in Literal[...]
            "selection": {
                "selection_mode": "word",
                "selected_paragraphs": [],
                "selected_lines": [],
                "selected_words": [],
            },
        },
    )
    assert resp.status_code in (400, 422)
