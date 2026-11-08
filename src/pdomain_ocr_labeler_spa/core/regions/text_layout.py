"""Resolve portable text evidence against OCR; source text never supplies a box.

Matching uses complete, unique token sequences after Unicode NFC and case
normalization. Missing or reordered tokens abstain. Physical columns require a
horizontal gutter at least four percent of page width and three median word
heights, two scan lines per column, and at least half their vertical extents
overlapping. These deterministic thresholds target left-to-right printed pages.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING, Literal

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_contracts.layout.regions import region_reading_order
from pdomain_book_contracts.layout.text_hints import (
    LayoutStructure,
    LayoutStructureLine,
    LayoutTableCell,
    LayoutTableRow,
    LayoutTextHint,
)
from pdomain_book_contracts.layout.types import LayoutRegion, RegionType
from pdomain_book_contracts.sources.pgdp.f2.structure import layout_hints_from_tokens
from pdomain_book_contracts.sources.pgdp.f2.tokens import read_f2_json_page
from pdomain_book_contracts.sources.pgdp.offsets import read_lexical_index
from pdomain_book_tools.typography import TypographyPageRecord
from pydantic import BaseModel, Field

from .coordinates import bounding_box_to_pixels
from .detector import DetectedRegion
from .models import FACET_LAYOUT_EVIDENCE, FACET_LINE_STRUCTURE, FACET_WORD_BOXES, FACET_WORD_TEXT

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pdomain_book_contracts.sources.pgdp.offsets import LexicalF2Index
    from pdomain_book_tools.ocr.page import Page

    from ..project_state import ProjectState
    from .detector import DetectorInput

log = logging.getLogger(__name__)
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class LayoutEvidence:
    """Page-selected text evidence and its optional stored word identities."""

    hints: tuple[LayoutTextHint, ...] = ()
    word_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    digest: str = ""


def _optional_payload(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("Cannot read optional layout evidence %s: %s", path, exc)
        return None


class _EditionHintGroup(BaseModel):
    page_ids: tuple[str, ...]
    hints: tuple[LayoutTextHint, ...]
    accepted: bool = True
    status: str = "accepted"


class _EditionHints(BaseModel):
    wire_schema: Literal["pdomain.edition-layout-hints"] = Field(alias="schema")
    version: Literal[1]
    groups: tuple[_EditionHintGroup, ...]


@lru_cache(maxsize=2)
def _f2_index(payload: bytes) -> LexicalF2Index:
    """Index a book once; tokenize only the requested page, never every page."""
    return read_lexical_index(payload)


def _edition_hints(payload: bytes, page_id: str) -> tuple[LayoutTextHint, ...]:
    data = _EditionHints.model_validate_json(payload)
    result: list[LayoutTextHint] = []
    for group in data.groups:
        if page_id not in group.page_ids:
            continue
        # Publication groups represent accepted paired operations only. If a
        # portable fixture supplies an explicit decision, reject nonaccepted.
        if not group.accepted or group.status != "accepted":
            continue
        result.extend(group.hints)
    return tuple(result)


def load_layout_evidence(state: ProjectState, page_index: int, page: Page | None = None) -> LayoutEvidence:
    """Read prepared artifact bytes or a loose mirror without source-data imports.

    A prepared caller must hold its existing labeling-page lease; its bundle
    bytes and stored IDs then belong to this page, including lazy books.
    """
    project = state.loaded_project
    if project is None:
        return LayoutEvidence()
    loaded = state.loaded_labeling_bundle
    f2: bytes | None = None
    sidecars: list[bytes] = []
    page_key = (
        project.image_paths[page_index].name
        if 0 <= page_index < len(project.image_paths)
        else str(page_index)
    )
    page_id = page_key
    word_ids: tuple[str, ...] = ()
    if loaded is not None:
        page_id = loaded.bundle.page_id
        for artifact in loaded.bundle.artifacts:
            payload = loaded.artifact_payloads.get(artifact.artifact_id)
            if payload is None:
                continue
            if artifact.relative_path.endswith("F2.json"):
                f2 = payload
            elif artifact.relative_path.endswith("layout-hints.json"):
                sidecars.append(payload)
            elif artifact.relative_path.endswith("page-record.json"):
                record = TypographyPageRecord.model_validate_json(payload)
                page_key = record.f2_page_key or page_key
        extra = loaded.artifact_payloads.get("layout_hints")
        if extra is not None:
            sidecars.append(extra)
        if page is not None:
            from .layout_structure import prepared_word_bindings

            bindings = prepared_word_bindings(page, loaded.bundle)
            inverse = {id(word): word_id for word_id, word in bindings.items()}
            if all(id(word) in inverse for word in page.words):
                word_ids = tuple(inverse[id(word)] for word in page.words)
    else:
        f2 = _optional_payload(project.project_root / "rounds" / "F2.json")
    optional = _optional_payload(project.project_root / "edition" / "layout-hints.json")
    if optional is not None:
        sidecars.append(optional)
    hints: list[LayoutTextHint] = []
    warnings: list[str] = []
    if f2 is not None:
        try:
            selected = read_f2_json_page(f2, page_key, _f2_index(f2))
            hints.extend(layout_hints_from_tokens(selected.parsed, source_ref="source/F2.json"))
        except (ValueError, TypeError, UnicodeError, KeyError) as exc:
            warnings.append(f"F2 layout evidence could not be read: {exc}")
    for payload in dict.fromkeys(sidecars):
        try:
            hints.extend(_edition_hints(payload, page_id))
        except (ValueError, TypeError, UnicodeError) as exc:
            warnings.append(f"Optional edition layout evidence could not be read: {exc}")
    digest = hashlib.sha256()
    digest.update(f2 or b"")
    digest.update(page_key.encode())
    digest.update(page_id.encode())
    for payload in dict.fromkeys(sidecars):
        digest.update(payload)
    return LayoutEvidence(tuple(hints), word_ids, tuple(warnings), digest.hexdigest())


def layout_evidence_digest(state: ProjectState, page_index: int) -> str:
    """Digest every source artifact consulted by the text detector."""
    return load_layout_evidence(state, page_index).digest


def review_layout_evidence(state: ProjectState, page_index: int, page: Page | None) -> LayoutEvidence:
    """Expose unmatched evidence for review without inventing a region box."""
    evidence = load_layout_evidence(state, page_index, page)
    warnings = list(evidence.warnings)
    words = _words(page) if page is not None else []
    for hint in evidence.hints:
        matches = _matches(hint.text, words)
        if len(matches) != 1:
            warnings.append(
                f"{hint.source} {hint.kind}: no unique ordered OCR match; "
                + "retained as unresolved source evidence."
            )
    if evidence.hints and not evidence.word_ids:
        warnings.append(
            "Detailed word-bound layout requires a prepared book with stored word IDs; "
            + "ordinary region review remains available."
        )
    return LayoutEvidence(evidence.hints, evidence.word_ids, tuple(warnings), evidence.digest)


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    return tuple(
        "".join(char for char in token if char.isalnum())
        for token in normalized.split()
        if any(char.isalnum() for char in token)
    )


@dataclass(frozen=True)
class _Word:
    index: int
    text: str
    box: Box
    line_index: int
    valid_geometry: bool


def _words(page: Page) -> list[_Word]:
    result: list[_Word] = []
    line_by_word = {id(word): index for index, line in enumerate(page.lines) for word in line.words}
    for index, word in enumerate(page.words):
        box = word.bounding_box
        pixels = (0, 0, 0, 0)
        if box.has_usable_coordinates:
            pixels = bounding_box_to_pixels(box, page_width=page.width, page_height=page.height)
        valid = pixels[0] < pixels[2] and pixels[1] < pixels[3]
        result.append(
            _Word(index, word.ground_truth_text or word.text, pixels, line_by_word.get(id(word), -1), valid)
        )
    return result


def _union(words: Sequence[_Word]) -> Box:
    return (
        min(word.box[0] for word in words),
        min(word.box[1] for word in words),
        max(word.box[2] for word in words),
        max(word.box[3] for word in words),
    )


def _matches(text: str, words: Sequence[_Word]) -> list[tuple[_Word, ...]]:
    target = _tokens(text)
    if not target:
        return []
    tokens: list[str] = []
    owners: list[_Word] = []
    starts: set[int] = set()
    ends: set[int] = set()
    for word in words:
        parts = _tokens(word.text)
        if not parts:
            continue
        starts.add(len(tokens))
        tokens.extend(parts)
        owners.extend([word] * len(parts))
        ends.add(len(tokens))
    matches: list[tuple[_Word, ...]] = []
    for start in sorted(starts):
        end = start + len(target)
        if end in ends and tuple(tokens[start:end]) == target:
            unique = {word.index: word for word in owners[start:end]}
            matches.append(tuple(unique.values()))
    return matches


def _columns(words: Sequence[_Word], page_width: int) -> list[tuple[_Word, ...]]:
    words = [word for word in words if word.valid_geometry]
    if len(words) < 4:
        return []
    height = statistics.median(word.box[3] - word.box[1] for word in words)
    min_gap = max(0.04 * page_width, 3 * height)
    # Full-width headings cross a genuine gutter; omit them from this
    # physical-column test rather than letting them bridge both columns.
    line_groups: dict[int, list[_Word]] = {}
    for word in words:
        line_groups.setdefault(word.line_index, []).append(word)
    headings: set[int] = set()
    for line_index, group in line_groups.items():
        ordered = sorted(group, key=lambda word: word.box[0])
        gaps = [right.box[0] - left.box[2] for left, right in pairwise(ordered)]
        box = _union(group)
        if box[2] - box[0] >= 0.7 * page_width and max(gaps, default=0) < min_gap:
            headings.add(line_index)
    narrow = [word for word in words if word.line_index not in headings]
    for left_word in sorted(narrow, key=lambda word: word.box[2]):
        cut = left_word.box[2]
        left = [word for word in narrow if word.box[2] <= cut]
        right = [word for word in narrow if word.box[0] >= cut + min_gap]
        if len(left) < 2 or len(right) < 2 or len(left) + len(right) != len(narrow):
            continue
        lbox, rbox = _union(left), _union(right)
        overlap = min(lbox[3], rbox[3]) - max(lbox[1], rbox[1])
        if overlap < 0.5 * min(lbox[3] - lbox[1], rbox[3] - rbox[1]):
            continue
        if min(len({word.box[1] for word in group}) for group in (left, right)) < 2:
            continue
        return [tuple(left), tuple(right)]
    return []


def _structure(
    hint: LayoutTextHint, matched: Sequence[_Word], word_ids: tuple[str, ...]
) -> LayoutStructure | None:
    if not word_ids or not all(word.index < len(word_ids) for word in matched):
        return None
    lines: list[LayoutStructureLine] = []
    used: set[int] = set()
    for line in hint.lines:
        if not line.text.strip():
            continue
        matches = _matches(line.text, matched)
        if len(matches) != 1 or used.intersection(word.index for word in matches[0]):
            return None
        bound = matches[0]
        used.update(word.index for word in bound)
        lines.append(
            LayoutStructureLine(
                text=line.text,
                word_ids=tuple(word_ids[word.index] for word in bound),
                stanza_index=line.stanza_index,
                indent_hint=line.indent_hint,
                measured_indent=float(min(word.box[0] for word in bound) - _union(matched)[0]),
            )
        )
    if not lines:
        return None
    kind = "poetry" if hint.kind == "poetry" else "blockquote"
    return LayoutStructure(kind=kind, lines=tuple(lines))


def _table_cells(hint: LayoutTextHint, matched: Sequence[_Word]) -> list[list[tuple[_Word, ...]]] | None:
    """Require semantic data evidence and a rectangular matched scan grid."""
    rows = hint.table_rows
    if len(rows) < 2 or len(rows[0]) < 2 or any(len(row) != len(rows[0]) for row in rows):
        return None
    attributes = dict(hint.attributes)
    explicit = attributes.get("role") == "table" or attributes.get("table_semantics") == "data"
    body = [cell for row in rows[1:] for cell in row]
    numeric = sum(any(char.isdigit() for char in cell) and len(cell.split()) <= 4 for cell in body)
    if not explicit and numeric < max(1, len(body) // 2):
        return None
    cells: list[list[tuple[_Word, ...]]] = []
    used: set[int] = set()
    height = statistics.median(word.box[3] - word.box[1] for word in matched)
    previous_bottom = -1
    column_lefts: list[int] = []
    for row in rows:
        bound_row: list[tuple[_Word, ...]] = []
        boxes: list[Box] = []
        for cell in row:
            found = _matches(cell, matched)
            if len(found) != 1 or used.intersection(word.index for word in found[0]):
                return None
            bound_row.append(found[0])
            used.update(word.index for word in found[0])
            boxes.append(_union(found[0]))
        if max(box[1] for box in boxes) - min(box[1] for box in boxes) > height:
            return None
        if min(box[1] for box in boxes) < previous_bottom:
            return None
        if any(left[2] >= right[0] for left, right in pairwise(boxes)):
            return None
        lefts = [box[0] for box in boxes]
        if column_lefts and any(
            abs(left - previous) > height for left, previous in zip(lefts, column_lefts, strict=True)
        ):
            return None
        column_lefts = lefts
        previous_bottom = max(box[3] for box in boxes)
        cells.append(bound_row)
    return cells if used == {word.index for word in matched} else None


def _table_structure(
    hint: LayoutTextHint, cells: Sequence[Sequence[Sequence[_Word]]], word_ids: tuple[str, ...]
) -> LayoutStructure | None:
    if not word_ids or any(word.index >= len(word_ids) for row in cells for cell in row for word in cell):
        return None
    rows = tuple(
        LayoutTableRow(
            cells=tuple(
                LayoutTableCell(text=text, word_ids=tuple(word_ids[word.index] for word in words))
                for text, words in zip(source, bound, strict=True)
            )
        )
        for source, bound in zip(hint.table_rows, cells, strict=True)
    )
    return LayoutStructure(kind="table", table_rows=rows)


@dataclass(frozen=True)
class TextLayoutDetector:
    """Portable F2/Gutenberg evidence plus conservative physical columns."""

    depends_on_facets: frozenset[str] = frozenset(
        {FACET_WORD_BOXES, FACET_WORD_TEXT, FACET_LINE_STRUCTURE, FACET_LAYOUT_EVIDENCE}
    )

    def __call__(self, detector_input: DetectorInput) -> list[DetectedRegion]:
        words = _words(detector_input.page)
        hints = detector_input.layout_hints
        result: list[DetectedRegion] = []
        consumed: set[int] = set()
        by_match: dict[tuple[int, ...], list[LayoutTextHint]] = {}
        for hint in hints:
            found = _matches(hint.text, words)
            if len(found) == 1 and all(word.valid_geometry for word in found[0]):
                key = tuple(word.index for word in found[0])
                by_match.setdefault(key, []).append(hint)
        matched_hints = tuple(hint for sources in by_match.values() for hint in sources)
        physical_columns = _columns(words, detector_input.page.width)
        has_data_table = any(
            _table_cells(hint, tuple(word for word in words if word.index in indices)) is not None
            for indices, sources in by_match.items()
            for hint in sources
            if hint.kind == "table_candidate"
        )
        if physical_columns and not has_data_table:
            result.extend(
                self._column_regions(
                    physical_columns,
                    matched_hints,
                    list(detector_input.layout_warnings),
                    detector_input.layout_word_ids,
                )
            )
            consumed.update(word.index for group in physical_columns for word in group)
        for indices, sources in sorted(by_match.items(), key=lambda item: -len(item[0])):
            if set(indices) <= consumed:
                continue
            matched = tuple(word for word in words if word.index in indices)
            primary = next((hint for hint in sources if hint.source == "f2"), sources[0])
            warnings = list(detector_input.layout_warnings)
            warnings.extend(warning for hint in sources for warning in hint.warnings)
            source_shapes = {
                (hint.kind, tuple((line.text, line.stanza_index, line.indent_hint) for line in hint.lines))
                for hint in sources
            }
            if len(source_shapes) > 1:
                warnings.append(
                    "F2 and Gutenberg disagree about role, lines, stanzas or indent; review both sources."
                )
            table_cells = _table_cells(primary, matched) if primary.kind == "table_candidate" else None
            if table_cells is not None:
                role = RegionRole.TABLE
            elif primary.kind in {"table_candidate", "column_flow"}:
                columns = _columns(matched, detector_input.page.width)
                if columns:
                    result.extend(
                        self._column_regions(columns, matched_hints, warnings, detector_input.layout_word_ids)
                    )
                    consumed.update(indices)
                    continue
                # Keep the unresolved evidence on an ordinary content proposal:
                # a table tag is never sufficient to choose a table label.
                role = RegionRole.PARAGRAPH
                warnings.append(
                    "Unresolved table layout: source markup alone does not establish "
                    + "a data table or physical columns."
                )
            else:
                role = RegionRole.POETRY if primary.kind == "poetry" else RegionRole.BLOCKQUOTE
            evidence: dict[str, object] = {
                "layout_hints": [hint.to_dict() for hint in sources],
                "layout_warnings": warnings,
                "structure_supported": bool(detector_input.layout_word_ids),
            }
            structure = (
                _structure(primary, matched, detector_input.layout_word_ids)
                if primary.kind in {"poetry", "blockquote"}
                else None
            )
            if table_cells is not None:
                structure = _table_structure(primary, table_cells, detector_input.layout_word_ids)
            if structure is not None:
                evidence["layout_structure"] = structure.to_dict()
            elif primary.kind in {"poetry", "blockquote"}:
                if detector_input.layout_word_ids:
                    warnings.append(
                        "Source lines cannot bind uniquely to separate OCR words; review region geometry."
                    )
                else:
                    warnings.append(
                        "Detailed verse lines require a prepared book with stored word IDs; "
                        + "ordinary region acceptance remains available."
                    )
            confidence = 0.9 if primary.source == "f2" else 0.7
            if len({hint.source for hint in sources}) > 1 and len(source_shapes) == 1:
                confidence = 0.95
            result.append(
                DetectedRegion(role=role, box=_union(matched), confidence=confidence, evidence=evidence)
            )
            consumed.update(indices)
        remaining = [word for word in words if word.index not in consumed]
        columns = _columns(remaining, detector_input.page.width)
        if columns:
            result.extend(self._column_regions(columns, (), list(detector_input.layout_warnings), ()))
        return result

    @staticmethod
    def _column_regions(
        columns: Sequence[Sequence[_Word]],
        hints: Sequence[LayoutTextHint],
        warnings: list[str],
        word_ids: tuple[str, ...],
    ) -> list[DetectedRegion]:
        group_id = (
            "columns-" + hashlib.sha256(str([_union(group) for group in columns]).encode()).hexdigest()[:16]
        )
        result: list[DetectedRegion] = []
        geometry = [
            LayoutRegion(type=RegionType.text, L=box[0], T=box[1], R=box[2], B=box[3])
            for box in (_union(group) for group in columns)
        ]
        groups = {_union(group): group for group in columns}
        for index, region in enumerate(region_reading_order(geometry)):
            words = groups[(region.L, region.T, region.R, region.B)]
            source_hints = [hint for hint in hints if len(_matches(hint.text, words)) == 1]
            parts: list[tuple[tuple[_Word, ...], LayoutTextHint | None]] = []
            assigned: set[int] = set()
            for source in source_hints:
                if source.kind not in {"poetry", "blockquote"}:
                    continue
                matched = _matches(source.text, words)[0]
                if assigned.intersection(word.index for word in matched):
                    continue
                parts.append((matched, source))
                assigned.update(word.index for word in matched)
            ordinary = tuple(word for word in words if word.index not in assigned)
            if ordinary:
                parts.append((ordinary, None))
            for chunk, source in sorted(parts, key=lambda part: (_union(part[0])[1], _union(part[0])[0])):
                role = RegionRole.PARAGRAPH
                kind: Literal["column_flow", "poetry", "blockquote"] = "column_flow"
                detailed = None
                confidence = 0.7
                chunk_warnings = list(warnings)
                if source is not None:
                    kind = "poetry" if source.kind == "poetry" else "blockquote"
                    role = RegionRole.POETRY if kind == "poetry" else RegionRole.BLOCKQUOTE
                    detailed = _structure(source, chunk, word_ids)
                    confidence = 0.9 if source.source == "f2" else 0.7
                    if detailed is None:
                        chunk_warnings.append(
                            "Detailed source lines require prepared word IDs and unique line matches."
                        )
                structure = LayoutStructure(
                    kind=kind,
                    column_group_id=group_id,
                    column_index=index,
                    reading_order=len(result),
                    lines=detailed.lines if detailed else (),
                )
                result.append(
                    DetectedRegion(
                        role=role,
                        box=_union(chunk),
                        confidence=confidence,
                        evidence={
                            "layout_structure": structure.to_dict(),
                            "layout_hints": [hint.to_dict() for hint in hints],
                            "layout_warnings": chunk_warnings,
                            "structure_supported": True,
                            "column_gap_min_page_share": 0.04,
                            "column_gap_min_word_heights": 3,
                            "column_vertical_overlap_min_share": 0.5,
                        },
                    )
                )
        return result
