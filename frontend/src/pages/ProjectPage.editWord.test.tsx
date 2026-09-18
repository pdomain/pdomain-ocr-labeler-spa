// ProjectPage.editWord.test.tsx — P2-WORD-EDIT
// Verifies that ProjectPage wires WordCell's pencil (onEditWord) to select
// the word and open the right panel, matching WordCell's own docstring:
// "Should select the word in the selection store and open the right panel."
// No dialog is rebuilt — §2.11 of the driver contract is retired.
//
// Strategy: mock the local WordMatchView component (matches the established
// pattern in ProjectPage.rebox.test.tsx, which mocks PageImageCanvas) so we
// can capture the onEditWord prop ProjectPage passes and call it directly.
// The real WordMatchView renders through @tanstack/react-virtual, which
// mounts no rows under jsdom (documented in WordMatchView.test.tsx) — so
// clicking a real pencil button end-to-end isn't reachable in this
// environment. Capturing the prop and invoking it is the faithful
// alternative: it exercises the exact handler ProjectPage constructs.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { clearSelection, selectionStore } from "../stores/selection-store";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// ─── Capture onEditWord ────────────────────────────────────────────────────
let capturedOnEditWord: ((lineIndex: number, wordIndex: number) => void) | null = null;

vi.mock("../components/WordMatchView", () => ({
  __esModule: true,
  WordMatchView: ({
    onEditWord,
  }: {
    lines?: unknown[];
    filter?: string;
    onEditWord?: (lineIndex: number, wordIndex: number) => void;
  }) => {
    capturedOnEditWord = onEditWord ?? null;
    return <div data-testid="word-match-view-stub" />;
  },
}));

// Mock canvas/konva pieces so the rest of the shell mounts cheaply — same
// stubs used across the other ProjectPage.*.test.tsx files.
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
    children,
  }: {
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => (
    <div data-testid="pdomain-image-canvas">
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

import ProjectPage from "./ProjectPage";

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            fuzz_score: null,
            normalized_match: false,
            is_validated: false,
            text_style_labels: [],
            word_components: [],
            bbox: { x: 0, y: 0, width: 10, height: 10 },
            word_id: "w-edit-0-0",
          },
        ],
      },
    ],
    selection: {
      selection_mode: "paragraph",
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
    page_text_ocr: "hello",
    page_text_gt: "hello",
    extra: {},
  };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ProjectPage — edit-word pencil selects the word and opens the right panel", () => {
  beforeEach(() => {
    capturedOnEditWord = null;
    dialogStore.reset();
    mockNavigate.mockReset();
    clearSelection();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("passes an onEditWord handler to WordMatchView (pencil is wired, not a no-op)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(typeof capturedOnEditWord).toBe("function");
    });
  });

  it("selects the word in selection-store when onEditWord fires", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(typeof capturedOnEditWord).toBe("function");
    });

    act(() => {
      capturedOnEditWord?.(0, 0);
    });

    await waitFor(() => {
      expect(selectionStore.getState().level).toBe("word");
    });
    expect(selectionStore.getState().selectedWords).toEqual([[0, 0]]);
    // P2-SELECTION-PAGE: the path carries the page it was selected on, so the
    // right panel resolves it against page 0 and not against whatever page is
    // loaded later.
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, lineId: 0, wordId: [0, 0] });
  });

  // The pencil lives inside WordMatchView, which the right panel only mounts
  // (as its level="none" textTabsSlot) while the panel itself is open — so
  // clicking it is only reachable with the panel already open. The handler
  // still sets rightPanelOpen defensively (see ProjectPage.handleEditWord),
  // which this test also covers.
  it("keeps the right panel open and routes it to the word level when onEditWord fires", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(typeof capturedOnEditWord).toBe("function");
    });
    expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "none");

    act(() => {
      capturedOnEditWord?.(0, 0);
    });

    await waitFor(() => {
      expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "word");
    });
    // With no dialog rebuilt, the panel itself must carry the word content —
    // not an empty placeholder.
    expect(screen.queryByTestId("right-panel-word-empty")).not.toBeInTheDocument();
  });
});
