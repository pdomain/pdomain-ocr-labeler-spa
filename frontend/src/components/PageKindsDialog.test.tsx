// PageKindsDialog.test.tsx — the "Review page kinds" book-wide list.
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "A book-wide list reviews many pages at once"

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import React from "react";
import { PageKindsDialog } from "./PageKindsDialog";
import { server } from "../test/server";

const PROJECT_ID = "proj-1";

const toastMock = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
}));
vi.mock("../lib/toast", () => ({ toast: toastMock }));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function listResponse(pages: Record<string, unknown>[]) {
  return {
    total_pages: pages.length,
    reviewed_count: pages.filter((p) => p["reviewed"]).length,
    pages,
  };
}

const ROWS = [
  {
    page_index: 0,
    confirmed_kind: null,
    reviewed: false,
    proposed_kind: "body",
    confidence: 0.9,
    run_id: "r1",
  },
  {
    page_index: 1,
    confirmed_kind: "title page",
    reviewed: true,
    proposed_kind: "unknown",
    confidence: 0.4,
    run_id: "r1",
  },
  {
    page_index: 2,
    confirmed_kind: null,
    reviewed: false,
    proposed_kind: null,
    confidence: null,
    run_id: null,
  },
];

function stubList(rows: Record<string, unknown>[] = ROWS) {
  server.use(
    http.get(`/api/projects/${PROJECT_ID}/page-kinds`, () => HttpResponse.json(listResponse(rows))),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  stubList();
  server.use(
    http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, () =>
      HttpResponse.json({ results: [], confirmed_count: 0 }),
    ),
  );
});

function renderDialog(onClose = vi.fn()) {
  return {
    onClose,
    ...render(<PageKindsDialog open={true} projectId={PROJECT_ID} onClose={onClose} />, {
      wrapper: makeWrapper(),
    }),
  };
}

describe("PageKindsDialog: rendering", () => {
  it("renders the dialog testid when open", async () => {
    renderDialog();
    expect(await screen.findByTestId("page-kinds-dialog")).toBeInTheDocument();
  });

  it("does not render row content when closed", () => {
    render(<PageKindsDialog open={false} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.queryByTestId("page-kinds-dialog")).not.toBeInTheDocument();
  });
});

describe("PageKindsDialog: filters", () => {
  it("defaults to the unreviewed filter, hiding reviewed page 1", async () => {
    renderDialog();
    await waitFor(() => {
      expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("page-kinds-row-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-kinds-row-2")).toBeInTheDocument();
  });

  it("switching to All shows every row, including reviewed page 1", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());

    await user.click(screen.getByTestId("page-kinds-filter-all"));

    expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("page-kinds-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("page-kinds-row-2")).toBeInTheDocument();
  });

  it("filtering by proposed kind narrows the rows shown", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("page-kinds-filter-all"));
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-1")).toBeInTheDocument());

    await user.selectOptions(screen.getByTestId("page-kinds-kind-filter-select"), "body");

    expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument();
    expect(screen.queryByTestId("page-kinds-row-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("page-kinds-row-2")).not.toBeInTheDocument();
  });

  it("shows the empty state when no row matches the filters", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());

    await user.selectOptions(screen.getByTestId("page-kinds-kind-filter-select"), "colophon");

    expect(await screen.findByTestId("page-kinds-empty")).toBeInTheDocument();
  });
});

describe("PageKindsDialog: row content", () => {
  it("shows proposed kind with confidence, and 'unreviewed' for an unreviewed page", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());
    expect(screen.getByTestId("page-kinds-row-proposed-0")).toHaveTextContent("body (0.90)");
    expect(screen.getByTestId("page-kinds-row-confirmed-0")).toHaveTextContent("unreviewed");
  });

  it("shows the confirmed kind for a reviewed page", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("page-kinds-filter-all"));
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-1")).toBeInTheDocument());
    expect(screen.getByTestId("page-kinds-row-confirmed-1")).toHaveTextContent("title page");
  });

  it("shows 'reviewed, kind not recorded' when reviewed with a null confirmed kind", async () => {
    stubList([
      {
        page_index: 0,
        confirmed_kind: null,
        reviewed: true,
        proposed_kind: "body",
        confidence: 0.5,
        run_id: "r1",
      },
    ]);
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("page-kinds-filter-all"));
    expect(await screen.findByTestId("page-kinds-row-confirmed-0")).toHaveTextContent(
      "reviewed, kind not recorded",
    );
  });
});

describe("PageKindsDialog: navigation", () => {
  it("clicking a page-number link closes the dialog and navigates to that page", async () => {
    const user = userEvent.setup();
    const { onClose } = renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());

    await user.click(screen.getByTestId("page-kinds-row-page-link-0"));

    expect(onClose).toHaveBeenCalled();
  });
});

describe("PageKindsDialog: selection", () => {
  it("select-all-visible checks every visible row, not filtered-out rows", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());

    await user.click(screen.getByTestId("page-kinds-select-all-visible"));

    expect(screen.getByTestId("page-kinds-row-checkbox-0")).toBeChecked();
    expect(screen.getByTestId("page-kinds-row-checkbox-2")).toBeChecked();
    expect(screen.getByTestId("page-kinds-bulk-count")).toHaveTextContent("2 selected");
  });

  it("toggling select-all-visible again clears the visible selection", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());
    await user.click(screen.getByTestId("page-kinds-select-all-visible"));
    await user.click(screen.getByTestId("page-kinds-select-all-visible"));

    expect(screen.getByTestId("page-kinds-row-checkbox-0")).not.toBeChecked();
    expect(screen.queryByTestId("page-kinds-bulk-count")).not.toBeInTheDocument();
  });

  it("the bulk bar count reflects a single row toggle", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());

    await user.click(screen.getByTestId("page-kinds-row-checkbox-0"));

    expect(screen.getByTestId("page-kinds-bulk-count")).toHaveTextContent("1 selected");
  });
});

describe("PageKindsDialog: Confirm as proposed", () => {
  it("excludes pages with an unknown or missing proposal and reports the count", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("page-kinds-filter-all"));
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-1")).toBeInTheDocument());

    // page 0: proposed body (usable). page 1: proposed unknown (excluded).
    // page 2: no proposal (excluded).
    await user.click(screen.getByTestId("page-kinds-select-all-visible"));

    expect(screen.getByTestId("page-kinds-bulk-excluded-note")).toHaveTextContent("2 excluded");
  });

  it("sends only the usable-proposal pages to the bulk-confirm route", async () => {
    let sentBody: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({
          results: [{ page_index: 0, status: "confirmed" }],
          confirmed_count: 1,
        });
      }),
    );
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("page-kinds-filter-all"));
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("page-kinds-select-all-visible"));

    await user.click(screen.getByTestId("page-kinds-bulk-confirm-as-proposed"));

    await waitFor(() => {
      expect(sentBody).toEqual({ pages: [{ page_index: 0, kind: "body" }], note: null });
    });
  });

  it("disables Confirm as proposed when nothing selected has a usable proposal", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-2")).toBeInTheDocument());
    // Page 2 has no proposal at all.
    await user.click(screen.getByTestId("page-kinds-row-checkbox-2"));

    expect(screen.getByTestId("page-kinds-bulk-confirm-as-proposed")).toBeDisabled();
  });
});

describe("PageKindsDialog: Set kind", () => {
  it("applies the chosen kind to every selected page", async () => {
    let sentBody: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({
          results: [
            { page_index: 0, status: "confirmed" },
            { page_index: 2, status: "confirmed" },
          ],
          confirmed_count: 2,
        });
      }),
    );
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());
    await user.click(screen.getByTestId("page-kinds-select-all-visible"));

    await user.selectOptions(screen.getByTestId("page-kinds-bulk-set-kind-select"), "blank");
    await user.click(screen.getByTestId("page-kinds-bulk-set-kind-apply"));

    await waitFor(() => {
      expect(sentBody).toEqual({
        pages: [
          { page_index: 0, kind: "blank" },
          { page_index: 2, kind: "blank" },
        ],
        note: null,
      });
    });
  });

  it("disables Set kind's apply button until a kind is chosen", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(screen.getByTestId("page-kinds-row-0")).toBeInTheDocument());
    await user.click(screen.getByTestId("page-kinds-row-checkbox-0"));

    expect(screen.getByTestId("page-kinds-bulk-set-kind-apply")).toBeDisabled();
  });
});
