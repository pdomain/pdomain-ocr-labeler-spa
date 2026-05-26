"""``/api/projects/{project_id}/export`` router.

Spec authority:
- ``docs/architecture/02-backend.md §5.9`` lines 325-328 — endpoint contracts.
- ``docs/architecture/01-data-models.md §2`` lines 415-425 — ``ExportScope``,
  ``ExportRequest``, ``ExportResponse`` shapes.
- ``docs/architecture/10-export.md`` — export dialog + DocTR export operation.

Routes:
- ``POST /api/projects/{project_id}/export`` → 202 ``ExportResponse{job_id}``.
  Enqueues an ``export`` job via the ``JobRunner`` and returns immediately.
  The caller opens ``EventSource(/api/jobs/{job_id}/events)`` to track
  progress.
- ``GET /api/projects/{project_id}/exports`` → list of past exports
  (best-effort, read from disk — stub returning empty list until the
  export handler writes manifests).

Security note: ``ExportRequest.style_filters`` and ``component_filter`` are
validated against ``_SAFE_LABEL_RE`` to prevent path-traversal attacks.
F-001: ``docs/specs/2026-05-24-F-001-export-path-traversal.md``.
"""

from __future__ import annotations

import enum
import re

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, model_validator

from ..core.jobs import JobRunner
from .dependencies import get_job_runner

router = APIRouter(prefix="/api/projects", tags=["export"])

# ---------------------------------------------------------------------------
# Validation — F-001 path-traversal guard
# ---------------------------------------------------------------------------

# Allowlist: starts with alphanumeric; remaining chars may be alphanumeric,
# space, hyphen, or underscore; max 63 chars total.  This admits all current
# style labels ("italics", "small caps", "drop cap", "footnote marker",
# "all", …) while rejecting traversal sequences and filesystem separators.
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,62}$")


class ExportScope(str, enum.Enum):
    """Export scope discriminant — spec §2 lines 411-412."""

    CURRENT = "current"
    ALL_VALIDATED = "all_validated"


class ExportRequest(BaseModel):
    """Body for ``POST /api/projects/{id}/export`` — spec §2 lines 414-420.

    ``page_index``: required when ``scope == "current"``; ignored for
    ``all_validated``.  Spec §2 line 419.

    ``normalize_recognition_labels``: when ``True``, recognition ``labels.json``
    strings are normalised (long-s → ASCII, ligatures → ASCII) before write.
    Image bytes are unchanged.  Requires ``pd_book_tools.text.normalize``;
    silently ignored when the module is absent.  Spec: §18-text-normalization.
    """

    scope: ExportScope
    page_index: int | None = None
    style_filters: list[str] = []
    component_filter: str | None = None
    include_classification: bool = False
    detection_only: bool = False
    recognition_only: bool = False
    normalize_recognition_labels: bool = False

    @field_validator("style_filters", mode="before")
    @classmethod
    def _validate_style_filters(cls, v: object) -> list[str]:
        """Reject any style filter that is not a safe path-component string.

        Spec: ``docs/specs/2026-05-24-F-001-export-path-traversal.md``.
        Raises ``ValueError`` so FastAPI returns 422 Unprocessable Entity.
        """
        if not isinstance(v, list):
            raise ValueError("style_filters must be a list")
        for label in v:
            if not isinstance(label, str) or not _SAFE_LABEL_RE.match(label):
                raise ValueError(f"Invalid style filter {label!r}: must match {_SAFE_LABEL_RE.pattern}")
        return v  # type: ignore[return-value]

    @field_validator("component_filter", mode="before")
    @classmethod
    def _validate_component_filter(cls, v: object) -> str | None:
        """Reject a component_filter that is not a safe path-component string.

        Spec: ``docs/specs/2026-05-24-F-001-export-path-traversal.md``.
        Raises ``ValueError`` so FastAPI returns 422 Unprocessable Entity.
        """
        if v is None:
            return None
        if not isinstance(v, str) or not _SAFE_LABEL_RE.match(v):
            raise ValueError(f"Invalid component_filter {v!r}: must match {_SAFE_LABEL_RE.pattern}")
        return v

    @model_validator(mode="after")
    def _validate_scope_and_mode_constraints(self) -> ExportRequest:
        """Cross-field validation for scope/page_index/mode consistency.

        F-005 constraints:
        1. ``page_index`` is mandatory when scope is ``current``.
        2. ``page_index`` must be non-negative when scope is ``current``.
        3. ``page_index`` must be ``None`` when scope is ``all_validated``
           (supplying a page index alongside "all validated" is contradictory).
        4. ``detection_only`` and ``recognition_only`` cannot both be ``True``
           (would disable all output while reporting success).
        """
        if self.scope == ExportScope.CURRENT:
            if self.page_index is None:
                raise ValueError("page_index is required when scope is 'current'")
            if self.page_index < 0:
                raise ValueError(
                    f"page_index must be non-negative for scope 'current'; got {self.page_index}"
                )
        elif self.scope == ExportScope.ALL_VALIDATED:
            if self.page_index is not None:
                raise ValueError(
                    "page_index must not be supplied when scope is 'all_validated'; "
                    "it is only meaningful for scope 'current'"
                )
        if self.detection_only and self.recognition_only:
            raise ValueError(
                "detection_only and recognition_only cannot both be True: "
                "this would disable all export output"
            )
        return self


class ExportResponse(BaseModel):
    """Response for export — spec §2 lines 422-423."""

    job_id: str


class ExportManifest(BaseModel):
    """One past export manifest entry — spec §5.9 line 326.

    Shape is best-effort: the export handler will write manifests in M3.
    Until then this model is a placeholder that matches the empty-list stub.
    Fields are intentionally minimal; the handler will expand them.
    """

    job_id: str
    scope: str
    created_at: str


@router.post("/{project_id}/export", response_model=ExportResponse, status_code=202)
def start_export(
    project_id: str,
    body: ExportRequest,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/projects/{id}/export`` — enqueue an export job.

    Spec §5.9 line 325. Returns 202 Accepted with ``{job_id}``; the
    caller opens ``EventSource(/api/jobs/{job_id}/events)`` to receive
    progress and the terminal event. The actual DocTR export pipeline
    is wired in the ``export`` job handler (``core/jobs/runner.py``
    ``_HANDLERS["export"]``); until full M3 wiring the handler completes
    immediately (stub body, no I/O).
    """
    job_id = runner.submit(
        "export",
        project_id=project_id,
        payload={
            "scope": body.scope.value,
            "page_index": body.page_index,
            "style_filters": body.style_filters,
            "component_filter": body.component_filter,
            "include_classification": body.include_classification,
            "detection_only": body.detection_only,
            "recognition_only": body.recognition_only,
        },
    )
    return JSONResponse(
        status_code=202,
        content=ExportResponse(job_id=job_id).model_dump(),
    )


@router.get("/{project_id}/export/styles", response_model=list[str])
def list_export_styles(project_id: str) -> JSONResponse:
    """``GET /api/projects/{id}/export/styles`` — distinct style labels.

    Spec: ``docs/specs/2026-05-12-export-design.md §Decision``
    ("Switching to 'All Validated Pages' fires GET .../export/styles").

    Returns a JSON array of distinct style label strings present in
    saved validated pages for this project.  Until the export handler
    writes manifests (and until the labeled-lane reader is wired), this
    returns an empty list — callers should render the "All (no style
    filter)" option as the sole available choice.

    Issue #225 acceptance: route registered, returns 200 JSON array.
    """
    return JSONResponse(status_code=200, content=[])


@router.get("/{project_id}/exports", response_model=list[ExportManifest])
def list_exports(project_id: str) -> JSONResponse:
    """``GET /api/projects/{id}/exports`` — past exports (best-effort).

    Spec §5.9 line 326. Returns a list of past export manifests read
    from disk. Until the export handler writes manifests, always returns
    an empty list (spec says "best-effort").
    """
    return JSONResponse(status_code=200, content=[])


def install_export_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the export router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "ExportRequest",
    "ExportResponse",
    "ExportScope",
    "install_export_router",
    "list_export_styles",
    "router",
]
