import { useState } from "react";

interface LayoutStructureLine {
  text: string;
  word_ids: string[];
  word_signatures: string[];
  stanza_index?: number;
  indent_hint?: string;
  measured_indent?: number;
}

export interface LayoutStructureDraft {
  kind: "poetry" | "blockquote" | "table" | "column_flow";
  lines: LayoutStructureLine[];
  column_group_id?: string;
  column_index?: number;
  reading_order?: number;
  table_rows: LayoutStructureTableRow[];
}

interface LayoutStructureTableRow {
  cells: LayoutStructureTableCell[];
}

interface LayoutStructureTableCell {
  text: string;
  word_ids: string[];
  word_signatures: string[];
}

export interface LayoutStructureEditorProps {
  structure: LayoutStructureDraft;
  onChange: (next: LayoutStructureDraft) => void;
  disabled?: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

function nonNegativeIntegerOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function stringArray(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? [...value]
    : null;
}

function lineFromUnknown(value: unknown): LayoutStructureLine | null {
  if (!isRecord(value)) return null;
  const text = stringOrUndefined(value["text"]);
  if (text === undefined) return null;
  const wordIds = stringArray(value["word_ids"]);
  if (wordIds === null || wordIds.length === 0 || wordIds.some((wordId) => wordId === ""))
    return null;
  const rawSignatures = value["word_signatures"];
  const signatures = rawSignatures === undefined ? [] : stringArray(rawSignatures);
  if (signatures === null || (signatures.length !== 0 && signatures.length !== wordIds.length))
    return null;
  const stanzaIndex = nonNegativeIntegerOrUndefined(value["stanza_index"]);
  const indentHint = stringOrUndefined(value["indent_hint"]);
  const rawMeasuredIndent = value["measured_indent"];
  const measuredIndent =
    typeof rawMeasuredIndent === "number" && Number.isFinite(rawMeasuredIndent)
      ? rawMeasuredIndent
      : undefined;
  return {
    text,
    word_ids: wordIds,
    word_signatures: signatures,
    ...(stanzaIndex === undefined ? {} : { stanza_index: stanzaIndex }),
    ...(indentHint === undefined ? {} : { indent_hint: indentHint }),
    ...(measuredIndent === undefined ? {} : { measured_indent: measuredIndent }),
  };
}

function tableRowsFromUnknown(value: unknown): LayoutStructureTableRow[] | null {
  if (value === undefined) return [];
  if (!Array.isArray(value)) return null;
  const rows = value.map((row) => {
    if (!isRecord(row) || !Array.isArray(row["cells"])) return null;
    const cells = row["cells"].map((cell) => {
      if (!isRecord(cell)) return null;
      const text = stringOrUndefined(cell["text"]);
      if (text === undefined) return null;
      const wordIds = stringArray(cell["word_ids"]);
      if (wordIds === null || wordIds.length === 0) return null;
      const rawSignatures = cell["word_signatures"];
      const signatures = rawSignatures === undefined ? [] : stringArray(rawSignatures);
      if (signatures === null || (signatures.length !== 0 && signatures.length !== wordIds.length))
        return null;
      return { text, word_ids: wordIds, word_signatures: signatures };
    });
    return cells.every((cell): cell is LayoutStructureTableCell => cell !== null)
      ? { cells }
      : null;
  });
  return rows.every((row): row is LayoutStructureTableRow => row !== null) ? rows : null;
}

/** Parses only the portable reviewed-structure wire shape from API evidence. */
export function layoutStructureFromUnknown(value: unknown): LayoutStructureDraft | null {
  if (!isRecord(value)) return null;
  const kind = value["kind"];
  if (kind !== "poetry" && kind !== "blockquote" && kind !== "table" && kind !== "column_flow")
    return null;
  const rawLines = value["lines"] === undefined ? [] : value["lines"];
  if (!Array.isArray(rawLines)) return null;
  const lines = rawLines.map(lineFromUnknown);
  if (!lines.every((line): line is LayoutStructureLine => line !== null)) return null;
  const tableRows = tableRowsFromUnknown(value["table_rows"]);
  if (tableRows === null) return null;
  const columnGroupId = stringOrUndefined(value["column_group_id"]);
  if (lines.length === 0 && tableRows.length === 0 && columnGroupId === undefined) return null;
  const columnIndex = nonNegativeIntegerOrUndefined(value["column_index"]);
  const readingOrder = nonNegativeIntegerOrUndefined(value["reading_order"]);
  return {
    kind,
    lines,
    ...(columnGroupId === undefined ? {} : { column_group_id: columnGroupId }),
    ...(columnIndex === undefined ? {} : { column_index: columnIndex }),
    ...(readingOrder === undefined ? {} : { reading_order: readingOrder }),
    table_rows: tableRows,
  };
}

function optionalInteger(value: string): number | undefined {
  if (value === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}

function updatedLine(
  structure: LayoutStructureDraft,
  index: number,
  update: (line: LayoutStructureLine) => LayoutStructureLine,
): LayoutStructureDraft {
  return {
    ...structure,
    lines: structure.lines.map((line, lineIndex) => (lineIndex === index ? update(line) : line)),
  };
}

export function LayoutStructureEditor({
  structure,
  onChange,
  disabled = false,
}: LayoutStructureEditorProps) {
  const [draft, setDraft] = useState(structure);

  function change(next: LayoutStructureDraft): void {
    setDraft(next);
    onChange(next);
  }

  return (
    <section
      data-testid="region-layout-editor"
      className="flex flex-col gap-2 border-t border-border-1 pt-3"
    >
      <div>
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Reviewed layout</p>
        <p className="text-[11px] text-ink-3">
          Word order is fixed by the prepared book. Edit the review fields below.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-1.5 text-[11px]">
        <label className="flex flex-col gap-0.5 text-ink-3">
          Column group
          <input
            data-testid="region-layout-column-group"
            value={draft.column_group_id ?? ""}
            disabled={disabled}
            onChange={(event) => {
              const columnGroupId = stringOrUndefined(event.target.value);
              if (columnGroupId === undefined) {
                const { column_group_id: _columnGroupId, ...withoutColumnGroup } = draft;
                change(withoutColumnGroup);
              } else change({ ...draft, column_group_id: columnGroupId });
            }}
            className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-ink-3">
          Column
          <input
            data-testid="region-layout-column-index"
            type="number"
            min="0"
            value={draft.column_index ?? ""}
            disabled={disabled}
            onChange={(event) => {
              const columnIndex = optionalInteger(event.target.value);
              if (columnIndex === undefined) {
                const { column_index: _columnIndex, ...withoutColumnIndex } = draft;
                change(withoutColumnIndex);
              } else change({ ...draft, column_index: columnIndex });
            }}
            className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-ink-3">
          Reading order
          <input
            data-testid="region-layout-reading-order"
            type="number"
            min="0"
            value={draft.reading_order ?? ""}
            disabled={disabled}
            onChange={(event) => {
              const readingOrder = optionalInteger(event.target.value);
              if (readingOrder === undefined) {
                const { reading_order: _readingOrder, ...withoutReadingOrder } = draft;
                change(withoutReadingOrder);
              } else change({ ...draft, reading_order: readingOrder });
            }}
            className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
          />
        </label>
      </div>
      {draft.lines.map((line, index) => (
        <fieldset
          key={line.word_ids.join("\0")}
          className="flex flex-col gap-1 border border-border-1 rounded-sm p-2"
        >
          <legend className="px-1 text-[11px] text-ink-2">Line {index + 1}</legend>
          <p className="text-[11px] text-ink-1">{line.text}</p>
          <p
            data-testid={`region-layout-line-${index}-word-count`}
            className="text-[11px] text-ink-3"
          >
            {line.word_ids.length} word{line.word_ids.length === 1 ? "" : "s"}
          </p>
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            <label className="flex flex-col gap-0.5 text-ink-3">
              Stanza
              <input
                data-testid={`region-layout-line-${index}-stanza`}
                type="number"
                min="0"
                value={line.stanza_index ?? ""}
                disabled={disabled}
                onChange={(event) => {
                  const stanzaIndex = optionalInteger(event.target.value);
                  change(
                    updatedLine(draft, index, (current) => {
                      if (stanzaIndex === undefined) {
                        const { stanza_index: _stanzaIndex, ...withoutStanzaIndex } = current;
                        return withoutStanzaIndex;
                      }
                      return { ...current, stanza_index: stanzaIndex };
                    }),
                  );
                }}
                className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
              />
            </label>
            <label className="flex flex-col gap-0.5 text-ink-3">
              Source indent
              <input
                data-testid={`region-layout-line-${index}-indent`}
                value={line.indent_hint ?? ""}
                disabled={disabled}
                onChange={(event) => {
                  const indentHint = stringOrUndefined(event.target.value);
                  change(
                    updatedLine(draft, index, (current) => {
                      if (indentHint === undefined) {
                        const { indent_hint: _indentHint, ...withoutIndentHint } = current;
                        return withoutIndentHint;
                      }
                      return { ...current, indent_hint: indentHint };
                    }),
                  );
                }}
                className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
              />
            </label>
          </div>
        </fieldset>
      ))}
      {draft.table_rows.map((row, rowIndex) => (
        <div
          key={row.cells.map((cell) => cell.word_ids.join("\0")).join("\x01")}
          className="grid gap-1 text-[11px]"
          style={{ gridTemplateColumns: `repeat(${String(row.cells.length)}, minmax(0, 1fr))` }}
        >
          {row.cells.map((cell, cellIndex) => (
            <label
              key={`${String(rowIndex)}:${String(cellIndex)}`}
              className="flex flex-col gap-0.5 text-ink-3"
            >
              Table {rowIndex + 1}.{cellIndex + 1}
              <input
                data-testid={`region-layout-table-${rowIndex}-${cellIndex}`}
                value={cell.text}
                disabled={disabled}
                onChange={(event) => {
                  const tableRows = draft.table_rows.map((currentRow, currentRowIndex) =>
                    currentRowIndex === rowIndex
                      ? {
                          cells: currentRow.cells.map((currentCell, currentCellIndex) =>
                            currentCellIndex === cellIndex
                              ? { ...currentCell, text: event.target.value }
                              : currentCell,
                          ),
                        }
                      : currentRow,
                  );
                  change({ ...draft, table_rows: tableRows });
                }}
                className="border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-1"
              />
            </label>
          ))}
        </div>
      ))}
    </section>
  );
}
