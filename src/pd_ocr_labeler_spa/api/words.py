"""``/api/projects/{project_id}/pages/{page_index}/words`` router — word mutations (§5.4).

Spec authority:
- ``docs/architecture/01-data-models.md §2`` — wire shapes for word routes.
- ``docs/architecture/02-backend.md §5.4`` — endpoint contracts.
- ``specs/23-page-payload-backend.md §9, §12, §13`` — mutation pattern:
  per-page lock → resolve word → call pd-book-tools method → bump
  ``PageState.generation`` → cached-envelope autosave (best-effort) →
  refreshed ``PagePayload`` via the keystone ``_page_payload`` helper
  in ``api/pages.py``.

Spec-23-C1 (#315) wired GT / style / component / validated / validate-batch.
Spec-23-C2 (#316) wired add / rebox / nudge / split / merge / erase-pixels.

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
- ``page.add_word(bbox, text)`` → ``Page.add_word_to_page(x1, y1, x2, y2, text)``
  (closest-line picked automatically; ``line_index`` request field is
  informational, not enforced).
- ``word.rebox(bbox)`` → ``Page.rebox_word(li, wi, x1, y1, x2, y2)``.
- ``word.nudge(left, right, top, bottom)`` →
  ``Page.nudge_word_bbox(li, wi, left, right, top, bottom, refine_after)``.
- ``word.split(orientation, marker_position)`` →
  ``Page.split_word(li, wi, split_fraction)`` — horizontal only;
  vertical split returns 400 ``mutation_failed``.
- ``page.merge_words(targets)`` — **no method exists** on pd-book-tools
  ``Page`` today (tracking issue ConcaveTrillion/pd-book-tools#53).
  Route delegates to per-line ``Line.merge_word_left(wi)`` /
  ``Line.merge_word_right(wi)`` (``pd_book_tools/ocr/block.py:785,789``).
- ``page.erase_pixels(bbox, fill_value)`` — **no method exists** in
  pd-book-tools (tracking issue #53). Handler mirrors the legacy
  labeler inline implementation at
  ``pd_ocr_labeler/state/page_state.py:1802``: clamp bbox to image
  extents, assign ``cv2_numpy_page_image[top:bottom, left:right] =
  fill_value``, then call ``page.finalize_page_structure()``.
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


def _mutation_failed(message: str) -> JSONResponse:
    """400 envelope used when a pd-book-tools mutation returns ``False``.

    pd-book-tools methods like ``Page.rebox_word``, ``Line.merge_word_left``,
    etc. return ``True``/``False`` rather than raising. The False return
    means the call was rejected (out-of-range index, invalid rect, no
    image to erase, etc.); spec §9 requires we surface that rather than
    silently no-op. ``mutation_failed`` is distinct from ``word_not_found``
    so the SPA can differentiate "couldn't find target" from "target
    found but mutation refused".
    """
    return JSONResponse(
        status_code=400,
        content=ApiError(error="mutation_failed", message=message).model_dump(),
    )


def _bbox_to_coords(bbox: BBox) -> tuple[int, int, int, int]:
    """Convert ``BBox(x, y, width, height)`` → ``(x1, y1, x2, y2)``.

    Spec wire-shape (``docs/architecture/01-data-models.md §1``):
    width/height are positive integers, so x2 = x + width and
    y2 = y + height are well-defined.
    """
    return bbox.x, bbox.y, bbox.x + bbox.width, bbox.y + bbox.height


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
    for the full mutation window: resolve → mutate → generation bump →
    cached-envelope write (spec §13).
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/add`` — insert a new word bbox.

    Spec 23 §9 row 6: ``page.add_word(bbox, text, line_index=None)`` →
    ``Page.add_word_to_page(x1, y1, x2, y2, text)`` in pd-book-tools.
    The request body's ``line_index`` is informational only:
    pd-book-tools picks the closest line by bbox centroid (see
    ``Page.add_word_to_page`` at
    ``pd_book_tools/ocr/page.py:2132``).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    x1, y1, x2, y2 = _bbox_to_coords(body.bbox)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = page.add_word_to_page(x1, y1, x2, y2, body.text)
        if not ok:
            return _mutation_failed(f"add_word_to_page rejected bbox=({x1}, {y1}, {x2}, {y2})")
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/rebox`` — replace the word's bounding box.

    Spec 23 §9 row 7: ``word.rebox(bbox)`` →
    ``Page.rebox_word(li, wi, x1, y1, x2, y2)`` in pd-book-tools
    (``pd_book_tools/ocr/page.py:2043``).
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
        x1, y1, x2, y2 = _bbox_to_coords(body.bbox)
        ok = page.rebox_word(line_index, word_index, x1, y1, x2, y2)
        if not ok:
            return _mutation_failed(
                f"rebox_word rejected line={line_index} word={word_index} bbox=({x1}, {y1}, {x2}, {y2})"
            )
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/nudge`` — nudge bbox edges by pixel offsets.

    Spec 23 §9 row 8: ``word.nudge(left, right, top, bottom)`` →
    ``Page.nudge_word_bbox(li, wi, left, right, top, bottom,
    refine_after)`` in pd-book-tools
    (``pd_book_tools/ocr/page.py:2571``).
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
        ok = page.nudge_word_bbox(
            line_index,
            word_index,
            body.left,
            body.right,
            body.top,
            body.bottom,
            body.refine_after,
        )
        if not ok:
            return _mutation_failed(
                f"nudge_word_bbox rejected line={line_index} word={word_index} "
                f"deltas=({body.left}, {body.right}, {body.top}, {body.bottom})"
            )
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/split`` — split one word bbox into two.

    Spec 23 §9 row 9: ``word.split(orientation, marker_position)`` →
    ``Page.split_word(li, wi, split_fraction)`` in pd-book-tools
    (``pd_book_tools/ocr/page.py:1756``). pd-book-tools only supports
    horizontal split today; ``direction='vertical'`` returns 400.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    if body.direction != "horizontal":
        return _mutation_failed(
            f"split_word direction={body.direction!r} not supported; "
            "pd-book-tools exposes only horizontal split"
        )

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        ok = page.split_word(line_index, word_index, body.x_fraction)
        if not ok:
            return _mutation_failed(
                f"split_word rejected line={line_index} word={word_index} fraction={body.x_fraction}"
            )
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/merge`` — merge with adjacent word.

    Spec 23 §9 row 10 names ``page.merge_words(targets)``, which is not
    implemented in pd-book-tools (tracking ConcaveTrillion/pd-book-tools#53).
    The route delegates to per-line ``Line.merge_word_left(wi)`` /
    ``Line.merge_word_right(wi)`` from ``pd_book_tools/ocr/block.py:785,789``.
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
        # Resolve the line — guaranteed in-range by _resolve_word success.
        line = page.lines[line_index]
        if body.direction == "left":
            ok = line.merge_word_left(word_index)
        else:
            ok = line.merge_word_right(word_index)
        if not ok:
            return _mutation_failed(
                f"merge_word_{body.direction} rejected line={line_index} word={word_index}"
            )
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/erase-pixels`` — erase pixels in a bbox.

    Spec 23 §9 row 11 names ``page.erase_pixels(bbox, fill_value=255)``,
    which does not exist in pd-book-tools (tracking ConcaveTrillion/
    pd-book-tools#53). The handler mirrors the legacy labeler's inline
    implementation at ``pd_ocr_labeler/state/page_state.py:1802``:

    1. Resolve ``page.cv2_numpy_page_image`` → numpy ndarray.
    2. Clamp the bbox to image extents.
    3. Assign ``image[top:bottom, left:right] = clamped_fill_value``.
    4. Call ``page.finalize_page_structure()`` so derived caches reset.

    Note that ``(line_index, word_index)`` is only used to anchor the
    operation onto a specific word for selection feedback; the actual
    erase rectangle is taken from ``body.bbox`` (image-coordinate, not
    word-relative).
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

        image = getattr(page, "cv2_numpy_page_image", None)
        shape = getattr(image, "shape", None)
        if image is None or shape is None or len(shape) < 2:
            return _mutation_failed("erase_pixels: page image unavailable (cv2_numpy_page_image)")

        try:
            height = int(shape[0])
            width = int(shape[1])
        except Exception:
            return _mutation_failed("erase_pixels: invalid page image shape")

        if width <= 0 or height <= 0:
            return _mutation_failed("erase_pixels: empty page image")

        x1, y1, x2, y2 = _bbox_to_coords(body.bbox)
        left = max(0, min(width, round(min(x1, x2))))
        right = max(0, min(width, round(max(x1, x2))))
        top = max(0, min(height, round(min(y1, y2))))
        bottom = max(0, min(height, round(max(y1, y2))))

        if right <= left or bottom <= top:
            return _mutation_failed(
                f"erase_pixels: rectangle out of bounds or empty "
                f"after clamp ({left}, {top}, {right}, {bottom})"
            )

        clamped_fill = max(0, min(255, int(body.fill_value)))
        try:
            image[top:bottom, left:right] = clamped_fill
        except Exception as exc:
            log.exception("erase_pixels: in-place assignment failed: %s", exc)
            return _mutation_failed(f"erase_pixels: in-place assignment failed: {exc}")

        # Mirror legacy: reset derived bbox/image caches.
        finalize = getattr(page, "finalize_page_structure", None)
        if callable(finalize):
            finalize()
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
