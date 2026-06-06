import { describe, it, expect } from "vitest";
import { toolbarMapping } from "./toolbarMapping";

describe("toolbarMapping", () => {
  it("should have all 56 cells (4 rows x 14 columns)", () => {
    const scopes = ["page", "paragraph", "line", "word"];
    const actions = [
      "merge",
      "refine",
      "expand-refine",
      "expand",
      "split-after",
      "split-selected",
      "word-to-line",
      "word-to-para",
      "gt-to-ocr",
      "ocr-to-gt",
      "validate",
      "unvalidate",
      "delete",
    ];

    // Grid is 4 rows × 14 columns = 56 cells
    // But column 1 is scope label, columns 2-14 are 13 actions
    // So we have 4 scopes × 13 actions = 52 action mappings
    // Plus 4 scope label cells = 56 total cells in the grid
    const expectedActionMappings = 52; // 4 scopes × 13 actions
    let count = 0;

    for (const scope of scopes) {
      for (const action of actions) {
        const key = `${scope}-${action}`;
        expect(toolbarMapping).toHaveProperty(key);
        count++;
      }
    }

    expect(count).toBe(expectedActionMappings);
    // Total cells in grid including scope labels: 56 (4 rows × 14 columns)
    // Mapping covers the 52 action cells, not the 4 scope label cells
  });

  it("should map each action to a valid endpoint", () => {
    for (const [_key, mapping] of Object.entries(toolbarMapping)) {
      if (mapping === null) {
        // null mappings are allowed for disabled cells
        continue;
      }
      expect(mapping).toHaveProperty("endpoint");
      expect(mapping).toHaveProperty("method");
      expect(mapping.endpoint).toMatch(/^\/api\//);
      expect(["GET", "POST", "DELETE", "PUT"]).toContain(mapping.method);
    }
  });

  // S1-1 carry-forward: the backend route is `lines/{line_index}/split-with-selected`
  // (no `-words` suffix). The earlier mapping pointed at `split-with-selected-words`
  // which 404s. Guard the correct suffix so the typo can't reappear.
  it("uses the real split-with-selected route (no -words suffix)", () => {
    const splitSelected = toolbarMapping["line-split-selected"];
    const wordToLine = toolbarMapping["word-word-to-line"];
    expect(splitSelected?.endpoint).toContain("/lines/{lineIndex}/split-with-selected");
    expect(splitSelected?.endpoint).not.toContain("split-with-selected-words");
    expect(wordToLine?.endpoint).toContain("/lines/{lineIndex}/split-with-selected");
    expect(wordToLine?.endpoint).not.toContain("split-with-selected-words");
  });

  // S4.2: word-word-to-line must NOT carry a static `mode` body — the backend
  // now expects `word_keys` (injected by useToolbarDispatch from selection).
  it("word-word-to-line has no static mode body (word_keys injected at dispatch)", () => {
    const mapping = toolbarMapping["word-word-to-line"];
    expect(mapping).not.toBeNull();
    // The old stub body was { mode: "extract_to_new" } — must be absent.
    // body may be undefined (no static body) or an object without mode.
    if (mapping?.body !== undefined) {
      expect(mapping.body).not.toHaveProperty("mode");
    }
    // Either way, mode must not be present.
    expect((mapping?.body as Record<string, unknown> | undefined)?.["mode"]).toBeUndefined();
  });
});
