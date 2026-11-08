"""Read-only F2, P3, and source-to-source consolidated text previews."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pdomain_book_contracts.annotation.provenance import KnowledgeState
from pdomain_book_contracts.matching.models import MatchOperationKind, MatchToken
from pdomain_book_contracts.matching.pgdp_visible import match_document_from_pgdp_text
from pdomain_book_contracts.typography.spans import split_graphemes
from pydantic import BaseModel, TypeAdapter, ValidationError

from .source_alignment import load_source_evidence

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pdomain_book_contracts.layout.text_hints import LayoutTextHint
    from pdomain_book_contracts.matching.models import MatchDocument, MatchGraph
    from pdomain_book_contracts.matching.pgdp_bounded import PgdpBoundedMatch
    from pdomain_book_contracts.matching.pgdp_visible import PgdpVisibleDocument
    from pdomain_book_contracts.typography.spans import StyleSpan

    from .project_state import ProjectState
    from .source_alignment import SourceAlignmentEvidence


_PageTextMap = TypeAdapter(dict[str, str])


class SourceTextDocument(BaseModel):
    """One verified source page's raw and rendered text."""

    raw_text: str
    visible_text: str


class SourceTextRun(BaseModel):
    """One contiguous P3 text segment with exact F2 styles only."""

    text: str
    styles: tuple[str, ...]


class SourceTextLayoutLine(BaseModel):
    """One reliable P3 line carrying F2 verse metadata."""

    text: str
    stanza_index: int | None
    indent_hint: str | None
    grapheme_range: tuple[int, int] | None = None
    indent_columns: int | None = None


class SourceTextLayoutHint(BaseModel):
    """A source layout hint retained without inferring a reviewed structure."""

    kind: str
    source_ref: str
    lines: tuple[SourceTextLayoutLine, ...]


class SourceTextUnresolved(BaseModel):
    """A source span or layout hint intentionally left out of the preview."""

    source_kind: Literal["style_span", "layout_hint"]
    source_ref: str
    source_text: str
    reason: str


class ConsolidatedSourceText(BaseModel):
    """P3 wording with only exact F2-to-P3 formatting projections."""

    text: str
    runs: tuple[SourceTextRun, ...]
    layout_hints: tuple[SourceTextLayoutHint, ...]
    unresolved: tuple[SourceTextUnresolved, ...]


class SourceTextPreview(BaseModel):
    """Read-only source text response independent of OCR page state."""

    project_id: str
    page_index: int
    page_key: str | None
    available: bool
    f2: SourceTextDocument | None
    p3: SourceTextDocument | None
    consolidated: ConsolidatedSourceText | None
    warnings: tuple[str, ...]


def source_text_preview_for_page(state: ProjectState, page_index: int) -> SourceTextPreview:
    """Read sealed source payloads for a request-bound page without loading OCR."""
    project = state.loaded_project
    if project is None:
        return _unavailable_preview(project_id="", page_index=page_index, page_key=None)
    loaded = state.loaded_labeling_bundle
    if loaded is None:
        return _unavailable_preview(
            project_id=project.project_id,
            page_index=page_index,
            page_key=None,
        )
    f2_payload = loaded.artifact_payloads.get("f2")
    p3_payload = loaded.artifact_payloads.get("p3")
    evidence = load_source_evidence(state, page_index)
    page_key = (
        evidence.page_key
        if evidence is not None
        else _page_key_for_bundle(
            page_id=loaded.bundle.page_id,
            f2_payload=f2_payload,
            p3_payload=p3_payload,
        )
    )
    return build_source_text_preview(
        project_id=project.project_id,
        page_index=page_index,
        page_key=page_key,
        f2_payload=f2_payload,
        p3_payload=p3_payload,
        evidence=evidence,
    )


def build_source_text_preview(
    *,
    page_key: str,
    f2_payload: bytes | None,
    p3_payload: bytes | None,
    evidence: SourceAlignmentEvidence | None,
    project_id: str = "",
    page_index: int = 0,
) -> SourceTextPreview:
    """Build a source-only preview from verified snapshot bytes and persisted evidence."""
    if f2_payload is None or p3_payload is None:
        return _unavailable_preview(
            project_id=project_id,
            page_index=page_index,
            page_key=page_key,
        )
    f2_raw = _source_page_text(f2_payload, page_key=page_key, source_name="F2")
    p3_raw = _source_page_text(p3_payload, page_key=page_key, source_name="P3")
    parsed_f2 = match_document_from_pgdp_text(
        f2_raw.encode(), document_id="source-preview:f2", page_id=page_key, artifact_id="f2"
    )
    parsed_p3 = match_document_from_pgdp_text(
        p3_raw.encode(), document_id="source-preview:p3", page_id=page_key, artifact_id="p3"
    )
    f2_document = parsed_f2
    p3_document = parsed_p3
    result = SourceTextPreview(
        project_id=project_id,
        page_index=page_index,
        page_key=page_key,
        available=True,
        f2=SourceTextDocument(raw_text=f2_raw, visible_text=f2_document.visible_text),
        p3=SourceTextDocument(raw_text=p3_raw, visible_text=p3_document.visible_text),
        consolidated=None,
        warnings=(),
    )
    if evidence is None:
        return result.model_copy(
            update={"warnings": ("Consolidated source needs persisted F2-to-P3 alignment evidence.",)}
        )
    _validate_evidence_documents(evidence, parsed_f2=parsed_f2, parsed_p3=parsed_p3)
    consolidated = _consolidated_text(evidence=evidence, f2_raw=f2_raw)
    return result.model_copy(update={"consolidated": consolidated})


def _unavailable_preview(*, project_id: str, page_index: int, page_key: str | None) -> SourceTextPreview:
    return SourceTextPreview(
        project_id=project_id,
        page_index=page_index,
        page_key=page_key,
        available=False,
        f2=None,
        p3=None,
        consolidated=None,
        warnings=("Prepared PGDP F2/P3 sources are unavailable for this page.",),
    )


def _source_page_text(payload: bytes, *, page_key: str, source_name: str) -> str:
    text = _source_pages(payload, source_name=source_name).get(page_key)
    if text is None:
        return _missing_page(page_key=page_key, source_name=source_name)
    return text


def _source_pages(payload: bytes, *, source_name: str) -> dict[str, str]:
    try:
        return _PageTextMap.validate_json(payload)
    except ValidationError as exc:
        msg = f"Prepared {source_name} source snapshot is malformed"
        raise ValueError(msg) from exc


def _missing_page(*, page_key: str, source_name: str) -> str:
    msg = f"Prepared {source_name} source snapshot has no page {page_key}"
    raise ValueError(msg)


def _page_key_for_bundle(*, page_id: str, f2_payload: bytes | None, p3_payload: bytes | None) -> str:
    if f2_payload is None or p3_payload is None:
        return page_id
    f2_pages = _source_pages(f2_payload, source_name="F2")
    p3_pages = _source_pages(p3_payload, source_name="P3")
    page_stem = page_id.rsplit(":", maxsplit=1)[-1]
    candidates = tuple(
        key
        for key in f2_pages
        if key in p3_pages and (key == page_id or key.removesuffix(".png") == page_stem)
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        msg = f"Prepared F2/P3 source snapshots have no key for page {page_id}"
        raise ValueError(msg)
    msg = f"Prepared F2/P3 source snapshots have ambiguous keys for page {page_id}"
    raise ValueError(msg)


def _validate_evidence_documents(
    evidence: SourceAlignmentEvidence,
    *,
    parsed_f2: PgdpVisibleDocument,
    parsed_p3: PgdpVisibleDocument,
) -> None:
    if evidence.f2.visible_text != parsed_f2.visible_text:
        raise ValueError("prepared F2 visible text does not match persisted source alignment evidence")
    if evidence.p3.visible_text != parsed_p3.visible_text:
        raise ValueError("prepared P3 visible text does not match persisted source alignment evidence")
    if evidence.f2_to_p3.graph.source_document != evidence.f2.document:
        raise ValueError("Persisted F2-to-P3 graph does not reference the prepared F2 document")
    if evidence.f2_to_p3.graph.target_document != evidence.p3.document:
        raise ValueError("Persisted F2-to-P3 graph does not reference the prepared P3 document")


def _consolidated_text(*, evidence: SourceAlignmentEvidence, f2_raw: str) -> ConsolidatedSourceText:
    f2_locations = _source_locations(evidence.f2.document)
    p3_locations = _visible_locations(evidence.p3)
    exact = _accepted_window_matches(evidence.f2_to_p3)
    styles, unresolved_styles = _project_styles(
        style_spans=evidence.style_spans,
        f2=evidence.f2,
        p3=evidence.p3,
        f2_raw=f2_raw,
        f2_locations=f2_locations,
        p3_locations=p3_locations,
        exact=exact,
    )
    layout_hints, unresolved_layout = _project_layout_hints(
        hints=evidence.hints,
        p3=evidence.p3,
        f2_locations=f2_locations,
        exact=exact,
    )
    return ConsolidatedSourceText(
        text=evidence.p3.visible_text,
        runs=_runs(evidence.p3.visible_text, styles),
        layout_hints=layout_hints,
        unresolved=(*unresolved_styles, *unresolved_layout),
    )


def _source_locations(document: MatchDocument) -> dict[int, tuple[str, int]]:
    locations: dict[int, tuple[str, int]] = {}
    for token in _tokens(document):
        global_indices = tuple(
            dict.fromkeys(
                index
                for artifact_range in token.artifact_ranges
                for index in range(artifact_range.grapheme_start, artifact_range.grapheme_end)
            )
        )
        grapheme_count = len(split_graphemes(token.text))
        if grapheme_count != len(global_indices):
            continue
        for local_index, global_index in enumerate(global_indices):
            locations[global_index] = (token.token_id, local_index)
    return locations


def _visible_locations(document: PgdpVisibleDocument) -> dict[tuple[str, int], int]:
    locations: dict[tuple[str, int], int] = {}
    for entry in document.token_lookup:
        start, end = entry.visible_grapheme_range
        for local_index, visible_index in enumerate(range(start, end)):
            locations[(entry.token_id, local_index)] = visible_index
    return locations


def _exact_matches(graph: MatchGraph) -> dict[tuple[str, int], tuple[str, int]]:
    source = {token.token_id: token for token in _tokens(graph.source_document)}
    target = {token.token_id: token for token in _tokens(graph.target_document)}
    exact: dict[tuple[str, int], tuple[str, int]] = {}
    for relation in graph.best_alternative.relations:
        source_locations = _relation_locations(relation.source_token_ids, source)
        target_locations = _relation_locations(relation.target_token_ids, target)
        for operation in relation.operations:
            if operation.kind is not MatchOperationKind.MATCH:
                continue
            source_slice = source_locations[slice(*operation.source_grapheme_range)]
            target_slice = target_locations[slice(*operation.target_grapheme_range)]
            if len(source_slice) != len(target_slice):
                continue
            exact.update(
                {
                    source_location: target_location
                    for source_location, target_location in zip(source_slice, target_slice, strict=True)
                    if _grapheme(source_location, source) == _grapheme(target_location, target)
                }
            )
    return exact


def _accepted_window_matches(
    bounded: PgdpBoundedMatch,
) -> dict[tuple[str, int], tuple[str, int]]:
    """Project only local graphs whose persisted acceptance permits use."""
    exact: dict[tuple[str, int], tuple[str, int]] = {}
    for window in bounded.windows:
        if window.graph.accepted:
            exact.update(_exact_matches(window.graph))
    return exact


def _tokens(document: MatchDocument) -> tuple[MatchToken, ...]:
    return tuple(token for page in document.pages for line in page.lines for token in line.tokens)


def _relation_locations(
    token_ids: tuple[str, ...], tokens: Mapping[str, MatchToken]
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (token_id, index)
        for token_id in token_ids
        for index in range(len(split_graphemes(tokens[token_id].text)))
    )


def _grapheme(location: tuple[str, int], tokens: Mapping[str, MatchToken]) -> str:
    return split_graphemes(tokens[location[0]].text)[location[1]]


def _project_styles(
    *,
    style_spans: tuple[StyleSpan, ...],
    f2: PgdpVisibleDocument,
    p3: PgdpVisibleDocument,
    f2_raw: str,
    f2_locations: Mapping[int, tuple[str, int]],
    p3_locations: Mapping[tuple[str, int], int],
    exact: Mapping[tuple[str, int], tuple[str, int]],
) -> tuple[list[set[str]], tuple[SourceTextUnresolved, ...]]:
    p3_styles = [set[str]() for _ in split_graphemes(p3.visible_text)]
    unresolved: list[SourceTextUnresolved] = []
    for span in style_spans:
        if span.state is not KnowledgeState.POSITIVE:
            continue
        mapped_indices: list[int] = []
        missing_indices: list[int] = []
        for source_index in range(span.start, span.end):
            f2_location = f2_locations.get(source_index)
            if f2_location is None:
                continue
            p3_location = exact.get(f2_location)
            p3_visible_index = None if p3_location is None else p3_locations.get(p3_location)
            if p3_visible_index is None:
                missing_indices.append(source_index)
                continue
            p3_styles[p3_visible_index].add(span.label.value)
            mapped_indices.append(source_index)
        if missing_indices:
            unresolved.append(
                SourceTextUnresolved(
                    source_kind="style_span",
                    source_ref=span.rule_ref or "style_span",
                    source_text=_source_words(
                        source_indices=missing_indices,
                        f2=f2,
                        f2_raw=f2_raw,
                        f2_locations=f2_locations,
                    ),
                    reason="style graphemes are not exact F2-to-P3 matches",
                )
            )
        if not mapped_indices and not missing_indices:
            unresolved.append(
                SourceTextUnresolved(
                    source_kind="style_span",
                    source_ref=span.rule_ref or "style_span",
                    source_text="".join(split_graphemes(f2_raw)[span.start : span.end]),
                    reason="style span has no visible F2 graphemes",
                )
            )
    return p3_styles, tuple(unresolved)


def _source_words(
    *,
    source_indices: list[int],
    f2: PgdpVisibleDocument,
    f2_raw: str,
    f2_locations: Mapping[int, tuple[str, int]],
) -> str:
    visible_locations = _visible_locations(f2)
    visible = split_graphemes(f2.visible_text)
    values = tuple(
        visible[visible_index]
        for source_index in source_indices
        if (f2_location := f2_locations.get(source_index)) is not None
        and (visible_index := visible_locations.get(f2_location)) is not None
    )
    if values:
        return "".join(values)
    raw = split_graphemes(f2_raw)
    return "".join(raw[index] for index in source_indices if index < len(raw))


def _runs(text: str, styles: list[set[str]]) -> tuple[SourceTextRun, ...]:
    graphemes = split_graphemes(text)
    if len(graphemes) != len(styles):
        raise ValueError("P3 style projection does not cover its visible text")
    runs: list[SourceTextRun] = []
    for grapheme, labels in zip(graphemes, styles, strict=True):
        frozen_labels = tuple(sorted(labels))
        if runs and runs[-1].styles == frozen_labels:
            previous = runs.pop()
            runs.append(SourceTextRun(text=previous.text + grapheme, styles=frozen_labels))
        else:
            runs.append(SourceTextRun(text=grapheme, styles=frozen_labels))
    return tuple(runs)


def _project_layout_hints(
    *,
    hints: tuple[LayoutTextHint, ...],
    p3: PgdpVisibleDocument,
    f2_locations: Mapping[int, tuple[str, int]],
    exact: Mapping[tuple[str, int], tuple[str, int]],
) -> tuple[tuple[SourceTextLayoutHint, ...], tuple[SourceTextUnresolved, ...]]:
    mapped: list[SourceTextLayoutHint] = []
    unresolved: list[SourceTextUnresolved] = []
    p3_visible = _visible_locations(p3)
    for hint in hints:
        lines = _map_hint_lines(
            hint=hint,
            p3=p3,
            f2_locations=f2_locations,
            exact=exact,
            p3_visible=p3_visible,
        )
        if lines is None:
            unresolved.append(
                SourceTextUnresolved(
                    source_kind="layout_hint",
                    source_ref=hint.source_ref,
                    source_text=hint.text,
                    reason="layout hint does not have a complete exact F2-to-P3 line mapping",
                )
            )
            continue
        mapped.append(SourceTextLayoutHint(kind=hint.kind, source_ref=hint.source_ref, lines=lines))
    return tuple(mapped), tuple(unresolved)


def _map_hint_lines(
    *,
    hint: LayoutTextHint,
    p3: PgdpVisibleDocument,
    f2_locations: Mapping[int, tuple[str, int]],
    exact: Mapping[tuple[str, int], tuple[str, int]],
    p3_visible: Mapping[tuple[str, int], int],
) -> tuple[SourceTextLayoutLine, ...] | None:
    if hint.grapheme_range is None:
        return None
    source_locations = tuple(
        f2_locations[index] for index in range(*hint.grapheme_range) if index in f2_locations
    )
    if not source_locations:
        return None
    target_locations = tuple(exact.get(location) for location in source_locations)
    if any(location is None for location in target_locations):
        return None
    target_ids = {location[0] for location in target_locations if location is not None}
    target_lines = tuple(
        line
        for page in p3.document.pages
        for line in page.lines
        if any(token.token_id in target_ids for token in line.tokens)
    )
    if len(target_lines) != len(hint.lines):
        return None
    if any(any(token.token_id not in target_ids for token in line.tokens) for line in target_lines):
        return None
    visible = split_graphemes(p3.visible_text)
    source_indents = _source_line_indents(hint)
    result: list[SourceTextLayoutLine] = []
    for source_line, target_line, source_indent in zip(hint.lines, target_lines, source_indents, strict=True):
        first = target_line.tokens[0]
        last = target_line.tokens[-1]
        start = p3_visible.get((first.token_id, 0))
        end = p3_visible.get((last.token_id, len(split_graphemes(last.text)) - 1))
        if start is None or end is None:
            return None
        grapheme_range = (start, end + 1)
        result.append(
            SourceTextLayoutLine(
                text="".join(visible[slice(*grapheme_range)]),
                stanza_index=source_line.stanza_index,
                indent_hint=source_line.indent_hint,
                grapheme_range=grapheme_range,
                indent_columns=_indent_columns(source_line.indent_hint, fallback=source_indent),
            )
        )
    return tuple(result)


def _source_line_indents(hint: LayoutTextHint) -> tuple[int | None, ...]:
    """Read source-leading spaces in order without locating P3 text by value."""
    source_lines = iter(hint.text.splitlines())
    indents: list[int | None] = []
    for expected in hint.lines:
        for source_line in source_lines:
            content = source_line.lstrip(" \t")
            if content != expected.text:
                continue
            prefix = source_line[: len(source_line) - len(content)]
            indents.append(len(prefix) if prefix.strip(" ") == "" else None)
            break
        else:
            indents.append(None)
    return tuple(indents)


def _indent_columns(indent_hint: str | None, *, fallback: int | None) -> int | None:
    if indent_hint is None:
        return fallback
    columns, separator, unit = indent_hint.partition(" ")
    if separator and columns.isdecimal() and unit in {"space", "spaces"}:
        return int(columns)
    return fallback
