// RegionDetail.test.tsx — tests for the region review detail panel.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 4
//
// Pattern copied from right-panel/LineDetail.test.tsx: a PagePayload literal,
// a QueryClientProvider with retries off, selection driven through the
// selection-store actions, and MSW for HTTP.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { RegionDetail } from "./RegionDetail";
import { clearSelection, selectProposal, selectRegion } from "../../stores/selection-store";
import { dialogStore } from "../../stores/dialog-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionView = components["schemas"]["RegionView"];
type RegionProposalView = components["schemas"]["RegionProposalView"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const PROPOSAL_REGION: RegionView = {
  region_id: null,
  proposal_id: "prop-1",
  role: "page header",
  box: { x: 0, y: 0, width: 100, height: 20 },
  confirmed: false,
  confidence: 0.8765,
  stale: false,
};

const STALE_PROPOSAL_REGION: RegionView = {
  region_id: null,
  proposal_id: "prop-2",
  role: "footnote",
  box: { x: 0, y: 200, width: 100, height: 20 },
  confirmed: false,
  confidence: 0.5,
  stale: true,
};

const CONFIRMED_FROM_PROPOSAL: RegionView = {
  region_id: "region-1",
  proposal_id: "prop-3",
  role: "title",
  box: { x: 0, y: 40, width: 100, height: 20 },
  confirmed: true,
  confidence: null,
  stale: false,
};

const CONFIRMED_DRAWN_BY_HAND: RegionView = {
  region_id: "region-2",
  proposal_id: null,
  role: "table",
  box: { x: 0, y: 80, width: 100, height: 20 },
  confirmed: true,
  confidence: null,
  stale: false,
};

const PROPOSAL_1_EVIDENCE: RegionProposalView = {
  proposal_id: "prop-1",
  run_id: "run-1",
  page_index: 0,
  role: "page header",
  box: { x: 0, y: 0, width: 100, height: 20 },
  confidence: 0.8765,
  evidence: { band: "header", cluster_width: 120, fitted: true },
  disposition: null,
};

const PROPOSAL_2_EVIDENCE: RegionProposalView = {
  proposal_id: "prop-2",
  run_id: "run-1",
  page_index: 0,
  role: "footnote",
  box: { x: 0, y: 200, width: 100, height: 20 },
  confidence: 0.5,
  evidence: { band: "footer" },
  disposition: null,
};

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    page_kind_reviewed: false,
    regions: [
      PROPOSAL_REGION,
      STALE_PROPOSAL_REGION,
      CONFIRMED_FROM_PROPOSAL,
      CONFIRMED_DRAWN_BY_HAND,
    ],
    proposals: [PROPOSAL_1_EVIDENCE, PROPOSAL_2_EVIDENCE],
  };
}

describe("RegionDetail", () => {
  beforeEach(() => {
    clearSelection();
    dialogStore.reset();
  });

  it("shows role, confidence and evidence keys for a selected proposal", () => {
    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);

    const panel = screen.getByTestId("region-detail");
    expect(panel).toHaveTextContent("page header");
    expect(panel).toHaveTextContent("0.88");
    expect(panel).toHaveTextContent("band");
    expect(panel).toHaveTextContent("cluster_width");
    expect(panel).toHaveTextContent("fitted");
  });

  it("shows a Stale badge for a stale proposal and not for a fresh one", () => {
    selectProposal("prop-2");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-detail-stale-badge")).toBeInTheDocument();
  });

  it("does not show a Stale badge for a non-stale proposal", () => {
    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.queryByTestId("region-detail-stale-badge")).not.toBeInTheDocument();
  });

  it("clicking Accept POSTs to the accept route with an empty body", async () => {
    const user = userEvent.setup();
    let method: string | undefined;
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          method = request.method;
          path = new URL(request.url).pathname;
          body = await request.json();
          return HttpResponse.json(makePage());
        },
      ),
    );

    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-detail-accept"));

    await waitFor(() => expect(body).toBeDefined());
    expect(method).toBe("POST");
    expect(path).toBe("/api/projects/p1/pages/0/regions/proposals/prop-1/accept");
    expect(body).toEqual({});
  });

  it("choosing a role in Accept as POSTs { role } to the accept route", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(makePage());
        },
      ),
    );

    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);

    await user.selectOptions(screen.getByTestId("region-detail-accept-as-select"), "page footer");
    await user.click(screen.getByTestId("region-detail-accept-as-apply"));

    await waitFor(() => expect(body).toBeDefined());
    expect(body).toEqual({ role: "page footer" });
  });

  it("clicking Reject POSTs to the reject route", async () => {
    const user = userEvent.setup();
    let method: string | undefined;
    let path: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ request }) => {
          method = request.method;
          path = new URL(request.url).pathname;
          return HttpResponse.json(makePage());
        },
      ),
    );

    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-detail-reject"));

    await waitFor(() => expect(method).toBeDefined());
    expect(method).toBe("POST");
    expect(path).toBe("/api/projects/p1/pages/0/regions/proposals/prop-1/reject");
  });

  it("shows 'From a proposal' for a confirmed region promoted from one", () => {
    selectRegion("region-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-detail-origin")).toHaveTextContent("From a proposal");
  });

  it("shows 'Drawn by hand' for a confirmed region with no proposal_id", () => {
    selectRegion("region-2");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-detail-origin")).toHaveTextContent("Drawn by hand");
  });

  it("Delete does not call the route until the confirm dialog is confirmed", async () => {
    const user = userEvent.setup();
    let deleteCalled = false;
    server.use(
      http.delete("/api/projects/:pid/pages/:idx/regions/:regionId", () => {
        deleteCalled = true;
        return HttpResponse.json(makePage());
      }),
    );

    selectRegion("region-2");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-detail-delete"));

    expect(deleteCalled).toBe(false);
    const confirm = dialogStore.getState().confirm;
    expect(confirm.open).toBe(true);

    confirm.onConfirm?.();
    dialogStore.close("confirm");

    await waitFor(() => expect(deleteCalled).toBe(true));
  });

  it("shows the not-found message when the id is in neither list", () => {
    selectProposal("prop-does-not-exist");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-detail")).toHaveTextContent(/no longer on the page/i);
  });

  it("shows the not-found message when a regionId is in neither list", () => {
    selectRegion("region-does-not-exist");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-detail")).toHaveTextContent(/no longer on the page/i);
  });
});
