interface SourceTextBlock {
  readonly raw_text: string;
  readonly visible_text: string;
}

interface ConsolidatedRun {
  readonly text: string;
  readonly styles: readonly string[];
}

interface ConsolidatedLayoutLine {
  readonly text: string;
  readonly stanza_index: number | null;
  readonly indent_hint: string | null;
  /** Exact P3 visible-text grapheme range, when the backend accepted the mapping. */
  readonly grapheme_range?: readonly [number, number] | undefined;
  /** Exact F2 indentation projected to the P3 range, when the mapping is accepted. */
  readonly indent_columns?: number | null | undefined;
}

interface ConsolidatedLayoutHint {
  readonly kind: string;
  readonly source_ref: string;
  readonly lines: readonly ConsolidatedLayoutLine[];
}

interface UnresolvedSourceFormatting {
  readonly source_kind: string;
  readonly source_ref: string;
  readonly source_text: string;
  readonly reason: string;
}

export interface ConsolidatedSourceText {
  readonly text: string;
  readonly runs: readonly ConsolidatedRun[];
  readonly layout_hints: readonly ConsolidatedLayoutHint[];
  readonly unresolved: readonly UnresolvedSourceFormatting[];
}

export interface SourceTextPreview {
  readonly project_id: string;
  readonly page_index: number;
  readonly page_key: string | null;
  readonly available: boolean;
  readonly f2: SourceTextBlock | null;
  readonly p3: SourceTextBlock | null;
  readonly consolidated: ConsolidatedSourceText | null;
  readonly warnings: readonly string[];
}

function recordOf(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return Object.fromEntries(Object.entries(value));
}

function stringOf(record: Record<string, unknown>, key: string, label: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new Error(`${label} must be a string`);
  return value;
}

function nullableStringOf(
  record: Record<string, unknown>,
  key: string,
  label: string,
): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "string") throw new Error(`${label} must be a string or null`);
  return value;
}

function nonNegativeIntegerOf(record: Record<string, unknown>, key: string, label: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value;
}

function stringListOf(
  record: Record<string, unknown>,
  key: string,
  label: string,
): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`${label} must be an array of strings`);
  }
  return value;
}

function nullableBlockOf(record: Record<string, unknown>, key: string): SourceTextBlock | null {
  const value = record[key];
  if (value === null) return null;
  const block = recordOf(value, `source text preview ${key}`);
  return {
    raw_text: stringOf(block, "raw_text", `source text preview ${key} raw_text`),
    visible_text: stringOf(block, "visible_text", `source text preview ${key} visible_text`),
  };
}

function parseRun(value: unknown): ConsolidatedRun {
  const record = recordOf(value, "source text preview consolidated run");
  return {
    text: stringOf(record, "text", "source text preview consolidated run text"),
    styles: stringListOf(record, "styles", "source text preview consolidated run styles"),
  };
}

function parseLayoutLine(value: unknown): ConsolidatedLayoutLine {
  const record = recordOf(value, "source text preview consolidated layout line");
  const stanzaIndex = record["stanza_index"];
  if (
    stanzaIndex !== null &&
    (typeof stanzaIndex !== "number" || !Number.isSafeInteger(stanzaIndex) || stanzaIndex < 0)
  ) {
    throw new Error(
      "source text preview consolidated layout line stanza_index must be a non-negative integer or null",
    );
  }
  const graphemeRange = record["grapheme_range"];
  let parsedGraphemeRange: readonly [number, number] | undefined;
  if (graphemeRange !== undefined && graphemeRange !== null) {
    if (
      !Array.isArray(graphemeRange) ||
      graphemeRange.length !== 2 ||
      !graphemeRange.every((item) => Number.isSafeInteger(item) && item >= 0) ||
      graphemeRange[0] === undefined ||
      graphemeRange[1] === undefined ||
      graphemeRange[0] > graphemeRange[1]
    ) {
      throw new Error(
        "source text preview consolidated layout line grapheme_range must be an ordered pair of non-negative integers",
      );
    }
    parsedGraphemeRange = [graphemeRange[0], graphemeRange[1]];
  }
  const indentColumns = record["indent_columns"];
  let parsedIndentColumns: number | null | undefined;
  if (indentColumns === null) {
    parsedIndentColumns = null;
  } else if (indentColumns !== undefined) {
    if (
      typeof indentColumns !== "number" ||
      !Number.isSafeInteger(indentColumns) ||
      indentColumns < 0
    ) {
      throw new Error(
        "source text preview consolidated layout line indent_columns must be a non-negative integer or null",
      );
    }
    parsedIndentColumns = indentColumns;
  }
  return {
    text: stringOf(record, "text", "source text preview consolidated layout line text"),
    stanza_index: stanzaIndex,
    indent_hint: nullableStringOf(
      record,
      "indent_hint",
      "source text preview consolidated layout line indent_hint",
    ),
    ...(parsedGraphemeRange === undefined ? {} : { grapheme_range: parsedGraphemeRange }),
    ...(parsedIndentColumns === undefined ? {} : { indent_columns: parsedIndentColumns }),
  };
}

function parseLayoutHint(value: unknown): ConsolidatedLayoutHint {
  const record = recordOf(value, "source text preview consolidated layout hint");
  const lines = record["lines"];
  if (!Array.isArray(lines)) {
    throw new Error("source text preview consolidated layout hint lines must be an array");
  }
  return {
    kind: stringOf(record, "kind", "source text preview consolidated layout hint kind"),
    source_ref: stringOf(
      record,
      "source_ref",
      "source text preview consolidated layout hint source_ref",
    ),
    lines: lines.map(parseLayoutLine),
  };
}

function parseUnresolved(value: unknown): UnresolvedSourceFormatting {
  const record = recordOf(value, "source text preview unresolved formatting");
  return {
    source_kind: stringOf(
      record,
      "source_kind",
      "source text preview unresolved formatting source_kind",
    ),
    source_ref: stringOf(
      record,
      "source_ref",
      "source text preview unresolved formatting source_ref",
    ),
    source_text: stringOf(
      record,
      "source_text",
      "source text preview unresolved formatting source_text",
    ),
    reason: stringOf(record, "reason", "source text preview unresolved formatting reason"),
  };
}

function parseConsolidated(value: unknown): ConsolidatedSourceText | null {
  if (value === null) return null;
  const record = recordOf(value, "source text preview consolidated");
  const runs = record["runs"];
  const hints = record["layout_hints"];
  const unresolved = record["unresolved"];
  if (!Array.isArray(runs))
    throw new Error("source text preview consolidated runs must be an array");
  if (!Array.isArray(hints))
    throw new Error("source text preview consolidated layout_hints must be an array");
  if (!Array.isArray(unresolved))
    throw new Error("source text preview consolidated unresolved must be an array");
  const text = stringOf(record, "text", "source text preview consolidated text");
  const parsedRuns = runs.map(parseRun);
  if (parsedRuns.map((run) => run.text).join("") !== text) {
    throw new Error("source text preview consolidated runs must concatenate to consolidated text");
  }
  const parsedHints = suppressInvalidLayoutProjections(hints.map(parseLayoutHint), text);
  return {
    text,
    runs: parsedRuns,
    layout_hints: parsedHints,
    unresolved: unresolved.map(parseUnresolved),
  };
}

function splitGraphemes(text: string): readonly string[] {
  return [...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(text)].map(
    (segment) => segment.segment,
  );
}

function isLineBoundary(grapheme: string | undefined): boolean {
  return grapheme !== undefined && /[\r\n]/u.test(grapheme);
}

function suppressInvalidLayoutProjections(
  hints: readonly ConsolidatedLayoutHint[],
  text: string,
): readonly ConsolidatedLayoutHint[] {
  const graphemes = splitGraphemes(text);
  return hints.map((hint) => ({
    ...hint,
    lines: hint.lines.map((line) => {
      const range = line.grapheme_range;
      if (range === undefined) return line;
      const [start, end] = range;
      const valid =
        end <= graphemes.length &&
        (start === 0 || isLineBoundary(graphemes[start - 1])) &&
        (end === graphemes.length || isLineBoundary(graphemes[end])) &&
        graphemes.slice(start, end).join("") === line.text;
      if (valid) return line;
      const {
        grapheme_range: _ignoredRange,
        indent_columns: _ignoredIndentColumns,
        ...withoutProjection
      } = line;
      return withoutProjection;
    }),
  }));
}

export function parseSourceTextPreview(value: unknown): SourceTextPreview {
  const record = recordOf(value, "source text preview");
  const available = record["available"];
  if (typeof available !== "boolean")
    throw new Error("source text preview available must be a boolean");
  const f2 = nullableBlockOf(record, "f2");
  const p3 = nullableBlockOf(record, "p3");
  const consolidated = parseConsolidated(record["consolidated"]);
  if (available && (f2 === null || p3 === null)) {
    throw new Error("available source text preview must include F2 and P3 text");
  }
  return {
    project_id: stringOf(record, "project_id", "source text preview project_id"),
    page_index: nonNegativeIntegerOf(record, "page_index", "source text preview page_index"),
    page_key: nullableStringOf(record, "page_key", "source text preview page_key"),
    available,
    f2,
    p3,
    consolidated,
    warnings: stringListOf(record, "warnings", "source text preview warnings"),
  };
}

export async function fetchSourceTextPreview(
  projectId: string,
  pageIndex: number,
  signal?: AbortSignal,
): Promise<SourceTextPreview> {
  const response = await fetch(
    `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/source-text`,
    { signal: signal ?? null },
  );
  if (!response.ok) {
    throw new Error(`GET source text preview failed: ${String(response.status)}`);
  }
  return parseSourceTextPreview((await response.json()) as unknown);
}
