// useRegionReviewHotkeys.ts — review region proposals from the keyboard.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
//   "Review runs from the keyboard, and advances by itself".
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 5.
//
// Keys, all registered through useHotkey so they respect its form-field and
// open-dialog guards:
//   n      — select the next undecided proposal, wrapping. Nothing selected
//            selects the first. Only fires when the rail target is "region".
//   p      — select the previous undecided proposal, wrapping. Only fires
//            when the rail target is "region".
//   enter  — accept the selected proposal with no role override. Only fires
//            when the rail target is "region" and a proposal is selected.
//   x      — reject the selected proposal. Only fires when the rail target
//            is "region" and a proposal is selected.
//   delete — delete the selected confirmed region, behind the existing
//            confirm dialog. Fires whenever a confirmed region is selected.
//
// n and p are free precisely because j/k, the obvious choice, are already
// bound at document scope: useRailHotkeys (1-4, v, r, a, e) and
// useMatchesHotkeys, registered unconditionally in ProjectPage (j, k, v, u,
// d, o, g, m, r). Rebinding review to j/k would also move the matches
// worklist cursor on every step through proposals — see
// useRegionReviewHotkeys.test.ts's collision regression test.
//
// Auto-advance: before firing accept or reject, the proposal that follows
// the current one in `orderedUndecidedProposals(page.regions)` is computed
// from the page payload the caller already holds — the mutation's success
// refetches the page and the decided proposal is gone from that payload, so
// computing the neighbour afterwards would find the wrong one.
//
// Whole-branch review defect 1 (double-fire / silent keyboard failure):
//   - `decisionPending` (from `useRegionDecisionPending`, a shared
//     `useIsMutating` read) gates enter/x/delete so a held or double-tapped
//     key — or a key pressed while `RegionDetail`'s button is mid-request —
//     cannot fire a second request. See useRegionMutations.ts.
//   - Every mutate call below gets an `onError` that toasts a short
//     "<Action> failed" message, so a failed keyboard decision is no longer
//     silent. `onSuccess` (auto-advance) does not run on failure, so nothing
//     advances when the request fails.
//
// Whole-branch review defect 2 (a selection can outlive its page):
//   `isProposalCurrent`/`isRegionCurrent` confirm the selected id is still
//   present on `page.regions`, with the right `confirmed` flag, before
//   acting. `ProjectPage` also clears a region-level selection on page
//   change (belt) — this check is the suspenders: it also covers a proposal
//   a refetch has just removed without a page change.

import { useSyncExternalStore } from "react";
import { useHotkey } from "./useHotkey";
import { railStore } from "../stores/rail-store";
import { selectionStore, selectProposal, clearSelection } from "../stores/selection-store";
import type { SelectionPath } from "../lib/selection-walk";
import { orderedUndecidedProposals } from "../lib/region-hit-test";
import {
  useAcceptProposal,
  useRejectProposal,
  useDeleteRegion,
  useRegionDecisionPending,
} from "./useRegionMutations";
import { dialogStore } from "../stores/dialog-store";
import { toast } from "../lib/toast";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];

const NO_PROPOSALS_MESSAGE = "No undecided proposals left on this page";

export interface UseRegionReviewHotkeysArgs {
  page: PagePayload | undefined;
  projectId: string;
  pageIndex: number;
}

function subscribeSelectionPath(cb: () => void): () => void {
  return selectionStore.subscribe(cb);
}
function getSelectionPath(): SelectionPath {
  return selectionStore.getState().path;
}

function subscribeRailTarget(cb: () => void): () => void {
  return railStore.subscribe(cb);
}
function getRailTarget(): string {
  return railStore.getState().target;
}

/** The first or last id in `ordered`, or null when it is empty. */
function edgeProposal(ordered: readonly string[], dir: 1 | -1): string | null {
  if (ordered.length === 0) return null;
  const id = dir === 1 ? ordered[0] : ordered[ordered.length - 1];
  return id ?? null;
}

/**
 * The proposal `dir` steps from `currentId` in `ordered`, wrapping. Nothing
 * selected (or a stale id no longer in `ordered`) behaves as if stepping
 * from just outside the list, landing on the first proposal for `n` and the
 * last for `p`.
 */
function stepProposal(
  ordered: readonly string[],
  currentId: string | undefined,
  dir: 1 | -1,
): string | null {
  if (ordered.length === 0) return null;
  const idx = currentId === undefined ? -1 : ordered.indexOf(currentId);
  if (idx === -1) return edgeProposal(ordered, dir);
  const nextIdx = (((idx + dir) % ordered.length) + ordered.length) % ordered.length;
  return ordered[nextIdx] ?? null;
}

/**
 * The proposal that follows `currentId` in `ordered`, accounting for
 * `currentId` itself being removed by the decision about to be made. With
 * `currentId` the only proposal left, there is nothing to advance to.
 */
function nextAfterDecision(ordered: readonly string[], currentId: string): string | null {
  if (ordered.length <= 1) return null;
  const idx = ordered.indexOf(currentId);
  const base = idx === -1 ? 0 : idx;
  const nextIdx = (base + 1) % ordered.length;
  return ordered[nextIdx] ?? null;
}

export function useRegionReviewHotkeys({
  page,
  projectId,
  pageIndex,
}: UseRegionReviewHotkeysArgs): void {
  const railTarget = useSyncExternalStore(subscribeRailTarget, getRailTarget, getRailTarget);
  const path = useSyncExternalStore(subscribeSelectionPath, getSelectionPath, getSelectionPath);

  const acceptProposal = useAcceptProposal(projectId, pageIndex);
  const rejectProposal = useRejectProposal(projectId, pageIndex);
  const deleteRegion = useDeleteRegion(projectId, pageIndex);
  const decisionPending = useRegionDecisionPending(projectId, pageIndex);

  const regionTargetActive = railTarget === "region";
  const selectedProposalId = path.proposalId;
  const selectedRegionId = path.regionId;

  function orderedProposals(): string[] {
    return page ? orderedUndecidedProposals(page.regions ?? []) : [];
  }

  /** True when `proposalId` is still an undecided proposal on `page`. */
  function isProposalCurrent(proposalId: string): boolean {
    return orderedProposals().includes(proposalId);
  }

  /** True when `regionId` is still a confirmed region on `page`. */
  function isRegionCurrent(regionId: string): boolean {
    return (page?.regions ?? []).some((r) => r.confirmed && r.region_id === regionId);
  }

  /** Select `next`, or clear the selection and say so when there is none. */
  function advanceTo(next: string | null): void {
    if (next === null) {
      clearSelection();
      toast.info(NO_PROPOSALS_MESSAGE);
      return;
    }
    selectProposal(next);
  }

  function selectStep(dir: 1 | -1): void {
    advanceTo(stepProposal(orderedProposals(), selectedProposalId, dir));
  }

  function acceptSelected(proposalId: string): void {
    const next = nextAfterDecision(orderedProposals(), proposalId);
    acceptProposal.mutate(
      { proposalId },
      {
        onSuccess: () => {
          advanceTo(next);
        },
        onError: () => {
          toast.error("Accept failed");
        },
      },
    );
  }

  function rejectSelected(proposalId: string): void {
    const next = nextAfterDecision(orderedProposals(), proposalId);
    rejectProposal.mutate(
      { proposalId },
      {
        onSuccess: () => {
          advanceTo(next);
        },
        onError: () => {
          toast.error("Reject failed");
        },
      },
    );
  }

  function deleteSelected(regionId: string): void {
    dialogStore.openConfirm({
      title: "Delete region",
      body: "This confirmed region will be permanently deleted.",
      onConfirm: () => {
        deleteRegion.mutate(
          { regionId },
          {
            onError: () => {
              toast.error("Delete failed");
            },
          },
        );
      },
    });
  }

  useHotkey(
    "n",
    () => {
      selectStep(1);
    },
    { enabled: regionTargetActive },
  );

  useHotkey(
    "p",
    () => {
      selectStep(-1);
    },
    { enabled: regionTargetActive },
  );

  useHotkey(
    "enter",
    () => {
      if (decisionPending) return;
      if (selectedProposalId === undefined) return;
      if (!isProposalCurrent(selectedProposalId)) return;
      acceptSelected(selectedProposalId);
    },
    { enabled: regionTargetActive && selectedProposalId !== undefined },
  );

  useHotkey(
    "x",
    () => {
      if (decisionPending) return;
      if (selectedProposalId === undefined) return;
      if (!isProposalCurrent(selectedProposalId)) return;
      rejectSelected(selectedProposalId);
    },
    { enabled: regionTargetActive && selectedProposalId !== undefined },
  );

  useHotkey(
    "delete",
    () => {
      if (decisionPending) return;
      if (selectedRegionId === undefined) return;
      if (!isRegionCurrent(selectedRegionId)) return;
      deleteSelected(selectedRegionId);
    },
    { enabled: selectedRegionId !== undefined },
  );
}
