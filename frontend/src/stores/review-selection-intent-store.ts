// review-selection-intent-store.ts — a pending selection to make once a
// page navigated-to by '['/']' has loaded.
//
// Design: docs/specs/2026-09-17-book-review-queue-design.md
//   "Selecting after navigation needs an intent, not a direct call":
//   a page change clears the region-level selection (ProjectPage.tsx), and
//   the destination page's payload has not loaded at the moment the bracket
//   key fires. useRegionReviewHotkeys.ts records the proposal to select
//   here, then navigates; ProjectPage.tsx applies it once the destination
//   page's payload arrives and contains that proposal, then clears it.
//
// This is a store separate from selectionStore on purpose: the page-change
// effect in ProjectPage.tsx clears selectionStore's region level on every
// page-index change, and that clear must not also wipe this intent — it is
// what makes the intent survive to be applied afterward.

import { createStore } from "zustand/vanilla";

export interface ReviewSelectionIntent {
  /** 0-based index of the page the proposal belongs to. */
  pageIndex: number;
  /** The proposal to select once that page's payload has loaded. */
  proposalId: string;
}

interface ReviewSelectionIntentState {
  intent: ReviewSelectionIntent | null;
}

export const reviewSelectionIntentStore = createStore<ReviewSelectionIntentState>(() => ({
  intent: null,
}));

/** Record a pending selection to make once `intent.pageIndex`'s payload loads. */
export function setReviewSelectionIntent(intent: ReviewSelectionIntent): void {
  reviewSelectionIntentStore.setState({ intent });
}

/** Clear the pending intent, whether or not it was consumed. */
export function clearReviewSelectionIntent(): void {
  reviewSelectionIntentStore.setState({ intent: null });
}
