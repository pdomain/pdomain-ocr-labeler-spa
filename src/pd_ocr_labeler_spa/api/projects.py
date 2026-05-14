"""``/api/projects`` router — list + load.

Spec authority:

- ``specs/02-backend.md §5.2`` lines 208-217 — endpoint contracts.
- ``specs/01-data-models.md §2`` lines 205-230 — wire shapes
  (``ListProjectsResponse``, ``ProjectKey``, ``LoadProjectRequest``,
  ``LoadProjectResponse``).
- ``specs/02-backend.md §13`` — the carrier semantics that
  ``POST /api/projects/load`` mutates.
- ``specs/02-backend.md §8`` — uniform error envelope (``ApiError``,
  ``{error: <tag>, message: <str>, details: <any>}``); flat shape, not
  nested under ``error.code``.

What this slice (M2 slice 5) ships ON TOP OF slice 4:

1. ``GET /api/projects`` (unchanged from slice 4) — composes the pure
   ``enumerate_projects`` scanner with the request-time ``Settings``
   and the ``ActiveProjectCarrier``.

2. ``POST /api/projects/load`` (UPGRADED): now reads ``pages.json`` /
   ``pages_manifest.json``, scans the project dir for image files, and
   reads optional ``project.json`` to construct a full ``Project``
   model. The model is then stashed on ``ProjectState`` so subsequent
   read endpoints (M2-proper's ``GET /api/projects/{id}``, M3+ page
   routes) can return real data. The slice-4 ``LoadProjectResponseStub``
   is replaced by ``LoadProjectResponse{project, current_page_index}``.

What this iter (M2-proper tail) ships ON TOP OF slice 5:

3. ``GET /api/projects/{project_id}`` — read-only handler that returns
   the ``Project`` currently held by ``ProjectState``. No on-demand
   load: if no project is open or the requested id doesn't match the
   loaded one, ``404 project_not_found``.

What this layer deliberately does NOT do (deferred):

- ``POST /api/projects/discover`` and ``POST /api/projects/source-root``
  — both depend on YAML config plumbing (M2-proper config milestone).
- The full spec-canonical ``LoadProjectResponse`` shape with
  ``current_page: PagePayload`` per spec §1 lines 221-223. ``PagePayload``
  bundles ``PageRecord`` + ``EncodedDims`` + ``LineMatch[]`` + image
  URLs which require the M3 OCR/page-cache plumbing
  (``ensure_page_model``, image cache, encode dims). Slice 5 ships
  ``current_page_index: int`` instead — the same URL stays stable;
  M3 will additively expand the response field name + type when the
  ``PagePayload`` model exists. The interim ``int`` is enough for the
  SPA to URL-redirect to ``/page/{idx0+1}`` per spec §URL.
- Writing ``session_state.json`` on successful load — also tied to
  the page-payload step (M3) since the writer needs the resolved
  page index.
- ``config_source`` provenance: slice 4 emits ``"default"``
  unconditionally; YAML/CLI source tracking lands with
  ``POST /api/projects/source-root`` in M2-proper.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.active_project import ActiveProjectCarrier, InvalidProjectDirError
from ..core.jobs import JobRunner
from ..core.models import Project
from ..core.ocr_models import AutoRotateAllRequest
from ..core.persistence.config_yaml import AppConfig, save_config
from ..core.persistence.ground_truth import load_ground_truth_from_directory
from ..core.persistence.project_envelope import build_project_from_directory
from ..core.persistence.session_state import (
    SESSION_STATE_SCHEMA_VERSION,
    SessionState,
    save_session_state,
)
from ..core.project_enumeration import enumerate_projects
from ..core.project_state import ProjectState
from ..core.source_root_state import SourceRootCarrier
from ..settings import Settings
from .dependencies import (
    get_active_project_carrier,
    get_job_runner,
    get_project_state,
    get_settings,
    get_source_root_carrier,
)
from .middleware.error_handler import ApiError
from .pages import SaveProjectResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ──────────────────────────────────────────────────────────────────────
# Wire shapes
# ──────────────────────────────────────────────────────────────────────


class ProjectKey(BaseModel):
    """One discoverable project. Spec §2 lines 212-216.

    Mirrors ``core.project_enumeration.EnumeratedProject`` but with
    ``Path`` rendered as a string in JSON (FastAPI's default).
    """

    project_id: str
    project_root: Path
    label: str


class ListProjectsResponse(BaseModel):
    """Spec §2 lines 206-210.

    - ``projects``: stable, sorted, deduped list per slice-4-starter.
    - ``selected``: ``project_id`` of the active project IF it lives
      under ``projects_root``; else ``None`` (the dropdown can only
      mark entries it actually shows).
    - ``projects_root``: the resolved root, or a sentinel empty path
      when ``Settings.source_projects_root is None``. The SPA's
      project-load controls render the un-configured case as "no
      source folder set" — sentinel ``Path("")`` keeps the response
      schema-compatible with the spec without an Optional field.
    - ``config_source``: provenance label. Slice 4 always emits
      ``"default"``; M2-proper's ``POST /api/projects/source-root``
      will flip it to ``"yaml"`` / ``"cli"``.
    """

    projects: list[ProjectKey]
    selected: str | None
    projects_root: Path
    config_source: Literal["yaml", "cli", "default"]


class LoadProjectRequest(BaseModel):
    """Spec §2 lines 217-219.

    ``initial_page_index`` defaults to 0; M2-proper's expanded handler
    will use it to seed the first page. Slice 4 accepts the field so
    the wire schema stays stable, but ignores it (no page graph yet).
    """

    project_root: Path
    initial_page_index: int = 0


class SetSourceProjectsRootRequest(BaseModel):
    """Body for ``POST /api/projects/source-root`` — spec §2 line 230."""

    path: Path


class SetSourceProjectsRootResponse(BaseModel):
    """Response for ``POST /api/projects/source-root`` — spec §2 lines 232-234."""

    projects_root: Path
    projects: list[ProjectKey]


class LoadProjectResponse(BaseModel):
    """M2 slice-5 response — interim shape on the path to spec-canonical.

    Spec-canonical (``§01-data-models.md`` lines 221-223) is::

        class LoadProjectResponse(BaseModel):
            project: Project
            current_page: PagePayload

    ``PagePayload`` (``§01-data-models.md`` lines 236-244) bundles
    ``PageRecord`` + ``EncodedDims`` + ``LineMatch[]`` + image-cache
    URLs — none of which exist yet (those models land in M3 with the
    OCR / page-cache / encode-dims plumbing).

    Slice 5 ships ``current_page_index: int`` in place of
    ``current_page: PagePayload``. Why this is acceptable scope:

    - The route name + URL stay spec-canonical (purely additive
      expansion in M3).
    - The carrier swap, project-state mutation, and ``Project``
      construction are all real — no stub data.
    - The SPA only needs the index right now to redirect to
      ``/page/{idx0+1}``; the rich ``PagePayload`` is a follow-up
      fetch via ``GET /api/projects/{id}/pages/{idx}`` in M3.

    M3 will rename ``current_page_index`` → ``current_page`` and
    swap ``int`` → ``PagePayload`` simultaneously when the page-payload
    plumbing is in place. The TS generator pins on field name + type,
    so a renamed field IS a breaking client change — the SPA will be
    updated in the same M3 milestone.

    ``generation`` mirrors slice 4's stub semantics: the
    ``ProjectState.generation`` counter AFTER the swap, so the SPA can
    distinguish "I just loaded X" from "someone else loaded X 2
    generations ago" once SSE lands.

    Fields:

    - ``project``: the loaded ``Project`` model — full image_paths +
      ground_truth_map + persisted-metadata.
    - ``current_page_index``: the 0-based cursor (clamped + seeded
      from ``project.json`` if previously saved).
    - ``generation``: the ``ProjectState.generation`` counter AFTER
      this load. Increments by ≥1 on every successful load.
    """

    project: Project
    current_page_index: int
    generation: int


# ──────────────────────────────────────────────────────────────────────
# Helpers — the pure logic kept out of route bodies for testability
# ──────────────────────────────────────────────────────────────────────


def _api_error(status_code: int, error: str, message: str, details: object = None) -> JSONResponse:
    """Emit the spec §8 envelope from a route handler.

    Routes can't raise ``HTTPException`` for these because the
    framework's ``StarletteHTTPException`` handler turns the error tag
    into ``http_<status>`` — losing the spec-mandated tags
    (``project_not_found``, ``invalid_project_dir`` etc.) that the SPA
    toast layer keys on. So we build the envelope ourselves.
    """
    return JSONResponse(
        status_code=status_code,
        content=ApiError(error=error, message=message, details=details).model_dump(),
    )


def _is_under_root(candidate: Path, root: Path) -> bool:
    """True iff ``candidate`` resolves to a path under ``root``.

    Both are ``Path.resolve()``-d before comparison so ``..`` segments
    and symlink chains are normalized — a request body of
    ``/projects/alpha/../../etc`` is rejected here, not silently
    accepted as an "alpha" sibling.

    Returns False when ``candidate == root`` — the root itself is not
    a project, and the legacy labeler never loaded the root as a
    project either.
    """
    try:
        candidate_resolved = candidate.resolve()
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return False
    if candidate_resolved == root_resolved:
        return False
    return root_resolved in candidate_resolved.parents


# ──────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────


def _build_list_response(
    effective_root: Path | None,
    carrier: ActiveProjectCarrier,
    config_source: str = "default",
) -> ListProjectsResponse:
    """Shared scan-and-build helper for GET /api/projects + POST /discover.

    Separated so both routes and ``POST /source-root`` can return a
    consistent ``ListProjectsResponse`` without duplicating the
    enumeration + selection logic.
    """
    enumerated = enumerate_projects(effective_root)
    projects = [
        ProjectKey(
            project_id=p.project_id,
            project_root=p.project_root,
            label=p.label,
        )
        for p in enumerated
    ]

    selected: str | None = None
    snap = carrier.snapshot()
    if snap is not None and effective_root is not None and _is_under_root(snap.path, effective_root):
        snap_resolved = snap.path.resolve()
        for p in enumerated:
            if p.project_root == snap_resolved:
                selected = p.project_id
                break

    projects_root = effective_root.resolve() if effective_root is not None else Path("")

    return ListProjectsResponse(
        projects=projects,
        selected=selected,
        projects_root=projects_root,
        config_source=config_source,  # type: ignore[arg-type]
    )


# ──────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────


@router.get("", response_model=ListProjectsResponse)
def list_projects(
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    src_carrier: SourceRootCarrier = Depends(get_source_root_carrier),
) -> ListProjectsResponse:
    """``GET /api/projects`` — enumerate + describe selection state.

    Spec §5.2 lines 208-211. Pure read; never mutates the carrier.

    The effective root comes from ``SourceRootCarrier`` (which is seeded
    at boot from CLI/env ``Settings.source_projects_root`` and can be
    updated at runtime by ``POST /api/projects/source-root``). This
    ensures a call to ``POST /source-root`` is immediately visible in
    the next ``GET /api/projects`` within the same process.
    """
    return _build_list_response(src_carrier.get(), carrier)


@router.post("/discover", response_model=ListProjectsResponse)
def discover_projects(
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    src_carrier: SourceRootCarrier = Depends(get_source_root_carrier),
) -> ListProjectsResponse:
    """``POST /api/projects/discover`` — force re-scan of the projects root.

    Spec §5.2 line 218 — "Force re-scan." Identical logic to
    ``GET /api/projects`` but registered as a POST so clients can
    explicitly trigger a refresh without relying on HTTP caching semantics
    (some proxies cache GET responses; a POST is always forwarded).

    Returns the same ``ListProjectsResponse`` shape as the GET endpoint.
    No body is required or accepted.
    """
    return _build_list_response(src_carrier.get(), carrier)


@router.post("/load")
def load_project(
    body: LoadProjectRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    project_state: ProjectState = Depends(get_project_state),
    src_carrier: SourceRootCarrier = Depends(get_source_root_carrier),
) -> JSONResponse:
    """``POST /api/projects/load`` — validate path, swap carrier.

    Validation order (cheapest-first; the order is observable via the
    error tag returned):

    1. Source root configured. If
       ``settings.source_projects_root is None``, no path can be
       "under it" → ``400 project_outside_source_root``.
    2. Path is under source root. ``_is_under_root`` resolves both
       paths, so ``..`` traversal is rejected here. → either
       ``400 project_outside_source_root`` (resolved path is outside)
       or ``404 project_not_found`` (resolved path doesn't exist —
       ``resolve()`` succeeded but the dir is gone).
    3. Path is a directory. We reach this only after the under-root
       check passed AND the path resolves; if it's a regular file
       (e.g. someone POSTed ``regular_file.txt``) → ``400
       invalid_project_dir``.
    4. Carrier swap via ``set_active_project``. The carrier
       re-validates internally — defensive belt-and-suspenders for the
       TOCTOU race where the dir vanished between our ``is_dir()`` and
       the carrier's. On rare TOCTOU, we surface ``404
       project_not_found`` (operator-actionable label, same shape the
       lifespan hook uses for the same race in slice 3).

    Slice 5 (this iter) extends slice 4 to also:

    - Build the full ``Project`` model from disk (``pages.json`` /
      ``pages_manifest.json`` ground truth + image-file scan +
      optional ``project.json`` saved metadata) via
      ``build_project_from_directory``.
    - Stash the model on ``ProjectState`` via ``set_loaded_project``.
    - Return a ``LoadProjectResponse{project, current_page_index, generation}``
      response (replacing the slice-4 ``LoadProjectResponseStub``).

    Session-state writeback is still omitted in slice 5: the
    ``save_session_state`` call wants to record both the project path
    AND the page index that the SPA actually displayed. Slice 5 stops
    short of the page-payload step (M3 territory: real OCR / image
    cache / encode dims), so the index we'd record is just whatever
    ``build_project_from_directory`` clamped — accurate, but the spec
    intentionally bundles session-state with the page-payload step.
    M3 will land both.
    """
    target = body.project_root
    # Use the runtime-effective root (may have been updated by POST /source-root).
    effective_root = src_carrier.get()

    # Step 1: source root configured?
    if effective_root is None:
        return _api_error(
            400,
            "project_outside_source_root",
            "no source_projects_root configured; cannot load any project",
        )

    # Step 2: under root? Order matters — check root-bounds before
    # is_dir() because the test fixture for the 'outside-root' case
    # uses a real on-disk dir; we want the under-root tag, not the
    # invalid_project_dir tag.
    if not _is_under_root(target, effective_root):
        # Could be (a) genuinely outside, (b) ``..`` traversal that
        # resolves outside, or (c) the path doesn't exist so resolve()
        # produced something not under root. Distinguish (c) so the
        # SPA can show "this project is gone" rather than "you're not
        # allowed to go there".
        try:
            exists = target.resolve().exists()
        except (OSError, RuntimeError):
            exists = False
        if not exists:
            return _api_error(
                404,
                "project_not_found",
                f"project not found: {target}",
            )
        return _api_error(
            400,
            "project_outside_source_root",
            f"project_root must be under source_projects_root: {target}",
        )

    # Step 3: resolved path exists?
    resolved = target.resolve()
    if not resolved.exists():
        return _api_error(
            404,
            "project_not_found",
            f"project not found: {target}",
        )

    # Step 4: is it a directory? (Could be a regular file under root.)
    if not resolved.is_dir():
        return _api_error(
            400,
            "invalid_project_dir",
            f"path is not a directory: {target}",
        )

    # Step 5: swap. Carrier validates again (TOCTOU defense) and may
    # raise InvalidProjectDirError if the dir vanished between the
    # is_dir() above and the carrier's check; surface that as
    # project_not_found.
    try:
        carrier.set_active_project(resolved)
    except InvalidProjectDirError:
        return _api_error(
            404,
            "project_not_found",
            f"project not found (vanished during load): {target}",
        )

    snap = carrier.snapshot()
    assert snap is not None  # we just set it

    # Step 6 (slice 5): build the full ``Project`` from disk — image
    # scan + ground-truth load + optional ``project.json`` metadata.
    # We fetch GT first (cheap, even on a no-GT project) and feed it
    # into the builder; the builder owns the on-disk-overrides + clamp
    # logic.
    ground_truth_map = load_ground_truth_from_directory(resolved)
    project = build_project_from_directory(resolved, ground_truth_map=ground_truth_map)

    # Step 7 (slice 5): stash the loaded project on ``ProjectState``.
    # ``set_loaded_project`` resets the per-page state map (page indices
    # are scoped to ONE project) and seeds ``current_page_index`` from
    # ``Project.current_page_index``. Bumps the state's generation
    # counter — separate from the carrier's, but moves in lockstep on
    # successful loads.
    project_state.set_loaded_project(project)

    # Step 8 (M2-tail): persist session state so the next startup can
    # resume at this project + page. Best-effort: a write failure must
    # not turn a successful load into an HTTP 500 (we already mutated
    # the carrier + ProjectState; rolling those back to honour a
    # session-state I/O error would be worse UX than logging and
    # continuing). Spec §02-backend.md §5.2 line 217 — "Saves session
    # state."; spec §09-persistence.md §6 — file shape.
    try:
        save_session_state(
            settings.data_root,
            SessionState(
                schema_version=SESSION_STATE_SCHEMA_VERSION,
                last_project_path=str(resolved),
                last_page_index=project_state.current_page_index,
            ),
        )
    except OSError as exc:
        log.warning(
            "Failed to write session_state.json after load (continuing): %s",
            exc,
        )

    response = LoadProjectResponse(
        project=project,
        current_page_index=project.current_page_index,
        generation=project_state.generation,
    )
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


@router.get("/{project_id}")
def get_project_by_id(
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``GET /api/projects/{project_id}`` — return the loaded ``Project``.

    Spec §02-backend.md line 220 — returns the loaded ``Project`` model
    by ``project_id``. This is M2-proper's read endpoint that pairs
    with slice-5's load handler: load mutates ``ProjectState``, GET
    reads it back.

    Behavior:

    - If ``ProjectState.loaded_project is None`` → ``404 project_not_found``.
      The spec ties ``project_not_found`` to "no project with that id is
      open"; the no-project-loaded case is a special instance of the
      same ("zero projects loaded means no id can match").
    - If ``loaded_project.project_id != project_id`` → ``404
      project_not_found``. The single-``ProjectState`` carrier addresses
      exactly one project at a time; asking for a different id is the
      same shape of miss.
    - Otherwise → ``200`` with the ``Project`` JSON, identical to the
      ``project`` field of ``LoadProjectResponse``.

    No on-demand load: this route never reaches the filesystem. To open
    a project, the SPA calls ``POST /api/projects/load`` first.

    The trailing-slash variant is NOT registered — FastAPI normalizes
    ``/api/projects/foo/`` to ``/api/projects/foo``, so a single route
    suffices.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _api_error(
            404,
            "project_not_found",
            f"project not found: {project_id}",
        )
    return JSONResponse(status_code=200, content=project.model_dump(mode="json"))


@router.post("/source-root", response_model=SetSourceProjectsRootResponse)
def set_source_root(
    body: SetSourceProjectsRootRequest,
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    src_carrier: SourceRootCarrier = Depends(get_source_root_carrier),
) -> JSONResponse:
    """``POST /api/projects/source-root`` — persist root to config.yaml + re-scan.

    Spec §5.2 line 224 — "Body: ``SetSourceProjectsRootRequest``.
    Persists to YAML config + re-scans."

    Validation:
    - ``body.path`` must resolve to an existing directory.  A missing
      path or a regular-file path both return ``400 invalid_path``.

    On success:
    1. Writes the new root to ``<config_root>/config.yaml`` atomically.
    2. Updates the in-process ``SourceRootCarrier`` so subsequent
       ``GET /api/projects`` and ``POST /discover`` calls see the new
       root immediately (without a server restart).
    3. Returns ``SetSourceProjectsRootResponse{projects_root, projects}``
       where ``projects`` is the freshly-scanned list under the new root.

    Config-write failure (``OSError``) is surfaced as a 500 — a write
    failure means the change would be lost on restart, which is more
    serious than a session-state save failure and warrants surfacing.
    """
    new_root = body.path
    try:
        resolved = new_root.resolve()
    except (OSError, RuntimeError):
        resolved = None

    if resolved is None or not resolved.exists() or not resolved.is_dir():
        return _api_error(
            400,
            "invalid_path",
            f"path is not an existing directory: {new_root}",
        )

    # Persist to config.yaml (may raise OSError on write failure).
    save_config(settings.config_root, AppConfig(source_projects_root=resolved))

    # Update in-process carrier so next GET/discover sees the new root.
    src_carrier.set(resolved)

    # Re-scan under the new root and return the list.
    response = _build_list_response(resolved, carrier, config_source="yaml")
    return JSONResponse(
        status_code=200,
        content={
            "projects_root": str(response.projects_root),
            "projects": [
                {
                    "project_id": p.project_id,
                    "project_root": str(p.project_root),
                    "label": p.label,
                }
                for p in response.projects
            ],
        },
    )


@router.post("/{project_id}/save-all", response_model=SaveProjectResponse)
def save_all(
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/projects/{pid}/save-all`` → ``202 {job_id}``.

    Spec §5.3: long-running save of all loaded pages. Returns 202 Accepted.
    The job handler is a stub that immediately completes (M3 will wire
    the real labeled-lane persistence). Callers track progress via
    ``GET /api/jobs/{job_id}/events``.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _api_error(
            404,
            "project_not_found",
            f"project not found: {project_id}",
        )

    job_id = runner.submit("save_project", project_id=project_id)
    return JSONResponse(status_code=202, content={"job_id": job_id})


@router.delete("/{project_id}", status_code=204, response_model=None)
def delete_project(
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
) -> Response:
    """``DELETE /api/projects/{project_id}`` → ``204`` — spec §5.2."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _api_error(  # type: ignore[return-value]
            404,
            "project_not_found",
            f"project not found: {project_id}",
        )

    project_state.clear()
    carrier.clear()
    return Response(status_code=204)


@router.post("/{project_id}/auto-rotate-all")
def post_auto_rotate_all(
    project_id: str,
    body: AutoRotateAllRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/projects/{id}/auto-rotate-all`` → ``202 {job_id}`` — spec §M9.2.

    Spec: ``docs/specs/2026-05-12-auto-rotation-design.md §Auto-rotate``

    Enqueues an ``auto_rotate_all`` job that iterates all pages in the
    project, runs auto-rotation detection on each (gt-best-match or
    layout, depending on ``method``), and applies any rotation with
    confidence ≥ 0.6.

    When ``overwrite_manual=False`` (default), pages with
    ``rotation_source == "manual"`` are skipped.

    Returns 404 when the requested project is not loaded.
    Returns 503 when the auto-rotate algorithm (``detect_best_rotation``)
    is not available (pd-book-tools not installed or missing the module).
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return JSONResponse(
            status_code=404,
            content=ApiError(
                error="project_not_found",
                message=f"project not found or not loaded: {project_id}",
            ).model_dump(),
        )

    # Graceful degradation — spec: "When rotation module absent: auto-rotate
    # disabled with tooltip; no 500."  Return 503 so the frontend can show
    # the disabled state rather than a crash.
    try:
        from pd_book_tools.ocr.rotation import detect_best_rotation  # noqa: F401
    except ImportError:
        return JSONResponse(
            status_code=503,
            content=ApiError(
                error="auto_rotate_unavailable",
                message=(
                    "Auto-rotate is not available: "
                    "pd_book_tools.ocr.rotation.detect_best_rotation not found. "
                    "Upgrade pd-book-tools to a version that includes this function."
                ),
            ).model_dump(),
        )

    job_id = runner.submit(
        "auto_rotate_all",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "method": body.method,
            "overwrite_manual": body.overwrite_manual,
            "page_count": project.total_pages,
        },
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


def install_projects_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the projects router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AutoRotateAllRequest",
    "ListProjectsResponse",
    "LoadProjectRequest",
    "LoadProjectResponse",
    "ProjectKey",
    "SetSourceProjectsRootRequest",
    "SetSourceProjectsRootResponse",
    "install_projects_router",
    "router",
]
