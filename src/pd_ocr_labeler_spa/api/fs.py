"""``GET /api/fs/ls`` — directory-listing helper for the source-folder picker.

Local-only; no auth, no path restriction.  The SPA uses this to populate
the directory browser in ``SourceFolderDialog``.

Frontend ``data-testid`` contract (for per-entry rows):
    ``data-testid="fs-ls-entry-{name}"``

Spec reference: docs/architecture/22-spec-projectpage.md §10
(real source-folder picker, issue #294).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/fs", tags=["fs"])


class FsEntry(BaseModel):
    """One directory entry returned by ``GET /api/fs/ls``."""

    name: str
    is_dir: bool


class FsListResponse(BaseModel):
    """Response for ``GET /api/fs/ls`` — spec §10."""

    path: str
    entries: list[FsEntry]


@router.get("/ls", response_model=FsListResponse)
def list_directory(
    path: str = Query(default="~", description="Absolute or ~ path to list"),
) -> JSONResponse:
    """``GET /api/fs/ls?path=<path>`` — list subdirectories at *path*.

    - ``path`` defaults to ``~`` (user home) if not provided.
    - Calls ``.expanduser().resolve()`` on the input.
    - Returns only directories, excluding hidden names (leading ``'.'``),
      sorted alphabetically.
    - If ``path`` doesn't exist or isn't a directory → returns an empty
      ``entries`` list rather than a 404, so the dialog degrades
      gracefully.

    Response shape::

        {
            "path": "/resolved/absolute/path",
            "entries": [
                {"name": "subdir1", "is_dir": true},
                ...
            ]
        }
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return JSONResponse({"path": path, "entries": []})

    if not resolved.exists() or not resolved.is_dir():
        return JSONResponse({"path": str(resolved), "entries": []})

    try:
        names = sorted(e.name for e in resolved.iterdir() if e.is_dir() and not e.name.startswith("."))
    except PermissionError:
        names = []

    entries = [{"name": n, "is_dir": True} for n in names]
    return JSONResponse({"path": str(resolved), "entries": entries})


def install_fs_router(app: FastAPI) -> None:
    """Register the ``/api/fs`` router on *app*."""
    app.include_router(router)
