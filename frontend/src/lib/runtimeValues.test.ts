import { describe, expect, it } from "vitest";
import {
  arrayLength,
  nonEmptyString,
  optionalNumber,
  optionalString,
  readField,
} from "./runtimeValues";

describe("untrusted response values", () => {
  it("keeps missing and malformed fields out of rendered strings and counters", () => {
    for (const payload of [null, undefined, 0, "bad", {}, { progress: null }]) {
      const progress = readField(payload, "progress");
      expect(optionalString(readField(progress, "message")) ?? "Working…").toBe("Working…");
      expect(optionalNumber(readField(progress, "current")) ?? 0).toBe(0);
    }
    for (const value of [undefined, null, "", 42, {}]) {
      expect(nonEmptyString(value) ?? "Proposing regions…").toBe("Proposing regions…");
    }
    expect(nonEmptyString("Done")).toBe("Done");
    expect(optionalString(42)).toBeUndefined();
    expect(optionalNumber("2")).toBeUndefined();
    expect(arrayLength(null)).toBeUndefined();
    expect(arrayLength({ length: 3 })).toBeUndefined();
  });

  it("preserves valid zero counts, empty text, and list lengths", () => {
    expect(optionalNumber(0) ?? 1).toBe(0);
    expect(optionalString("") ?? "fallback").toBe("");
    expect(arrayLength([])).toBe(0);
    expect(arrayLength(["a", "b"])).toBe(2);
  });
});
