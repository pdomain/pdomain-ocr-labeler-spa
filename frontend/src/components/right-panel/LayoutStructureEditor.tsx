import {
  type LayoutStructureDraft,
  type LayoutStructureLine,
  stringOrUndefined,
} from "./layoutStructure";
import { useState } from "react";

export interface LayoutStructureEditorProps {
  structure: LayoutStructureDraft;
  onChange: (next: LayoutStructureDraft) => void;
  disabled?: boolean;
}

/** Parses only the portable reviewed-structure wire shape from API evidence. */

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
            data-testid={`region-layout-line-${String(index)}-word-count`}
            className="text-[11px] text-ink-3"
          >
            {line.word_ids.length} word{line.word_ids.length === 1 ? "" : "s"}
          </p>
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            <label className="flex flex-col gap-0.5 text-ink-3">
              Stanza
              <input
                data-testid={`region-layout-line-${String(index)}-stanza`}
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
                data-testid={`region-layout-line-${String(index)}-indent`}
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
                data-testid={`region-layout-table-${String(rowIndex)}-${String(cellIndex)}`}
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
