type SourceAlignmentDecision = "pending" | "accepted" | "rejected" | "edited";

interface SourceAlignmentGroup {
  readonly group_id: string;
  readonly f2_text: string;
  readonly p3_text: string;
  readonly ocr_text: string;
  readonly disposition: string;
  readonly decision: SourceAlignmentDecision;
  readonly note: string;
  readonly reviewed_text: string | null;
  readonly warnings: readonly string[];
}

interface SourceAlignmentResult {
  readonly result_id: string;
  readonly input_generation: number;
  readonly groups: readonly SourceAlignmentGroup[];
  readonly layout_hints: readonly ProjectedLayoutHint[];
  readonly warnings: readonly string[];
  readonly unresolved: readonly UnresolvedFormatting[];
}

interface UnresolvedFormatting {
  readonly source_kind: string;
  readonly source_ref: string;
  readonly disposition: string;
  readonly warnings: readonly string[];
}

interface ProjectedLayoutLine {
  readonly text: string;
  readonly stanza_index: number | null;
  readonly indent_hint: string | null;
}

interface ProjectedLayoutHint {
  readonly kind: string;
  readonly source: string;
  readonly source_ref: string;
  readonly group_ids: readonly string[];
  readonly disposition: string;
  readonly lines: readonly ProjectedLayoutLine[];
}

export interface SourceAlignmentEnvelope {
  readonly generation: number;
  readonly stale: boolean;
  readonly result: SourceAlignmentResult | null;
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

function integerOf(record: Record<string, unknown>, key: string, label: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value;
}

function booleanOf(record: Record<string, unknown>, key: string, label: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
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

function parseGroup(value: unknown): SourceAlignmentGroup {
  const record = recordOf(value, "source alignment group");
  const decision = stringOf(record, "decision", "source alignment group decision");
  if (
    decision !== "pending" &&
    decision !== "accepted" &&
    decision !== "rejected" &&
    decision !== "edited"
  ) {
    throw new Error("source alignment group decision is not supported");
  }
  const warnings = record["warnings"];
  if (!Array.isArray(warnings) || !warnings.every((warning) => typeof warning === "string")) {
    throw new Error("source alignment group warnings must be strings");
  }
  return {
    group_id: stringOf(record, "group_id", "source alignment group group_id"),
    f2_text: stringOf(record, "f2_text", "source alignment group f2_text"),
    p3_text: stringOf(record, "p3_text", "source alignment group p3_text"),
    ocr_text: stringOf(record, "ocr_text", "source alignment group ocr_text"),
    disposition: stringOf(record, "disposition", "source alignment group disposition"),
    decision,
    note: stringOf(record, "note", "source alignment group note"),
    reviewed_text: nullableStringOf(
      record,
      "reviewed_text",
      "source alignment group reviewed_text",
    ),
    warnings,
  };
}

function parseUnresolvedFormatting(value: unknown): UnresolvedFormatting {
  const record = recordOf(value, "unresolved formatting");
  const warnings = record["warnings"];
  if (!Array.isArray(warnings) || !warnings.every((warning) => typeof warning === "string")) {
    throw new Error("unresolved formatting warnings must be strings");
  }
  return {
    source_kind: stringOf(record, "source_kind", "unresolved formatting source_kind"),
    source_ref: stringOf(record, "source_ref", "unresolved formatting source_ref"),
    disposition: stringOf(record, "disposition", "unresolved formatting disposition"),
    warnings,
  };
}

function parseProjectedLayoutHint(value: unknown): ProjectedLayoutHint {
  const record = recordOf(value, "projected layout hint");
  const hint = recordOf(record["hint"], "projected layout hint hint");
  const groupIds = record["group_ids"];
  const lines = hint["lines"];
  if (!Array.isArray(groupIds) || !groupIds.every((groupId) => typeof groupId === "string")) {
    throw new Error("projected layout hint group_ids must be strings");
  }
  if (!Array.isArray(lines)) throw new Error("projected layout hint lines must be an array");
  return {
    kind: stringOf(hint, "kind", "projected layout hint kind"),
    source: stringOf(hint, "source", "projected layout hint source"),
    source_ref: stringOf(hint, "source_ref", "projected layout hint source_ref"),
    group_ids: groupIds,
    disposition: stringOf(record, "disposition", "projected layout hint disposition"),
    lines: lines.map((line): ProjectedLayoutLine => {
      const lineRecord = recordOf(line, "projected layout line");
      const stanza = lineRecord["stanza_index"];
      if (
        stanza !== null &&
        (typeof stanza !== "number" || !Number.isSafeInteger(stanza) || stanza < 0)
      ) {
        throw new Error(
          "projected layout line stanza_index must be a non-negative integer or null",
        );
      }
      return {
        text: stringOf(lineRecord, "text", "projected layout line text"),
        stanza_index: stanza,
        indent_hint: nullableStringOf(
          lineRecord,
          "indent_hint",
          "projected layout line indent_hint",
        ),
      };
    }),
  };
}

export function parseSourceAlignmentEnvelope(value: unknown): SourceAlignmentEnvelope {
  const record = recordOf(value, "source alignment envelope");
  const rawResult = record["result"];
  if (rawResult === null) {
    return {
      generation: integerOf(record, "generation", "source alignment envelope generation"),
      stale: booleanOf(record, "stale", "source alignment envelope stale"),
      result: null,
    };
  }
  const result = recordOf(rawResult, "source alignment result");
  const groups = result["groups"];
  const projection = recordOf(result["projection"], "source alignment projection");
  const layoutHints = projection["layout_hints"];
  const unresolved = projection["unresolved"];
  const warnings = result["warnings"];
  if (!Array.isArray(groups)) throw new Error("source alignment result groups must be an array");
  if (!Array.isArray(layoutHints))
    throw new Error("source alignment projection layout_hints must be an array");
  if (!Array.isArray(unresolved))
    throw new Error("source alignment projection unresolved must be an array");
  if (!Array.isArray(warnings) || !warnings.every((warning) => typeof warning === "string")) {
    throw new Error("source alignment result warnings must be strings");
  }
  return {
    generation: integerOf(record, "generation", "source alignment envelope generation"),
    stale: booleanOf(record, "stale", "source alignment envelope stale"),
    result: {
      result_id: stringOf(result, "result_id", "source alignment result result_id"),
      input_generation: integerOf(
        result,
        "input_generation",
        "source alignment result input_generation",
      ),
      groups: groups.map(parseGroup),
      layout_hints: layoutHints.map(parseProjectedLayoutHint),
      warnings,
      unresolved: unresolved.map(parseUnresolvedFormatting),
    },
  };
}

export async function fetchSourceAlignment(
  projectId: string,
  pageIndex: number,
  signal: AbortSignal,
): Promise<SourceAlignmentEnvelope> {
  const response = await fetch(
    `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/source-alignment`,
    { signal },
  );
  const body: unknown = await response.json();
  if (!response.ok) throw new Error(`GET source alignment failed: ${String(response.status)}`);
  return parseSourceAlignmentEnvelope(body);
}
