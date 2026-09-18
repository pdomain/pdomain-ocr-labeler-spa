// CarriedRejectionsPanel.test.tsx — tests for the carried-rejection summary
// RightPanel mounts unconditionally (see RegionDetail.tsx's own doc comment
// for why it is not part of <RegionDetail>, and RightPanel.tsx for where it
// mounts).
//
// Pattern copied from RegionDetail.test.tsx: a PagePayload literal, a
// QueryClientProvider with retries off, and MSW for HTTP. No selection-store
// interaction here — that is the whole point of this component.

import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { CarriedRejectionsPanel } from "./RegionDetail";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
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

const UNDECIDED_PROPOSAL: RegionProposalView = {
  proposal_id: "prop-undecided",
  run_id: "run-1",
  page_index: 0,
  role: "page header",
  box: { x: 0, y: 0, width: 100, height: 20 },
  confidence: 0.9,
  evidence: {},
  disposition: null,
};

const CARRIED_REJECTED_PROPOSAL: RegionProposalView = {
  proposal_id: "prop-carried-rejected",
  run_id: "run-2",
  page_index: 0,
  role: "sidenote",
  box: { x: 0, y: 400, width: 100, height: 20 },
  confidence: 0.62,
  evidence: {},
  disposition: "rejected",
  carried_from_run_id: "run-1",
  carried_from_proposal_id: "prop-original",
};

const DIRECTLY_REJECTED_PROPOSAL: RegionProposalView = {
  proposal_id: "prop-directly-rejected",
  run_id: "run-1",
  page_index: 0,
  role: "caption",
  box: { x: 0, y: 440, width: 100, height: 20 },
  confidence: 0.4,
  evidence: {},
  disposition: "rejected",
};

const REOPENED_PROPOSAL: RegionProposalView = {
  proposal_id: "prop-reopened",
  run_id: "run-1",
  page_index: 0,
  role: "footnote",
  box: { x: 0, y: 480, width: 100, height: 20 },
  confidence: 0.55,
  evidence: {},
  disposition: "reopened",
  carried_from_run_id: null,
  carried_from_proposal_id: null,
};

function makePage(proposals: RegionProposalView[]): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    page_kind_reviewed: false,
    regions: [],
    proposals,
  };
}

describe("CarriedRejectionsPanel", () => {
  it("renders nothing when the page has no carried rejections", () => {
    renderWithQuery(
      <CarriedRejectionsPanel
        page={makePage([UNDECIDED_PROPOSAL, DIRECTLY_REJECTED_PROPOSAL, REOPENED_PROPOSAL])}
        projectId="p1"
        pageIndex={0}
      />,
    );
    expect(screen.queryByTestId("carried-rejections-summary")).not.toBeInTheDocument();
  });

  it("counts only carried rejections, not a direct rejection, an undecided, or a reopened proposal", () => {
    renderWithQuery(
      <CarriedRejectionsPanel
        page={makePage([
          UNDECIDED_PROPOSAL,
          CARRIED_REJECTED_PROPOSAL,
          DIRECTLY_REJECTED_PROPOSAL,
          REOPENED_PROPOSAL,
        ])}
        projectId="p1"
        pageIndex={0}
      />,
    );
    expect(screen.getByTestId("carried-rejections-count")).toHaveTextContent(
      "1 rejected proposal carried from an earlier decision",
    );
  });

  it("is collapsed by default and expands the list on toggle", async () => {
    const user = userEvent.setup();
    renderWithQuery(
      <CarriedRejectionsPanel
        page={makePage([CARRIED_REJECTED_PROPOSAL, DIRECTLY_REJECTED_PROPOSAL])}
        projectId="p1"
        pageIndex={0}
      />,
    );
    expect(screen.queryByTestId("carried-rejections-list")).not.toBeInTheDocument();
    const toggle = screen.getByTestId("carried-rejections-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("carried-rejections-list")).toBeInTheDocument();
    expect(screen.getByTestId("carried-rejections-item-prop-carried-rejected")).toHaveTextContent(
      "sidenote",
    );
    expect(
      screen.queryByTestId("carried-rejections-item-prop-directly-rejected"),
    ).not.toBeInTheDocument();
  });

  it("clicking Bring back POSTs to the unreject route", async () => {
    const user = userEvent.setup();
    let method: string | undefined;
    let path: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/unreject",
        ({ request }) => {
          method = request.method;
          path = new URL(request.url).pathname;
          return HttpResponse.json(makePage([]));
        },
      ),
    );

    renderWithQuery(
      <CarriedRejectionsPanel
        page={makePage([CARRIED_REJECTED_PROPOSAL])}
        projectId="p1"
        pageIndex={0}
      />,
    );
    await user.click(screen.getByTestId("carried-rejections-toggle"));
    await user.click(screen.getByTestId("carried-rejections-bring-back-prop-carried-rejected"));

    await waitFor(() => expect(method).toBeDefined());
    expect(method).toBe("POST");
    expect(path).toBe("/api/projects/p1/pages/0/regions/proposals/prop-carried-rejected/unreject");
  });

  it("shows an inline error when un-reject fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/unreject",
        () => new HttpResponse("proposal not rejected", { status: 409 }),
      ),
    );

    renderWithQuery(
      <CarriedRejectionsPanel
        page={makePage([CARRIED_REJECTED_PROPOSAL])}
        projectId="p1"
        pageIndex={0}
      />,
    );
    await user.click(screen.getByTestId("carried-rejections-toggle"));
    await user.click(screen.getByTestId("carried-rejections-bring-back-prop-carried-rejected"));

    expect(
      await screen.findByTestId("carried-rejections-error-prop-carried-rejected"),
    ).toBeInTheDocument();
  });
});
