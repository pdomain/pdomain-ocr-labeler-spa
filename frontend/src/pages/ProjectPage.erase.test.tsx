// ProjectPage.erase.test.tsx — P1-CANVAS-ERASE
// Verifies that onErasePixels is wired in ProjectPage's PageImageCanvas mount.
// Spec: docs/issues/2026-07-21-canvas-erase-mode-noop.md
//
// Strategy: mirror ProjectPage.rebox.test.tsx — mock the local
// PageImageCanvas component to capture the onErasePixels prop, then call it
// directly (simulating a completed drag in "erase" mode) and assert a POST
// to .../pages/0/erase-pixels fires with the source-pixel bbox, a
// success toast, page-query invalidation, and that a second drag while the
// first is in flight does not fire a duplicate request. A failing request
// shows an error toast and leaves the page query un-invalidated.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { viewportStore } from "../stores/viewport-store";
import { toast } from "../lib/toast";
import { ERASE_PAGE_PIXELS_TIMEOUT_MS } from "../hooks/usePageMutations";

// ─── Capture onErasePixels ──────────────────────────────────────────────────
// Mock the LOCAL PageImageCanvas component (not the pdomain-ui one) so we can
// capture the onErasePixels prop passed by ProjectPage.
let capturedOnErasePixels:
  ((rect: { x: number; y: number; width: number; height: number }) => void) | null = null;
let capturedEncodedScale: number | null = null;

// Unlike ProjectPage.rebox.test.tsx, this file does NOT mock react-router-dom's
// useNavigate — the page-navigation guard test below needs real navigation to
// exercise the idx0 change (see ProjectPage.pageChange.test.tsx, same reason).

// Mock the local PageImageCanvas component to capture onErasePixels.
vi.mock("../components/PageImageCanvas", () => ({
  __esModule: true,
  default: ({
    page,
    encoded,
    children,
    onErasePixels,
  }: {
    imageUrl?: string;
    encoded?: { scale?: number } | null;
    page?: { width: number; height: number };
    projectId?: string;
    pageIndex?: number;
    onBoxSelect?: unknown;
    onAddWord?: unknown;
    onRebox?: unknown;
    onErasePixels?: (rect: { x: number; y: number; width: number; height: number }) => void;
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => {
    capturedOnErasePixels = onErasePixels ?? null;
    capturedEncodedScale = encoded?.scale ?? null;
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

// GET /api/projects/{id} returns the flat Project model (useProject.ts) —
// NOT a {project, current_page_index, generation} wrapper. ProjectNavigation
// Controls reads `data.image_paths.length` directly for nav bounds, so the
// nav-next-button test below needs the real shape (>=2 image_paths) to be
// enabled.
function projectFixture() {
  return {
    project_id: "p1",
    project_root: "/data/p1",
    image_paths: ["page_001.png", "page_002.png"],
    ground_truth_map: {},
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

describe("ProjectPage — onErasePixels wired to PageImageCanvas (P1-CANVAS-ERASE)", () => {
  beforeEach(() => {
    capturedOnErasePixels = null;
    capturedEncodedScale = null;
    dialogStore.reset();
    viewportStore.setState({ mode: "select", pendingReboxTarget: null });
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixtureWithWords())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("passes onErasePixels to PageImageCanvas", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    expect(typeof capturedOnErasePixels).toBe("function");
  });

  it("POSTs to .../pages/0/erase-pixels with the source-pixel bbox, rect shape, and fill 255; shows a success toast", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/erase-pixels", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );
    const successSpy = vi.spyOn(toast, "success");

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(capturedEncodedScale).toBe(0.5);
    });

    act(() => {
      viewportStore.setState({ mode: "erase" });
    });

    // display rect: x=20, y=10, width=40, height=15 → src: x=40, y=20, width=80, height=30
    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    await waitFor(() => {
      expect(capturedBody).toEqual({
        bbox: { x: 40, y: 20, width: 80, height: 30 },
        fill_value: 255,
        shape: "rect",
      });
    });
    await waitFor(() => {
      expect(successSpy).toHaveBeenCalled();
    });
  });

  it("a failing erase request shows an error toast and does not invalidate the page query", async () => {
    let pageGetCount = 0;
    server.use(
      http.get("/api/projects/:pid/pages/:idx", () => {
        pageGetCount += 1;
        return HttpResponse.json(pageFixtureWithWords());
      }),
      http.post("/api/projects/:pid/pages/:idx/erase-pixels", () =>
        HttpResponse.json({ message: "erase failed" }, { status: 500 }),
      ),
    );
    const errorSpy = vi.spyOn(toast, "error");

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(capturedEncodedScale).toBe(0.5);
    });
    const countAfterLoad = pageGetCount;

    act(() => {
      viewportStore.setState({ mode: "erase" });
    });
    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalled();
    });
    // No invalidation → no extra GET beyond the initial load.
    expect(pageGetCount).toBe(countAfterLoad);
  });

  it("does not start a second erase request while one is still in flight", async () => {
    let postCount = 0;
    let resolveFirst: (() => void) | undefined;
    const firstRequestStarted = new Promise<void>((resolve) => {
      resolveFirst = resolve;
    });
    server.use(
      http.post("/api/projects/:pid/pages/:idx/erase-pixels", async () => {
        postCount += 1;
        resolveFirst?.();
        // Hold the response open so a second drag lands while this is pending.
        await new Promise((r) => setTimeout(r, 50));
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(capturedEncodedScale).toBe(0.5);
    });

    act(() => {
      viewportStore.setState({ mode: "erase" });
    });

    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });
    await firstRequestStarted;

    // Second drag fires while the first request is still in flight.
    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    await new Promise((r) => setTimeout(r, 80));
    expect(postCount).toBe(1);
  });

  // Reviewer finding 1 (medium): the in-flight guard was one plain boolean
  // that never remounts across page navigation — an erase started on page 0
  // that has not settled silently blocked a legitimate erase on page 1.
  it("does not block a legitimate erase drag on a different page while the previous page's erase is still in flight", async () => {
    let page0Started = false;
    let resolvePage0Started: (() => void) | undefined;
    const page0Started$ = new Promise<void>((resolve) => {
      resolvePage0Started = resolve;
    });
    let page1Body: unknown;
    let page1GetCount = 0;
    server.use(
      // Page 1's own GET must resolve (settling `pagePayload`/`encoded_dims`
      // for the NEW page) before the second drag fires below — otherwise the
      // handler would still read the stale (or default) scale.
      http.get("/api/projects/:pid/pages/1", () => {
        page1GetCount += 1;
        return HttpResponse.json(pageFixtureWithWords());
      }),
      http.post("/api/projects/:pid/pages/0/erase-pixels", async () => {
        page0Started = true;
        resolvePage0Started?.();
        // Held open well past this test's own assertions — simulates a
        // request still in flight when the user navigates to another page.
        await new Promise((r) => setTimeout(r, 5_000));
        return HttpResponse.json(pageFixtureWithWords());
      }),
      http.post("/api/projects/:pid/pages/1/erase-pixels", async ({ request }) => {
        page1Body = await request.json();
        return HttpResponse.json(pageFixtureWithWords());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(capturedEncodedScale).toBe(0.5);
    });

    // Start an erase on page 0 (index 0) and let it start, but not settle.
    act(() => {
      viewportStore.setState({ mode: "erase" });
    });
    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });
    await page0Started$;
    expect(page0Started).toBe(true);

    // Navigate to page 2 (index 1) while page 0's erase is still pending.
    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    // Wait for page 1's own payload to have loaded (its GET settled) before
    // dragging — otherwise the handler could read page 0's stale scale.
    await waitFor(() => expect(page1GetCount).toBeGreaterThan(0));

    // A drag on the NEW page must still post — it is a different target
    // from the still-in-flight page-0 erase, so the guard must not block it.
    act(() => {
      viewportStore.setState({ mode: "erase" });
    });
    act(() => {
      capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
    });

    await waitFor(() => {
      expect(page1Body).toEqual({
        bbox: { x: 40, y: 20, width: 80, height: 30 },
        fill_value: 255,
        shape: "rect",
      });
    });
  });

  // Reviewer finding 2 (low): a request that never settled left the guard
  // stuck for the life of the mount with no toast and no way back.
  it("a hung erase request times out, shows an error toast, and releases the guard for a retry", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let postCount = 0;
      server.use(
        http.post("/api/projects/:pid/pages/:idx/erase-pixels", () => {
          postCount += 1;
          // The first attempt hangs forever (never settles); the retry
          // after the guard is released succeeds normally.
          if (postCount === 1) return new Promise(() => {});
          return HttpResponse.json(pageFixtureWithWords());
        }),
      );
      const errorSpy = vi.spyOn(toast, "error");

      renderProjectPage();
      await screen.findByTestId("project-page");
      await waitFor(() => {
        expect(capturedEncodedScale).toBe(0.5);
      });

      act(() => {
        viewportStore.setState({ mode: "erase" });
      });
      act(() => {
        capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
      });
      await waitFor(() => expect(postCount).toBe(1));

      await vi.advanceTimersByTimeAsync(ERASE_PAGE_PIXELS_TIMEOUT_MS);
      await waitFor(() => {
        expect(errorSpy).toHaveBeenCalled();
      });
      const lastMessage = String(errorSpy.mock.calls.at(-1)?.[0]);
      expect(lastMessage).toMatch(/timed out/i);

      // The guard must be released: a second drag on the SAME page now posts.
      act(() => {
        viewportStore.setState({ mode: "erase" });
      });
      act(() => {
        capturedOnErasePixels?.({ x: 20, y: 10, width: 40, height: 15 });
      });
      await waitFor(() => expect(postCount).toBe(2));
    } finally {
      vi.useRealTimers();
    }
  });
});
