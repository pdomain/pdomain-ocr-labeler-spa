// ReviewQueuePanel.test.tsx — unit tests for the book-wide review queue panel.
// Spec: docs/specs/2026-09-17-book-review-queue-design.md
//   "What this increment does not build" — the queue panel and the
//   confidence-order UI this file exercises.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ReviewQueuePanel } from "./ReviewQueuePanel";
import { useUiPrefs } from "../../stores/ui-prefs";
import { selectionStore, clearSelection, selectProposal } from "../../stores/selection-store";
import {
  reviewSelectionIntentStore,
  clearReviewSelectionIntent,
} from "../../stores/review-selection-intent-store";
import type { components } from "../../api/types";

type RegionReviewQueueItem = components["schemas"]["RegionReviewQueueItem"];

const PROJECT_ID = "proj-1";

function item(overrides: Partial<RegionReviewQueueItem> = {}): RegionReviewQueueItem {
  return {
    page_index: 0,
    proposal_id: "p1",
    run_id: "r1",
    role: "paragraph",
    confidence: 0.5,
    box: { x: 0, y: 0, width: 10, height: 10 },
    evidence: {},
    ...overrides,
  };
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** Writes the current location's pathname to a locator the tests can read. */
function LocationSpy() {
  const loc = useLocation();
  return <span data-testid="current-url">{loc.pathname}</span>;
}

function renderPanel(pageIndex = 0, qc = makeQueryClient()) {
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter
          initialEntries={[`/projects/${PROJECT_ID}/pages/pageno/${String(pageIndex + 1)}`]}
        >
          <LocationSpy />
          <Routes>
            <Route
              path="/projects/:projectId/pages/pageno/:pageNo"
              element={<ReviewQueuePanel projectId={PROJECT_ID} pageIndex={pageIndex} />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
    qc,
  };
}

function currentUrl(): string {
  return screen.getByTestId("current-url").textContent ?? "";
}

function mockReviewQueue(
  items: RegionReviewQueueItem[],
  opts?: { onRequest?: (url: URL) => void },
) {
  server.use(
    http.get(`/api/projects/${PROJECT_ID}/regions/review-queue`, ({ request }) => {
      opts?.onRequest?.(new URL(request.url));
      return HttpResponse.json({ total_undecided: items.length, pages: [], items });
    }),
  );
}

beforeEach(() => {
  useUiPrefs.setState({ reviewQueueOrder: "reading" });
  clearSelection();
  clearReviewSelectionIntent();
});

describe("ReviewQueuePanel — order toggle", () => {
  it("requests order=reading and limit=200 by default", async () => {
    let requestedUrl: URL | undefined;
    mockReviewQueue([item()], { onRequest: (url) => (requestedUrl = url) });

    renderPanel();

    await waitFor(() => expect(requestedUrl).toBeDefined());
    expect(requestedUrl?.searchParams.get("order")).toBe("reading");
    expect(requestedUrl?.searchParams.get("limit")).toBe("200");
  });

  it("clicking the confidence toggle requests order=confidence", async () => {
    const user = userEvent.setup();
    let requestedUrl: URL | undefined;
    mockReviewQueue([item()], { onRequest: (url) => (requestedUrl = url) });

    renderPanel();
    await screen.findByTestId("review-queue-list");

    await user.click(screen.getByTestId("review-queue-order-confidence"));

    await waitFor(() => expect(requestedUrl?.searchParams.get("order")).toBe("confidence"));
    expect(useUiPrefs.getState().reviewQueueOrder).toBe("confidence");
  });

  it("reading order is the default and its toggle is pressed", async () => {
    mockReviewQueue([]);
    renderPanel();
    await screen.findByTestId("review-queue-empty");
    expect(screen.getByTestId("review-queue-order-reading")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("review-queue-order-confidence")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

describe("ReviewQueuePanel — loading vs. empty state", () => {
  it("shows a loading message while the first fetch is in flight, never claiming emptiness", async () => {
    let release: (() => void) | undefined;
    server.use(
      http.get(`/api/projects/${PROJECT_ID}/regions/review-queue`, async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({ total_undecided: 0, pages: [], items: [] });
      }),
    );

    renderPanel();

    expect(await screen.findByTestId("review-queue-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("review-queue-empty")).not.toBeInTheDocument();

    release?.();
    await screen.findByTestId("review-queue-empty");
  });

  it("shows an empty-book message once loaded with no undecided proposals", async () => {
    mockReviewQueue([]);
    renderPanel();

    const empty = await screen.findByTestId("review-queue-empty");
    expect(empty).toHaveTextContent(/no undecided proposals/i);
    expect(screen.queryByTestId("review-queue-loading")).not.toBeInTheDocument();
  });

  it("lists items with page number, role and confidence to two decimals", async () => {
    mockReviewQueue([
      item({ page_index: 2, proposal_id: "pA", role: "table", confidence: 0.6789 }),
    ]);
    renderPanel();

    const row = await screen.findByTestId("review-queue-item-2-pA");
    expect(row).toHaveTextContent("Page 3");
    expect(row).toHaveTextContent("table");
    expect(row).toHaveTextContent("0.68");
  });
});

describe("ReviewQueuePanel — clicking an item", () => {
  it("clicking an item on another page navigates and records a selection intent", async () => {
    const user = userEvent.setup();
    mockReviewQueue([item({ page_index: 4, proposal_id: "other-page-proposal" })]);

    renderPanel(0);
    await screen.findByTestId("review-queue-item-4-other-page-proposal");

    await user.click(screen.getByTestId("review-queue-item-4-other-page-proposal"));

    await waitFor(() => expect(currentUrl()).toBe(`/projects/${PROJECT_ID}/pages/pageno/5`));
    expect(reviewSelectionIntentStore.getState().intent).toEqual({
      pageIndex: 4,
      proposalId: "other-page-proposal",
    });
  });

  it("clicking the item for the current page selects it without navigating", async () => {
    const user = userEvent.setup();
    mockReviewQueue([item({ page_index: 0, proposal_id: "current-page-proposal" })]);

    renderPanel(0);
    await screen.findByTestId("review-queue-item-0-current-page-proposal");
    const before = currentUrl();

    await user.click(screen.getByTestId("review-queue-item-0-current-page-proposal"));

    expect(currentUrl()).toBe(before);
    expect(selectionStore.getState().level).toBe("region");
    expect(selectionStore.getState().path.proposalId).toBe("current-page-proposal");
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("highlights the row matching the current selection", async () => {
    mockReviewQueue([
      item({ page_index: 0, proposal_id: "selected-one" }),
      item({ page_index: 0, proposal_id: "unselected-one" }),
    ]);
    selectProposal("selected-one");

    renderPanel(0);

    const selectedRow = await screen.findByTestId("review-queue-item-0-selected-one");
    const unselectedRow = await screen.findByTestId("review-queue-item-0-unselected-one");
    expect(selectedRow).toHaveAttribute("data-selected", "true");
    expect(unselectedRow).not.toHaveAttribute("data-selected");
  });
});

describe("ReviewQueuePanel — stable during a decision", () => {
  it("keeps showing the same rows while a refetch (e.g. after a decision) is in flight", async () => {
    mockReviewQueue([
      item({ page_index: 0, proposal_id: "row-a" }),
      item({ page_index: 1, proposal_id: "row-b" }),
    ]);
    const { qc } = renderPanel(0);

    await screen.findByTestId("review-queue-item-0-row-a");
    await screen.findByTestId("review-queue-item-1-row-b");

    // Simulate the invalidation a decision triggers (useRegionMutations.ts)
    // landing on a slow refetch — the rows must stay exactly as they were
    // (no reorder, no clear-to-loading/empty) for the whole pending window.
    let release: (() => void) | undefined;
    server.use(
      http.get(`/api/projects/${PROJECT_ID}/regions/review-queue`, async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({
          total_undecided: 2,
          pages: [],
          items: [
            item({ page_index: 0, proposal_id: "row-a" }),
            item({ page_index: 1, proposal_id: "row-b" }),
          ],
        });
      }),
    );
    void qc.invalidateQueries({ queryKey: ["review-queue", PROJECT_ID] });

    await waitFor(() => expect(release).toBeDefined());

    // Still mid-flight: both original rows remain, in their original order,
    // and neither the loading nor the empty placeholder has appeared.
    const rows = screen.getAllByTestId(/^review-queue-item-/);
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
      "review-queue-item-0-row-a",
      "review-queue-item-1-row-b",
    ]);
    expect(screen.queryByTestId("review-queue-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-queue-empty")).not.toBeInTheDocument();

    release?.();
    await waitFor(() => expect(qc.isFetching({ queryKey: ["review-queue", PROJECT_ID] })).toBe(0));
  });
});
