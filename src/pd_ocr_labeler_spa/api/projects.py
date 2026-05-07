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

What this slice (M2 slice 4 — second half) ships:

1. ``GET /api/projects`` composes the pure ``enumerate_projects``
   scanner (slice 4 starter, iter 2) with the request-time
   ``Settings`` and the ``ActiveProjectCarrier`` (slice 2). The
   response surfaces the scanner's output plus the active-project
   pointer + provenance.

2. ``POST /api/projects/load`` validates the requested ``project_root``
   is (a) a real directory, (b) under ``Settings.source_projects_root``,
   then swaps the carrier and returns the new active-project key + the
   carrier's bumped ``generation``.

What this slice deliberately does NOT do (deferred to M2-proper):

- ``POST /api/projects/discover`` and ``POST /api/projects/source-root``
  — both depend on YAML config plumbing that lands in M2-proper.
- ``GET /api/projects/{project_id}`` — needs the loaded ``Project``
  graph (M2-proper).
- ``LoadProjectResponse`` carrying ``project: Project`` +
  ``current_page: PagePayload`` per spec §1 lines 221-223 — those
  models don't exist yet. Slice 4 ships an interim slim shape
  (``LoadProjectResponseStub`` with ``project_key`` + ``generation``)
  whose docstring spells out the deviation. The route name + URL stay
  spec-canonical so the M2-proper expansion is purely additive — the
  SPA will see additional fields, not renamed ones.
- ``config_source`` provenance: slice 4 emits ``"default"``
  unconditionally; the YAML/CLI source tracking lands with
  ``POST /api/projects/source-root`` in M2-proper.
- Writing ``session_state.json`` on a successful load — see route
  docstring.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.active_project import ActiveProjectCarrier, InvalidProjectDirError
from ..core.project_enumeration import enumerate_projects
from ..settings import Settings
from .dependencies import get_active_project_carrier, get_settings
from .middleware.error_handler import ApiError

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


class LoadProjectResponseStub(BaseModel):
    """Slice-4 interim shape — see module docstring.

    The spec-canonical ``LoadProjectResponse`` is::

        class LoadProjectResponse(BaseModel):
            project: Project
            current_page: PagePayload

    Both ``Project`` and ``PagePayload`` arrive in M2-proper. Until
    they exist, this slim shape lets the SPA drive the load handshake
    end-to-end (carrier swap + URL update + dropdown re-mark) with no
    fake data. The class is named with the ``Stub`` suffix so that
    M2-proper's expansion (which keeps the URL constant and just
    extends the response schema) doesn't accidentally re-export this
    type from generated TS.

    Fields:

    - ``project_key``: the ``ProjectKey`` of the now-active project.
    - ``generation``: the carrier's monotonically-increasing counter
      AFTER the swap. Lets the SPA distinguish "I just loaded X"
      from "someone else loaded X 2 generations ago" once SSE lands.
    """

    project_key: ProjectKey
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
# Routes
# ──────────────────────────────────────────────────────────────────────


@router.get("", response_model=ListProjectsResponse)
def list_projects(
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
) -> ListProjectsResponse:
    """``GET /api/projects`` — enumerate + describe selection state.

    Spec §5.2 lines 208-211. Pure read; never mutates the carrier.

    The "is the active project under the configured root?" check uses
    ``_is_under_root`` so an off-root active project (e.g. one set via
    ``--project`` CLI override pointing outside the configured
    ``source_projects_root``) shows up as ``selected: None`` — the SPA
    dropdown can't mark an entry it doesn't display.
    """
    enumerated = enumerate_projects(settings.source_projects_root)
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
    if snap is not None and settings.source_projects_root is not None:
        if _is_under_root(snap.path, settings.source_projects_root):
            # Match by resolved path so a symlinked project entry still
            # marks correctly (slice-4-starter resolves project_root in
            # the EnumeratedProject; we resolve snap.path here too to be
            # symmetric).
            snap_resolved = snap.path.resolve()
            for p in enumerated:
                if p.project_root == snap_resolved:
                    selected = p.project_id
                    break

    # Sentinel empty path when no root is configured — keeps the
    # response shape stable (spec §2 line 209 declares the field
    # non-Optional).
    projects_root = (
        settings.source_projects_root.resolve() if settings.source_projects_root is not None else Path("")
    )

    return ListProjectsResponse(
        projects=projects,
        selected=selected,
        projects_root=projects_root,
        config_source="default",
    )


@router.post("/load")
def load_project(
    body: LoadProjectRequest,
    request: Request,  # noqa: ARG001  reserved for future SSE / session-state plumbing
    settings: Settings = Depends(get_settings),
    carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
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

    Per the module docstring, slice 4 returns ``LoadProjectResponseStub``;
    M2-proper will additively expand the response to the spec-canonical
    ``LoadProjectResponse``.

    Session-state writeback is intentionally omitted at slice 4. The
    spec says the load endpoint "Saves session state" (§5.2 line 217),
    but the writer (``save_session_state``) needs the page-payload
    plumbing to know what page index to record — and the page payload
    isn't in the slim slice-4 response. M2-proper bundles writeback
    with the page-payload extension.
    """
    target = body.project_root

    # Step 1: source root configured?
    if settings.source_projects_root is None:
        return _api_error(
            400,
            "project_outside_source_root",
            "no source_projects_root configured; cannot load any project",
        )

    # Step 2: under root? Order matters — check root-bounds before
    # is_dir() because the test fixture for the 'outside-root' case
    # uses a real on-disk dir; we want the under-root tag, not the
    # invalid_project_dir tag.
    if not _is_under_root(target, settings.source_projects_root):
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
    response = LoadProjectResponseStub(
        project_key=ProjectKey(
            project_id=resolved.name,
            project_root=resolved,
            label=resolved.name,
        ),
        generation=carrier.generation,
    )
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


def install_projects_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the projects router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "LoadProjectRequest",
    "LoadProjectResponseStub",
    "ListProjectsResponse",
    "ProjectKey",
    "install_projects_router",
    "router",
]
