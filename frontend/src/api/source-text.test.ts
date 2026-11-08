import { describe, expect, it } from "vitest";

import { parseSourceTextPreview } from "./source-text";

describe("source text preview runtime validation", () => {
  it("accepts a read-only P3 and F2 preview with explicit unresolved formatting", () => {
    const preview = parseSourceTextPreview({
      project_id: "project-1",
      page_index: 1,
      page_key: "002.png",
      available: true,
      f2: { raw_text: "<i>F2</i>", visible_text: "F2" },
      p3: { raw_text: "P3", visible_text: "P3" },
      consolidated: {
        text: "P3",
        runs: [{ text: "P3", styles: ["italic"] }],
        layout_hints: [],
        unresolved: [
          {
            source_kind: "style_span",
            source_ref: "italic",
            source_text: "F2",
            reason: "changed source text",
          },
        ],
      },
      warnings: [],
    });

    expect(preview.consolidated?.runs.map((run) => run.text).join("")).toBe("P3");
    expect(preview.consolidated?.unresolved[0]?.source_text).toBe("F2");
  });

  it("accepts a source-unavailable response without manufacturing empty source text", () => {
    const preview = parseSourceTextPreview({
      project_id: "project-1",
      page_index: 0,
      page_key: null,
      available: false,
      f2: null,
      p3: null,
      consolidated: null,
      warnings: ["This project has no prepared PGDP source."],
    });

    expect(preview.available).toBe(false);
    expect(preview.f2).toBeNull();
    expect(preview.warnings).toEqual(["This project has no prepared PGDP source."]);
  });

  it("accepts prepared F2 and P3 when no exact source graph supports consolidation", () => {
    const preview = parseSourceTextPreview({
      project_id: "project-1",
      page_index: 0,
      page_key: "001.png",
      available: true,
      f2: { raw_text: "F2", visible_text: "F2" },
      p3: { raw_text: "P3", visible_text: "P3" },
      consolidated: null,
      warnings: ["No persisted F2-to-P3 graph is available for this page."],
    });

    expect(preview.available).toBe(true);
    expect(preview.consolidated).toBeNull();
  });

  it("rejects a consolidated response whose runs do not reproduce its P3 text", () => {
    expect(() =>
      parseSourceTextPreview({
        project_id: "project-1",
        page_index: 0,
        page_key: "001.png",
        available: true,
        f2: { raw_text: "F2", visible_text: "F2" },
        p3: { raw_text: "P3", visible_text: "P3" },
        consolidated: {
          text: "P3",
          runs: [{ text: "different", styles: [] }],
          layout_hints: [],
          unresolved: [],
        },
        warnings: [],
      }),
    ).toThrow("source text preview consolidated runs must concatenate to consolidated text");
  });
});
