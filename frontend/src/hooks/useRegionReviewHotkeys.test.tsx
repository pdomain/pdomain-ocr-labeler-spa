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
import { server } from "../test/server";
import { useRegionReviewHotkeys } from "./useRegionReviewHotkeys";
import { railStore } from "../stores/rail-store";
import {
  selectionStore,
  selectProposal,
  selectRegion,
  clearSelection,
} from "../stores/selection-store";
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

function renderHotkeys(page: PagePayload) {
  const qc = makeQueryClient();
  return renderHook(
    () => useRegionReviewHotkeys({ page, projectId: PROJECT_ID, pageIndex: PAGE_IDX }),
    {
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      ),
    },
  );
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
});

afterEach(() => {
  railStore.reset();
  clearSelection();
  worklistStore.reset();
  dialogStore.reset();
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
  it("POSTs reject for the last remaining proposal, clears selection, and shows the toast", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    let rejectedId: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ params }) => {
          rejectedId = params.proposalId as string;
          return HttpResponse.json({ ...PAGE_ONE_PROPOSAL });
        },
      ),
    );
    act(() => selectProposal("only"));
    renderHotkeys(PAGE_ONE_PROPOSAL);

    pressKey("x");

    await waitFor(() => expect(rejectedId).toBe("only"));
    await waitFor(() => expect(selectionStore.getState().level).toBe("none"));
    expect(infoSpy).toHaveBeenCalledWith("No undecided proposals left on this page");
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
