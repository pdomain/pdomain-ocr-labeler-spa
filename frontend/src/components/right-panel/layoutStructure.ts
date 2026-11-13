export interface LayoutStructureLine {
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function stringOrUndefined(value: unknown): string | undefined {
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
