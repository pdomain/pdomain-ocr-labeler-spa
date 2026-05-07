"""M2 slice 4 acceptance: ``api/projects.py`` router wires enumerator +
carrier + Settings into the public HTTP surface.

Spec authority:

- ``specs/02-backend.md §5.2`` lines 208-217 — endpoint contracts.
- ``specs/01-data-models.md §2`` lines 205-230 — wire shapes
  (``ListProjectsResponse``, ``ProjectKey``, ``LoadProjectRequest``,
  ``LoadProjectResponse``).
- ``specs/02-backend.md §13`` — startup discovery + the carrier
  semantics that ``POST /api/projects/load`` mutates.

What slice 4 ships under TDD:

1. ``GET /api/projects`` composes the pure ``enumerate_projects``
   scanner with the request-time ``Settings`` and the
   ``ActiveProjectCarrier`` so the response surfaces:
   - ``projects``: stable, sorted, deduped ``ProjectKey`` list
     (delegating ordering rules to the slice-4-starter scanner).
   - ``selected``: the currently active project's ``project_id`` if
     the carrier holds one AND it lives under the configured root.
   - ``projects_root``: the configured ``Settings.source_projects_root``
     (or a sentinel when unset — see ``test_get_no_root_configured``).
   - ``config_source``: provenance label — slice 4 ships ``"default"``
     unconditionally; M2-proper's ``POST /api/projects/source-root``
     will start tracking ``"yaml"`` / ``"cli"``.

2. ``POST /api/projects/load`` validates the requested ``project_root``
   is a real directory, then swaps the carrier and returns the new
   active-project key + the carrier's bumped ``generation``. The
   spec-canonical ``LoadProjectResponse`` is ``{project: Project,
   current_page: PagePayload}``; that requires the M2-proper Project
   graph + page persistence layer which don't exist yet, so slice 4
   ships an interim slim shape (``project_key`` + ``generation``)
   documented at the response model and the route docstring. The
   route name + URL stay spec-canonical so the M2-proper expansion
   is purely additive.

Slice 4 deliberately does NOT:

- Implement ``POST /api/projects/discover`` or
  ``POST /api/projects/source-root`` — both depend on the YAML
  config plumbing that lands in M2-proper.
- Implement ``GET /api/projects/{project_id}`` — needs the loaded
  ``Project`` graph (M2-proper).
- Write to ``session_state.json`` on successful load — the writer
  half (``save_session_state``) exists in
  ``core/persistence/session_state.py`` (iter 44) but the load
  endpoint's slim slice-4 shape doesn't yet include the
  page-payload step that the spec ties the session-write to. The
  M2-proper expansion will add it; pinning that here would force
  scope creep.

Test names follow the milestone convention: each pins one
spec-mandated behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """``Settings`` rooted at ``tmp_path`` for hermetic tests.

    ``mode="api_only"`` keeps the SPA fallback off so we don't need a
    populated ``static/`` bundle for these route tests.
    """
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
    """A pre-populated source_projects_root with three project dirs.

    Mix is deliberate: ``alpha`` / ``Beta`` / ``gamma`` exercises the
    case-fold sort. ``.hidden`` and ``regular_file.txt`` exercise the
    filter rules. Slice-4-starter's ``enumerate_projects`` already
    pins those rules in its own unit tests; here we just want a
    realistic input shape.
    """
    root = tmp_path / "projects"
    root.mkdir()
    (root / "alpha").mkdir()
    (root / "Beta").mkdir()
    (root / "gamma").mkdir()
    (root / ".hidden").mkdir()
    (root / "regular_file.txt").write_text("ignored")
    return root


@pytest.fixture
def client_with_root(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """``TestClient`` over an app whose Settings names ``projects_root``."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_root(tmp_path: Path) -> Iterator[TestClient]:
    """``TestClient`` over an app whose Settings has no projects_root."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────
# GET /api/projects
# ──────────────────────────────────────────────────────────────────────


def test_get_projects_lists_three_dirs_sorted_case_fold(
    client_with_root: TestClient,
) -> None:
    """Sort order = ``casefold`` of ``project_id`` (slice-4-starter rule)."""
    resp = client_with_root.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    ids = [p["project_id"] for p in body["projects"]]
    assert ids == ["alpha", "Beta", "gamma"]


def test_get_projects_skips_hidden_and_files(
    client_with_root: TestClient,
) -> None:
    """``.hidden`` and regular files don't appear in the response."""
    body = client_with_root.get("/api/projects").json()
    ids = {p["project_id"] for p in body["projects"]}
    assert ".hidden" not in ids
    assert "regular_file.txt" not in ids


def test_get_projects_returns_resolved_project_root(
    client_with_root: TestClient, projects_root: Path
) -> None:
    """``project_root`` field is the resolved absolute path of each entry."""
    body = client_with_root.get("/api/projects").json()
    alpha_entry = next(p for p in body["projects"] if p["project_id"] == "alpha")
    assert alpha_entry["project_root"] == str((projects_root / "alpha").resolve())


def test_get_projects_label_defaults_to_project_id(
    client_with_root: TestClient,
) -> None:
    """``label`` field defaults to ``project_id`` when no collision."""
    body = client_with_root.get("/api/projects").json()
    for p in body["projects"]:
        assert p["label"] == p["project_id"]


def test_get_projects_selected_none_when_carrier_empty(
    client_with_root: TestClient,
) -> None:
    """No active project loaded → ``selected: None``."""
    body = client_with_root.get("/api/projects").json()
    assert body["selected"] is None


def test_get_projects_projects_root_echoes_settings(
    client_with_root: TestClient, projects_root: Path
) -> None:
    """``projects_root`` reflects the configured Settings value."""
    body = client_with_root.get("/api/projects").json()
    assert body["projects_root"] == str(projects_root.resolve())


def test_get_projects_config_source_default(client_with_root: TestClient) -> None:
    """Slice 4 ships ``config_source: "default"`` unconditionally.

    M2-proper's ``POST /api/projects/source-root`` will start tracking
    ``"yaml"`` / ``"cli"`` once the YAML config plumbing lands.
    """
    body = client_with_root.get("/api/projects").json()
    assert body["config_source"] == "default"


def test_get_projects_no_root_configured_returns_empty_list(
    client_no_root: TestClient,
) -> None:
    """``source_projects_root=None`` → empty list, no error."""
    resp = client_no_root.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == []
    assert body["selected"] is None


def test_get_projects_after_load_marks_selected(client_with_root: TestClient, projects_root: Path) -> None:
    """After ``POST /load``, the next ``GET`` carries ``selected``=loaded id.

    Pins the round-trip wiring: load mutates the carrier, list reads it.
    """
    target = projects_root / "alpha"
    load_resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert load_resp.status_code == 200, load_resp.text

    body = client_with_root.get("/api/projects").json()
    assert body["selected"] == "alpha"


def test_get_projects_selected_omitted_if_loaded_outside_root(tmp_path: Path, projects_root: Path) -> None:
    """If the carrier holds a project NOT under ``source_projects_root``,
    ``selected`` is ``None`` — the dropdown can only mark entries it
    actually shows.
    """
    # Build an off-root project; preload it via cli_project_dir so the
    # carrier picks it up at lifespan-startup.
    off_root = tmp_path / "off_root_project"
    off_root.mkdir()
    settings = _make_settings(
        tmp_path,
        source_projects_root=projects_root,
        cli_project_dir=off_root,
    )
    app = build_app(settings)
    with TestClient(app) as c:
        body = c.get("/api/projects").json()
    assert body["selected"] is None


# ──────────────────────────────────────────────────────────────────────
# POST /api/projects/load
# ──────────────────────────────────────────────────────────────────────


def test_post_load_swaps_carrier_and_returns_key(client_with_root: TestClient, projects_root: Path) -> None:
    """Happy path: valid project_root → 200 + ProjectKey + generation."""
    target = projects_root / "alpha"
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_key"]["project_id"] == "alpha"
    assert body["project_key"]["project_root"] == str(target.resolve())
    assert body["project_key"]["label"] == "alpha"
    assert isinstance(body["generation"], int)
    assert body["generation"] >= 1


def test_post_load_increments_generation_on_repeat(client_with_root: TestClient, projects_root: Path) -> None:
    """Re-loading the same project bumps ``generation`` (every state
    change is observable; the carrier's contract from slice 2)."""
    target = projects_root / "alpha"
    body1 = client_with_root.post("/api/projects/load", json={"project_root": str(target)}).json()
    body2 = client_with_root.post("/api/projects/load", json={"project_root": str(target)}).json()
    assert body2["generation"] > body1["generation"]


def test_post_load_rejects_missing_dir(client_with_root: TestClient, projects_root: Path) -> None:
    """Non-existent path → 404 + structured error envelope."""
    target = projects_root / "does_not_exist"
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert resp.status_code == 404
    body = resp.json()
    # Spec §8 error envelope: {error: <tag>, message: <str>, details: ...}
    assert body["error"] == "project_not_found"


def test_post_load_rejects_regular_file(client_with_root: TestClient, projects_root: Path) -> None:
    """Path is a file, not a dir → 400 invalid_project_dir."""
    target = projects_root / "regular_file.txt"
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_project_dir"


def test_post_load_rejects_path_outside_source_root(client_with_root: TestClient, tmp_path: Path) -> None:
    """Path-traversal guard: project_root MUST be under source_projects_root.

    Spec §5.2 doesn't spell this out verbatim, but the legacy labeler
    only ever loads from inside the configured root, and accepting an
    arbitrary on-disk path would make the source_projects_root setting
    advisory rather than enforced. This is the conservative slice-4
    stance; M2-proper may relax it once the source-root setter exists.
    """
    outside = tmp_path / "rogue_project"
    outside.mkdir()
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(outside)},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "project_outside_source_root"


def test_post_load_rejects_when_no_source_root_configured(client_no_root: TestClient, tmp_path: Path) -> None:
    """Without a configured root, no path can be inside it → 400."""
    target = tmp_path / "any_project"
    target.mkdir()
    resp = client_no_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "project_outside_source_root"


def test_post_load_rejects_traversal_via_dotdot(client_with_root: TestClient, projects_root: Path) -> None:
    """``..`` segments resolve before the under-root check."""
    target = projects_root / "alpha" / ".." / ".." / "etc"
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    # Either project_not_found (resolved path doesn't exist) or
    # project_outside_source_root — both are correct refusals.
    assert resp.status_code in (400, 404)
    body = resp.json()
    assert body["error"] in (
        "project_not_found",
        "project_outside_source_root",
    )


def test_post_load_validation_error_on_missing_body_field(
    client_with_root: TestClient,
) -> None:
    """Missing ``project_root`` → 400 ``validation_error``.

    The repo's error_handler maps ``RequestValidationError`` to 400
    (spec §8 ``ApiError`` envelope with ``error="validation_error"``),
    not the FastAPI default 422 — pinning here so a future refactor of
    the error handler can't silently change the contract.
    """
    resp = client_with_root.post("/api/projects/load", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "validation_error"
