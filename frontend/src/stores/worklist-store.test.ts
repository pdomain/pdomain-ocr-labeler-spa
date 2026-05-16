// worklist-store.test.ts — Tests for the worklist external store.

import { describe, it, expect, beforeEach } from "vitest";
import { worklistStore } from "./worklist-store";

describe("searchQuery", () => {
  beforeEach(() => worklistStore.reset());

  it("starts as empty string", () => {
    expect(worklistStore.getState().searchQuery).toBe("");
  });

  it("setSearchQuery updates the field", () => {
    worklistStore.setSearchQuery("hello");
    expect(worklistStore.getState().searchQuery).toBe("hello");
  });

  it("reset clears searchQuery", () => {
    worklistStore.setSearchQuery("something");
    worklistStore.reset();
    expect(worklistStore.getState().searchQuery).toBe("");
  });
});
