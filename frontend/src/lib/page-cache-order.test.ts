import { describe, it, expect, beforeEach } from "vitest";
import {
  acceptPagePayload,
  isCurrentPageCacheEpoch,
  pageCacheEpoch,
  pageCacheScope,
  resetPageCacheOrder,
  resetPageCacheOrderForProject,
} from "./page-cache-order";

beforeEach(() => {
  resetPageCacheOrder();
});

describe("acceptPagePayload", () => {
  const scope = pageCacheScope("proj-001", 0, "all");

  it("keeps a newer payload when an older one arrives afterwards", () => {
    const newer = { generation: 2, label: "second" };
    const older = { generation: 1, label: "first" };
    expect(acceptPagePayload(scope, newer)).toBe(newer);
    expect(acceptPagePayload(scope, older)).toBe(newer);
  });

  it("replaces the stored payload when the next generation is newer", () => {
    const older = { generation: 1, label: "first" };
    const newer = { generation: 2, label: "second" };
    acceptPagePayload(scope, older);
    expect(acceptPagePayload(scope, newer)).toBe(newer);
  });

  it("lets an equal generation replace the stored payload", () => {
    const first = { generation: 3, label: "a" };
    const second = { generation: 3, label: "b" };
    acceptPagePayload(scope, first);
    expect(acceptPagePayload(scope, second)).toBe(second);
  });

  it("treats a missing generation as 0", () => {
    const numbered = { generation: 1, label: "numbered" };
    const missing: { generation?: number; label: string } = { label: "missing" };
    acceptPagePayload(scope, numbered);
    expect(acceptPagePayload(scope, missing)).toBe(numbered);
  });

  it("does not share state across filters", () => {
    const all = pageCacheScope("proj-001", 0, "all");
    const unvalidated = pageCacheScope("proj-001", 0, "unvalidated");
    const allPayload = { generation: 4, label: "all" };
    const filtered = { generation: 1, label: "unvalidated" };
    acceptPagePayload(all, allPayload);
    expect(acceptPagePayload(unvalidated, filtered)).toBe(filtered);
    expect(acceptPagePayload(all, { generation: 1, label: "late-all" })).toBe(allPayload);
  });

  it("accepts a reset generation after a project reload without clearing another project", () => {
    const reloaded = pageCacheScope("proj-001", 0, "all");
    const otherProject = pageCacheScope("proj-002", 0, "all");
    const previous = { generation: 7, label: "before reload" };
    const other = { generation: 3, label: "other project" };
    acceptPagePayload(reloaded, previous);
    acceptPagePayload(otherProject, other);
    const oldEpoch = pageCacheEpoch("proj-001");

    resetPageCacheOrderForProject("proj-001");

    expect(isCurrentPageCacheEpoch("proj-001", oldEpoch)).toBe(false);
    expect(acceptPagePayload(reloaded, { generation: 0, label: "after reload" }).label).toBe(
      "after reload",
    );
    expect(acceptPagePayload(otherProject, { generation: 1, label: "late other" })).toBe(other);
  });
});
