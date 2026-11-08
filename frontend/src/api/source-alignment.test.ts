import { describe, expect, it } from "vitest";

import { parseSourceAlignmentEnvelope } from "./source-alignment";

describe("source alignment runtime validation", () => {
  it("accepts a current group with its frozen review fields", () => {
    const envelope = parseSourceAlignmentEnvelope({
      generation: 7,
      stale: false,
      result: {
        result_id: "result-1",
        input_generation: 7,
        projection: { layout_hints: [], unresolved: [] },
        warnings: [],
        groups: [
          {
            group_id: "group-1",
            f2_text: "F2",
            p3_text: "P3",
            ocr_text: "OCR",
            disposition: "ambiguous",
            decision: "pending",
            note: "",
            reviewed_text: null,
            warnings: [],
          },
        ],
      },
    });

    expect(envelope.result?.groups[0]?.group_id).toBe("group-1");
  });

  it("rejects an envelope without a boolean stale field", () => {
    expect(() => parseSourceAlignmentEnvelope({ generation: 7, result: null })).toThrow(
      "source alignment envelope stale must be a boolean",
    );
  });
});
