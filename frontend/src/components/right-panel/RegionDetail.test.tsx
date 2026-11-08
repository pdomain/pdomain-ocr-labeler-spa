// RegionDetail.test.tsx — tests for the region review detail panel.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 4
//
// Pattern copied from right-panel/LineDetail.test.tsx: a PagePayload literal,
// a QueryClientProvider with retries off, selection driven through the
// selection-store actions, and MSW for HTTP.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { RegionDetail, RegionDrawPrompt } from "./RegionDetail";
import {
  clearSelection,
  selectProposal,
  selectRegion,
  selectionStore,
} from "../../stores/selection-store";
import { regionDraftStore } from "../../stores/region-draft-store";
import { dialogStore } from "../../stores/dialog-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionView = components["schemas"]["RegionView"];
type RegionProposalView = components["schemas"]["RegionProposalView"];
type LayoutStructure = components["schemas"]["LayoutStructure"];

const VERSE_STRUCTURE: LayoutStructure = {
  kind: "poetry",
  lines: [
    {
      text: "First line",
      word_ids: ["word-1"],
      word_signatures: ["word-1@0,0,10,10"],
      stanza_index: 0,
      indent_hint: "2em",
    },
  ],
  table_rows: [],
};

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
      { ...PROPOSAL_REGION },
      { ...STALE_PROPOSAL_REGION },
      { ...CONFIRMED_FROM_PROPOSAL },
      { ...CONFIRMED_DRAWN_BY_HAND },
    ],
    proposals: [
      { ...PROPOSAL_1_EVIDENCE, evidence: { ...PROPOSAL_1_EVIDENCE.evidence } },
      { ...PROPOSAL_2_EVIDENCE, evidence: { ...PROPOSAL_2_EVIDENCE.evidence } },
    ],
  };
}

describe("RegionDetail", () => {
  beforeEach(() => {
    clearSelection();
    dialogStore.reset();
    regionDraftStore.reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it("shows editable reviewed structure and sends it when accepting a proposal", async () => {
    const user = userEvent.setup();
    let body: unknown;
    const page = makePage();
    const proposal = page.proposals?.find((item) => item.proposal_id === "prop-1");
    if (proposal) {
      proposal.evidence = { layout_structure: VERSE_STRUCTURE, structure_supported: true };
    }
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(page);
        },
      ),
    );

    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={page} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-layout-editor")).toHaveTextContent("First line");
    await user.click(screen.getByTestId("region-detail-accept"));

    await waitFor(() => expect(body).toEqual({ layout_structure: VERSE_STRUCTURE }));
  });

  it("shows loose poetry evidence without a matched structure and keeps ordinary acceptance available", async () => {
    const user = userEvent.setup();
    let body: unknown;
    const page = makePage();
    const proposal = page.proposals?.find((item) => item.proposal_id === "prop-1");
    if (proposal)
      proposal.evidence = {
        structure_supported: false,
        layout_warnings: ["No unique ordered OCR match."],
        layout_hints: [
          {
            source: "f2",
            kind: "poetry",
            lines: [{ text: "Loose verse", stanza_index: 0, indent_hint: "2em" }],
          },
        ],
      };
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(page);
        },
      ),
    );

    selectProposal("prop-1");
    renderWithQuery(<RegionDetail page={page} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-layout-prepared-required")).toBeInTheDocument();
    expect(screen.getByTestId("region-layout-hint-0-line-0")).toHaveTextContent(
      "Loose verse Stanza 0 Source indent 2em",
    );
    expect(screen.getByTestId("region-layout-warning-0")).toHaveTextContent(
      "No unique ordered OCR match.",
    );
    expect(screen.queryByTestId("region-layout-editor")).toBeNull();
    await user.click(screen.getByTestId("region-detail-accept"));
    await waitFor(() => expect(body).toEqual({}));
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

  it("saves reviewed structure on a confirmed region and starts a regions-only export", async () => {
    const user = userEvent.setup();
    let editBody: unknown;
    let exportBody: unknown;
    const page = makePage();
    const region = page.regions?.find((item) => item.region_id === "region-1");
    if (region) region.layout_structure = VERSE_STRUCTURE;
    server.use(
      http.patch("/api/projects/:pid/pages/:idx/regions/:regionId", async ({ request }) => {
        editBody = await request.json();
        return HttpResponse.json(page);
      }),
      http.post("/api/projects/:pid/export", async ({ request }) => {
        exportBody = await request.json();
        return HttpResponse.json({ job_id: "export-regions" }, { status: 202 });
      }),
    );

    selectRegion("region-1");
    renderWithQuery(<RegionDetail page={page} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-layout-save"));
    await waitFor(() => expect(editBody).toEqual({ layout_structure: VERSE_STRUCTURE }));
    await user.click(screen.getByTestId("region-layout-export"));
    await waitFor(() =>
      expect(exportBody).toEqual({
        scope: "current",
        page_index: 0,
        style_filters: [],
        component_filter: null,
        include_classification: false,
        detection_only: false,
        recognition_only: false,
        regions_only: true,
      }),
    );
  });

  it("shows a regions-only export job error from SSE", async () => {
    let listener: ((event: MessageEvent) => void) | undefined;
    class EventSourceMock {
      static readonly CLOSED = 2;
      readonly readyState = 0;
      addEventListener(type: string, callback: (event: MessageEvent) => void): void {
        if (type === "error") listener = callback;
      }
      removeEventListener(): void {}
      close(): void {}
    }
    vi.stubGlobal("EventSource", EventSourceMock);
    const user = userEvent.setup();
    server.use(
      http.post("/api/projects/:pid/export", () =>
        HttpResponse.json({ job_id: "export-regions" }, { status: 202 }),
      ),
    );
    selectRegion("region-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-layout-export"));
    await waitFor(() => expect(listener).toBeDefined());
    act(() => {
      listener?.({
        data: JSON.stringify({
          id: "export-regions",
          type: "export",
          project_id: "p1",
          status: "error",
          progress: { current: 0, total: 1, message: "Export failed" },
          created_at: "",
          updated_at: "",
          event: "error",
          error_message: "No output space.",
          result: null,
        }),
      } as MessageEvent);
    });
    expect(await screen.findByTestId("region-layout-export-job-error")).toHaveTextContent(
      "No output space.",
    );
  });

  it("shows a regions-only export cancellation from SSE", async () => {
    let listener: ((event: MessageEvent) => void) | undefined;
    class EventSourceMock {
      static readonly CLOSED = 2;
      readonly readyState = 0;
      addEventListener(type: string, callback: (event: MessageEvent) => void): void {
        if (type === "cancelled") listener = callback;
      }
      removeEventListener(): void {}
      close(): void {}
    }
    vi.stubGlobal("EventSource", EventSourceMock);
    const user = userEvent.setup();
    server.use(
      http.post("/api/projects/:pid/export", () =>
        HttpResponse.json({ job_id: "export-regions" }, { status: 202 }),
      ),
    );
    selectRegion("region-1");
    renderWithQuery(<RegionDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-layout-export"));
    await waitFor(() => expect(listener).toBeDefined());
    act(() => {
      listener?.({
        data: JSON.stringify({
          id: "export-regions",
          type: "export",
          project_id: "p1",
          status: "cancelled",
          progress: { current: 0, total: 1, message: "Cancelled" },
          created_at: "",
          updated_at: "",
          event: "cancelled",
          error_message: null,
          result: null,
        }),
      } as MessageEvent);
    });
    expect(await screen.findByTestId("region-layout-export-cancelled")).toHaveTextContent(
      "cancelled",
    );
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

  it("checks words that match the region and saves the edited set", async () => {
    const user = userEvent.setup();
    const page = makePage();
    page.line_matches = [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "one two",
        ground_truth_line_text: "one two",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "one",
            ground_truth_text: "one",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 10, y: 20, width: 30, height: 8 },
          },
          {
            line_index: 0,
            word_index: 1,
            ocr_text: "two",
            ground_truth_text: "two",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 50, y: 20, width: 10, height: 8 },
          },
        ],
        overall_match_status: "exact",
        exact_count: 2,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 2,
        is_fully_validated: false,
      },
    ];
    const drawn = page.regions?.find((region) => region.region_id === "region-2");
    if (drawn) drawn.member_word_signatures = [[10, 20, 40, 28, false]];

    let body: unknown;
    server.use(
      http.put("/api/projects/:pid/pages/:idx/regions/:regionId/words", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(page);
      }),
    );

    selectRegion("region-2");
    renderWithQuery(<RegionDetail page={page} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-member-0-0")).toBeChecked();
    expect(screen.getByTestId("region-member-0-1")).not.toBeChecked();

    await user.click(screen.getByTestId("region-member-0-1"));
    await user.click(screen.getByTestId("region-membership-save"));

    await waitFor(() =>
      expect(body).toEqual({
        word_refs: [
          { line_index: 0, word_index: 0 },
          { line_index: 0, word_index: 1 },
        ],
      }),
    );
  });
});

describe("RegionDrawPrompt", () => {
  beforeEach(() => {
    clearSelection();
    regionDraftStore.reset();
  });

  it("posts the draft box with the paragraph role and selects the new region", async () => {
    const user = userEvent.setup();
    regionDraftStore.getState().setBox({ x: 8, y: 9, width: 10, height: 11 });
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions", async ({ request }) => {
        body = await request.json();
        const created = makePage();
        created.regions = [
          ...(created.regions ?? []),
          {
            region_id: "region-new",
            proposal_id: "hand-drawn",
            role: "paragraph",
            box: { x: 8, y: 9, width: 10, height: 11 },
            confirmed: true,
            confidence: null,
            stale: false,
          },
        ];
        return HttpResponse.json(created);
      }),
    );

    renderWithQuery(<RegionDrawPrompt page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("region-draw-role")).toHaveValue("paragraph");
    await user.click(screen.getByTestId("region-draw-create"));

    await waitFor(() =>
      expect(body).toEqual({ role: "paragraph", box: { x: 8, y: 9, width: 10, height: 11 } }),
    );
    expect(selectionStore.getState().path.regionId).toBe("region-new");
    expect(regionDraftStore.getState().box).toBeNull();
  });

  it("clears the draft when Cancel is clicked", async () => {
    const user = userEvent.setup();
    regionDraftStore.getState().setBox({ x: 1, y: 1, width: 2, height: 2 });
    renderWithQuery(<RegionDrawPrompt page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("region-draw-cancel"));
    expect(regionDraftStore.getState().box).toBeNull();
    expect(screen.queryByTestId("region-draw-prompt")).toBeNull();
  });
});
