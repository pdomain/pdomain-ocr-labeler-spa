// region-hit-test.ts — pure region/proposal hit-test helpers.
// Spec: docs/plans/2026-09-17-region-review-surface.md Task 2.
// Design: docs/specs/2026-09-17-region-review-surface-design.md
//   "Regions become a fifth rail target".
//
// A region's canvas item id today is `region_id ?? proposal_id`. A confirmed
// region promoted from a proposal carries BOTH ids, so a hit on the existing
// overlay item list cannot tell a confirmed region apart from a proposal.
// `RegionCandidate` keeps an explicit `kind` so the caller always knows which
// one it clicked.
//
// This module is pure on purpose: the ordering and tie-break rules below are
// the part most likely to be wrong, and testing them here needs no mocked
// canvas.

import type { components } from "../api/types";

type RegionView = components["schemas"]["RegionView"];
type BBox = components["schemas"]["BBox"];

export interface RegionCandidate {
  kind: "region" | "proposal";
  /** `region_id` for kind "region", `proposal_id` for kind "proposal". */
  id: string;
  /** In the same coordinate space the caller hit-tests in (post-`toBox`). */
  box: BBox;
  area: number;
}

/**
 * Build the hit-testable candidate list from a page's regions.
 *
 * A `RegionView` with `confirmed === true` and a `region_id` becomes kind
 * "region"; one with `confirmed === false` and a `proposal_id` becomes kind
 * "proposal". Anything else (a shape lacking the id its confirmed state
 * requires) is dropped — it cannot be addressed by either mutation route.
 *
 * `toBox` is the coordinate transform. Pass the same conversion the caller
 * draws with (e.g. `encoded ? rectToDisplay(r.box, encoded) : r.box`) so the
 * hit-test agrees with what is on screen.
 */
export function regionCandidates(
  regions: readonly RegionView[],
  toBox: (box: BBox) => BBox,
): RegionCandidate[] {
  const candidates: RegionCandidate[] = [];
  for (const region of regions) {
    let kind: RegionCandidate["kind"];
    let id: string | null | undefined;
    if (region.confirmed) {
      kind = "region";
      id = region.region_id;
    } else {
      kind = "proposal";
      id = region.proposal_id;
    }
    if (!id) continue;
    const box = toBox(region.box);
    candidates.push({ kind, id, box, area: box.width * box.height });
  }
  return candidates;
}

function containsPoint(box: BBox, x: number, y: number): boolean {
  return x >= box.x && x <= box.x + box.width && y >= box.y && y <= box.y + box.height;
}

/**
 * Return the smallest candidate containing `(x, y)`, edges inclusive.
 *
 * Regions nest by design, and a proposal from a newer run can overlap a
 * region someone already confirmed — the smallest candidate is the one a
 * person is pointing at. On exactly equal area, the undecided proposal wins,
 * since it is the one still waiting for a decision. Returns `null` when no
 * candidate contains the point.
 */
export function hitTestRegions(
  candidates: readonly RegionCandidate[],
  x: number,
  y: number,
): RegionCandidate | null {
  let best: RegionCandidate | null = null;
  for (const candidate of candidates) {
    if (!containsPoint(candidate.box, x, y)) continue;
    if (best === null || candidate.area < best.area) {
      best = candidate;
    } else if (candidate.area === best.area && candidate.kind === "proposal") {
      best = candidate;
    }
  }
  return best;
}

/**
 * Every unconfirmed region's `proposal_id`, ordered top to bottom then left
 * to right — the order a person reads the page in.
 *
 * Works in page coordinates, not display coordinates, since the order does
 * not depend on zoom.
 */
export function orderedUndecidedProposals(regions: readonly RegionView[]): string[] {
  return regions
    .filter(
      (region): region is RegionView & { proposal_id: string } =>
        !region.confirmed && !!region.proposal_id,
    )
    .sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x)
    .map((region) => region.proposal_id);
}
