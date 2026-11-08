"""Configured PGDP catalog and idempotent selected-page preparation."""

from __future__ import annotations

from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ..adapters.source_data import SourceDataBridge, SourceDataError
from ..core.jobs.runner import JobRunner, RequestIdConflictError
from .automation import request_app
from .dependencies import get_job_runner

router = APIRouter(prefix="/api/pgdp", tags=["pgdp"])


class PrepareRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=200)
    page_keys: list[str] = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=200)


class ProjectSummary(BaseModel):
    project_id: str
    title: str
    author: str | None = None
    available_rounds: list[str]
    page_count: int


class ProjectCatalog(BaseModel):
    projects: list[ProjectSummary]
    offset: int
    limit: int
    next_offset: int | None
    scanned_count: int
    truncated: bool
    warnings: list[str]


class ScanMetadata(BaseModel):
    relative_path: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class SourcePage(BaseModel):
    page_key: str
    available_rounds: list[str]
    image: ScanMetadata | None = None


class PageCatalog(BaseModel):
    project_id: str
    title: str
    pages: list[SourcePage]
    offset: int
    limit: int
    next_offset: int | None
    page_count: int
    warnings: list[str]


class PrepareResponse(BaseModel):
    job_id: str


def get_source_data(request: Request) -> SourceDataBridge:
    app = request_app(request.scope)
    bridge: object = getattr(app.state, "source_data", None)
    if not isinstance(bridge, SourceDataBridge):
        raise RuntimeError("app.state.source_data is not configured")
    return bridge


def source_error(exc: SourceDataError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": exc.code, "message": str(exc), "details": exc.details}
    )


Bridge = Annotated[SourceDataBridge, Depends(get_source_data)]
Runner = Annotated[JobRunner, Depends(get_job_runner)]


@router.get("/projects", response_model=ProjectCatalog)
async def projects(
    *,
    bridge: Bridge,
    query: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectCatalog | JSONResponse:
    try:
        request: dict[str, JsonValue] = {"command": "projects", "limit": limit, "offset": offset}
        if query:
            request["query"] = query
        return ProjectCatalog.model_validate(await bridge.call(request))
    except SourceDataError as exc:
        return source_error(exc)
    except ValidationError:
        return source_error(
            SourceDataError("Invalid project catalog response", code="source_invalid_response", status=502)
        )


@router.get("/projects/{project_id}/pages", response_model=PageCatalog)
async def pages(
    project_id: str,
    *,
    bridge: Bridge,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageCatalog | JSONResponse:
    try:
        return PageCatalog.model_validate(
            await bridge.call(
                {"command": "pages", "project_id": project_id, "limit": limit, "offset": offset}
            )
        )
    except SourceDataError as exc:
        return source_error(exc)
    except ValidationError:
        return source_error(
            SourceDataError("Invalid page catalog response", code="source_invalid_response", status=502)
        )


@router.post("/prepare", status_code=202, response_model=PrepareResponse)
def prepare(
    body: PrepareRequest,
    bridge: Bridge,
    runner: Runner,
) -> PrepareResponse | JSONResponse:
    try:
        bridge.require_configured(prepare=True)
    except SourceDataError as exc:
        return source_error(exc)
    try:
        payload: dict[str, JsonValue] = {"project_id": body.project_id, "page_keys": list(body.page_keys)}
        job_id = runner.submit_idempotent(
            "prepare_pgdp",
            request_id=body.request_id,
            project_id=body.project_id,
            payload=payload,
        )
    except RequestIdConflictError as exc:
        return JSONResponse(
            status_code=409, content={"error": "request_id_conflict", "message": str(exc), "details": None}
        )
    return PrepareResponse(job_id=job_id)
