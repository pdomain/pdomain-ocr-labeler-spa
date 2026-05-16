"""Domain models — the typed in-memory shapes shared by adapters + wire.

Spec authority:
- ``docs/architecture/01-data-models.md §1`` — all domain model shapes.
- ``docs/architecture/01-data-models.md`` lines 7-12 — convention: domain models
  live here and are reused by both the ``IStorage`` / ``IOCREngine``
  Protocols AND the wire (no separate DTO layer).

Adding new models: append; never reorder. Generated TS via
``make openapi-export`` keys on field name + position.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import OCRProvenance

_MAX_DISPLAY_DIMENSION = 1200


class Project(BaseModel):
    """One labeler project — ``docs/architecture/01-data-models.md §1`` lines 28-44.

    Mirrors legacy ``pd_ocr_labeler/models/project_model.py:9``.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_root: Path
    image_paths: list[Path]
    ground_truth_map: dict[str, str]
    version: str = "1.0"
    source_lib: str = "doctr-pd-labeled"
    total_pages: int
    saved_pages: int = 0
    current_page_index: int = 0
    include_images: bool = True
    copied_images: bool = False

    @property
    def page_count(self) -> int:
        return len(self.image_paths)


class PageSource(StrEnum):
    """How a page's OCR data was sourced — spec §1 ``PageSource``."""

    OCR = "ocr"
    CACHED_OCR = "cached_ocr"
    FILESYSTEM = "filesystem"
    FALLBACK = "fallback"


class MatchStatus(StrEnum):
    """Per-word match result — spec §1 ``MatchStatus``.

    Exactly five values, matching legacy ``WordMatch.match_status``.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    MISMATCH = "mismatch"
    UNMATCHED_OCR = "unmatched_ocr"
    UNMATCHED_GT = "unmatched_gt"


class BBox(BaseModel):
    """Image-coordinate bounding box — ``docs/architecture/01-data-models.md §1`` lines 137-143."""

    x: int
    y: int
    width: int
    height: int


class EncodedDims(BaseModel):
    """Source + display dimensions with scale factor.

    Algorithm matches legacy ``image_tabs._compute_encoded_dimensions:962``:
    display_width = min(src_width, 1200), display_height proportional (integer
    math), scale = display_width / src_width.
    """

    src_width: int
    src_height: int
    display_width: int
    display_height: int
    scale: float

    @classmethod
    def from_source_dims(cls, src_width: int, src_height: int) -> EncodedDims:
        display_width = min(src_width, _MAX_DISPLAY_DIMENSION)
        display_height = int(src_height * display_width / src_width)
        scale = display_width / src_width
        return cls(
            src_width=src_width,
            src_height=src_height,
            display_width=display_width,
            display_height=display_height,
            scale=scale,
        )


class CachedImageSet(BaseModel):
    """Optional filenames for each cached image type."""

    original: str | None = None
    lines: str | None = None
    paragraphs: str | None = None
    words: str | None = None
    matched_words: str | None = None


class RotationSource(StrEnum):
    """How a page's rotation was determined.

    Spec: ``docs/specs/2026-05-12-auto-rotation-design.md §PageRecord`` /
    issue #263 (M9.1).  Defaults to ``"none"`` (original orientation).
    """

    NONE = "none"
    AUTO = "auto"
    MANUAL = "manual"


class PageRecord(BaseModel):
    """Per-page metadata — spec §1 ``PageRecord``.

    The actual ``Page`` object lives in ``PageState`` in-memory and is
    NOT serialised here. Wire shapes that need page contents use
    ``PagePayload`` (defined in ``api/pages.py``).

    v2.2 rotation fields (spec §19 / issue #263):
    ``rotation_degrees`` tracks cumulative rotation applied since original
    image; ``rotation_source`` distinguishes auto (OCR+GT best-match),
    manual (user-initiated), and none (original orientation).
    """

    page_index: int
    page_number: int
    image_path: Path
    page_source: PageSource = PageSource.OCR
    ocr_failed: bool = False
    ocr_provenance: OCRProvenance | None = None
    saved_provenance: dict[str, Any] | None = None
    cached_images: CachedImageSet = Field(default_factory=CachedImageSet)
    # M9.1 rotation fields (issue #263 / spec §19)
    rotation_degrees: int = 0
    rotation_source: RotationSource = RotationSource.NONE
    # GAP-1: human-readable provenance one-liner for the source badge tooltip.
    # Assembled by api/pages.py::_build_provenance_summary at payload-build time.
    # None when no meaningful provenance data is available.
    provenance_summary: str | None = None


class WordMatch(BaseModel):
    """Per-word match result — spec §1 ``WordMatch``."""

    line_index: int
    word_index: int | None
    ocr_text: str
    ground_truth_text: str
    match_status: MatchStatus
    fuzz_score: float | None = None
    normalized_match: bool = False
    """True when ``match_status=exact`` was only achieved after normalization
    (long-s / ligature → ASCII). The UI renders a ``≈`` badge on this word's
    status icon. Default False (non-normalized exact or any other status).
    Added in issue #259 / spec
    ``docs/specs/2026-05-12-text-normalization-design.md``."""
    is_validated: bool = False
    text_style_labels: list[str] = Field(default_factory=list)
    word_components: list[str] = Field(default_factory=list)
    bbox: BBox
    word_id: str | None = None


class LineMatch(BaseModel):
    """Per-line rollup with pre-computed counters — spec §1 ``LineMatch``."""

    line_index: int
    paragraph_index: int | None
    # FO-7: block_index groups lines into top-level layout blocks.
    # Populated when the OCR engine exposes a block layer (e.g. via
    # ``Page.items[block_idx]``).  ``None`` until M3-proper wires a real
    # ``LocalDoctrPageLoader`` that maps lines → parent block indices.
    # The frontend ``selection-walk.ts`` uses this to enable block-level
    # sibling navigation; when ``None`` on all lines, block walk is a no-op.
    block_index: int | None = None
    ocr_line_text: str
    ground_truth_line_text: str
    word_matches: list[WordMatch]
    overall_match_status: MatchStatus
    exact_count: int
    fuzzy_count: int
    mismatch_count: int
    unmatched_gt_count: int
    unmatched_ocr_count: int
    validated_word_count: int
    total_word_count: int
    is_fully_validated: bool


class Selection(BaseModel):
    """Backend-canonical per-page UI selection state."""

    selection_mode: Literal["paragraph", "line", "word"] = "word"
    selected_paragraphs: set[int] = Field(default_factory=set)
    selected_lines: set[int] = Field(default_factory=set)
    selected_words: set[tuple[int, int]] = Field(default_factory=set)


class LineFilter(StrEnum):
    """Line display filter — spec §1 ``LineFilter``."""

    UNVALIDATED = "unvalidated"
    MISMATCHED = "mismatched"
    ALL = "all"


class JobStatus(StrEnum):
    """Job lifecycle state — spec §1 ``JobStatus``."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class JobType(StrEnum):
    """Discriminant for background job kind — spec §1 ``JobType``."""

    REFINE_BBOXES_PAGE = "refine_bboxes_page"
    EXPAND_REFINE_BBOXES_PAGE = "expand_refine_bboxes_page"
    RELOAD_OCR_PAGE = "reload_ocr_page"
    EXPORT = "export"
    SAVE_PROJECT = "save_project"
    REFINE_BBOXES_PROJECT = "refine_bboxes_project"


class JobProgress(BaseModel):
    """Progress counters for a running job — spec §1 ``JobProgress``."""

    current: int = 0
    total: int = 0
    current_page: int | None = None
    message: str = ""


class Job(BaseModel):
    """Background job record — spec §1 ``Job``. Mirrors pgdp-prep ``core/models.py``."""

    id: str
    type: JobType
    project_id: str | None
    status: JobStatus
    progress: JobProgress
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "BBox",
    "CachedImageSet",
    "EncodedDims",
    "Job",
    "JobProgress",
    "JobStatus",
    "JobType",
    "LineFilter",
    "LineMatch",
    "MatchStatus",
    "OCRProvenance",
    "PageRecord",
    "PageSource",
    "Project",
    "RotationSource",
    "Selection",
    "WordMatch",
]
