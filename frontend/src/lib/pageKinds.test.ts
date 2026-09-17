// pageKinds.test.ts — the shared PageKind enumeration used by the
// page-toolbar kind control and the book-wide Review page kinds dialog.

import { describe, it, expect } from "vitest";
import { PAGE_KINDS } from "./pageKinds";

describe("PAGE_KINDS", () => {
  it("lists all fourteen PageKind values, in a stable order", () => {
    expect(PAGE_KINDS).toEqual([
      "body",
      "chapter opening",
      "title page",
      "half title",
      "contents",
      "index",
      "dedication",
      "preface",
      "errata",
      "plate",
      "blank",
      "advertisement",
      "colophon",
      "unknown",
    ]);
  });

  it("has no duplicate values", () => {
    expect(new Set(PAGE_KINDS).size).toBe(PAGE_KINDS.length);
  });
});
