"""Domain models — the typed in-memory shapes shared by adapters + wire.

Spec authority:
- ``specs/01-data-models.md §1`` — all domain model shapes.
- ``specs/01-data-models.md`` lines 7-12 — convention: domain models
  live here and are reused by both the ``IStorage`` / ``IOCREngine``
  Protocols AND the wire (no separate DTO layer).

Adding new models: append; never reorder. Generated TS via
``make openapi-export`` keys on field name + position.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import OCRProvenance

_MAX_DISPLAY_DIMENSION = 1200


class Project(BaseModel):
    """One labeler project — ``specs/01-data-models.md §1`` lines 28-44.

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
    """``specs/01-data-models.md §1`` lines 55-59."""

    OCR = "ocr"
    CACHED_OCR = "cached_ocr"
    FILESYSTEM = "filesystem"
    FALLBACK = "fallback"


class MatchStatus(StrEnum):
    """Five-value match status — ``specs/01-data-models.md §1`` lines 87-93.

    Matches legacy ``pd_ocr_labeler.models.word_match.MatchStatus`` exactly.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    MISMATCH = "mismatch"
    UNMATCHED_OCR = "unmatched_ocr"
    UNMATCHED_GT = "unmatched_gt"


class BBox(BaseModel):
    """Image-coordinate bounding box — ``specs/01-data-models.md §1`` lines 137-143."""

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


class PageRecord(BaseModel):
    """Per-page metadata — ``specs/01-data-models.md §1`` lines 49-80.

    The actual ``Page`` object lives in ``PageState`` in-memory; it is
    NOT serialised through this model.
    """

    page_index: int
    page_number: int
    image_path: Path
    page_source: PageSource = PageSource.OCR
    ocr_failed: bool = False
    ocr_provenance: OCRProvenance | None = None
    saved_provenance: dict[str, Any] | None = None
    cached_images: CachedImageSet = Field(default_factory=CachedImageSet)


class WordMatch(BaseModel):
    """Per-word match result — ``specs/01-data-models.md §1`` lines 96-109."""

    line_index: int
    word_index: int | None
    ocr_text: str
    ground_truth_text: str
    match_status: MatchStatus
    fuzz_score: float | None = None
    is_validated: bool = False
    text_style_labels: list[str] = Field(default_factory=list)
    word_components: list[str] = Field(default_factory=list)
    bbox: BBox
    word_id: str | None = None


class LineMatch(BaseModel):
    """Per-line rollup with pre-computed counters — ``specs/01-data-models.md §1``."""

    line_index: int
    paragraph_index: int | None
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
    """Line filter toggle — ``specs/01-data-models.md §1`` lines 183-192."""

    UNVALIDATED = "unvalidated"
    MISMATCHED = "mismatched"
    ALL = "all"


__all__ = [
    "BBox",
    "CachedImageSet",
    "EncodedDims",
    "LineFilter",
    "LineMatch",
    "MatchStatus",
    "PageRecord",
    "PageSource",
    "Project",
    "Selection",
    "WordMatch",
]
