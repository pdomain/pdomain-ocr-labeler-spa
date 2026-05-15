"""``/api/projects/{project_id}/pages/{page_index}/words`` router — word mutations (§5.4).

Spec authority:
- ``docs/architecture/01-data-models.md §2`` — wire shapes for word routes.
- ``docs/architecture/02-backend.md §5.4`` — endpoint contracts.
- ``specs/23-page-payload-backend.md §9, §12, §13`` — mutation pattern:
  per-page lock → resolve word → call pd-book-tools method → bump
  ``PageState.generation`` → cached-envelope autosave (best-effort) →
  refreshed ``PagePayload`` via the keystone ``_page_payload`` helper
  in ``api/pages.py``.

The five spec-23-C1 handlers below
(GT / style / component / validated / validate-batch) are fully wired.
The remaining word endpoints (add, rebox, nudge, split, merge,
erase-pixels) still return stub payloads — they belong to
spec-23-C2/C3 issues.

Pd-book-tools method mapping (spec §9 names → actual pd-book-tools API):

- ``set_ground_truth_text(text)`` → ``word.ground_truth_text = text``
  (property setter at ``pd_book_tools.ocr.word.Word.ground_truth_text``).
- ``apply_style(style, scope)`` → ``word.apply_style_scope(style, scope)``.
- ``set_component(component, enabled)`` → ``word.apply_component(component, enabled=enabled)``.
- ``set_validated(bool)`` → **no method exists** on pd-book-tools'
  ``Word`` today. Tracking issue: ConcaveTrillion/pd-book-tools#52.
  Until that lands, the SPA writes the flag onto a per-page
  ``validated_words`` map on ``PageState`` (lossy across envelope
  round-trips; documented limitation).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from ..core.models import BBox
from ..core.persistence.lanes import LaneResolver
from ..core.persistence.user_page_envelope import (
    USER_PAGE_SOURCE_LANE_CACHED,
    OCRProvenance,
    build_envelope,
)
from ..core.project_state import PageState, ProjectState
from ..settings import Settings
from .dependencies import get_project_state, get_settings
from .middleware.error_handler import ApiError
from .pages import PagePayload, _page_payload

log = logging.getLogger(__name__)

# Forbidden codepoint ranges for GT input.
# U+FB00-U+FB06: Latin ligatures (ff, fi, fl, ffi, ffl, long-st variants).
# U+017F: Latin small letter long s.
# Spec: docs/specs/2026-05-12-text-normalization-design.md - GT validation.
_GT_FORBIDDEN_CODEPOINTS: frozenset[int] = frozenset(range(0xFB00, 0xFB07)) | {0x017F}

router = APIRouter(prefix="/api/projects", tags=["words"])


# ── Request models ─────────────────────────────────────────────────────


class UpdateWordGroundTruthRequest(BaseModel):
    """Spec §2 line 285."""

    text: str

    @field_validator("text")
    @classmethod
    def _reject_forbidden_codepoints(cls, v: str) -> str:
        """Reject GT text containing ligature codepoints or long-s.

        Spec (docs/specs/2026-05-12-text-normalization-design.md):
        'Backend rejects GT input containing U+FB00-U+FB06 or U+017F
        with 400 validation_error.'

        GT strings must be clean ASCII / normalized Unicode. The SPA should
        normalize these before calling the API; if raw glyph codepoints arrive
        here, it is a client-side bug and the 400 surfaces it clearly.
        """
        bad = [hex(ord(ch)) for ch in v if ord(ch) in _GT_FORBIDDEN_CODEPOINTS]
        if bad:
            raise ValueError(
                f"GT text contains forbidden codepoints: {', '.join(bad)}. "
                "Normalize ligatures and long-s to ASCII before saving GT."
            )
        return v


class ApplyStyleRequest(BaseModel):
    """Spec §2 lines 288-290."""

    style: str
    scope: Literal["whole", "part"] = "whole"


class ApplyComponentRequest(BaseModel):
    """Spec §2 lines 293-295."""

    component: str
    enabled: bool


class ToggleValidatedRequest(BaseModel):
    """Spec §2 lines 297-298."""

    validated: bool | None = None


class ValidateBatchRequest(BaseModel):
    """Spec §2 lines 300-306."""

    scope: Literal["page", "paragraph", "line", "word"]
    line_index: int | None = None
    word_indices: list[tuple[int, int]] = []
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    validated: bool


class AddWordRequest(BaseModel):
    """Spec §2 lines 308-311."""

    line_index: int | None = None
    bbox: BBox
    text: str = ""


class ReboxWordRequest(BaseModel):
    """Spec §2 lines 313-314."""

    bbox: BBox


class NudgeBboxRequest(BaseModel):
    """Spec §2 lines 316-321."""

    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0
    refine_after: bool = False


class SplitWordRequest(BaseModel):
    """Spec §2 lines 323-325."""

    x_fraction: float
    direction: Literal["horizontal", "vertical"]


class MergeWordsRequest(BaseModel):
    """Spec §2 lines 327-328."""

    direction: Literal["left", "right"]


class ErasePixelsRequest(BaseModel):
    """Spec §2 lines 330-332."""

    bbox: BBox
    fill_value: int = 255


# ── Helpers ────────────────────────────────────────────────────────────


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


def _page_not_loaded(page_index: int) -> JSONResponse:
    """400 envelope used by mutation handlers when ``PageState`` is empty.

    Mirrors ``api/pages.py:save_page`` (#308) — the client should load
    or run OCR for the page before attempting a mutation. The spec-23-C1
    mutation handlers all resolve the target word through
    ``PageState.page_record.payload``; without a populated payload they
    have nothing to mutate.
    """
    return JSONResponse(
        status_code=400,
        content=ApiError(
            error="page_not_loaded",
            message=(f"page {page_index} has no in-memory page record; load or run OCR first"),
        ).model_dump(),
    )


def _word_not_found(line_index: int, word_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="word_not_found",
            message=f"word not found: line {line_index}, word {word_index}",
        ).model_dump(),
    )


def _resolve_page_object(pstate: PageState | None) -> Any | None:
    """Pull the ``Page``-like object out of ``PageState.page_record``.

    The page record (``PageLoadOutcome``) carries the loaded Page in
    its ``payload`` field. Returns ``None`` when no record is cached
    yet — callers map that to a 400 ``page_not_loaded`` envelope.
    """
    if pstate is None or pstate.page_record is None:
        return None
    return getattr(pstate.page_record, "payload", None)


def _resolve_word(page: Any, line_index: int, word_index: int) -> Any | None:
    """Resolve ``page.lines[line_index].words[word_index]`` or ``None``.

    Defensive against missing attributes (allows the SPA-side stubs in
    tests to opt out of the full Page contract) and out-of-range
    indices — both map to a 404 ``word_not_found`` envelope.
    """
    lines = getattr(page, "lines", None)
    if lines is None or not (0 <= line_index < len(lines)):
        return None
    words = getattr(lines[line_index], "words", None)
    if words is None or not (0 <= word_index < len(words)):
        return None
    return words[word_index]


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
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch
        log.warning(
            "words: cached-envelope write failed project=%s page=%d: %s — continuing",
            project.project_id,
            page_index,
            exc,
        )


def _stub_payload_response(project_id: str, page_index: int) -> JSONResponse:
    """Empty ``PagePayload`` for the not-yet-wired word endpoints.

    Add / rebox / nudge / split / merge / erase-pixels are still
    stub-handlers pending their respective spec-23-C2 / spec-23-C3
    issues. Until then they return a deterministic empty payload so the
    SPA wire-shape contract stays stable.
    """
    payload = PagePayload(project_id=project_id, page_index=page_index)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


def _refresh_payload_response(
    *,
    project_id: str,
    page_index: int,
    project_state: ProjectState,
    settings: Settings,
) -> JSONResponse:
    """Build the spec-23-A populated ``PagePayload`` response."""
    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


# ── Routes ─────────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/gt",
    response_model=PagePayload,
)
def update_word_ground_truth(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: UpdateWordGroundTruthRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/gt`` — update ground-truth text for a word.

    Spec 23 §9 row 1: ``word.set_ground_truth_text(text)`` → property
    setter ``word.ground_truth_text = text``. Holds the per-page lock
    for the mutation + generation bump; releases before the cached
    write so disk I/O doesn't serialize cross-page edits.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        word.ground_truth_text = body.text
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/style",
    response_model=PagePayload,
)
def apply_style(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ApplyStyleRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/style`` — apply text style label to a word.

    Spec 23 §9 row 2: ``word.apply_style(style_id, scope)`` →
    ``word.apply_style_scope(style, scope)`` in pd-book-tools.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        word.apply_style_scope(body.style, body.scope)
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/component",
    response_model=PagePayload,
)
def apply_component(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ApplyComponentRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/component`` — toggle a word component flag.

    Spec 23 §9 row 3: ``word.set_component(component_id)`` →
    ``word.apply_component(component, enabled=enabled)`` in pd-book-tools.
    ``enabled=False`` removes the component (idempotent — pd-book-tools'
    ``apply_component`` discards if not present).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        word.apply_component(body.component, enabled=body.enabled)
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/validated",
    response_model=PagePayload,
)
def toggle_validated(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ToggleValidatedRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/validated`` — toggle the validated flag.

    Spec 23 §9 row 4 calls for ``word.set_validated(bool)``. pd-book-tools
    does not yet expose this method (tracking issue
    ConcaveTrillion/pd-book-tools#52). Until that lands, we set
    ``word.is_validated`` directly on the Python object: pd-book-tools'
    ``Word`` is a regular class (not frozen), so attribute assignment
    succeeds — but the flag is **lost** on envelope ``from_dict``
    round-trip because ``Word.to_dict`` does not serialize it. This
    matches the documented spec-23-C1 workaround.

    Body shape:
    - ``validated=None`` → toggle the current flag.
    - ``validated=bool`` → set to that exact value.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        current = bool(getattr(word, "is_validated", False))
        new_value = (not current) if body.validated is None else bool(body.validated)
        word.is_validated = new_value
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/validate-batch",
    response_model=PagePayload,
)
def validate_batch(
    project_id: str,
    page_index: int,
    body: ValidateBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/validate-batch`` — bulk validate/unvalidate a scope.

    Spec 23 §9 row 5: iterate over the requested scope and apply
    ``word.is_validated = body.validated`` to each. Scopes:

    - ``page``: every word on the page.
    - ``paragraph``: words in ``page.paragraphs[pi]`` for each ``pi`` in
      ``paragraph_indices``.
    - ``line``: words in ``page.lines[li]`` for each ``li`` in
      ``line_indices`` (or the single ``body.line_index`` for backward
      compatibility with the existing wire shape).
    - ``word``: each ``(li, wi)`` tuple in ``word_indices``.

    Single ``pstate.generation`` bump for the whole batch (one
    user-observable mutation event); one cached-envelope write.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        targets = _collect_validate_batch_targets(page, body)
        for word in targets:
            word.is_validated = body.validated
        # Bump generation even if targets was empty — observable from
        # the SPA as "I sent a validate-batch and got an updated
        # generation back".
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


def _collect_validate_batch_targets(page: Any, body: ValidateBatchRequest) -> list[Any]:
    """Walk the requested scope and return the list of target words.

    Defensive against missing ``page.lines`` / ``page.paragraphs`` —
    returns whatever subset is reachable. Out-of-range indices are
    silently skipped (the SPA may send stale indices from a re-OCRed
    page and shouldn't get a 500 for it; the batch is best-effort by
    design).
    """
    targets: list[Any] = []
    scope = body.scope
    if scope == "page":
        targets.extend(getattr(page, "words", []) or [])
        return targets
    if scope == "paragraph":
        paragraphs = getattr(page, "paragraphs", None) or []
        for pi in body.paragraph_indices:
            if 0 <= pi < len(paragraphs):
                targets.extend(getattr(paragraphs[pi], "words", []) or [])
        return targets
    if scope == "line":
        lines = getattr(page, "lines", None) or []
        line_ids: list[int] = list(body.line_indices)
        if body.line_index is not None:
            line_ids.append(body.line_index)
        for li in line_ids:
            if 0 <= li < len(lines):
                targets.extend(getattr(lines[li], "words", []) or [])
        return targets
    # Remaining branch: scope == "word".
    for li, wi in body.word_indices:
        w = _resolve_word(page, li, wi)
        if w is not None:
            targets.append(w)
    return targets


@router.post(
    "/{project_id}/pages/{page_index}/words/add",
    response_model=PagePayload,
)
def add_word(
    project_id: str,
    page_index: int,
    body: AddWordRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/add`` — insert a new word bbox."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/rebox",
    response_model=PagePayload,
)
def rebox_word(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ReboxWordRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/rebox`` — replace the word's bounding box."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/nudge",
    response_model=PagePayload,
)
def nudge_bbox(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: NudgeBboxRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/nudge`` — nudge bbox edges by pixel offsets."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/split",
    response_model=PagePayload,
)
def split_word(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: SplitWordRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/split`` — split one word bbox into two."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/merge",
    response_model=PagePayload,
)
def merge_words(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: MergeWordsRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/merge`` — merge this word with an adjacent one."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/erase-pixels",
    response_model=PagePayload,
)
def erase_pixels(
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ErasePixelsRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/erase-pixels`` — erase pixels inside a bbox region."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_payload_response(project_id, page_index)


def install_words_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the words router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AddWordRequest",
    "ApplyComponentRequest",
    "ApplyStyleRequest",
    "ErasePixelsRequest",
    "MergeWordsRequest",
    "NudgeBboxRequest",
    "ReboxWordRequest",
    "SplitWordRequest",
    "ToggleValidatedRequest",
    "UpdateWordGroundTruthRequest",
    "ValidateBatchRequest",
    "install_words_router",
    "router",
]
