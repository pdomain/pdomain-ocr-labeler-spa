// HistoryPanel.test.tsx — unit tests for the U-M7 read-only history panel.
// Spec: docs/specs/2026-06-12-event-store-undo.md "U-M7 — history panel +
// jump-to-version" — capability matrix U-14/U-15/U-16.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { HistoryPanel } from "./HistoryPanel";
import type { components } from "../../api/types";

type HistoryVersionInfo = components["schemas"]["HistoryVersionInfo"];

const PROJECT_ID = "proj-1";
const PAGE_IDX = 0;

function version(overrides: Partial<HistoryVersionInfo> = {}): HistoryVersionInfo {
  return {
    node_id: "root",
    label: "OCR",
    timestamp: null,
    is_current: false,
    ...overrides,
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderPanel(qc = makeQueryClient()) {
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <HistoryPanel projectId={PROJECT_ID} pageIndex={PAGE_IDX} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

function mockVersions(versions: HistoryVersionInfo[]) {
  server.use(
    http.get(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/history/versions`, () =>
      HttpResponse.json(versions),
    ),
  );
}

beforeEach(() => {
  server.resetHandlers();
});

/** Narrow `rows.find(...)`'s possibly-`undefined` result — never a `!` assertion. */
function getRowByNodeId(rows: readonly HTMLElement[], nodeId: string): HTMLElement {
  const row = rows.find((r) => r.getAttribute("data-node-id") === nodeId);
  if (row === undefined) {
    throw new Error(`no history-version-row with data-node-id="${nodeId}"`);
  }
  return row;
}

describe("HistoryPanel", () => {
  it("shows history-loading before the fetch resolves", () => {
    mockVersions([version()]);
    renderPanel();
    expect(screen.getByTestId("history-loading")).toBeInTheDocument();
  });

  it("shows history-empty once loaded with no versions", async () => {
    mockVersions([]);
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("history-empty")).toBeInTheDocument();
    });
  });

  it("renders one row per version, root first, plus its label and relative time (U-14)", async () => {
    mockVersions([
      version({ node_id: "root", label: "OCR", timestamp: null, is_current: false }),
      version({
        node_id: "edit-0",
        label: "Word validated",
        timestamp: new Date(Date.now() - 5 * 60_000).toISOString(),
        is_current: true,
      }),
    ]);
    renderPanel();

    const rows = await screen.findAllByTestId("history-version-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-node-id", "root");
    expect(rows[0]).toHaveTextContent("OCR");
    expect(rows[0]).toHaveTextContent("time unknown"); // honest gap — root has no timestamp
    expect(rows[1]).toHaveAttribute("data-node-id", "edit-0");
    expect(rows[1]).toHaveTextContent("Word validated");
    expect(rows[1]).toHaveTextContent("min ago");
  });

  it("highlights the current row and hides its jump button (U-14)", async () => {
    mockVersions([
      version({ node_id: "root", is_current: false }),
      version({ node_id: "edit-0", is_current: true }),
    ]);
    renderPanel();

    const rows = await screen.findAllByTestId("history-version-row");
    const currentRow = getRowByNodeId(rows, "edit-0");
    const olderRow = getRowByNodeId(rows, "root");
    expect(currentRow).toHaveAttribute("data-current", "true");
    expect(within(currentRow).queryByTestId("history-jump-button")).not.toBeInTheDocument();
    expect(olderRow).not.toHaveAttribute("data-current");
    expect(within(olderRow).getByTestId("history-jump-button")).toBeInTheDocument();
  });

  it("clicking Jump on an older row POSTs its node_id to .../jump (U-15)", async () => {
    mockVersions([
      version({ node_id: "root", is_current: false }),
      version({ node_id: "edit-0", is_current: true }),
    ]);
    let receivedBody: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/jump`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({ project_id: PROJECT_ID, page_index: PAGE_IDX });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    const rows = await screen.findAllByTestId("history-version-row");
    const rootRow = getRowByNodeId(rows, "root");
    await user.click(within(rootRow).getByTestId("history-jump-button"));

    await waitFor(() => {
      expect(receivedBody).toEqual({ node_id: "root" });
    });
  });

  it("shows history-error when a jump request 409s (U-16 — truncated/unknown target)", async () => {
    mockVersions([
      version({ node_id: "root", is_current: false }),
      version({ node_id: "edit-0", is_current: true }),
    ]);
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/jump`, () =>
        HttpResponse.json(
          { error: "jump_unavailable", message: "target not in active chain" },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    const rows = await screen.findAllByTestId("history-version-row");
    const rootRow = getRowByNodeId(rows, "root");
    await user.click(within(rootRow).getByTestId("history-jump-button"));

    await waitFor(() => {
      expect(screen.getByTestId("history-error")).toHaveTextContent("target not in active chain");
    });
  });
});
