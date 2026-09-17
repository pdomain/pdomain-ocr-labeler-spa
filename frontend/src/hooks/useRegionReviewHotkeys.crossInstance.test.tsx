// useRegionReviewHotkeys.crossInstance.test.tsx — proves the shared in-flight
// signal (whole-branch review defect 1) works across separate hook/component
// instances, not just within one.
//
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// `RegionDetail` and `useRegionReviewHotkeys` each build their own
// `useAcceptProposal`/`useRejectProposal`/`useEditRegion`/`useDeleteRegion`
// instances — `RegionDetail` is the right-panel component; the hotkeys hook
// is registered once at the page level (`ProjectPage.tsx`). They only share
// a `QueryClient`, never a React subtree. `Harness` below mounts both under
// one `QueryClientProvider`, the same relationship they have in the real
// app, so a guard that only checked "my own instance's `isPending`" would
// pass here and still fail in production.

import React from "react";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useRegionReviewHotkeys } from "./useRegionReviewHotkeys";
import { RegionDetail } from "../components/right-panel/RegionDetail";
import { railStore } from "../stores/rail-store";
import { selectProposal, clearSelection } from "../stores/selection-store";
import { dialogStore } from "../stores/dialog-store";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionView = components["schemas"]["RegionView"];

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

const PAGE: PagePayload = {
  project_id: PROJECT_ID,
  page_index: PAGE_IDX,
  page_record: null,
  line_matches: [],
  encoded_dims: null,
  line_filter: "all",
  image_url: null,
  generation: 1,
  regions: [proposal("p1", 0), proposal("p2", 10)],
  proposals: [],
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/**
 * Mounts the hotkeys hook and the right-panel component side by side under
 * one QueryClient — the real app's relationship, minus everything else
 * ProjectPage renders.
 */
function Harness({ page }: { page: PagePayload }) {
  useRegionReviewHotkeys({ page, projectId: PROJECT_ID, pageIndex: PAGE_IDX });
  return <RegionDetail page={page} projectId={PROJECT_ID} pageIndex={PAGE_IDX} />;
}

function renderHarness(page: PagePayload) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <Harness page={page} />
    </QueryClientProvider>,
  );
}

function pressEnter() {
  fireEvent.keyDown(document, { key: "enter", code: "Enter" });
}

beforeEach(() => {
  railStore.reset();
  railStore.getState().setTarget("region");
  clearSelection();
  dialogStore.reset();
});

afterEach(() => {
  railStore.reset();
  clearSelection();
  dialogStore.reset();
});

describe("useRegionReviewHotkeys + RegionDetail: one decision at a time, across instances", () => {
  it("a keyboard 'enter' sends nothing while the panel's own Accept click is still pending", async () => {
    const user = userEvent.setup();
    let acceptCount = 0;
    let resolvePanelAccept!: () => void;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () => {
        acceptCount += 1;
        return new Promise<Response>((resolve) => {
          resolvePanelAccept = () => resolve(HttpResponse.json({ ...PAGE }));
        });
      }),
    );
    selectProposal("p1");
    renderHarness(PAGE);

    await user.click(screen.getByTestId("region-detail-accept"));
    await waitFor(() => expect(screen.getByTestId("region-detail-accept")).toBeDisabled());
    expect(acceptCount).toBe(1);

    // The hotkeys hook is a separate useAcceptProposal instance — its own
    // isPending is false. Only the shared mutationKey can catch this.
    pressEnter();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(acceptCount).toBe(1);
    resolvePanelAccept();
    await waitFor(() => expect(screen.getByTestId("region-detail-accept")).not.toBeDisabled());
  });

  it("the panel's Accept button is disabled while a keyboard-initiated accept is pending", async () => {
    let resolveKeyboardAccept!: () => void;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        () =>
          new Promise<Response>((resolve) => {
            resolveKeyboardAccept = () => resolve(HttpResponse.json({ ...PAGE }));
          }),
      ),
    );
    selectProposal("p1");
    renderHarness(PAGE);

    // The panel's own acceptProposal.isPending is false here — the hotkey
    // hook's instance is the one making the request.
    pressEnter();

    await waitFor(() => expect(screen.getByTestId("region-detail-accept")).toBeDisabled());
    expect(screen.getByTestId("region-detail-reject")).toBeDisabled();

    resolveKeyboardAccept();
    await waitFor(() => expect(screen.getByTestId("region-detail-accept")).not.toBeDisabled());
  });
});
