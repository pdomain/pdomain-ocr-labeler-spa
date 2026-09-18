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
  opts?: { onRequest?: (url: URL) => void; totalUndecided?: number },
) {
  server.use(
    http.get(`/api/projects/${PROJECT_ID}/regions/review-queue`, ({ request }) => {
      opts?.onRequest?.(new URL(request.url));
      return HttpResponse.json({
        total_undecided: opts?.totalUndecided ?? items.length,
        pages: [],
        items,
      });
    }),
  );
}

beforeEach(() => {
  useUiPrefs.setState({ reviewQueueOrder: "reading", reviewQueueKind: null });
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

describe("ReviewQueuePanel — a book with more proposals than the list holds", () => {
  it("says how many of the book's undecided proposals it is showing", async () => {
    mockReviewQueue([item({ proposal_id: "p1" }), item({ proposal_id: "p2" })], {
      totalUndecided: 412,
    });
    renderPanel();

    const notice = await screen.findByTestId("review-queue-truncated");
    expect(notice).toHaveTextContent("Showing 2 of 412");
  });

  it("says nothing when the list holds every undecided proposal", async () => {
    mockReviewQueue([item({ proposal_id: "p1" })]);
    renderPanel();

    await screen.findByTestId("review-queue-item-0-p1");
    expect(screen.queryByTestId("review-queue-truncated")).toBeNull();
  });
});

// ─── Kind selector (one-answer-to-what-to-review-next) ─────────────────────
// Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
// review-next.md "How the SPA uses the new route" — "The Queue drawer tab
// grows a kind selector, defaulting to that same kind [the rail badge's]."

function kindEntry(overrides: Record<string, unknown> = {}) {
  return {
    kind: "page_kind",
    outstanding: 0,
    total: 0,
    available: true,
    blocked_by: null,
    first_page_index: null,
    pages_not_counted: 0,
    is_lower_bound: false,
    ...overrides,
  };
}

function mockKindsQueue(kinds: Record<string, unknown>[]) {
  server.use(
    http.get(`/api/projects/${PROJECT_ID}/review-queue`, () => HttpResponse.json({ kinds })),
  );
}

describe("ReviewQueuePanel — kind selector defaulting and switching", () => {
  it("defaults to the first kind with outstanding, unblocked work", async () => {
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 40, total: 80 }),
      kindEntry({ kind: "region", outstanding: 12, total: 29 }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    const pageKindButton = await screen.findByTestId("review-queue-kind-select-page_kind");
    expect(pageKindButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("review-queue-kind-select-region")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(await screen.findByTestId("review-queue-kind-count")).toHaveTextContent("40 of 80");
  });

  it("switching the selector shows the picked kind's own count and starting page", async () => {
    const user = userEvent.setup();
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 40, total: 80 }),
      kindEntry({ kind: "word", outstanding: 9, total: 100, first_page_index: 4 }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    await screen.findByTestId("review-queue-kind-select-page_kind");
    await user.click(screen.getByTestId("review-queue-kind-select-word"));

    expect(screen.getByTestId("review-queue-kind-select-word")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await screen.findByTestId("review-queue-kind-count")).toHaveTextContent("9 of 100");
    expect(screen.getByTestId("review-queue-kind-start")).toHaveTextContent("5");
    expect(useUiPrefs.getState().reviewQueueKind).toBe("word");
  });

  it("keeps showing the region item list unchanged when region is selected", async () => {
    mockKindsQueue([kindEntry({ kind: "region", outstanding: 1, total: 1 })]);
    mockReviewQueue([item({ proposal_id: "p1" })]);
    renderPanel();

    await screen.findByTestId("review-queue-list");
    expect(screen.queryByTestId("review-queue-kind-summary")).not.toBeInTheDocument();
  });

  it("shows what a blocked kind is waiting for, instead of looking finished", async () => {
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 0, total: 10 }),
      kindEntry({ kind: "region", outstanding: 5, total: 5, blocked_by: "page_kind" }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    const user = userEvent.setup();
    await screen.findByTestId("review-queue-kind-select-region");
    await user.click(screen.getByTestId("review-queue-kind-select-region"));

    const blocked = await screen.findByTestId("review-queue-kind-blocked");
    expect(blocked).toHaveTextContent(/page kind/i);
  });

  it("shows an unavailable kind's reason, not a zero", async () => {
    const user = userEvent.setup();
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 3, total: 10 }),
      kindEntry({
        kind: "glyph",
        outstanding: 0,
        total: 0,
        available: false,
        unavailable_reason: "no glyph predictor is wired",
      }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    await screen.findByTestId("review-queue-kind-select-glyph");
    await user.click(screen.getByTestId("review-queue-kind-select-glyph"));

    const reason = await screen.findByTestId("review-queue-kind-unavailable");
    expect(reason).toHaveTextContent("no glyph predictor is wired");
    expect(screen.queryByTestId("review-queue-kind-count")).not.toBeInTheDocument();
  });

  it("reads a lower-bound count as 'at least', never as a completion figure", async () => {
    const user = userEvent.setup();
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 3, total: 10 }),
      kindEntry({
        kind: "typography",
        outstanding: 18463,
        total: 18463,
        is_lower_bound: true,
      }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    await screen.findByTestId("review-queue-kind-select-typography");
    await user.click(screen.getByTestId("review-queue-kind-select-typography"));

    const count = await screen.findByTestId("review-queue-kind-count");
    expect(count).toHaveTextContent(/at least/i);
    expect(count).toHaveTextContent("18463");
  });

  it("says how many pages could not be counted for a word lower bound", async () => {
    const user = userEvent.setup();
    mockKindsQueue([
      kindEntry({ kind: "page_kind", outstanding: 3, total: 10 }),
      kindEntry({
        kind: "word",
        outstanding: 3,
        total: 5,
        pages_not_counted: 6,
        is_lower_bound: true,
      }),
    ]);
    mockReviewQueue([]);
    renderPanel();

    await screen.findByTestId("review-queue-kind-select-word");
    await user.click(screen.getByTestId("review-queue-kind-select-word"));

    const notCounted = await screen.findByTestId("review-queue-kind-pages-not-counted");
    expect(notCounted).toHaveTextContent("6");
  });
});

describe("ReviewQueuePanel — the selected row", () => {
  it("marks the selected row for assistive technology, not only for tests", async () => {
    const user = userEvent.setup();
    mockReviewQueue([item({ proposal_id: "p1" })]);
    renderPanel();

    const row = await screen.findByTestId("review-queue-item-0-p1");
    expect(row).not.toHaveAttribute("aria-current");

    await user.click(row);

    await waitFor(() => {
      expect(screen.getByTestId("review-queue-item-0-p1")).toHaveAttribute("aria-current", "true");
    });
  });
});
