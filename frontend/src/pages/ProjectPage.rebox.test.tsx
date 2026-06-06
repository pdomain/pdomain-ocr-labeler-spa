// ProjectPage.rebox.test.tsx — Task S3.1
// Verifies that onRebox is wired in ProjectPage's PageImageCanvas mount.
// Spec: docs/plans/2026-06-06-parity-gap-completion.md §S3
//
// Strategy: override the @pdomain/pdomain-ui/canvas mock to capture the
// onRebox prop. The test then calls capturedOnRebox directly (simulating a
// completed drag in "rebox" mode) and asserts that a POST to
// .../words/0/0/rebox fires with the correct source-pixel bbox.

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
import { viewportStore } from "../stores/viewport-store";

// ─── Capture onRebox ─────────────────────────────────────────────────────────
// Mock the LOCAL PageImageCanvas component (not the pdomain-ui one) so we can
// capture the onRebox prop passed by ProjectPage. The component is imported
// from ../components/PageImageCanvas in ProjectPage.tsx.
let capturedOnRebox:
  | ((rect: { x: number; y: number; width: number; height: number }) => void)
  | null = null;

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock the local PageImageCanvas component to capture onRebox.
vi.mock("../components/PageImageCanvas", () => ({
  __esModule: true,
  default: ({
    page,
    children,
    onRebox,
  }: {
    imageUrl?: string;
    encoded?: unknown;
    page?: { width: number; height: number };
    projectId?: string;
    pageIndex?: number;
    onBoxSelect?: unknown;
    onAddWord?: unknown;
    onRebox?: (rect: { x: number; y: number; width: number; height: number }) => void;
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => {
    capturedOnRebox = onRebox ?? null;
    return (
      <div
        data-testid="image-viewport"
        data-width={page?.width}
        data-height={page?.height}
        tabIndex={0}
      >
        {children?.selection?.({})}
        {children?.tool?.({})}
      </div>
    );
  },
}));

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
  // PageImageCanvas from pdomain-ui is not used directly by ProjectPage
  // (it uses the local component wrapper), but mock it to be safe.
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
      image_paths: ["page_001.png", "page_002.png"],
      ground_truth_map: {},
    },
    current_page_index: 0,
    generation: 1,
  };
}

function pageFixtureWithWords() {
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
        line_text: "hello world",
        ocr_text: "hello world",
        ground_truth_text: null,
        status: "ok",
        bbox: { x: 10, y: 10, width: 200, height: 30 },
        word_matches: [
          {
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: null,
            status: "ok",
            bbox: { x: 10, y: 10, width: 80, height: 30 },
            validated: false,
            char_bboxes: [],
            styles: [],
            components: [],
            char_ranges: [],
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
    page_text_ocr: "hello world",
    page_text_gt: "hello world",
    extra: {},
  };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ProjectPage — onRebox wired to PageImageCanvas (S3.1)", () => {
  beforeEach(() => {
    capturedOnRebox = null;
    dialogStore.reset();
    mockNavigate.mockReset();
    viewportStore.setState({ mode: "select", pendingReboxTarget: null });
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixtureWithWords())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("passes onRebox to PageImageCanvas", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    // After rendering with data, capturedOnRebox should be a function
    expect(typeof capturedOnRebox).toBe("function");
  });

  it("POSTs to .../words/0/0/rebox with source-pixel bbox when onRebox fires", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/rebox", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    // Set rebox mode with a target word
    act(() => {
      viewportStore.setState({
        mode: "rebox",
        pendingReboxTarget: { lineIndex: 0, wordIndex: 0 },
      });
    });

    // Simulate a completed draw drag: display coords (scale=0.5, so src = display/0.5)
    // display rect: x=20, y=10, width=40, height=15 → src: x=40, y=20, width=80, height=30
    act(() => {
      capturedOnRebox?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    await waitFor(() => {
      expect(capturedBody).toEqual({ bbox: { x: 40, y: 20, width: 80, height: 30 } });
    });
  });

  it("does nothing when onRebox fires but pendingReboxTarget is null", async () => {
    let reboxCalled = false;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/rebox", () => {
        reboxCalled = true;
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    // No rebox target set — just fire onRebox
    act(() => {
      capturedOnRebox?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    // Allow any async work to settle
    await new Promise((r) => setTimeout(r, 50));
    expect(reboxCalled).toBe(false);
  });
});
