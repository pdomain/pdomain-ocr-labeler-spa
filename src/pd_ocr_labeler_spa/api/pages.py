"""``/api/projects/{project_id}/pages`` router — spec §5.3."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core import text_normalize
from ..core.jobs import JobRunner
from ..core.models import EncodedDims, LineFilter, LineMatch, PageRecord, Selection
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import get_job_runner, get_project_state, get_settings
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/pages",
    tags=["pages"],
)


# ── Wire shapes — spec §01-data-models.md §2 ─────────────────────────


class PagePayload(BaseModel):
    """Full per-page payload — spec §5.3 / §1 ``PagePayload``.

    ``page_text_ocr`` and ``page_text_gt`` are pre-built plaintext strings
    assembled from the page's OCR / GT words.  When
    ``normalize_plaintext_tabs=True`` in ``AppConfig`` these are normalised
    (long-s → ASCII etc.) before serialisation.  The envelope itself is never
    modified.
    """

    project_id: str
    page_index: int
    page_record: PageRecord | None = None
    line_matches: list[LineMatch] = Field(default_factory=list)
    selection: Selection = Field(default_factory=Selection)
    encoded_dims: EncodedDims | None = None
    line_filter: LineFilter = LineFilter.ALL
    image_url: str | None = None
    generation: int = 0
    # Plaintext representations — spec §1 ``PagePayload``.
    page_text_ocr: str | None = None
    page_text_gt: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SavePageRequest(BaseModel):
    """Body for ``POST .../save`` — spec §5.3."""

    generation: int | None = None


class SavePageResponse(BaseModel):
    """Response for ``POST .../save`` — spec §5.3."""

    project_id: str
    page_index: int
    saved: bool = True


class SaveFailure(BaseModel):
    """Error detail for failed save operations — spec §5.3."""

    page_index: int
    error: str


class SaveProjectResponse(BaseModel):
    """Response for ``POST .../save-all`` → ``202 {job_id}`` — spec §5.3."""

    job_id: str
    failures: list[SaveFailure] = Field(default_factory=list)


class ReloadOCRRequest(BaseModel):
    """Body for ``POST .../reload-ocr`` — spec §5.3."""

    force: bool = False


class ReloadOCRResponse(BaseModel):
    """Response for ``POST .../reload-ocr`` → 202 Accepted — spec §5.3."""

    job_id: str


class RematchGtRequest(BaseModel):
    """Body for ``POST .../rematch-gt`` — spec §5.3."""

    pass


class RotatePageRequest(BaseModel):
    """Body for ``POST .../rotate`` — spec §19 (M9.1).

    ``degrees`` must be one of ``-90``, ``90``, ``180``.
    ``manual`` distinguishes user-initiated (``True``) from
    auto-rotate (``False``) for ``rotation_source`` tracking.
    """

    degrees: int
    manual: bool = True


class RotatePageResponse(BaseModel):
    """Response for ``POST .../rotate`` → ``202 Accepted`` — spec §19 (M9.1)."""

    job_id: str


# ── Helpers ──────────────────────────────────────────────────────────


def _project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="project_not_found",
            message=f"project not found: {project_id}",
        ).model_dump(),
    )


def _page_not_found(page_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="page_not_found",
            message=f"page not found: {page_index}",
        ).model_dump(),
    )


def _not_implemented(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=ApiError(
            error="not_implemented",
            message=message,
        ).model_dump(),
    )


def _check_project_and_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState,
) -> JSONResponse | None:
    """Return an error response if the project/page isn't valid, else None."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _project_not_found(project_id)
    if page_index < 0 or page_index >= project.total_pages:
        return _page_not_found(page_index)
    return None


# ── Payload assembly helpers — spec-23-A (issue #306) ─────────────────


def _read_source_dims(image_path: Path) -> tuple[int, int] | None:
    """Return ``(src_width, src_height)`` for ``image_path`` or ``None``.

    Uses ``PIL.Image.open`` lazily; missing-file / unreadable-bytes
    fall through to ``None`` so ``_page_payload`` can still respond
    with a degraded-but-useful payload (the image route serves the
    bytes when called).
    """
    try:
        from PIL import Image  # lazy — PIL ships with pd-book-tools deps.

        with Image.open(image_path) as img:
            return int(img.size[0]), int(img.size[1])
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("failed to read image dims for %s: %s", image_path, exc)
        return None


def _build_image_url(
    project_id: str,
    page_index: int,
    encoded_dims: EncodedDims | None,
) -> str:
    """Return the relative image-route URL for this page.

    Shape (spec §3): ``/api/projects/{id}/pages/{idx}/image?w={display_width}``.

    When ``encoded_dims is None`` (image unreadable at GET time), the
    ``?w=`` query param is omitted — the frontend can still hit the
    route and the image-cache layer is allowed to choose a default
    width.  This keeps the URL valid in the degraded path.
    """
    base = f"/api/projects/{project_id}/pages/{page_index}/image"
    if encoded_dims is None:
        return base
    return f"{base}?w={encoded_dims.display_width}"


def _render_plaintext(
    line_matches: list[LineMatch],
    *,
    source: str,
    normalize_tabs: bool,
) -> str:
    """Join per-line text into a single plaintext string.

    ``source="ocr"`` uses ``LineMatch.ocr_line_text``;
    ``source="gt"`` uses ``LineMatch.ground_truth_line_text``.  Lines
    are joined with ``"\\n"`` — matches legacy plaintext rendering
    in ``pd-ocr-labeler/operations/.../page_text.py`` (one line per
    OCR line, no trailing newline).

    When ``normalize_tabs=True``, delegates to
    ``core.text_normalize.normalize_string`` (per
    ``AppConfig.normalize_plaintext_tabs`` — spec §3).  When
    pd_book_tools.text.normalize is unavailable, ``normalize_string``
    is a no-op (see ``core/text_normalize.py`` for the contract).
    """
    if source == "ocr":
        lines = [lm.ocr_line_text for lm in line_matches]
    elif source == "gt":
        lines = [lm.ground_truth_line_text for lm in line_matches]
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown source: {source!r}")

    text = "\n".join(lines)
    if normalize_tabs and text:
        text = text_normalize.normalize_string(text)
    return text


def _page_payload(
    *,
    project_id: str,
    page_index: int,
    project_state: ProjectState,
    settings: Settings,
) -> PagePayload:
    """Build a ``PagePayload`` from current in-memory state — spec §3.

    Keystone helper for spec-23.  Mutation endpoints in spec-23-C/D/E
    apply a state change then call ``_page_payload(...)`` to refresh
    the response shape; ``GET /pages/{idx}`` is the read-only entry
    point.

    Pre-condition (caller responsibility): ``project_state.loaded_project``
    is the project with ``project_id`` and ``page_index`` is in range.
    ``_check_project_and_page`` enforces this on the HTTP path.

    Today's behavior:

    - ``page_record``, ``line_matches`` come from
      ``PageState.page_record`` when present (a future slice will wire
      ``ensure_page_model`` with a real ``LocalDoctrPageLoader`` so a
      first-call GET runs OCR).  When no OCR has run yet they are
      ``None`` / ``[]`` — the frontend renders the image and an empty
      lines pane.
    - ``encoded_dims`` is computed from the on-disk image (PIL).
    - ``selection`` / ``line_filter`` default to ``Selection()`` /
      ``LineFilter.ALL`` — the current ``PageState`` shape does not
      yet carry per-page selection state (spec-23-E wires that).
    - ``generation`` echoes ``ProjectState.generation`` so SSE
      consumers can diff against a remembered value.
    - ``page_text_ocr`` / ``page_text_gt`` are rendered from
      ``line_matches`` (empty when no OCR has run).

    Concurrency: pure read over ``ProjectState`` — no lock needed
    here.  The mutation endpoints that call this helper hold the
    per-project lock for their state change; the snapshot returned
    here is consistent with the state at the moment the lock was
    released.
    """
    project = project_state.loaded_project
    # Pre-condition guaranteed by _check_project_and_page on the HTTP
    # path; assert here so misuse from a non-HTTP caller fails loudly.
    assert project is not None and project.project_id == project_id
    assert 0 <= page_index < project.total_pages

    pstate = project_state.get_page_state(page_index)

    # Page record + line matches: pulled from the cached PageState.
    # When no OCR has run yet, both are absent — the response is still
    # well-formed (PagePayload allows them None / []).
    page_record: PageRecord | None = None
    line_matches: list[LineMatch] = []
    outcome = pstate.page_record if pstate is not None else None
    if outcome is not None:
        # ``PageLoadOutcome.payload`` divergence between lanes (see
        # ``core/page_state.py`` module docstring):
        # - run_ocr → payload is a ``pd_book_tools.ocr.page.Page``
        # - load_labeled / load_cached → payload is a ``UserPageEnvelope``
        # Both lifts are out-of-scope for this slice; future slices
        # (spec-23-C/D/E) attach ``page_record`` / ``line_matches``
        # directly onto ``PageState`` after the mutation.
        candidate_record = getattr(outcome, "record", None)
        if isinstance(candidate_record, PageRecord):
            page_record = candidate_record
        candidate_matches = getattr(outcome, "line_matches", None)
        if isinstance(candidate_matches, list):
            line_matches = candidate_matches

    # Encoded dims from on-disk image.  None when PIL can't open the
    # bytes; the URL builder degrades gracefully.
    encoded_dims: EncodedDims | None = None
    if 0 <= page_index < len(project.image_paths):
        dims = _read_source_dims(project.image_paths[page_index])
        if dims is not None:
            encoded_dims = EncodedDims.from_source_dims(*dims)

    image_url = _build_image_url(project_id, page_index, encoded_dims)

    # Plaintext: empty until OCR runs.  normalize_tabs defaults to
    # False; AppConfig wiring lands in a follow-up slice (the
    # ``settings`` parameter is reserved on the signature so the
    # change is additive).
    page_text_ocr = _render_plaintext(line_matches, source="ocr", normalize_tabs=False)
    page_text_gt = _render_plaintext(line_matches, source="gt", normalize_tabs=False)

    return PagePayload(
        project_id=project_id,
        page_index=page_index,
        page_record=page_record,
        line_matches=line_matches,
        selection=Selection(),
        encoded_dims=encoded_dims,
        line_filter=LineFilter.ALL,
        image_url=image_url,
        generation=project_state.generation,
        page_text_ocr=page_text_ocr,
        page_text_gt=page_text_gt,
    )


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/{page_index}", response_model=PagePayload)
def get_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``GET /api/projects/{pid}/pages/{idx}`` — populated PagePayload.

    Spec authority: ``specs/23-page-payload-backend.md §3`` (issue #306,
    spec-23-A).  The keystone backend slice — every Phase D mutation
    endpoint (spec-23-C/D/E) reuses the ``_page_payload`` helper this
    slice introduces.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/{page_index}/save", response_model=SavePageResponse)
def save_page(
    project_id: str,
    page_index: int,
    body: SavePageRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../save`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("save page requires M3 persistence plumbing")


@router.post("/{page_index}/load", response_model=PagePayload)
def load_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../load`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("reload page from disk requires M3 persistence plumbing")


@router.post("/{page_index}/reload-ocr", response_model=ReloadOCRResponse)
def reload_ocr(
    project_id: str,
    page_index: int,
    body: ReloadOCRRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../reload-ocr`` → ``202 {job_id}`` — spec §5.3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    job_id = runner.submit(
        "reload_ocr",
        project_id=project_id,
        payload={"page_index": page_index},
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


@router.post("/{page_index}/rematch-gt", response_model=PagePayload)
def rematch_gt(
    project_id: str,
    page_index: int,
    body: RematchGtRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../rematch-gt`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("rematch-gt requires M3 plumbing")


@router.post("/{page_index}/rotate", response_model=RotatePageResponse)
def rotate_page(
    project_id: str,
    page_index: int,
    body: RotatePageRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../rotate`` → ``202 {job_id}`` — spec §19 (M9.1).

    Enqueues a ``rotate_page`` job that rotates the source image, re-runs
    OCR, updates ``PageRecord.rotation_degrees`` / ``rotation_source``, and
    auto-saves the envelope.

    ``degrees`` must be one of ``-90``, ``90``, ``180``; other values are
    rejected with ``400 invalid_degrees``.  ``manual=True`` (default) sets
    ``rotation_source="manual"``; ``False`` sets ``"auto"`` (used by the
    auto-rotate-all pass in M9.2).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    if body.degrees not in (-90, 90, 180):
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="invalid_degrees",
                message=f"degrees must be -90, 90, or 180; got {body.degrees}",
            ).model_dump(),
        )

    job_id = runner.submit(
        "rotate_page",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "page_index": page_index,
            "degrees": body.degrees,
            "manual": body.manual,
        },
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


def install_pages_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the pages router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "PagePayload",
    "ReloadOCRRequest",
    "ReloadOCRResponse",
    "RematchGtRequest",
    "RotatePageRequest",
    "RotatePageResponse",
    "SaveFailure",
    "SavePageRequest",
    "SavePageResponse",
    "SaveProjectResponse",
    "_build_image_url",
    "_page_payload",
    "_render_plaintext",
    "install_pages_router",
    "router",
]
