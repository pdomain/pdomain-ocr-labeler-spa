// useRegionReviewHotkeys.test.tsx — unit tests for the review hotkeys hook.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
//   "Review runs from the keyboard, and advances by itself".
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 5.
//
// Covers: n/p stepping and wrap, enter/x deciding a proposal and
// auto-advancing to the next undecided one, the rail-target gate that keeps
// n/enter/x from firing outside the region target, delete behind the
// confirm dialog, and the collision regression: n must not touch
// worklistStore's selectedLineIndex, the field useMatchesHotkeys' j/k own.

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { NavigateFunction } from "react-router-dom";
import { server } from "../test/server";
import { useRegionReviewHotkeys } from "./useRegionReviewHotkeys";
import { railStore } from "../stores/rail-store";
import {
  selectionStore,
  selectProposal,
  selectRegion,
  clearSelection,
} from "../stores/selection-store";
import { reviewSelectionIntentStore } from "../stores/review-selection-intent-store";
import { worklistStore } from "../stores/worklist-store";
import { dialogStore } from "../stores/dialog-store";
import { toast } from "../lib/toast";
import type { components } from "../api/types";

type RegionView = components["schemas"]["RegionView"];
type PagePayload = components["schemas"]["PagePayload"];

const PROJECT_ID = "proj1";
const PAGE_IDX = 0;

function proposal(proposal_id: string, y: number, x = 0): RegionView {
  return {
    region_id: null,
    proposal_id,
    role: "paragraph",
    box: { x, y, width: 10, height: 10 },
    confirmed: false,
    confidence: 0.9,
    stale: false,
  };
}

function confirmedRegion(region_id: string, y: number, x = 0): RegionView {
  return {
    region_id,
    proposal_id: null,
    role: "paragraph",
    box: { x, y, width: 10, height: 10 },
    confirmed: true,
    confidence: null,
    stale: false,
  };
}

// Three proposals, deliberately out of y-order in the array so ordering is
// exercised rather than incidentally correct.
const PAGE: PagePayload = {
  project_id: PROJECT_ID,
  page_index: PAGE_IDX,
  page_record: null,
  line_matches: [],
  encoded_dims: null,
  line_filter: "all",
  image_url: null,
  generation: 1,
  regions: [proposal("p2", 10), proposal("p1", 0), proposal("p3", 20)],
};

function pageWithConfirmedRegion(): PagePayload {
  return { ...PAGE, regions: [...(PAGE.regions ?? []), confirmedRegion("r1", 30)] };
}

// A single undecided proposal — deciding it leaves none behind, which is
// the case the auto-advance rule's clear-and-toast branch covers.
const PAGE_ONE_PROPOSAL: PagePayload = {
  ...PAGE,
  regions: [proposal("only", 0)],
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderHotkeys(
  page: PagePayload,
  options?: { navigate?: NavigateFunction; pageIndex?: number },
) {
  const qc = makeQueryClient();
  const navigate: NavigateFunction = options?.navigate ?? vi.fn();
  const pageIndex = options?.pageIndex ?? PAGE_IDX;
  return {
    ...renderHook(
      () => useRegionReviewHotkeys({ page, projectId: PROJECT_ID, pageIndex, navigate }),
      {
        wrapper: ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={qc}>{children}</QueryClientProvider>
        ),
      },
    ),
    navigate,
    qc,
  };
}

/**
 * Like `renderHotkeys`, but returns `rerender` wired to swap in a new
 * `page`/`pageIndex` pair without unmounting — used to simulate navigating
 * between pages within one hook instance's lifetime (its `useRef` state
 * persists across the rerender, same as it would across a real route change
 * within one mounted `ProjectPage`).
 */
function renderHotkeysReRenderable(
  page: PagePayload,
  options?: { navigate?: NavigateFunction; pageIndex?: number },
) {
  const qc = makeQueryClient();
  const navigate: NavigateFunction = options?.navigate ?? vi.fn();
  const pageIndex = options?.pageIndex ?? PAGE_IDX;
  const utils = renderHook(
    (props: { page: PagePayload; pageIndex: number }) =>
      useRegionReviewHotkeys({
        page: props.page,
        projectId: PROJECT_ID,
        pageIndex: props.pageIndex,
        navigate,
      }),
    {
      initialProps: { page, pageIndex },
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      ),
    },
  );
  return { ...utils, navigate, qc };
}

// react-hotkeys-hook 5 matches against the physical `KeyboardEvent.code`
// (e.g. "KeyN"), not `.key` — jsdom does not derive it from `key`, so every
// combo used in these tests needs its code spelled out explicitly.
const KEY_CODE: Record<string, string> = {
  n: "KeyN",
  p: "KeyP",
  x: "KeyX",
  enter: "Enter",
  delete: "Delete",
  "[": "BracketLeft",
  "]": "BracketRight",
};

function pressKey(key: string) {
  const code = KEY_CODE[key];
  if (code === undefined) throw new Error(`no KEY_CODE mapping for "${key}"`);
  fireEvent.keyDown(document, { key, code });
}

function deleteRoute(onCalled: () => void) {
  return http.delete("/api/projects/:pid/pages/:idx/regions/:regionId", () => {
    onCalled();
    return HttpResponse.json({ ...PAGE });
  });
}

beforeEach(() => {
  railStore.reset();
  railStore.getState().setTarget("region");
  clearSelection();
  worklistStore.reset();
  dialogStore.reset();
  reviewSelectionIntentStore.setState({ intent: null });
});

afterEach(() => {
  railStore.reset();
  clearSelection();
  worklistStore.reset();
  dialogStore.reset();
  reviewSelectionIntentStore.setState({ intent: null });
  vi.restoreAllMocks();
});

describe("useRegionReviewHotkeys: n / p stepping", () => {
  it("'n' from nothing selected selects the topmost proposal", () => {
    renderHotkeys(PAGE);
    pressKey("n");
    expect(selectionStore.getState().path.proposalId).toBe("p1");
  });

  it("'n' twice selects the second proposal in order", () => {
    renderHotkeys(PAGE);
    pressKey("n");
    pressKey("n");
    expect(selectionStore.getState().path.proposalId).toBe("p2");
  });

  it("'p' from the first proposal wraps to the last", () => {
    renderHotkeys(PAGE);
    pressKey("n"); // selects p1
    pressKey("p"); // wraps back to p3
    expect(selectionStore.getState().path.proposalId).toBe("p3");
  });
});

describe("useRegionReviewHotkeys: rail-target gate", () => {
  it("'n', 'enter' and 'x' do nothing when the rail target is not region", () => {
    railStore.getState().setTarget("word");
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("n");
    expect(selectionStore.getState().path.proposalId).toBe("p1");

    pressKey("enter");
    pressKey("x");
    // No mutation should have fired — selection untouched, still p1.
    expect(selectionStore.getState().path.proposalId).toBe("p1");
  });
});

describe("useRegionReviewHotkeys: enter accepts and auto-advances", () => {
  it("POSTs accept for the selected proposal, then selects the next one in order", async () => {
    let acceptedId: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        ({ params }) => {
          acceptedId = params.proposalId as string;
          return HttpResponse.json({ ...PAGE });
        },
      ),
    );
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("enter");

    await waitFor(() => expect(acceptedId).toBe("p1"));
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("p2"));
  });
});

describe("useRegionReviewHotkeys: x rejects and clears at the end of the list", () => {
  it("POSTs reject for the last remaining proposal in an otherwise-empty book, clears selection, and shows the book-empty toast", async () => {
    // The book's queue mirrors PAGE_ONE_PROPOSAL exactly: "only" is the sole
    // undecided proposal in the whole book, so deciding it should leave 0.
    const infoSpy = vi.spyOn(toast, "info");
    let rejectedId: string | undefined;
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({
          total_undecided: 1,
          pages: [
            {
              page_index: PAGE_IDX,
              undecided: 1,
              first_proposal_id: "only",
              last_proposal_id: "only",
            },
          ],
          items: [],
        }),
      ),
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ params }) => {
          rejectedId = params.proposalId as string;
          return HttpResponse.json({ ...PAGE_ONE_PROPOSAL });
        },
      ),
    );
    act(() => selectProposal("only"));
    const { qc } = renderHotkeys(PAGE_ONE_PROPOSAL);
    await waitFor(() =>
      expect(qc.getQueryData(["review-queue", PROJECT_ID, "reading", 0])).toBeDefined(),
    );

    pressKey("x");

    await waitFor(() => expect(rejectedId).toBe("only"));
    await waitFor(() => expect(selectionStore.getState().level).toBe("none"));
    expect(infoSpy).toHaveBeenCalledWith(
      "No undecided proposals left on this page. None left in the book.",
    );
  });

  it("names the book's remaining count and the ] key when the book still has work", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    let rejectedId: string | undefined;
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({
          total_undecided: 13,
          pages: [
            {
              page_index: PAGE_IDX,
              undecided: 1,
              first_proposal_id: "only",
              last_proposal_id: "only",
            },
            {
              page_index: PAGE_IDX + 3,
              undecided: 12,
              first_proposal_id: "q1",
              last_proposal_id: "q12",
            },
          ],
          items: [],
        }),
      ),
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ params }) => {
          rejectedId = params.proposalId as string;
          return HttpResponse.json({ ...PAGE_ONE_PROPOSAL });
        },
      ),
    );
    act(() => selectProposal("only"));
    const { qc } = renderHotkeys(PAGE_ONE_PROPOSAL);
    await waitFor(() =>
      expect(qc.getQueryData(["review-queue", PROJECT_ID, "reading", 0])).toBeDefined(),
    );

    pressKey("x");

    await waitFor(() => expect(rejectedId).toBe("only"));
    expect(infoSpy).toHaveBeenCalledWith(
      "No undecided proposals left on this page. 12 left in the book; press ] for the next.",
    );
  });

  // Finding 3 (low, ~line 245): `bookRemainingAfter` used to subtract a flat
  // 1 from whatever total_undecided was already cached. Two page-emptying
  // decisions that both settle before the review-queue invalidation refetch
  // resolves — the cache stays stale the whole time in this test, since the
  // queue route only ever answers once — both used to read `total - 1` and
  // report the same "12 left" count. Deciding on two different pages (the
  // second via `rerender`, simulating navigating there) means the second
  // decision isn't blocked by the shared-mutation-key `decisionPending` gate
  // (whole-branch review defect 1), which only covers one page at a time.
  it("counts decisions made since the cached queue value, not just the most recent one", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    let queueFetchCount = 0;
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () => {
        queueFetchCount += 1;
        if (queueFetchCount > 1) return new Promise<Response>(() => {}); // invalidation refetch: never resolves
        return HttpResponse.json({
          total_undecided: 13,
          pages: [
            { page_index: 5, undecided: 1, first_proposal_id: "onlyA", last_proposal_id: "onlyA" },
            { page_index: 6, undecided: 1, first_proposal_id: "onlyB", last_proposal_id: "onlyB" },
          ],
          items: [],
        });
      }),
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ params }) => HttpResponse.json({ ...PAGE, regions: [], page_index: Number(params.idx) }),
      ),
    );
    const pageOnlyA: PagePayload = { ...PAGE, page_index: 5, regions: [proposal("onlyA", 0)] };
    const pageOnlyB: PagePayload = { ...PAGE, page_index: 6, regions: [proposal("onlyB", 0)] };

    act(() => selectProposal("onlyA"));
    const { rerender, qc } = renderHotkeysReRenderable(pageOnlyA, { pageIndex: 5 });
    await waitFor(() =>
      expect(qc.getQueryData(["review-queue", PROJECT_ID, "reading", 0])).toBeDefined(),
    );

    pressKey("x");
    await waitFor(() =>
      expect(infoSpy).toHaveBeenLastCalledWith(
        "No undecided proposals left on this page. 12 left in the book; press ] for the next.",
      ),
    );

    // Simulate navigating to a different page with its own single proposal,
    // before the first decision's invalidation refetch (still pending, per
    // the handler above) has resolved — the queue cache is still the same
    // stale `total_undecided: 13`.
    rerender({ page: pageOnlyB, pageIndex: 6 });
    act(() => selectProposal("onlyB"));

    pressKey("x");
    await waitFor(() =>
      expect(infoSpy).toHaveBeenLastCalledWith(
        "No undecided proposals left on this page. 11 left in the book; press ] for the next.",
      ),
    );
  });

  it("wraps to the first proposal when others remain undecided", async () => {
    let rejectedId: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ params }) => {
          rejectedId = params.proposalId as string;
          return HttpResponse.json({ ...PAGE });
        },
      ),
    );
    act(() => selectProposal("p3"));
    renderHotkeys(PAGE);

    pressKey("x");

    await waitFor(() => expect(rejectedId).toBe("p3"));
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("p1"));
  });
});

describe("useRegionReviewHotkeys: delete behind the confirm dialog", () => {
  it("does not call the delete route until the confirm dialog is confirmed", async () => {
    const onCalled = vi.fn();
    server.use(deleteRoute(onCalled));
    const page = pageWithConfirmedRegion();
    act(() => selectRegion("r1"));
    renderHotkeys(page);

    pressKey("delete");

    expect(dialogStore.getState().confirm.open).toBe(true);
    expect(onCalled).not.toHaveBeenCalled();

    const onConfirm = dialogStore.getState().confirm.onConfirm;
    expect(onConfirm).toBeDefined();
    act(() => onConfirm?.());

    await waitFor(() => expect(onCalled).toHaveBeenCalledTimes(1));
  });
});

describe("useRegionReviewHotkeys: collision regression", () => {
  it("'n' under the region target leaves worklistStore's selectedLineIndex unchanged", () => {
    worklistStore.setSelectedLineIndex(3);
    renderHotkeys(PAGE);

    pressKey("n");

    expect(worklistStore.getState().selectedLineIndex).toBe(3);
  });
});

// ─── Whole-branch review defect 1: a decision can be sent twice ────────────

describe("useRegionReviewHotkeys: one decision at a time", () => {
  it("sends one accept request when 'enter' is pressed twice while the first is still pending", async () => {
    let acceptCount = 0;
    let resolveFirst!: () => void;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () => {
        acceptCount += 1;
        return new Promise<Response>((resolve) => {
          resolveFirst = () => resolve(HttpResponse.json({ ...PAGE }));
        });
      }),
    );
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("enter");
    // Let the mutation observer's pending state reach the hook's next render
    // before the second key arrives — otherwise both handlers would still
    // close over the pre-mutate `decisionPending=false`, same as a real
    // double-tap that lands inside one render's worth of wall-clock time
    // would not (react-query's own scheduling gives every render at least
    // one JS-engine tick to see the update).
    await waitFor(() => expect(acceptCount).toBe(1));

    pressKey("enter");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(acceptCount).toBe(1);
    resolveFirst();
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("p2"));
  });

  it("does not fire 'x' while an accept from 'enter' is still pending", async () => {
    let requestCount = 0;
    let resolveAccept!: () => void;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () => {
        requestCount += 1;
        return new Promise<Response>((resolve) => {
          resolveAccept = () => resolve(HttpResponse.json({ ...PAGE }));
        });
      }),
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject", () => {
        requestCount += 1;
        return HttpResponse.json({ ...PAGE });
      }),
    );
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("enter");
    await waitFor(() => expect(requestCount).toBe(1));

    pressKey("x");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(requestCount).toBe(1);
    resolveAccept();
  });
});

describe("useRegionReviewHotkeys: keyboard failures are no longer silent", () => {
  it("a keyboard accept that 500s shows an error toast and does not advance selection", async () => {
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("enter");

    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith("Accept failed"));
    // No advance: still on the proposal that was selected before the failure.
    expect(selectionStore.getState().path.proposalId).toBe("p1");
  });

  it("a keyboard reject that 500s shows an error toast and does not advance selection", async () => {
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );
    act(() => selectProposal("p1"));
    renderHotkeys(PAGE);

    pressKey("x");

    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith("Reject failed"));
    expect(selectionStore.getState().path.proposalId).toBe("p1");
  });

  it("a keyboard delete that 500s shows an error toast", async () => {
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.delete("/api/projects/:pid/pages/:idx/regions/:regionId", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );
    const page = pageWithConfirmedRegion();
    act(() => selectRegion("r1"));
    renderHotkeys(page);

    pressKey("delete");
    const onConfirm = dialogStore.getState().confirm.onConfirm;
    act(() => onConfirm?.());

    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith("Delete failed"));
  });
});

// ─── Whole-branch review defect 2: a selection can outlive its page ────────

describe("useRegionReviewHotkeys: the selection must still be on the current page", () => {
  it("'enter' with a proposalId absent from page.regions sends nothing", async () => {
    let acceptCount = 0;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () => {
        acceptCount += 1;
        return HttpResponse.json({ ...PAGE });
      }),
    );
    act(() => selectProposal("stale-from-old-page"));
    renderHotkeys(PAGE);

    pressKey("enter");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(acceptCount).toBe(0);
  });

  it("'x' with a proposalId absent from page.regions sends nothing", async () => {
    let rejectCount = 0;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject", () => {
        rejectCount += 1;
        return HttpResponse.json({ ...PAGE });
      }),
    );
    act(() => selectProposal("stale-from-old-page"));
    renderHotkeys(PAGE);

    pressKey("x");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(rejectCount).toBe(0);
  });

  it("'delete' with a regionId absent from page.regions sends nothing and does not open the confirm dialog", async () => {
    act(() => selectRegion("stale-region-from-old-page"));
    renderHotkeys(PAGE);

    pressKey("delete");

    expect(dialogStore.getState().confirm.open).toBe(false);
  });

  it("'enter' with a proposalId that is now a confirmed region (not undecided) sends nothing", async () => {
    // Simulates a refetch that just accepted the proposal from elsewhere:
    // the id now names a confirmed region, not an undecided proposal.
    let acceptCount = 0;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () => {
        acceptCount += 1;
        return HttpResponse.json({ ...PAGE });
      }),
    );
    const page = pageWithConfirmedRegion();
    act(() => selectProposal("r1"));
    renderHotkeys(page);

    pressKey("enter");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(acceptCount).toBe(0);
  });
});

// ─── Book review queue: '['/']' move between pages that have work ─────────
// Design: docs/specs/2026-09-17-book-review-queue-design.md
//   "Two keys move between pages that have work".

describe("useRegionReviewHotkeys: ']' and '[' move between pages with work", () => {
  // A page index comfortably away from 0 so "previous page" cases exercise
  // real page indices rather than incidentally passing at the book's start.
  const CURRENT = 5;

  function queueWith(pages: { page_index: number; first: string; last: string }[]) {
    return http.get("/api/projects/:pid/regions/review-queue", () =>
      HttpResponse.json({
        total_undecided: pages.length,
        pages: pages.map((p) => ({
          page_index: p.page_index,
          undecided: 1,
          first_proposal_id: p.first,
          last_proposal_id: p.last,
        })),
        items: [],
      }),
    );
  }

  async function renderAtCurrentPage() {
    const rendered = renderHotkeys(PAGE, { pageIndex: CURRENT });
    await waitFor(() =>
      expect(rendered.qc.getQueryData(["review-queue", PROJECT_ID, "reading", 0])).toBeDefined(),
    );
    return rendered;
  }

  it("']' navigates to the next page with work and records its first proposal to select", async () => {
    server.use(
      queueWith([
        { page_index: CURRENT, first: "p-here", last: "p-here" },
        { page_index: CURRENT + 2, first: "q-first", last: "q-last" },
      ]),
    );
    const { navigate } = await renderAtCurrentPage();

    pressKey("]");

    expect(navigate).toHaveBeenCalledWith(
      `/projects/${PROJECT_ID}/pages/pageno/${String(CURRENT + 2 + 1)}`,
    );
    expect(reviewSelectionIntentStore.getState().intent).toEqual({
      pageIndex: CURRENT + 2,
      proposalId: "q-first",
    });
  });

  it("'[' navigates to the previous page with work and records its last proposal to select", async () => {
    server.use(
      queueWith([
        { page_index: CURRENT - 3, first: "r-first", last: "r-last" },
        { page_index: CURRENT, first: "p-here", last: "p-here" },
      ]),
    );
    const { navigate } = await renderAtCurrentPage();

    pressKey("[");

    expect(navigate).toHaveBeenCalledWith(
      `/projects/${PROJECT_ID}/pages/pageno/${String(CURRENT - 3 + 1)}`,
    );
    expect(reviewSelectionIntentStore.getState().intent).toEqual({
      pageIndex: CURRENT - 3,
      proposalId: "r-last",
    });
  });

  it("']' with no later page shows the toast and does not navigate", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    server.use(queueWith([{ page_index: CURRENT, first: "p-here", last: "p-here" }]));
    const { navigate } = await renderAtCurrentPage();

    pressKey("]");

    expect(navigate).not.toHaveBeenCalled();
    expect(infoSpy).toHaveBeenCalledWith("No more pages with undecided proposals after this page.");
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("'[' with no earlier page shows the toast and does not navigate", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    server.use(queueWith([{ page_index: CURRENT, first: "p-here", last: "p-here" }]));
    const { navigate } = await renderAtCurrentPage();

    pressKey("[");

    expect(navigate).not.toHaveBeenCalled();
    expect(infoSpy).toHaveBeenCalledWith("No pages with undecided proposals before this page.");
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("'[' and ']' do nothing when the rail target is not region", async () => {
    railStore.getState().setTarget("word");
    server.use(
      queueWith([
        { page_index: CURRENT - 1, first: "r-first", last: "r-last" },
        { page_index: CURRENT + 1, first: "q-first", last: "q-last" },
      ]),
    );
    const { navigate } = await renderAtCurrentPage();

    pressKey("]");
    pressKey("[");

    expect(navigate).not.toHaveBeenCalled();
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  // Finding 2 (medium, ~line 296): before the first queue fetch resolves,
  // `queueQ.data` is undefined, so `queueQ.data?.pages ?? []` reads as an
  // empty page list — indistinguishable from a book with no work at all.
  // Pressing ']'/'[' in that window showed the "no more pages" toast even
  // when work exists elsewhere in the book.
  it("']' shows a loading toast and does not navigate when the queue has not fetched yet", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    server.use(
      http.get(
        "/api/projects/:pid/regions/review-queue",
        () => new Promise<Response>(() => {}), // never resolves in this test
      ),
    );
    const { navigate } = renderHotkeys(PAGE, { pageIndex: CURRENT });

    pressKey("]");

    expect(navigate).not.toHaveBeenCalled();
    expect(infoSpy).toHaveBeenCalledWith("Review queue is still loading.");
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("'[' shows a loading toast and does not navigate when the queue has not fetched yet", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    server.use(
      http.get(
        "/api/projects/:pid/regions/review-queue",
        () => new Promise<Response>(() => {}), // never resolves in this test
      ),
    );
    const { navigate } = renderHotkeys(PAGE, { pageIndex: CURRENT });

    pressKey("[");

    expect(navigate).not.toHaveBeenCalled();
    expect(infoSpy).toHaveBeenCalledWith("Review queue is still loading.");
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });
});
