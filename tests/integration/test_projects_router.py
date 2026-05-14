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


def test_post_load_swaps_carrier_and_returns_project(
    client_with_root: TestClient, projects_root: Path
) -> None:
    """Happy path (slice-5 shape): 200 + full ``Project`` + cursor + generation.

    Slice 5 replaced the slice-4 ``LoadProjectResponseStub`` with the
    real ``LoadProjectResponse{project, current_page_index, generation}``.
    The route also wires ``ProjectState.set_loaded_project`` so subsequent
    handlers can read the loaded model — that side of the contract is
    pinned by ``test_post_load_populates_project_state`` below; this
    test just pins the wire shape.

    A fresh source-lane project (no ``project.json``, no ``pages.json``,
    no images) yields an empty ``Project`` with ``total_pages=0`` and
    ``current_page_index=0``. Loading is still a successful operation
    — the route emits an empty-but-valid project, not an error. (The
    SPA's ``/page/0`` redirect target gracefully handles the empty case
    via a "no images" placeholder.)
    """
    target = projects_root / "alpha"
    resp = client_with_root.post(
        "/api/projects/load",
        json={"project_root": str(target)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Top-level shape (LoadProjectResponse).
    assert "project" in body
    assert "current_page_index" in body
    assert "generation" in body
    # The Project model carries the spec §1 fields.
    project = body["project"]
    assert project["project_id"] == "alpha"
    assert project["project_root"] == str(target.resolve())
    assert project["total_pages"] == 0  # empty fixture project
    assert project["image_paths"] == []
    assert project["ground_truth_map"] == {}
    assert project["current_page_index"] == 0
    assert body["current_page_index"] == 0
    assert isinstance(body["generation"], int)
    assert body["generation"] >= 1


def test_post_load_returns_project_with_images_and_ground_truth(
    tmp_path: Path,
) -> None:
    """A populated source-lane project surfaces its image_paths + GT.

    Slice 5 contract: when the project dir has images + ``pages.json``,
    the loaded ``Project`` carries them through verbatim. This is the
    integration pin of the ``ground_truth.py`` + ``project_envelope.py``
    composition.
    """
    import json as _json

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "real_book"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")
    (project_dir / "002.png").write_bytes(b"\x00")
    (project_dir / "pages.json").write_text(
        _json.dumps({"001.png": "first page text", "002.png": "second page text"}),
        encoding="utf-8",
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    project = body["project"]
    assert project["total_pages"] == 2
    assert [Path(p).name for p in project["image_paths"]] == ["001.png", "002.png"]
    # GT map: the original keys both survive (lowercase aliases also
    # populated, which the ground_truth tests pin separately).
    assert project["ground_truth_map"]["001.png"] == "first page text"
    assert project["ground_truth_map"]["002.png"] == "second page text"


def test_post_load_populates_project_state(
    tmp_path: Path,
) -> None:
    """Slice-5 wiring pin: ``ProjectState`` carries the loaded project.

    Loading must mutate ``app.state.project_state`` so subsequent
    handlers (M2-proper's ``GET /api/projects/{id}``, M3+ page routes)
    can read the loaded model. Pinned at the integration layer because
    the wiring crosses three boundaries (route → DI → state).
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "stateful_book"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
        assert resp.status_code == 200
    # Read directly from app.state to confirm the wire path mutated it.
    project_state = app.state.project_state
    assert project_state.loaded_project is not None
    assert project_state.loaded_project.project_id == "stateful_book"
    assert project_state.loaded_project.total_pages == 1
    assert project_state.current_page_index == 0
    assert project_state.generation >= 1


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


# ──────────────────────────────────────────────────────────────────────
# GET /api/projects/{project_id}  # noqa: ERA001  # section-separator comment, not commented-out code
# ──────────────────────────────────────────────────────────────────────
#
# Spec §02-backend.md line 220 — ``GET /api/projects/{project_id} →
# Project``. M2-proper read endpoint that returns the loaded ``Project``
# model from ``ProjectState``. No on-demand load: if no project is
# currently loaded, or if the requested ``project_id`` doesn't match
# the one held by ``ProjectState``, → ``404 project_not_found``.
#
# This is intentionally simpler than what the spec ultimately envisions
# (spec §00-overview.md line 193 — multi-project ``AppState`` with one
# ``ProjectState`` per project). The single-``ProjectState`` skeleton
# (slice-5 carrier) means "loaded project" and "addressable project"
# coincide for now; multi-project bookkeeping is deferred.


def test_get_project_by_id_returns_loaded_project(
    tmp_path: Path,
) -> None:
    """``GET /api/projects/{id}`` returns the loaded ``Project`` model.

    After a successful ``POST /api/projects/load``, the GET route must
    surface the same ``Project`` (by ``project_id``) that the load
    response carried. Pinned end-to-end so the route layer's read of
    ``ProjectState.loaded_project`` is exercised against a real
    persisted-shape project.
    """
    import json as _json

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "real_book"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")
    (project_dir / "002.png").write_bytes(b"\x00")
    (project_dir / "pages.json").write_text(
        _json.dumps({"001.png": "first", "002.png": "second"}),
        encoding="utf-8",
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
        assert load_resp.status_code == 200, load_resp.text
        loaded = load_resp.json()["project"]

        resp = c.get(f"/api/projects/{loaded['project_id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "real_book"
    assert body["total_pages"] == 2
    assert body["ground_truth_map"]["001.png"] == "first"


def test_get_project_by_id_404_when_nothing_loaded(
    client_with_root: TestClient,
) -> None:
    """No project loaded → ``404 project_not_found`` (spec §8 envelope).

    Asking for any id when ``ProjectState.loaded_project is None`` must
    return the canonical ``project_not_found`` tag, not a bare 404 nor
    a misleading ``no_project_loaded`` tag (the spec's ``ApiError`` tag
    set keeps ``project_not_found`` as the universal "we don't have
    that" answer for project-scoped routes).
    """
    resp = client_with_root.get("/api/projects/some_book")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "project_not_found"


def test_post_load_writes_session_state(
    tmp_path: Path,
) -> None:
    """``POST /api/projects/load`` persists ``session_state.json``.

    Spec §09-persistence.md §6 + §02-backend.md §5.2 line 217 ("Saves
    session state.") — on a successful load, the route writes
    ``<data_root>/session_state.json`` with the resolved project_root +
    current_page_index so a subsequent restart can resume.

    Pinned at the integration layer: route → save_session_state →
    on-disk JSON. The ``session_state.py`` unit tests pin the byte
    shape; this test only pins the wiring (file present, fields named
    per the spec, point at the project we just loaded).
    """
    import json as _json

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "alpha"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    data_root = tmp_path / "data"
    settings = _make_settings(
        tmp_path,
        source_projects_root=projects_root,
        data_root=data_root,
    )
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
        assert resp.status_code == 200, resp.text

    session_file = data_root / "session_state.json"
    assert session_file.exists(), f"session_state.json was not written under {data_root}"
    payload = _json.loads(session_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["last_project_path"] == str(project_dir.resolve())
    assert payload["last_page_index"] == 0


def test_post_load_session_state_save_error_does_not_fail_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If session-state write raises, the load request still succeeds.

    Session-state writeback is best-effort persistence: a failed write
    is operationally bad but must not turn a successful project load
    into an HTTP 500. The route logs the error and returns 200 with
    the loaded project; the SPA still gets a usable response.
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "alpha"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)

    # Patch the imported reference inside the route module.
    from pd_ocr_labeler_spa.api import projects as projects_mod

    def _boom(*_a: object, **_kw: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(projects_mod, "save_session_state", _boom)

    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["project"]["project_id"] == "alpha"


def test_get_project_by_id_404_when_id_mismatches_loaded(
    tmp_path: Path,
) -> None:
    """Loaded project_id != requested project_id → 404.

    The single-ProjectState carrier means we can address only the one
    loaded project; asking for a different id is the same case as
    "no project with that id is open" → ``project_not_found``.
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "alpha"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post("/api/projects/load", json={"project_root": str(project_dir)})
        assert load_resp.status_code == 200
        # Ask for a project_id we know isn't loaded.
        resp = c.get("/api/projects/different_book")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "project_not_found"


# ──────────────────────────────────────────────────────────────────────
# POST /api/projects/discover
# ──────────────────────────────────────────────────────────────────────
# Spec §5.2 line 218 — "Force re-scan." Returns the same shape as GET
# /api/projects but re-enumerates from disk on every call.


def test_post_discover_returns_list_projects_response(
    client_with_root: TestClient,
) -> None:
    """POST /api/projects/discover returns a ListProjectsResponse body."""
    resp = client_with_root.post("/api/projects/discover")
    assert resp.status_code == 200
    body = resp.json()
    assert "projects" in body
    assert "projects_root" in body
    assert "config_source" in body


def test_post_discover_lists_same_projects_as_get(
    client_with_root: TestClient,
) -> None:
    """POST /discover returns the same project list as GET /api/projects."""
    get_resp = client_with_root.get("/api/projects")
    post_resp = client_with_root.post("/api/projects/discover")
    assert get_resp.status_code == 200
    assert post_resp.status_code == 200
    assert get_resp.json()["projects"] == post_resp.json()["projects"]


def test_post_discover_picks_up_new_project_dir(
    tmp_path: Path,
    projects_root: Path,
) -> None:
    """POST /discover re-scans so a newly-added dir appears immediately."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        before = c.get("/api/projects").json()
        project_ids_before = {p["project_id"] for p in before["projects"]}

        # Add a new project dir after the app has started.
        (projects_root / "delta").mkdir()

        after = c.post("/api/projects/discover").json()
        project_ids_after = {p["project_id"] for p in after["projects"]}

    assert "delta" not in project_ids_before
    assert "delta" in project_ids_after


def test_post_discover_no_root_configured_returns_empty_list(
    client_no_root: TestClient,
) -> None:
    """POST /discover with no source_projects_root → empty list, 200."""
    resp = client_no_root.post("/api/projects/discover")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == []
