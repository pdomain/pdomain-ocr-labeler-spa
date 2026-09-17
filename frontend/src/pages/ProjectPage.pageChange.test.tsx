// ProjectPage.pageChange.test.tsx — whole-branch review defect 2: a region
// selection outlives the page it belongs to.
//
// Selecting a proposal or a confirmed region, then navigating to another
// page, must clear that region-level selection — otherwise a hotkey fires
// against the new page's URL carrying the old page's id. Word, line,
// paragraph and block selections are explicitly NOT touched by this fix
// (predates it; see the region review guards report), so one of them is
// pinned here to prove this change did not widen.
//
// Unlike ProjectPage.test.tsx, this file does NOT mock react-router-dom's
// useNavigate — real navigation is what exercises the pageIndex change this
// fix reacts to. `nav-next-button` (ProjectNavigationControls) drives it.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import {
  clearSelection,
  selectionStore,
  selectLine,
  selectProposal,
  selectRegion,
} from "../stores/selection-store";
import type { components } from "../api/types";

type RegionView = components["schemas"]["RegionView"];

// ─── Mocks (mirrors ProjectPage.test.tsx's canvas stack — same reasons) ────
vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (
    bbox: { x: number; y: number; width: number; height: number },
    encoded: { scale: number },
  ) => ({
    x: bbox.x * encoded.scale,
    y: bbox.y * encoded.scale,
    width: bbox.width * encoded.scale,
    height: bbox.height * encoded.scale,
  }),
  rectItemsToDisplay: <T extends { bbox: { x: number; y: number; width: number; height: number } }>(
    items: T[],
    encoded: { scale: number } | null,
  ) =>
    encoded
      ? items.map((item) => ({
          ...item,
          bbox: {
            x: item.bbox.x * encoded.scale,
            y: item.bbox.y * encoded.scale,
            width: item.bbox.width * encoded.scale,
            height: item.bbox.height * encoded.scale,
          },
        }))
      : items,
  RectOverlayLayer: ({
    layer,
    items,
    dimmed,
  }: {
    layer: string;
    items: Array<{ id: string }>;
    dimmed?: boolean;
  }) => (
    <div
      data-testid={`bbox-overlay-${layer}`}
      data-item-count={items.length}
      data-dimmed={dimmed ? "true" : undefined}
    />
  ),
  PageImageCanvas: ({
    page,
    children,
  }: {
    src?: string;
    page?: { width: number; height: number };
    words?: unknown[];
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => (
    <div
      data-testid="image-viewport"
      data-width={page?.width}
      data-height={page?.height}
      tabIndex={0}
    >
      {children?.selection?.({})}
      {children?.tool?.({})}
    </div>
  ),
}));
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": tid,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div data-testid={tid ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div data-testid="konva-rect" />,
  Image: () => <div data-testid="konva-image" />,
}));
vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

// Import AFTER mocks so the page pulls them.
import ProjectPage from "./ProjectPage";

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderProjectPage(path = "/projects/p1/pages/pageno/1") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={ROUTES.PROJECT_PAGE_NO} element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function projectFixture() {
  return {
    project_id: "p1",
    project_root: "/data/p1",
    image_paths: ["page_001.png", "page_002.png"],
    ground_truth_map: {},
  };
}

function proposalRegion(proposal_id: string): RegionView {
  return {
    region_id: null,
    proposal_id,
    role: "paragraph",
    box: { x: 0, y: 0, width: 10, height: 10 },
    confirmed: false,
    confidence: 0.9,
    stale: false,
  };
}

function pageFixture(idx: number) {
  return {
    project_id: "p1",
    page_index: idx,
    line_matches: [
      {
        line_index: 3,
        paragraph_index: 0,
        overall_match_status: "exact",
        is_fully_validated: true,
        validated_word_count: 0,
        total_word_count: 0,
        word_matches: [],
      },
    ],
    line_filter: "all",
    image_url: `/api/projects/p1/image/${String(idx)}`,
    generation: 1,
    regions: [proposalRegion("prop-1")],
  };
}

describe("ProjectPage — region selection is scoped to its page (defect 2)", () => {
  beforeEach(() => {
    dialogStore.reset();
    clearSelection();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", ({ params }) => {
        const idx = Number(params["idx"]);
        return HttpResponse.json(pageFixture(idx));
      }),
    );
  });

  it("clears a selected proposal when the page index changes", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectProposal("prop-1");
    expect(selectionStore.getState().level).toBe("region");

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    expect(selectionStore.getState().level).toBe("none");
    expect(selectionStore.getState().path).toEqual({});
  });

  it("clears a selected confirmed region when the page index changes", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectRegion("region-1");
    expect(selectionStore.getState().level).toBe("region");

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    expect(selectionStore.getState().level).toBe("none");
  });

  it("does NOT clear a line selection when the page index changes (pin: this fix stays region-only)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectLine(3);
    expect(selectionStore.getState().level).toBe("line");
    expect(selectionStore.getState().path).toEqual({ lineId: 3 });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    expect(selectionStore.getState().level).toBe("line");
    expect(selectionStore.getState().path).toEqual({ lineId: 3 });
  });
});
