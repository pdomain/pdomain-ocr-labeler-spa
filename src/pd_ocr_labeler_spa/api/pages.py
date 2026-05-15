"""``/api/projects/{project_id}/pages`` router — spec §5.3."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..core import text_normalize
from ..core.ground_truth_matcher import rematch_page
from ..core.jobs import JobRunner
from ..core.models import EncodedDims, LineFilter, LineMatch, PageRecord, Selection
from ..core.page_state import ensure_page_model, persist_page_to_file
from ..core.persistence.ground_truth import find_ground_truth_text
from ..core.persistence.lanes import LaneResolver
from ..core.persistence.user_page_envelope import (
    USER_PAGE_SOURCE_LANE_CACHED,
    OCRProvenance,
    build_envelope,
)
from ..core.project_state import PageState, ProjectState
from ..core.selection import SelectionMode, apply_selection
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


class UpdateSelectionRequest(BaseModel):
    """Body for ``POST .../selection`` — spec-23-E §10.

    ``mode`` chooses the set operation applied to ``pstate.selection``:

    - ``replace`` — drop the current selection and adopt ``selection``.
    - ``remove`` — subtract ``selection`` from the current selection.
    - ``toggle`` — symmetric-difference: items present in both clear,
      items in exactly one are kept.

    ``selection`` is the canonical ``Selection`` wire shape from spec
    §01-data-models — ``selection_mode`` + ``selected_paragraphs`` +
    ``selected_lines`` + ``selected_words`` (as ``(line, word)`` pairs).
    """

    mode: SelectionMode
    selection: Selection


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


def _write_cached_envelope_best_effort(
    *,
    page: Any,
    project_state: ProjectState,
    page_index: int,
    settings: Settings,
) -> None:
    """Write the cached-lane envelope; log + swallow on failure.

    Spec 23 §12: cached-lane write is best-effort. ``LaneResolver.write_cached``
    already swallows ``OSError``; we still wrap broad ``Exception`` here
    so a misconfigured envelope (e.g. a stub Page whose ``to_dict``
    raises) cannot turn a successful in-memory mutation into a 500.
    """
    project = project_state.loaded_project
    if project is None:
        return
    try:
        envelope = build_envelope(
            page=page,
            project=project,
            page_index=page_index,
            ocr_provenance=OCRProvenance(),
            source_lane=USER_PAGE_SOURCE_LANE_CACHED,
        )
        resolver = LaneResolver(
            data_root=settings.data_root,
            cache_root=settings.cache_root,
            project_id=project.project_id,
        )
        resolver.write_cached(page_index, envelope)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning(
            "pages: cached-envelope write failed project=%s page=%d: %s — continuing",
            project.project_id,
            page_index,
            exc,
        )


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
    - ``selection`` is read from ``PageState.selection`` (spec-23-E
      §10).  Defaults to empty ``Selection()`` for pages without a
      ``PageState`` yet.  ``line_filter`` defaults to ``LineFilter.ALL``
      until M3 wires per-page filter state.
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

    # spec-23-E §10: ``pstate.selection`` is the per-page UI selection
    # mutated by ``POST .../selection``; echo it onto the payload so a
    # subsequent ``GET`` sees the same selection. Defaults to empty
    # ``Selection()`` for pages with no ``PageState`` yet.
    selection = pstate.selection if pstate is not None else Selection()

    return PagePayload(
        project_id=project_id,
        page_index=page_index,
        page_record=page_record,
        line_matches=line_matches,
        selection=selection,
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../save`` — write the labeled-lane envelope (spec-23-B2 §4).

    Pre-conditions enforced:

    - Project loaded + ``page_index`` in range (else 404, as
      ``_check_project_and_page``).
    - ``PageState.page_record`` is populated — there must be something
      to persist. If not, returns 400 ``page_not_loaded`` (the frontend
      should run OCR / load first; this distinguishes the case from a
      missing project / page).
    - If ``body.generation`` is provided, must equal
      ``pstate.generation`` — else 409 ``generation_mismatch`` so the
      frontend can re-fetch.

    Calls ``persist_page_to_file`` (#284) with the bound project /
    ``data_root``. On ``OSError`` returns a 500 envelope
    (``save_failed``). On success, advances ``last_saved_generation``
    to the page's current ``generation`` so a subsequent
    ``save_project`` pass is a no-op until the next mutation.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    if pstate is None or pstate.page_record is None:
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="page_not_loaded",
                message=(f"page {page_index} has no in-memory state to save; load or run OCR first"),
            ).model_dump(),
        )

    if body.generation is not None and body.generation != pstate.generation:
        return JSONResponse(
            status_code=409,
            content={
                "error": "generation_mismatch",
                "message": (
                    f"generation mismatch: client sent {body.generation}, server has {pstate.generation}"
                ),
                "current_generation": pstate.generation,
            },
        )

    # ``PageLoadOutcome.payload`` is the Page-like object exposing
    # ``to_dict()`` for ``build_envelope``. See lane-divergence note
    # ``project_envelope_lanes_payload_divergence`` — labeled / cached
    # lanes store a ``UserPageEnvelope`` here, but those paths shouldn't
    # be dirty under current code (OCR lane is the only dirty-marker).
    page_obj = pstate.page_record.payload

    project = project_state.loaded_project
    assert project is not None  # _check_project_and_page guarantees

    try:
        persist_page_to_file(
            page=page_obj,
            project=project,
            page_index=page_index,
            data_root=settings.data_root,
        )
    except OSError as exc:
        log.exception("save_page: persist failed project=%s page=%d", project_id, page_index)
        return JSONResponse(
            status_code=500,
            content=ApiError(
                error="save_failed",
                message=f"failed to persist page {page_index}: {exc}",
            ).model_dump(),
        )

    pstate.last_saved_generation = pstate.generation

    return JSONResponse(
        status_code=200,
        content=SavePageResponse(project_id=project_id, page_index=page_index, saved=True).model_dump(
            mode="json"
        ),
    )


@router.post("/{page_index}/load", response_model=PagePayload)
def load_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../load`` — re-read the page from disk, discard in-memory edits.

    Spec §5. Discards any in-memory ``PageState`` for this index, then
    calls ``ensure_page_model`` with the route-layer-injected
    ``PageLoader`` (probes labeled → cached → OCR lanes in that order).
    Returns the freshly-assembled ``PagePayload`` so the SPA can render
    the just-loaded state.

    The page_loader is read off ``runner.context["page_loader"]`` (the
    same wiring slot the ``reload_ocr`` job uses, per spec §6); a
    503 ``page_loader_not_wired`` is returned when no loader is wired
    (tests inject a fake; M3 wiring binds a ``LocalDoctrPageLoader``
    once DocTR is in scope).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    loader = runner.context.get("page_loader")
    if loader is None:
        return JSONResponse(
            status_code=503,
            content=ApiError(
                error="page_loader_not_wired",
                message=(
                    "page loader is not wired on the job runner; "
                    "the route layer must inject a PageLoader (M3 follow-on)"
                ),
            ).model_dump(),
        )

    # Discard in-memory state so ensure_page_model re-probes from disk
    # (the lane probes are loader-driven and don't consult in-memory
    # state; clearing here keeps the contract explicit and means a
    # future swap to a precedence-aware ``force_reload`` flag on
    # ``ensure_page_model`` won't change observable behavior).
    project_state._page_states.pop(page_index, None)

    # Call the dispatcher. Holds the project lock for the lane probes
    # + optional OCR run.
    ensure_page_model(
        project_state,
        page_index,
        loader=loader,  # type: ignore[arg-type]
    )

    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../rematch-gt`` — re-run page-level GT matching (spec §7).

    Spec authority: ``specs/23-page-payload-backend.md §7``.

    Re-runs ``core/ground_truth_matcher.rematch_page`` — a thin wrapper
    over ``pd_book_tools.ocr.ground_truth_matching`` reached via the
    ``Page.remove_ground_truth`` / ``Page.add_ground_truth`` pair.
    Replaces ``page.line_matches`` with freshly-matched results; per-word
    GT edits are *discarded* (legacy semantics, mirrored from
    ``pd_ocr_labeler/state/page_state.py:2357 rematch_ground_truth``).

    Error envelopes:

    - ``project_not_found`` (404) — unknown ``project_id``.
    - ``page_not_found`` (404) — ``page_index`` out of range.
    - ``page_not_loaded`` (400) — ``PageState`` empty (caller must
      ``GET /pages/{idx}`` first to run OCR or load envelope).
    - ``no_ground_truth`` (400) — the page's image filename has no
      entry in ``Project.ground_truth_map``. Legacy parity: the
      legacy ``_GroundTruthRematchSkippedError`` path; surfaces a
      banner in the SPA so the user knows GT must be supplied
      before rematching.
    - ``rematch_failed`` (400) — the page object lacks the
      ``remove_ground_truth`` / ``add_ground_truth`` method pair
      (e.g. a legacy page-dict that was never wrapped in
      ``pd_book_tools.ocr.page.Page``).

    Body (``RematchGtRequest``) is intentionally empty — the
    confirmation prompt is the frontend's responsibility
    (``ConfirmDialog`` per spec 22). The endpoint is unconditional
    when GT is available.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    project = project_state.loaded_project
    assert project is not None  # _check_project_and_page guarantees

    pstate = project_state.get_page_state(page_index)
    if pstate is None or pstate.page_record is None:
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="page_not_loaded",
                message=(f"page {page_index} has no in-memory page record; load or run OCR first"),
            ).model_dump(),
        )
    page = getattr(pstate.page_record, "payload", None)
    if page is None:
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="page_not_loaded",
                message=(f"page {page_index} record carries no payload; load or run OCR first"),
            ).model_dump(),
        )

    # Resolve GT source text for this page via the project's
    # ground-truth map (keyed by image filename / stem variants).
    # Legacy parity: ``_rematch_page_ground_truth`` raises
    # ``_GroundTruthRematchSkippedError`` when GT is unavailable;
    # the SPA returns 400 so the frontend can surface a banner.
    image_name = (
        project.image_paths[page_index].name
        if 0 <= page_index < len(project.image_paths)
        else ""  # pragma: no cover - bounds already enforced above
    )
    gt_text = find_ground_truth_text(image_name, project.ground_truth_map)
    if not gt_text:
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="no_ground_truth",
                message=(
                    f"no ground-truth text available for page {page_index} "
                    f"(image {image_name!r}); add a pages.json or manifest entry "
                    "before rematching"
                ),
            ).model_dump(),
        )

    # Mutate under the per-page lock — spec §13. The lock covers the
    # full mutation window: resolve → mutate → generation bump → cache
    # write.  Keeping the cache write inside the lock prevents a torn
    # ``write_json_atomic`` race where two concurrent handlers both do
    # ``os.replace`` on the same ``.tmp`` target for the same page.
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = rematch_page(page, gt_text)
        if not ok:
            return JSONResponse(
                status_code=400,
                content=ApiError(
                    error="rematch_failed",
                    message=(
                        f"page {page_index} payload type "
                        f"{type(page).__name__!r} lacks "
                        "remove_ground_truth / add_ground_truth"
                    ),
                ).model_dump(),
            )
        pstate.generation += 1

        # Best-effort cached-envelope autosave — spec §12 + §13.
        # Inside the lock so the cache write is serialised with the
        # mutation (prevents torn writes from concurrent rematches).
        _write_cached_envelope_best_effort(
            page=page,
            project_state=project_state,
            page_index=page_index,
            settings=settings,
        )

    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


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


@router.post("/{page_index}/selection", response_model=PagePayload)
def update_selection(
    project_id: str,
    page_index: int,
    body: UpdateSelectionRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../selection`` — fold a delta into ``pstate.selection``.

    Spec authority: ``specs/23-page-payload-backend.md §10``.

    Behaviour:

    1. Validate ``project_id`` / ``page_index`` (``_check_project_and_page``).
    2. Get-or-create a ``PageState`` for ``page_index`` — selection is a
       pure UI carrier that doesn't depend on OCR having run.
    3. Under the per-page lock (spec §13): apply the set operation
       (``core.selection.apply_selection``), bump ``pstate.generation``.
    4. Return the spec-23-A populated ``PagePayload`` so the frontend can
       update its cached page state in one round-trip — matches the
       contract shared with the spec-23-C/D word/line/paragraph
       mutations.

    No cached-envelope autosave: selection is per-session UI state, not
    part of the saved labeled envelope.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    if pstate is None:
        # Selection can be mutated before OCR runs — create an empty
        # PageState carrier so we have a slot to store ``selection``.
        pstate = PageState(page_index=page_index)
        project_state.set_page_state(page_index, pstate)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        pstate.selection = apply_selection(pstate.selection, body.mode, body.selection)
        pstate.generation += 1

    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/{page_index}/image")
def get_page_image(
    project_id: str,
    page_index: int,
    w: int | None = None,
    project_state: ProjectState = Depends(get_project_state),
) -> Response:
    """``GET /api/projects/{id}/pages/{idx}/image`` — serve the page image.

    Spec §3: the ``image_url`` returned by ``GET .../pages/{idx}``
    points here.  When ``?w=N`` is given the image is resized to width
    ``N`` (height scaled proportionally) before JPEG encoding.  Caches
    for one hour via ``Cache-Control: public, max-age=3600``.

    Error paths:
    - 404 ``project_not_found`` / ``page_not_found`` (via
      ``_check_project_and_page``).
    - 404 ``image_not_found`` on PIL open failure (missing file, corrupt
      bytes).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err  # type: ignore[return-value]

    project = project_state.loaded_project
    assert project is not None  # _check_project_and_page guarantees

    image_path = project.image_paths[page_index]

    try:
        from PIL import Image  # lazy — PIL ships with pd-book-tools deps.

        with Image.open(image_path) as img_raw:
            img = img_raw.convert("RGB")

        if w is not None and img.width != w:
            new_h = max(1, int(img.height * w / img.width))
            img = img.resize((w, new_h))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        content = buf.getvalue()
    except Exception as exc:
        log.debug("get_page_image: failed to open %s: %s", image_path, exc)
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content=ApiError(error="image_not_found", message=str(exc)).model_dump(),
        )

    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
    "UpdateSelectionRequest",
    "_build_image_url",
    "_page_payload",
    "_render_plaintext",
    "get_page_image",
    "install_pages_router",
    "router",
]
