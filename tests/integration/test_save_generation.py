"""BUG-SMOKE-2 regression: GET /pages returns project-level generation; save checks page-level.

Covers: B-ACTIONS-019, F-SAVE-LOAD-ROUNDTRIP-01

Root cause: ``_page_payload`` stamped ``generation=project_state.generation``
(the project-level monotone counter, e.g. 4 after load+nav) while
``save_page`` validated ``body.generation == pstate.generation`` (the
page-level counter, starts at 0 until a mutation bumps it).

This meant every fresh save attempt after loading a page returned 409
``generation_mismatch`` — the frontend got generation=4 from GET, sent 4
on save, but the server had pstate.generation==0.

Fix: ``_page_payload`` must stamp ``pstate.generation`` (page-level) so
the GET response value matches what ``save_page`` validates against.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.user_page_envelope import (
    UserPageEnvelope,
    UserPagePayload,
)
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


def _seed_page_state_with_envelope(
    client: TestClient,
    *,
    page_index: int,
    page_generation: int = 0,
) -> None:
    """Inject a minimal ``PageState`` so save_page has something to persist.

    Uses a ``UserPageEnvelope`` as the payload (mimicking labeled lane).
    ``persist_page_to_file`` is not called — save is mocked to succeed if
    the generation check passes. We need a non-None page_record so the
    page_not_loaded guard does not trigger.
    """
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    page_dict: dict[str, Any] = {
        "lines": [],
        "paragraphs": [],
        "words": [],
        "source_identifier": "001.png",
        "image_path": "",
    }
    envelope = UserPageEnvelope(
        payload=UserPagePayload(page=page_dict),
    )
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=PageSource.FILESYSTEM,
        payload=envelope,
    )
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = page_generation
    pstate.last_saved_generation = page_generation
    project_state._page_states[page_index] = pstate


# ── The regression test ────────────────────────────────────────────────────


def test_save_page_with_generation_from_get_succeeds(
    loaded_client: TestClient,
    tmp_path: Path,
    projects_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save with the generation returned by GET should not 409.

    BUG-SMOKE-2: before the fix, GET returned project-level generation
    (e.g. 4) but save_page checked pstate.generation (0) → 409.

    We monkeypatch ``persist_page_to_file`` to avoid needing a real Page
    object (the envelope payload is not a ``Page`` with ``to_dict``).
    The generation alignment is the behaviour under test.
    """
    import pdomain_ocr_labeler_spa.api.pages as pages_mod

    monkeypatch.setattr(pages_mod, "persist_page_to_file", lambda **_kw: None)

    # Seed page 0 with page-level generation == 0 (fresh, unmodified).
    _seed_page_state_with_envelope(loaded_client, page_index=0, page_generation=0)

    # GET the page — capture the generation field the server returns.
    page_resp = loaded_client.get("/api/projects/book1/pages/0")
    assert page_resp.status_code == 200, page_resp.text
    generation = page_resp.json().get("generation", -999)

    # Save with exactly the generation the GET returned.
    save_resp = loaded_client.post(
        "/api/projects/book1/pages/0/save",
        json={"generation": generation},
    )
    assert save_resp.status_code == 200, (
        f"Expected 200 but got {save_resp.status_code}: {save_resp.text}\n"
        f"generation from GET was {generation!r}.\n"
        "BUG-SMOKE-2: _page_payload must stamp pstate.generation, not project_state.generation."
    )
    assert save_resp.json()["saved"] is True


def test_save_page_with_stale_generation_still_409(
    loaded_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generation guard must still reject genuinely stale generations.

    This confirms the fix only aligns the counters; it doesn't disable the
    conflict-detection guard. After a mutation bumps pstate.generation,
    a save with the pre-mutation generation must still 409.
    """
    import pdomain_ocr_labeler_spa.api.pages as pages_mod

    monkeypatch.setattr(pages_mod, "persist_page_to_file", lambda **_kw: None)

    # Seed page 0 with page-level generation == 3 (post some mutations).
    _seed_page_state_with_envelope(loaded_client, page_index=0, page_generation=3)

    # Attempt save with a deliberately wrong generation.
    save_resp = loaded_client.post(
        "/api/projects/book1/pages/0/save",
        json={"generation": 99},
    )
    assert save_resp.status_code == 409, (
        f"Expected 409 for stale generation but got {save_resp.status_code}: {save_resp.text}"
    )
    assert save_resp.json()["error"] == "generation_mismatch"


def test_save_page_without_generation_always_succeeds(
    loaded_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the ``generation`` field bypasses the conflict check.

    The spec says ``generation`` is optional — when absent, save proceeds
    unconditionally (frontend can opt out of conflict detection).
    This must still work after the counter-alignment fix.
    """
    import pdomain_ocr_labeler_spa.api.pages as pages_mod

    monkeypatch.setattr(pages_mod, "persist_page_to_file", lambda **_kw: None)

    _seed_page_state_with_envelope(loaded_client, page_index=0, page_generation=7)

    save_resp = loaded_client.post(
        "/api/projects/book1/pages/0/save",
        json={},
    )
    assert save_resp.status_code == 200, (
        f"Expected 200 when generation omitted but got {save_resp.status_code}: {save_resp.text}"
    )
    assert save_resp.json()["saved"] is True
