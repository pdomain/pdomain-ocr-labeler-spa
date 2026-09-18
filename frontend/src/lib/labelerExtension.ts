// labelerExtension.ts — runtime-checked accessor for
// PageRecord.extensions["labeler"].
//
// `PageRecord.extensions` is a namespaced dict of `{ [key: string]: unknown }`
// blobs (api/types.ts) — a loose backend contract, not a typed schema.
// Three call sites (ProjectPage.tsx, PageActionsCompact.tsx x2) each used to
// cast this blob straight to a hand-picked shape with no runtime check. A
// TypeScript `as` cast is compile-time only: if the backend key or a
// field's shape ever drifts, the cast still "succeeds", the gated feature
// (Reload OCR Edited's hasEditedImage gate, the page-source badge) silently
// reads `undefined`, and nothing tells anyone it stopped working.
//
// This is the one place that reads the "labeler" extension. It validates
// each field's actual runtime type instead of trusting a cast, so a
// malformed or renamed field degrades to "feature off" (the existing,
// already-handled default) rather than a false positive from an unchecked
// cast finding a same-named field of the wrong type.

import type { components } from "../api/types";

type PageRecord = components["schemas"]["PageRecord"];

export interface LabelerExtension {
  has_edited_image?: boolean;
  page_source?: string;
}

/**
 * Read and validate `pageRecord.extensions["labeler"]`.
 *
 * Returns a `LabelerExtension` containing only the fields that are actually
 * present with the expected runtime type. Missing, malformed, or
 * wrong-typed fields come back `undefined`, the same as a genuinely absent
 * extension — callers use the same `?.field` access pattern either way, and
 * never see a value whose type this function didn't check.
 */
export function getLabelerExtension(pageRecord: PageRecord | null | undefined): LabelerExtension {
  const raw: unknown = pageRecord?.extensions?.["labeler"];
  if (raw === null || typeof raw !== "object") return {};
  const ext = raw as Record<string, unknown>;

  const result: LabelerExtension = {};
  if (typeof ext["has_edited_image"] === "boolean") {
    result.has_edited_image = ext["has_edited_image"];
  }
  if (typeof ext["page_source"] === "string") {
    result.page_source = ext["page_source"];
  }
  return result;
}
