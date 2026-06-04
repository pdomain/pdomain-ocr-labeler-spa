// ProjectPage.toolbar.test.tsx — Lane B / Task B1.
//
// Verifies that the toolbar action grid dispatches a real mutation (not just
// a page invalidation) when a non-stub, enabled cell is clicked.
//
// The grid lives in a hidden stub container in ProjectPage (driver-contract
// §2.9), so we click cells with `fireEvent.click` (userEvent checks
// visibility). Selection is driven through the real selection-store so the
// button-state machinery (`useToolbarButtonStates`) enables the target cell.
//
// react-konva / pdomain-ui canvas are mocked exactly as in ProjectPage.test.tsx
// so the PageImageCanvas tree renders as plain divs under jsdom.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../../test/server";
import { ROUTES } from "../../lib/routes";
import { dialogStore } from "../../stores/dialog-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { selectionStore, clearSelection, selectLine } from "../../stores/selection-store";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (
    bbox: { x: number; y: number; width: number; height: number } | null | undefined,
    encoded: { scale: number },
  ) =>
    bbox
      ? {
          x: bbox.x * encoded.scale,
          y: bbox.y * encoded.scale,
          width: bbox.width * encoded.scale,
          height: bbox.height * encoded.scale,
        }
      : null,
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
  RectOverlayLayer: ({ layer, items }: { layer: string; items: Array<{ id: string }> }) => (
    <div data-testid={`bbox-overlay-${layer}`} data-item-count={items.length} />
  ),
  PageImageCanvas: ({
    children,
  }: {
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => (
    <div data-testid="image-viewport" tabIndex={0}>
      {children?.selection?.({})}
      {children?.tool?.({})}
    </div>
  ),
}));
vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="konva-stage">{children}</div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div data-testid="konva-rect" />,
  Image: () => <div data-testid="konva-image" />,
}));
vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

import ProjectPage from "../ProjectPage";

function renderProjectPage(path = "/projects/p1/pages/pageno/1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
    project: {
      project_id: "p1",
      project_root: "/data/p1",
      image_paths: ["page_001.png"],
      ground_truth_map: {},
    },
    current_page_index: 0,
    generation: 1,
  };
}

// A page with one line (index 0) containing one unvalidated word so the
// line/validate cell is enabled by useToolbarButtonStates.
function pageFixture() {
  return {
    project_id: "p1",
    page_index: 0,
    page_record: {
      page_index: 0,
      page_number: 1,
      image_path: "/data/p1/page_001.png",
      page_source: "ocr",
      ocr_failed: false,
      rotation_degrees: 0,
      rotation_source: null,
    },
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        bbox: { x: 10, y: 10, width: 100, height: 20 },
        overall_match_status: "mismatch",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            bbox: { x: 10, y: 10, width: 100, height: 20 },
            ocr_text: "Hello",
            gt_text: "Hello",
            match_status: "exact",
            is_validated: false,
          },
        ],
      },
    ],
    selection: {
      selection_mode: "line",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    },
    encoded_dims: {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale: 0.5,
    },
    line_filter: "all",
    image_url: "/api/projects/p1/image/0",
    generation: 1,
    page_text_ocr: "Hello",
    page_text_gt: "Hello",
    extra: {},
  };
}

describe("ProjectPage — toolbar grid dispatch (Lane B / B1)", () => {
  beforeEach(() => {
    dialogStore.reset();
    mockNavigate.mockReset();
    clearSelection();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true, selectionMode: "line" });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("dispatches validate-batch when the line/validate grid cell is clicked", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");
    // Wait for the page query to settle so line_matches feed the grid.
    await screen.findByTestId("toolbar-line-validate");

    // Select line 0 through the real store so the cell becomes enabled.
    selectLine(0);
    await waitFor(() => {
      expect(selectionStore.getState().selectedLines).toEqual([0]);
    });

    fireEvent.click(screen.getByTestId("toolbar-line-validate"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    expect(calls[0].url).toContain("/words/validate-batch");
    expect(calls[0].body).toEqual(expect.objectContaining({ scope: "line", validated: true }));
  });
});
