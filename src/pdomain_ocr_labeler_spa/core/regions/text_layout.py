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
from pdomain_book_contracts.matching.pgdp_layout_projection import PgdpAlignmentDisposition
from pdomain_book_contracts.sources.pgdp.f2.structure import layout_hints_from_tokens
from pdomain_book_contracts.sources.pgdp.f2.tokens import read_f2_json_page
from pdomain_book_contracts.sources.pgdp.offsets import read_lexical_index
from pdomain_book_contracts.typography.spans import split_graphemes
from pdomain_book_tools.typography import TypographyPageRecord
from pydantic import BaseModel, Field

from ..source_alignment import alignment_from_page, load_source_evidence, ocr_signature
from .coordinates import bounding_box_to_pixels
from .detector import DetectedRegion
from .models import FACET_LAYOUT_EVIDENCE, FACET_LINE_STRUCTURE, FACET_WORD_BOXES, FACET_WORD_TEXT

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pdomain_book_contracts.sources.pgdp.offsets import LexicalF2Index
    from pdomain_book_tools.ocr.page import Page

    from ..project_state import ProjectState
    from ..source_alignment import SourceAlignmentResult
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
    source_alignment: SourceAlignmentResult | None = None
    composed_source: bool = False


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
    source = load_source_evidence(state, page_index)
    if source is not None:
        pstate = state.get_page_state(page_index)
        result = pstate.source_alignment if pstate is not None else None
        if result is None and page is not None:
            result = alignment_from_page(page)
        source_warnings: tuple[str, ...] = ()
        if result is None:
            source_warnings = ("Run source alignment to project F2 formatting through P3 onto scan OCR.",)
        elif page is not None and result.ocr_signature != ocr_signature(page):
            result = None
            source_warnings = ("Source alignment is stale; rerun it for current OCR.",)
        digest = hashlib.sha256(source.model_dump_json(by_alias=True).encode())
        if result is not None:
            digest.update(result.model_dump_json().encode())
        edition: list[LayoutTextHint] = []
        optional_payloads: list[bytes] = []
        if loaded is not None:
            for artifact in loaded.bundle.artifacts:
                if artifact.relative_path.endswith("layout-hints.json"):
                    payload = loaded.artifact_payloads.get(artifact.artifact_id)
                    if payload is not None:
                        optional_payloads.append(payload)
            payload = loaded.artifact_payloads.get("layout_hints")
            if payload is not None:
                optional_payloads.append(payload)
        payload = _optional_payload(project.project_root / "edition" / "layout-hints.json")
        if payload is not None:
            optional_payloads.append(payload)
        for payload in dict.fromkeys(optional_payloads):
            digest.update(payload)
            try:
                edition.extend(_edition_hints(payload, source.page_id))
            except (ValueError, TypeError, UnicodeError) as exc:
                source_warnings += (f"Optional edition layout evidence could not be read: {exc}",)
        for hint in edition:
            if not any(_tokens(hint.text) == _tokens(original.text) for original in source.hints):
                source_warnings += (
                    f"{hint.source} {hint.kind}: retained; no corresponding composed source span.",
                )
        return LayoutEvidence(
            source.hints + tuple(edition), (), source_warnings, digest.hexdigest(), result, True
        )
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
    if evidence.composed_source:
        result = evidence.source_alignment
        extra = (
            tuple(
                f"{item.source_kind}: {item.disposition.value}; " + "; ".join(item.warnings)
                for item in result.projection.unresolved
            )
            if result is not None
            else ()
        )
        return LayoutEvidence(evidence.hints, (), evidence.warnings + extra, evidence.digest, result, True)
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


def _columns(
    words: Sequence[_Word],
    page_width: int,
    *,
    gutter_page_share: float = 0.04,
    gutter_word_heights: float = 3,
) -> list[tuple[_Word, ...]]:
    words = [word for word in words if word.valid_geometry]
    if len(words) < 4:
        return []
    height = statistics.median(word.box[3] - word.box[1] for word in words)
    min_gap = max(gutter_page_share * page_width, gutter_word_heights * height)
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
        if detector_input.composed_source:
            return composed_layout_regions(
                page=detector_input.page,
                result=detector_input.source_alignment,
                warnings=detector_input.layout_warnings,
                hints=detector_input.layout_hints,
            )
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
                self.column_regions(
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
                        self.column_regions(columns, matched_hints, warnings, detector_input.layout_word_ids)
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
            elif primary.kind == "formatted_block":
                role = RegionRole.PARAGRAPH
                warnings.append(
                    "Formatted block preserves source layout; its marker does not establish verse."
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
            result.extend(self.column_regions(columns, (), list(detector_input.layout_warnings), ()))
        return result

    @staticmethod
    def column_regions(
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


def _formatted_verse(hint: LayoutTextHint) -> bool:
    """Require sentence-case verse and stanza/indent evidence beyond a marker."""
    lines = [line.text.strip() for line in hint.lines if line.text.strip()]
    if len(lines) < 3 or any("..." in line or " . " in line for line in lines):
        return False
    alnum = [char for line in lines for char in line if char.isalnum()]
    if not alnum or sum(char.isdigit() for char in alnum) / len(alnum) > 0.05:
        return False
    headings = {"chapter", "part", "book", "section", "contents"}
    if any(_tokens(line)[0] in headings and len(_tokens(line)) <= 6 for line in lines[:2] if _tokens(line)):
        return False
    sentence_lines = sum(
        sum(token[0].islower() for token in line.split() if token and token[0].isalpha()) >= 2
        for line in lines
    )
    if sentence_lines / len(lines) < 0.75:
        return False
    stanzas = {line.stanza_index for line in hint.lines if line.stanza_index is not None}
    if len(stanzas) < 2 and not any(line.indent_hint for line in hint.lines):
        return False
    capitals = sum(next((char for char in line if char.isalpha()), "").isupper() for line in lines)
    return capitals / len(lines) >= 0.75 and statistics.median(len(line.split()) for line in lines) <= 14


def _composed_lines(
    hint: LayoutTextHint, result: SourceAlignmentResult, words: Sequence[_Word]
) -> tuple[list[LayoutStructureLine], tuple[_Word, ...]]:
    """Resolve source line ranges through groups, including changed wording."""
    if hint.grapheme_range is None:
        return [], ()
    start, end = hint.grapheme_range
    source = "".join(split_graphemes(result.f2.visible_text)[start:end])
    groups = {token: group for group in result.groups for token in group.f2_token_ids}
    by_index = {word.index: word for word in words}
    lines: list[LayoutStructureLine] = []
    bound_words: dict[int, _Word] = {}
    used_source: set[str] = set()
    cursor = start
    line_index = 0
    for raw in source.splitlines(keepends=True):
        line_end = cursor + len(split_graphemes(raw))
        if not raw.strip():
            cursor = line_end
            continue
        if line_index >= len(hint.lines):
            return [], ()
        metadata = hint.lines[line_index]
        line_index += 1
        source_tokens = tuple(
            item.token_id
            for item in result.f2.token_lookup
            if item.visible_grapheme_range[0] < line_end and item.visible_grapheme_range[1] > cursor
        )
        cursor = line_end
        if raw.strip() != metadata.text.strip() or not source_tokens:
            continue
        linked = {groups[token].group_id: groups[token] for token in source_tokens if token in groups}
        if len(
            {token for group in linked.values() for token in group.f2_token_ids} & set(source_tokens)
        ) != len(source_tokens):
            continue
        if any(
            group.disposition not in {PgdpAlignmentDisposition.ACCEPTED, PgdpAlignmentDisposition.CHANGED}
            or group.decision == "rejected"
            or not group.ocr_refs
            for group in linked.values()
        ):
            continue
        # A split/join crossing a source line cannot be assigned arbitrarily.
        if any(set(group.f2_token_ids) - set(source_tokens) for group in linked.values()):
            continue
        ids = tuple(
            dict.fromkeys(source_id for group in linked.values() for source_id in group.source_word_ids)
        )
        indices = tuple(
            dict.fromkeys(ref.reading_order for group in linked.values() for ref in group.ocr_refs)
        )
        matched = tuple(by_index[index] for index in indices if index in by_index)
        if (
            not ids
            or used_source.intersection(ids)
            or len(matched) != len(indices)
            or not all(word.valid_geometry for word in matched)
        ):
            continue
        used_source.update(ids)
        bound_words.update((word.index, word) for word in matched)
        lines.append(
            LayoutStructureLine(
                text=metadata.text,
                word_ids=ids,
                stanza_index=metadata.stanza_index,
                indent_hint=metadata.indent_hint,
                measured_indent=float(min(word.box[0] for word in matched)),
            )
        )
    if lines and bound_words:
        left = min(word.box[0] for word in bound_words.values())
        lines = [
            line.model_copy(update={"measured_indent": line.measured_indent - left})
            if line.measured_indent is not None
            else line
            for line in lines
        ]
    return lines, tuple(bound_words.values())


def composed_layout_regions(
    *,
    page: Page,
    result: SourceAlignmentResult | None,
    warnings: tuple[str, ...] = (),
    hints: tuple[LayoutTextHint, ...] = (),
) -> list[DetectedRegion]:
    """Use only composed links for textual layout; preserve unmatched geometry."""
    if result is None or result.ocr_signature != ocr_signature(page):
        return []
    words = _words(page)
    regions: list[DetectedRegion] = []
    consumed: set[int] = set()
    for projected in result.projection.layout_hints:
        hint = projected.hint
        supporting = tuple(
            item for item in hints if item.source != hint.source and _tokens(item.text) == _tokens(hint.text)
        )
        lines, matched = _composed_lines(hint, result, words)
        if not matched:
            continue
        verse = hint.kind == "poetry" or (
            hint.kind == "formatted_block"
            and (any(item.kind == "poetry" for item in supporting) or _formatted_verse(hint))
        )
        role = (
            RegionRole.POETRY
            if verse
            else RegionRole.BLOCKQUOTE
            if hint.kind == "blockquote"
            else RegionRole.PARAGRAPH
        )
        evidence: dict[str, object] = {
            "alignment_result_id": result.result_id,
            "alignment_group_ids": list(projected.group_ids),
            "layout_hints": [hint.to_dict(), *(item.to_dict() for item in supporting)],
            "projection_disposition": projected.disposition.value,
            "layout_warnings": [*warnings, *projected.warnings],
            "structure_supported": bool(lines),
            "verse_text_evidence": verse and hint.kind == "formatted_block",
        }
        if verse or hint.kind == "blockquote":
            structure = LayoutStructure(kind="poetry" if verse else "blockquote", lines=tuple(lines))
            evidence["layout_structure"] = structure.to_dict()
        regions.append(DetectedRegion(role=role, box=_union(matched), confidence=0.8, evidence=evidence))
        consumed.update(word.index for word in matched)
    # Columns are physical scan facts. Resolve from mapped words first; retain
    # unlinked captions/words separately rather than stretching source spans.
    mapped = {
        ref.reading_order
        for group in result.groups
        if group.disposition in {PgdpAlignmentDisposition.ACCEPTED, PgdpAlignmentDisposition.CHANGED}
        and group.decision != "rejected"
        for ref in group.ocr_refs
    }
    remaining = [word for word in words if word.index not in consumed]
    if any(region.role == RegionRole.POETRY for region in regions) or any(
        item.hint.kind == "formatted_block" and not _formatted_verse(item.hint)
        for item in result.projection.layout_hints
    ):
        return regions
    column_words = _column_body_words(remaining, mapped, page.width)
    columns = _mapped_columns(column_words, mapped, page.width, original_words=words)
    if not columns:
        columns = _columns(column_words, page.width)
    if columns and not _supported_text_columns(columns, words):
        columns = []
    if columns:
        resolved = columns
        regions.extend(TextLayoutDetector.column_regions(resolved, (), list(warnings), ()))
        for region in regions:
            if "column_gap_min_page_share" in region.evidence:
                region.evidence["column_gap_min_page_share"] = 0.02
                region.evidence["column_gap_min_word_heights"] = 1
                region.evidence["column_vertical_overlap_tolerance_word_heights"] = 1
                region.evidence["column_min_complete_original_lines"] = 3
                region.evidence["alignment_result_id"] = result.result_id
        assigned = {word.index for column in resolved for word in column}
        unlinked_lines: dict[int, list[_Word]] = {}
        for word in remaining:
            if word.valid_geometry and word.index not in assigned:
                unlinked_lines.setdefault(word.line_index, []).append(word)
        regions.extend(
            DetectedRegion(
                role=RegionRole.PARAGRAPH,
                box=_union(line),
                confidence=0.5,
                evidence={
                    "alignment_result_id": result.result_id,
                    "layout_warnings": ["Unmatched or spanning scan content retained for review."],
                },
            )
            for line in unlinked_lines.values()
        )
    return regions


def _column_body_words(words: Sequence[_Word], mapped: set[int], page_width: int) -> list[_Word]:
    """Keep isolated shared headings and unmatched small captions outside columns."""
    usable = [word for word in words if word.valid_geometry]
    if not usable:
        return []
    height = statistics.median(word.box[3] - word.box[1] for word in usable)
    by_line: dict[int, list[_Word]] = {}
    for word in usable:
        by_line.setdefault(word.line_index, []).append(word)
    rows = sorted(by_line.values(), key=lambda row: (_union(row)[1], _union(row)[0]))
    excluded: set[int] = set()
    for count in range(1, min(3, len(rows) - 1) + 1):
        leading = [word for row in rows[:count] for word in row]
        box = _union(leading)
        if box[0] < page_width / 2 < box[2] and _union(rows[count])[1] - box[3] >= 4 * height:
            excluded.update(word.index for word in leading)
            break
    for row in rows:
        box = _union(row)
        if box[3] - box[1] < 0.7 * height and not any(word.index in mapped for word in row):
            excluded.update(word.index for word in row)
    return [word for word in usable if word.index not in excluded]


def _mapped_columns(
    words: Sequence[_Word], mapped: set[int], page_width: int, *, original_words: Sequence[_Word]
) -> list[tuple[_Word, ...]]:
    """Use mapped gutter candidates and full scan extents, retaining spanning words."""
    usable = [word for word in words if word.valid_geometry]
    if not usable:
        return []
    height = statistics.median(word.box[3] - word.box[1] for word in usable)
    gap = max(0.02 * page_width, height)
    best: list[tuple[_Word, ...]] = []
    for word in usable:
        if not 0.3 * page_width <= word.box[2] <= 0.7 * page_width:
            continue
        cut = word.box[2]
        left = tuple(item for item in usable if item.box[2] <= cut)
        right = tuple(item for item in usable if item.box[0] >= cut + gap)
        if any(len({item.line_index for item in column}) < 3 for column in (left, right)):
            continue
        if any(sum(item.index in mapped for item in column) < 3 for column in (left, right)):
            continue
        if not _supported_text_columns((left, right), original_words):
            continue
        lbox, rbox = _union(left), _union(right)
        overlap = min(lbox[3], rbox[3]) - max(lbox[1], rbox[1])
        if overlap + height < 0.5 * min(lbox[3] - lbox[1], rbox[3] - rbox[1]):
            continue
        if len(left) + len(right) > sum(len(column) for column in best):
            best = [left, right]
    return best


def _supported_text_columns(columns: Sequence[Sequence[_Word]], original_words: Sequence[_Word]) -> bool:
    """Require columns independently supported by complete original OCR rows."""
    if len(columns) != 2 or any(not column for column in columns):
        return False
    bounds = [_union(column) for column in columns]
    original_lines: dict[int, list[_Word]] = {}
    for word in original_words:
        if word.valid_geometry and word.line_index >= 0:
            original_lines.setdefault(word.line_index, []).append(word)
    line_bounds = {index: _union(line) for index, line in original_lines.items()}
    for column, box in zip(columns, bounds, strict=True):
        complete = sum(
            box[0] <= line_bounds[index][0] and line_bounds[index][2] <= box[2]
            for index in {word.line_index for word in column}
            if index in line_bounds
        )
        if complete < 3:
            return False
    return True
