// region-hit-test.test.ts — Tests for the pure region/proposal hit-test helpers.
// Spec: docs/plans/2026-09-17-region-review-surface.md Task 2.
//
// Pure module: no mocked canvas needed. Each test builds a hand-rolled
// RegionView[] fixture and exercises regionCandidates / hitTestRegions /
// orderedUndecidedProposals directly.

import { describe, it, expect } from "vitest";
import { regionCandidates, hitTestRegions, orderedUndecidedProposals } from "./region-hit-test";
import type { components } from "../api/types";

type RegionView = components["schemas"]["RegionView"];

const identity = (box: RegionView["box"]) => box;

function confirmedRegion(
  region_id: string,
  box: RegionView["box"],
  overrides: Partial<RegionView> = {},
): RegionView {
  return {
    region_id,
    proposal_id: null,
    role: "paragraph",
    box,
    confirmed: true,
    confidence: null,
    stale: false,
    ...overrides,
  };
}

function proposal(
  proposal_id: string,
  box: RegionView["box"],
  overrides: Partial<RegionView> = {},
): RegionView {
  return {
    region_id: null,
    proposal_id,
    role: "paragraph",
    box,
    confirmed: false,
    confidence: 0.9,
    stale: false,
    ...overrides,
  };
}

describe("regionCandidates", () => {
  it("keeps a confirmed region with a region_id as kind region", () => {
    const regions = [confirmedRegion("r1", { x: 0, y: 0, width: 100, height: 100 })];
    const candidates = regionCandidates(regions, identity);
    expect(candidates).toEqual([
      { kind: "region", id: "r1", box: { x: 0, y: 0, width: 100, height: 100 }, area: 10_000 },
    ]);
  });

  it("keeps an unconfirmed region with a proposal_id as kind proposal", () => {
    const regions = [proposal("p1", { x: 0, y: 0, width: 10, height: 10 })];
    const candidates = regionCandidates(regions, identity);
    expect(candidates).toEqual([
      { kind: "proposal", id: "p1", box: { x: 0, y: 0, width: 10, height: 10 }, area: 100 },
    ]);
  });

  it("drops a confirmed RegionView with no region_id", () => {
    const regions = [
      confirmedRegion("ignored", { x: 0, y: 0, width: 10, height: 10 }, { region_id: null }),
    ];
    expect(regionCandidates(regions, identity)).toEqual([]);
  });

  it("drops an unconfirmed RegionView with no proposal_id", () => {
    const regions = [
      proposal("ignored", { x: 0, y: 0, width: 10, height: 10 }, { proposal_id: null }),
    ];
    expect(regionCandidates(regions, identity)).toEqual([]);
  });

  it("applies the toBox coordinate transform", () => {
    const regions = [confirmedRegion("r1", { x: 10, y: 20, width: 30, height: 40 })];
    const candidates = regionCandidates(regions, (box) => ({
      x: box.x * 2,
      y: box.y * 2,
      width: box.width * 2,
      height: box.height * 2,
    }));
    expect(candidates[0]?.box).toEqual({ x: 20, y: 40, width: 60, height: 80 });
    expect(candidates[0]?.area).toBe(60 * 80);
  });
});

describe("hitTestRegions", () => {
  it("hits the smaller proposal nested inside a large confirmed region", () => {
    const regions = [
      confirmedRegion("outer", { x: 0, y: 0, width: 200, height: 200 }),
      proposal("inner", { x: 50, y: 50, width: 20, height: 20 }),
    ];
    const candidates = regionCandidates(regions, identity);
    const hit = hitTestRegions(candidates, 55, 55);
    expect(hit).toEqual({
      kind: "proposal",
      id: "inner",
      box: { x: 50, y: 50, width: 20, height: 20 },
      area: 400,
    });
  });

  it("hits the inner region of two nested confirmed regions", () => {
    const regions = [
      confirmedRegion("outer", { x: 0, y: 0, width: 200, height: 200 }),
      confirmedRegion("inner", { x: 20, y: 20, width: 40, height: 40 }),
    ];
    const candidates = regionCandidates(regions, identity);
    const hit = hitTestRegions(candidates, 30, 30);
    expect(hit?.id).toBe("inner");
  });

  it("prefers the proposal when a region and a proposal have exactly equal area", () => {
    const box = { x: 0, y: 0, width: 50, height: 50 };
    const regions = [confirmedRegion("r1", box), proposal("p1", box)];
    const candidates = regionCandidates(regions, identity);
    const hit = hitTestRegions(candidates, 10, 10);
    expect(hit).toEqual({ kind: "proposal", id: "p1", box, area: 2500 });
  });

  it("returns null when the click is outside every candidate", () => {
    const regions = [confirmedRegion("r1", { x: 0, y: 0, width: 10, height: 10 })];
    const candidates = regionCandidates(regions, identity);
    expect(hitTestRegions(candidates, 100, 100)).toBeNull();
  });

  it("treats edges as inclusive", () => {
    const regions = [confirmedRegion("r1", { x: 0, y: 0, width: 10, height: 10 })];
    const candidates = regionCandidates(regions, identity);
    expect(hitTestRegions(candidates, 10, 10)?.id).toBe("r1");
    expect(hitTestRegions(candidates, 0, 0)?.id).toBe("r1");
  });
});

describe("orderedUndecidedProposals", () => {
  it("orders proposals by y then x, and skips confirmed regions", () => {
    const regions = [
      proposal("bottom", { x: 50, y: 200, width: 10, height: 10 }),
      confirmedRegion("confirmed", { x: 0, y: 0, width: 10, height: 10 }),
      proposal("top-right", { x: 80, y: 10, width: 10, height: 10 }),
      proposal("top-left", { x: 5, y: 10, width: 10, height: 10 }),
    ];
    expect(orderedUndecidedProposals(regions)).toEqual(["top-left", "top-right", "bottom"]);
  });

  it("returns an empty list when there are no unconfirmed proposals", () => {
    const regions = [confirmedRegion("r1", { x: 0, y: 0, width: 10, height: 10 })];
    expect(orderedUndecidedProposals(regions)).toEqual([]);
  });
});
