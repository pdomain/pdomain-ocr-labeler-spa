// labelerExtension.test.ts — unit tests for the runtime-checked labeler
// extension accessor.
//
// Three call sites (ProjectPage.tsx, PageActionsCompact.tsx x2) used to each
// cast `PageRecord.extensions["labeler"]` to a hand-picked shape with no
// runtime check — if the backend key or field shape drifted, the cast still
// "succeeded" at compile time and the gated feature silently stopped
// working. These tests pin the accessor's behavior when the blob is
// missing, malformed, or has the wrong field types — the exact drift this
// exists to catch.
//
// Test fixtures below cast through `as unknown as PageRecord` where they
// deliberately construct a malformed backend payload (a real API response
// TypeScript could never type-check against `PageRecord` in the first
// place) — the whole point of testing a runtime guard is exercising input
// the type system can't rule out.

import { describe, it, expect } from "vitest";
import type { components } from "../api/types";
import { getLabelerExtension } from "./labelerExtension";

type PageRecord = components["schemas"]["PageRecord"];

function pageRecordWithExtensions(extensions: unknown): PageRecord {
  return {
    page_id: "p",
    page_index: 0,
    source: "ocr",
    ocr_failed: false,
    rotation_degrees: 0,
    rotation_source: "none",
    extensions,
  } as unknown as PageRecord;
}

describe("getLabelerExtension", () => {
  it("returns an empty object for undefined pageRecord", () => {
    expect(getLabelerExtension(undefined)).toEqual({});
  });

  it("returns an empty object for null pageRecord", () => {
    expect(getLabelerExtension(null)).toEqual({});
  });

  it("returns an empty object when extensions is missing", () => {
    expect(getLabelerExtension(pageRecordWithExtensions(undefined))).toEqual({});
  });

  it("returns an empty object when extensions.labeler is missing", () => {
    expect(getLabelerExtension(pageRecordWithExtensions({}))).toEqual({});
  });

  it("returns an empty object when extensions.labeler is not an object (backend shape drift)", () => {
    for (const malformed of ["not-an-object", 42, true, null]) {
      expect(getLabelerExtension(pageRecordWithExtensions({ labeler: malformed }))).toEqual({});
    }
  });

  it("reads has_edited_image when it is a real boolean", () => {
    const pageRecord = pageRecordWithExtensions({ labeler: { has_edited_image: true } });
    expect(getLabelerExtension(pageRecord).has_edited_image).toBe(true);
  });

  it("has_edited_image is undefined, not the wrong-typed value, when the field drifts (backend shape drift)", () => {
    // string, not boolean
    const pageRecord = pageRecordWithExtensions({ labeler: { has_edited_image: "true" } });
    expect(getLabelerExtension(pageRecord).has_edited_image).toBeUndefined();
  });

  it("reads page_source when it is a real string", () => {
    const pageRecord = pageRecordWithExtensions({ labeler: { page_source: "ocr" } });
    expect(getLabelerExtension(pageRecord).page_source).toBe("ocr");
  });

  it("page_source is undefined, not the wrong-typed value, when the field drifts (backend shape drift)", () => {
    // number, not string
    const pageRecord = pageRecordWithExtensions({ labeler: { page_source: 123 } });
    expect(getLabelerExtension(pageRecord).page_source).toBeUndefined();
  });

  it("reads both fields together from the same blob", () => {
    const pageRecord = pageRecordWithExtensions({
      labeler: { has_edited_image: true, page_source: "reocr" },
    });
    expect(getLabelerExtension(pageRecord)).toEqual({
      has_edited_image: true,
      page_source: "reocr",
    });
  });
});
