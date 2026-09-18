// useRegionReviewHotkeys.ts — review region proposals from the keyboard.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
//   "Review runs from the keyboard, and advances by itself".
// Spec: docs/specs/2026-09-17-book-review-queue-design.md
//   "Two keys move between pages that have work".
// Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
//   review-next.md "How the SPA uses the new route" — "`[`/`]` keep working
//   on the selected kind."
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
//   ]/[    — follow the resolved review-queue kind: whichever kind the
//            Queue drawer's selector has explicitly picked, or —
//            unpicked — `firstActionableKind` (the same book-wide default
//            the Rail badge and Queue panel use). See
//            `resolvedReviewQueueKind`'s comment below for the reasoning.
//            Kind resolves to "region": go to the next/previous page (by
//            page_index) with an undecided region proposal and select its
//            first/last, gated on the rail's region target, exactly as
//            before this kind selector existed. Kind resolves to anything
//            else: jump to that kind's one known `first_page_index`,
//            active regardless of rail target (there is no rail-target
//            equivalent for those kinds) — see `nonRegionKindMessage`'s
//            docstring for what that can and cannot do with only one page
//            index to go on.
//

// n and p are free precisely because j/k, the obvious choice, are already
// bound at document scope: useRailHotkeys (1-4, v, r, a, e) and
// useMatchesHotkeys, registered unconditionally in ProjectPage (j, k, v, u,
// d, o, g, m, r). Rebinding review to j/k would also move the matches
// worklist cursor on every step through proposals — see
// useRegionReviewHotkeys.test.ts's collision regression test.
//
// `[`/`]` are registered as "bracketleft"/"bracketright" — react-hotkeys-hook
// 5 matches combos against the normalized `KeyboardEvent.code`
// ("BracketLeft"/"BracketRight" → "bracketleft"/"bracketright"), the same
// scheme every other single-key combo here already uses (n → KeyN, 5 →
// Digit5). `shift+p`, the obvious pair for `shift+n`, is already bound to the
// paragraphs-layer toggle in the viewport scope, which is why brackets were
// chosen instead (docs/specs/2026-09-17-book-review-queue-design.md).
//
// This is deliberately physical-code-based, unlike `mod+,` / `shift+?`
// (App.tsx, HotkeyHelpModal.tsx), which are registered by character
// (`useKey: true`) instead. Here the pair of adjacent physical keys IS the
// affordance — "the key to the left" / "the key to the right" of home
// position, the same idea as arrow keys — so binding to position is
// correct, not an oversight; layout portability isn't the goal. `,` and `?`
// are the opposite case: the user wants that specific character, wherever
// their layout puts it.
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
//
// Selecting after `[`/`]` navigation (book review queue design, "Selecting
// after navigation needs an intent, not a direct call"): the destination
// page's payload is not loaded at the moment the key fires, and ProjectPage
// clears any region-level selection on the page-index change the navigation
// causes. `setReviewSelectionIntent` records which proposal to select once
// that page's payload arrives; `ProjectPage.tsx` applies it in an effect
// ordered *after* its page-change clear so the clear cannot undo it (see
// that file's comment on the two effects' ordering).

import { useEffect, useRef, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { NavigateFunction } from "react-router-dom";
import { useHotkey } from "./useHotkey";
import { useReviewQueue, reviewQueueKey, type RegionReviewQueueResponse } from "./useReviewQueue";
import {
  useBookReviewQueue,
  firstActionableKind,
  blockedByMessage,
  REVIEW_QUEUE_KIND_LABELS,
  type ReviewQueueKindEntry,
  type ReviewQueueKindName,
} from "./useBookReviewQueue";
import { railStore } from "../stores/rail-store";
import { selectionStore, selectProposal, clearSelection } from "../stores/selection-store";
import { setReviewSelectionIntent } from "../stores/review-selection-intent-store";
import { useUiPrefs } from "../stores/ui-prefs";
import type { SelectionPath } from "../lib/selection-walk";
import { orderedUndecidedProposals } from "../lib/region-hit-test";
import { pageNoUrl } from "../lib/routes";
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
type RegionReviewQueuePageSummary = components["schemas"]["RegionReviewQueuePageSummary"];

const NO_PROPOSALS_ON_PAGE_MESSAGE = "No undecided proposals left on this page";
const NO_NEXT_PAGE_MESSAGE = "No more pages with undecided proposals after this page.";
const NO_PREV_PAGE_MESSAGE = "No pages with undecided proposals before this page.";
const QUEUE_LOADING_MESSAGE = "Review queue is still loading.";

/**
 * `[`/`]` for a non-region kind (pdomain-ocr-synth's docs/specs/2026-09-18-
 * one-answer-to-what-to-review-next.md "How the SPA uses the new route").
 *
 * The per-kind route carries only `first_page_index` — a single earliest
 * page, never an ordered list of every page with work the way the
 * region-only route's `pages` summary is. So there is no "next" or
 * "previous" page to compute for these kinds, only "the one known page,
 * once". Both keys collapse to the same action here, deliberately: jump to
 * `first_page_index` if not already there, and say so, honestly, once there
 * is nowhere further the data can send a person.
 *
 * Reviewer finding (low): a blocked entry can still carry a
 * `first_page_index` (typography mirrors word's while blocked, for
 * example), and the keys used to navigate there with no mention of the
 * block — the Queue drawer's banner for the same entry
 * (ReviewQueuePanel.tsx) says what it is waiting for; the keys must say
 * the same thing, via `blockedByMessage`, not stay silent.
 */
function nonRegionKindMessage(
  kind: Exclude<ReviewQueueKindName, "region">,
  entry: ReviewQueueKindEntry | undefined,
  pageIndex: number,
): { message: string } | { navigateToPageIndex: number; blockedNote?: string } {
  const label = REVIEW_QUEUE_KIND_LABELS[kind];
  if (!entry?.available) {
    const reason = entry?.unavailable_reason;
    return { message: reason ? `${label} is unavailable: ${reason}.` : `${label} is unavailable.` };
  }
  const firstPageIndex = entry.first_page_index;
  if (firstPageIndex === null) {
    return { message: `${label} has no known starting page yet.` };
  }
  if (firstPageIndex === pageIndex) {
    return {
      message: `${label}'s only known page is this one — there is no further page to jump to.`,
    };
  }
  return entry.blocked_by !== null
    ? { navigateToPageIndex: firstPageIndex, blockedNote: blockedByMessage(entry.blocked_by) }
    : { navigateToPageIndex: firstPageIndex };
}

export interface UseRegionReviewHotkeysArgs {
  page: PagePayload | undefined;
  projectId: string;
  pageIndex: number;
  /** From `useNavigate()` — drives the `[`/`]` page jump. */
  navigate: NavigateFunction;
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

function getReviewQueueKind(): ReviewQueueKindName | null {
  return useUiPrefs.getState().reviewQueueKind;
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

/** The first page in `pages` (page order) after `currentPageIndex`, or null. */
function nextPageWithWork(
  pages: readonly RegionReviewQueuePageSummary[],
  currentPageIndex: number,
): RegionReviewQueuePageSummary | null {
  return pages.find((p) => p.page_index > currentPageIndex) ?? null;
}

/** The last page in `pages` (page order) before `currentPageIndex`, or null. */
function prevPageWithWork(
  pages: readonly RegionReviewQueuePageSummary[],
  currentPageIndex: number,
): RegionReviewQueuePageSummary | null {
  return pages.filter((p) => p.page_index < currentPageIndex).at(-1) ?? null;
}

/**
 * The end-of-page toast text. `remaining` is the book's undecided count
 * *after* accounting for whatever just emptied the current page — undefined
 * when the queue hasn't loaded (falls back to the plain on-page message).
 *
 * Always leads with the on-page sentence (finding 4, low): an earlier
 * version replaced it outright with a book-wide "No undecided proposals
 * left in the book." once the book count hit zero, dropping the page text
 * the driver contract's toast assertion (tests/e2e/test_region_review_loop.py)
 * depends on. The zero case now extends the same on-page sentence instead of
 * swapping it out, matching the non-zero form's shape.
 */
function endOfPageMessage(remaining: number | undefined): string {
  if (remaining === undefined) return NO_PROPOSALS_ON_PAGE_MESSAGE;
  if (remaining <= 0) return `${NO_PROPOSALS_ON_PAGE_MESSAGE}. None left in the book.`;
  return `${NO_PROPOSALS_ON_PAGE_MESSAGE}. ${String(remaining)} left in the book; press ] for the next.`;
}

export function useRegionReviewHotkeys({
  page,
  projectId,
  pageIndex,
  navigate,
}: UseRegionReviewHotkeysArgs): void {
  const railTarget = useSyncExternalStore(subscribeRailTarget, getRailTarget, getRailTarget);
  const path = useSyncExternalStore(subscribeSelectionPath, getSelectionPath, getSelectionPath);

  // One-answer-to-what-to-review-next: `[`/`]` follow the resolved
  // review-queue kind (design: "`[`/`]` keep working on the selected
  // kind"), using the SAME rule the Rail badge and Queue panel default to
  // — an explicit Queue-drawer pick when there is one, else
  // `firstActionableKind`, falling back to "region" only once nothing else
  // qualifies.
  //
  // This does mean `]`/`[` can jump to a page-kind (or word, or
  // typography) page instead of stepping through region pages, the moment
  // any such kind has outstanding, unblocked work — true of most books
  // before their page kinds are confirmed. That is intentional, not a
  // regression: `firstActionableKind` names the thing a person genuinely
  // should do next, and a book whose page kinds are unreviewed genuinely
  // has page-kind work ahead of region work in the order this route
  // defines. One selection — shown on the Rail badge, defaulted in the
  // Queue drawer, and followed by these keys — is a simpler, more honest
  // mental model than a keyboard shortcut that quietly disagrees with what
  // the UI is telling a person to do next.
  //
  // The cost is real and worth naming: `n`/`p`/`enter`/`x`/`delete` below
  // stay region-only (nothing else has a keyboard accept/reject flow yet),
  // so once a book's first actionable kind is something other than
  // region, `]`/`[` and those other keys are no longer working the same
  // loop. That split exists already, in miniature, the moment a person
  // explicitly picks a non-region kind in the Queue drawer — extending it
  // to the auto-picked default is a difference of degree, not of kind.
  //
  // When the Rail badge's auto-picked kind and a person's explicit Queue
  // pick disagree (they chose to work on something else on purpose), the
  // badge keeps naming the book-wide next kind — an honest, passive
  // reading — while these keys follow the explicit pick, not the badge:
  // a deliberate choice to work on region while page-kind work remains
  // outstanding is respected, not silently overridden.
  const explicitReviewQueueKind = useSyncExternalStore(
    useUiPrefs.subscribe,
    getReviewQueueKind,
    getReviewQueueKind,
  );
  const bookQueueQ = useBookReviewQueue(projectId);
  const autoReviewQueueKind = firstActionableKind(bookQueueQ.data?.kinds ?? [])?.kind;
  const resolvedReviewQueueKind: ReviewQueueKindName =
    explicitReviewQueueKind ?? autoReviewQueueKind ?? "region";

  const acceptProposal = useAcceptProposal(projectId, pageIndex);
  const rejectProposal = useRejectProposal(projectId, pageIndex);
  const deleteRegion = useDeleteRegion(projectId, pageIndex);
  const decisionPending = useRegionDecisionPending(projectId, pageIndex);
  const qc = useQueryClient();
  // Book review queue (design: "Two keys move between pages that have work"
  // / "A count stays visible"). `order`/`limit` default to reading order and
  // 0 — the bracket keys only need `pages`, and the end-of-page message only
  // needs `total_undecided`.
  const queueQ = useReviewQueue(projectId);
  const queuePages = queueQ.data?.pages ?? [];

  // Finding 3 (low, ~line 245): how many page-emptying decisions have
  // completed since the review-queue cache last landed a fetch. Reset
  // whenever `queueQ.dataUpdatedAt` changes — that is the instant a fresh
  // fetch (e.g. the invalidation refetch a decision itself triggers) lands
  // in the cache, so counting starts over against the new baseline. Two
  // page-emptying decisions that both settle before that refetch resolves
  // each bump the count, so the toast subtracts 2 (not 1 twice) from the
  // stale cached total. The reset lives in an effect (rather than a
  // render-time ref mutation, which `eslint-plugin-react-hooks`'s `refs`
  // rule forbids) — it still lands before any decision made after the next
  // commit, since a decision is always a later, separate event (a keypress
  // or a mutation's `onSuccess`), never something that can run inside the
  // same render pass as the `dataUpdatedAt` change itself.
  const decisionsSinceFetchRef = useRef(0);
  const queueDataUpdatedAtRef = useRef(queueQ.dataUpdatedAt);
  useEffect(() => {
    if (queueDataUpdatedAtRef.current !== queueQ.dataUpdatedAt) {
      queueDataUpdatedAtRef.current = queueQ.dataUpdatedAt;
      decisionsSinceFetchRef.current = 0;
    }
  }, [queueQ.dataUpdatedAt]);

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

  /**
   * The book's undecided count to show in the end-of-page toast.
   *
   * Read straight from the `QueryClient` cache (not the reactive `queueQ`
   * above) so this always sees whatever is cached at the instant a decision
   * settles, rather than whichever render's `queueQ.data` closure the
   * mutation's `onSuccess` callback happened to capture — `acceptSelected`/
   * `rejectSelected` are rebuilt every render, so a `useIsMutating`/network
   * race could otherwise read a render-stale value.
   *
   * The cached value is from the last completed fetch, taken *before* the
   * decision that just emptied this page — its own invalidation
   * (useRegionMutations.ts) has only just fired and the refetch is still in
   * flight, so waiting for it would delay the toast on an unrelated network
   * round trip. Subtracting the number of page-emptying decisions made since
   * that fetch (tracked by `decisionsSinceFetchRef`, floored at 0) stays
   * exact even when a second decision settles before the first decision's
   * invalidation refetch resolves — otherwise both would subtract 1 from the
   * same stale total and report the same count.
   */
  function bookRemainingAfter(decided: boolean): number | undefined {
    const cached = qc.getQueryData<RegionReviewQueueResponse>(reviewQueueKey(projectId));
    const total = cached?.total_undecided;
    if (total === undefined) return undefined;
    if (!decided) return total;
    decisionsSinceFetchRef.current += 1;
    return Math.max(total - decisionsSinceFetchRef.current, 0);
  }

  /** Select `next`, or clear the selection and say so when there is none. */
  function advanceTo(next: string | null, decided: boolean): void {
    if (next === null) {
      clearSelection();
      toast.info(endOfPageMessage(bookRemainingAfter(decided)));
      return;
    }
    selectProposal(next);
  }

  function selectStep(dir: 1 | -1): void {
    advanceTo(stepProposal(orderedProposals(), selectedProposalId, dir), false);
  }

  function acceptSelected(proposalId: string): void {
    const next = nextAfterDecision(orderedProposals(), proposalId);
    acceptProposal.mutate(
      { proposalId },
      {
        onSuccess: () => {
          advanceTo(next, true);
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
          advanceTo(next, true);
        },
        onError: () => {
          toast.error("Reject failed");
        },
      },
    );
  }

  /** Navigate to the next page with work and record who to select there. */
  function goToNextPageWithWork(): void {
    // Finding 2 (medium, ~line 296): before the first queue fetch resolves,
    // `queueQ.data` is undefined and `queuePages` reads as `[]` — the same
    // shape as a book with no work at all. Without this guard, pressing ']'
    // in that window showed "no more pages" even when work exists elsewhere
    // in the book, because the queue just hadn't answered yet.
    if (queueQ.data === undefined) {
      toast.info(QUEUE_LOADING_MESSAGE);
      return;
    }
    const next = nextPageWithWork(queuePages, pageIndex);
    if (next === null) {
      toast.info(NO_NEXT_PAGE_MESSAGE);
      return;
    }
    setReviewSelectionIntent({ pageIndex: next.page_index, proposalId: next.first_proposal_id });
    void navigate(pageNoUrl(projectId, next.page_index + 1));
  }

  /** Navigate to the previous page with work and record who to select there. */
  function goToPrevPageWithWork(): void {
    if (queueQ.data === undefined) {
      toast.info(QUEUE_LOADING_MESSAGE);
      return;
    }
    const prev = prevPageWithWork(queuePages, pageIndex);
    if (prev === null) {
      toast.info(NO_PREV_PAGE_MESSAGE);
      return;
    }
    setReviewSelectionIntent({ pageIndex: prev.page_index, proposalId: prev.last_proposal_id });
    void navigate(pageNoUrl(projectId, prev.page_index + 1));
  }

  /**
   * `[`/`]` for whichever non-region kind is selected — see
   * `nonRegionKindMessage`'s docstring for why both keys do the same thing.
   * No selection intent is recorded: unlike a region proposal, there is
   * nothing on the destination page for a non-region kind to select yet.
   */
  function goToKindPage(kind: Exclude<ReviewQueueKindName, "region">): void {
    if (bookQueueQ.data === undefined) {
      toast.info(QUEUE_LOADING_MESSAGE);
      return;
    }
    const entry = bookQueueQ.data.kinds.find((k) => k.kind === kind);
    const result = nonRegionKindMessage(kind, entry, pageIndex);
    if ("message" in result) {
      toast.info(result.message);
      return;
    }
    if (result.blockedNote !== undefined) {
      toast.info(result.blockedNote);
    }
    void navigate(pageNoUrl(projectId, result.navigateToPageIndex + 1));
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

  // `[`/`]` follow `resolvedReviewQueueKind` (design: "`[`/`]` keep working
  // on the selected kind"). The "region" case is unconditionally active
  // here — the rail-target gate that used to sit in `useHotkey`'s `enabled`
  // option is now checked inside the callback instead, so the gate applies
  // to exactly the same case it always did (kind resolves to "region") and
  // never blocks a non-region kind that has nothing to do with the rail's
  // region target.
  useHotkey("bracketright", () => {
    if (resolvedReviewQueueKind === "region") {
      if (!regionTargetActive) return;
      goToNextPageWithWork();
      return;
    }
    goToKindPage(resolvedReviewQueueKind);
  });

  useHotkey("bracketleft", () => {
    if (resolvedReviewQueueKind === "region") {
      if (!regionTargetActive) return;
      goToPrevPageWithWork();
      return;
    }
    goToKindPage(resolvedReviewQueueKind);
  });
}
