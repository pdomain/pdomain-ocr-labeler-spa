// ProjectPage.wordEditDialog.test.tsx — Task S1.2
// Verifies that WordEditDialog mutation callbacks are wired in ProjectPage.
// Spec: docs/specs/2026-06-06-word-edit-dialog-wiring.md capability matrix
//
// Acceptance: each wired callback fires the correct POST endpoint (MSW spy).
// Tests open the dialog via dialogStore.openWordEdit, click the action button,
// and assert that the correct HTTP request was made.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { toast } from "../lib/toast";

// ─── Mocks (must mirror ProjectPage.test.tsx) ────────────────────────────────

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

import ProjectPage from "./ProjectPage";

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
          {
            word_index: 1,
            ocr_text: "world",
            ground_truth_text: null,
            status: "ok",
            bbox: { x: 100, y: 10, width: 80, height: 30 },
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

describe("ProjectPage — WordEditDialog mutation wiring (S1.2)", () => {
  beforeEach(() => {
    dialogStore.reset();
    mockNavigate.mockReset();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixtureWithWords())),
      // current-page-index fires on mount (debounced cursor persistence)
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("fires POST to .../words/0/0/merge with direction:right when merge-next clicked", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/merge", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    // Wait for page data to load
    await screen.findByTestId("project-page");

    // Open the word-edit dialog for line 0, word 0
    act(() => {
      dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    });

    // Dialog should now be open
    await screen.findByTestId("word-edit-dialog");

    // Click merge-next
    fireEvent.click(screen.getByTestId("dialog-merge-next-button"));

    await waitFor(() => {
      expect(capturedBody).toEqual({ direction: "right" });
    });
  });

  it("fires POST to .../pages/0/delete with word scope when delete clicked", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/delete", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    act(() => {
      dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    });

    await screen.findByTestId("word-edit-dialog");

    fireEvent.click(screen.getByTestId("dialog-delete-word-button"));

    await waitFor(() => {
      expect(capturedBody).toEqual({
        scope: "word",
        word_indices: [[0, 0]],
        line_indices: [],
        paragraph_indices: [],
      });
    });
  });

  it("fires POST to .../words/0/0/gt when GT input is committed", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/gt", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    act(() => {
      dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    });

    await screen.findByTestId("word-edit-dialog");

    const gtInput = screen.getByTestId("dialog-gt-input");
    fireEvent.change(gtInput, { target: { value: "helo" } });
    fireEvent.keyDown(gtInput, { key: "Enter" });

    await waitFor(() => {
      expect(capturedBody).toEqual({ text: "helo" });
    });
  });

  it("fires POST to .../words/0/0/style when apply-style clicked", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/style", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    act(() => {
      dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    });

    await screen.findByTestId("word-edit-dialog");

    // Select a style option and click apply
    const styleSelect = screen.getByTestId("dialog-style-select");
    fireEvent.change(styleSelect, { target: { value: "bold" } });
    fireEvent.click(screen.getByTestId("dialog-apply-style-button"));

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ style: "bold" });
    });
  });

  it("surfaces a toast when Refine fails (e.g. page image absent)", async () => {
    // Spec WED-7: refine raises on the backend when the page image is not
    // loaded — it must be surfaced, not swallowed silently.
    const warnSpy = vi.spyOn(toast, "warn").mockImplementation(() => "");
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/nudge", () =>
        HttpResponse.json({ detail: "page image not loaded" }, { status: 400 }),
      ),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");

    act(() => {
      dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    });
    await screen.findByTestId("word-edit-dialog");

    fireEvent.click(screen.getByTestId("dialog-refine-button"));

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalled();
    });
    warnSpy.mockRestore();
  });
});
