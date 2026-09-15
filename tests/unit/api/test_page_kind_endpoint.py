"""Unit tests for POST .../pages/{idx}/page-kind — confirming a page kind.

Pattern mirrors tests/unit/api/test_rematch_gt.py: seed a real Page into
PageState via project_state._page_states, then POST through a real TestClient.

A confirmed kind has to reach the event store, so the seeded PageState also
carries the ``page_id`` of a real ``PageAggregate`` written through the app's
own store — the same wiring ``run_ocr`` produces in production. The
``store_backed=False`` variant covers the page that has no such aggregate.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from starlette.datastructures import State

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState
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
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c


def _app_state(client: TestClient) -> State:
    """``client.app`` is typed as a bare ASGI callable; narrow it to the app."""
    app = client.app
    assert isinstance(app, FastAPI)
    return app.state


def _seed_page_state(
    client: TestClient, *, page_index: int, page: Page, store_backed: bool = True
) -> PageState:
    state = _app_state(client)
    project_state: ProjectState = state.project_state
    outcome = PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = 1
    if store_backed:
        store: LabelerPageStore = state.page_store
        aggregate = _ingest_ocr_result(
            page=page,
            image_bytes=b"\x89PNG\r\n",
            page_index=page_index,
            store=store,
            project=project_state.loaded_project,
        )
        pstate.page_id = aggregate.id
    project_state._page_states[page_index] = pstate
    return pstate


def test_confirming_a_page_kind_writes_it_and_marks_it_reviewed(
    loaded_client: TestClient, projects_root: Path
) -> None:
    page = Page(width=100, height=100, page_index=0, blocks=[])
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/page-kind",
        json={"kind": "title page", "note": "looks right"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extra"]["page_kind"] == "title page"
    assert body["extra"]["page_kind_reviewed"] is True
    assert page.page_kind is not None
    assert page.page_kind.value == "title page"
    assert pstate.generation == gen_before + 1

    reviewed = PageKindReviewedStore(projects_root / "book1").latest_for_page(0)
    assert reviewed is not None
    assert reviewed.note == "looks right"


def test_an_invalid_page_kind_is_rejected_by_body_validation(loaded_client: TestClient) -> None:
    """``kind`` is the ``PageKind`` enum, so pydantic rejects an unknown kind
    before the route body runs — the same path a bad ``role`` takes on the
    region routes. The app's ``RequestValidationError`` handler renders that
    as ``400 validation_error`` in the ``ApiError`` envelope.
    """
    page = Page(width=100, height=100, page_index=0, blocks=[])
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post("/api/projects/book1/pages/0/page-kind", json={"kind": "not-a-real-kind"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "validation_error"


def test_an_underscored_page_kind_is_normalized_to_the_canonical_spelling(
    loaded_client: TestClient,
) -> None:
    """``chapter_opening`` is the spelling a client echoes back from a
    proposal's ``evidence.page_class``; it has to land as the canonical
    ``PageKind.CHAPTER_OPENING`` rather than being rejected.
    """
    page = Page(width=100, height=100, page_index=0, blocks=[])
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post("/api/projects/book1/pages/0/page-kind", json={"kind": "chapter_opening"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["extra"]["page_kind"] == "chapter opening"
    assert page.page_kind is not None
    assert page.page_kind.value == "chapter opening"


def test_a_page_kind_that_cannot_be_persisted_is_refused_and_leaves_no_marker(
    loaded_client: TestClient, projects_root: Path
) -> None:
    """A page with no aggregate in the event store has nowhere to put the
    confirmed kind. Returning 200 there would leave a durable reviewed marker
    claiming a person confirmed a kind that was never stored, so the route
    refuses instead — and writes neither the kind nor the marker.
    """
    page = Page(width=100, height=100, page_index=0, blocks=[])
    pstate = _seed_page_state(loaded_client, page_index=0, page=page, store_backed=False)
    gen_before = pstate.generation

    resp = loaded_client.post("/api/projects/book1/pages/0/page-kind", json={"kind": "body"})

    assert resp.status_code == 503, resp.text
    assert resp.json()["error"] == "store_unavailable"
    assert page.page_kind is None
    assert pstate.generation == gen_before
    assert PageKindReviewedStore(projects_root / "book1").latest_for_page(0) is None


def test_confirming_a_page_kind_on_an_unloaded_page_returns_400(loaded_client: TestClient) -> None:
    resp = loaded_client.post("/api/projects/book1/pages/0/page-kind", json={"kind": "body"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"
