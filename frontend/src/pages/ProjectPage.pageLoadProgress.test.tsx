// ProjectPage.pageLoadProgress.test.tsx — on-demand page-OCR job progress.
//
// Spec: docs/specs/2026-08-08-page-load-progress-design.md
// Issue: docs/issues/2026-08-08-page-load-progress-unbuilt.md
//
// `GET .../pages/{idx}` now returns immediately even on a store miss: the
// response carries `page_load_job_id` and the SPA subscribes to that job's
// SSE stream (`GET /api/jobs/{id}/events`) instead of the request blocking
// for the OCR pass. One test per acceptance criterion this slice covers:
//
//   1. the job's stage text shows within the first frame, and changes as
//      later frames arrive (design: "shows a named stage within one
//      second" / "stage text changes as the work moves between ... stages").
//   2. the rest of the shell (toolbar, worklist column) stays interactive —
//      the status sits inside `image-pane`, not a full-viewport overlay.
//   3. the "Loading project" overlay does not persist through the page-load
//      job wait (it is a different, already-finished stage).
//   4. a terminal job error renders in the page region, distinct from the
//      synchronous `page_load_error` banner.
//   5. a page served from the store (no `page_load_job_id`) shows no
//      progress UI and opens no EventSource.
//   6. the page re-fetches once the job completes, so the OCR'd words
//      appear.
//
// The EventSource stub mirrors useJobProgress.test.tsx's — a real
// `function` (not an arrow function) is required so `new EventSource(...)`
// in the hook under test can construct it (Vitest 5 / JS spec).

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";

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

// ─── EventSource stub — mirrors hooks/useJobProgress.test.tsx ──────────────

interface MockEventSource {
  url: string;
  listeners: Record<string, ((e: MessageEvent) => void)[]>;
  readyState: number;
  addEventListener(type: string, fn: (e: MessageEvent) => void): void;
  removeEventListener(type: string, fn: (e: MessageEvent) => void): void;
  close(): void;
  _emit(type: string, data: unknown): void;
}

function makeMockEventSource(url: string): MockEventSource {
  const es: MockEventSource = {
    url,
    listeners: {},
    readyState: 1,
    addEventListener(type, fn) {
      es.listeners[type] = es.listeners[type] ?? [];
      es.listeners[type].push(fn);
    },
    removeEventListener(type, fn) {
      es.listeners[type] = (es.listeners[type] ?? []).filter((h) => h !== fn);
    },
    close() {
      es.readyState = 2;
    },
    _emit(type, data) {
      const e = new MessageEvent(type, { data: JSON.stringify(data) });
      (es.listeners[type] ?? []).forEach((h) => h(e));
    },
  };
  return es;
}

let sources: MockEventSource[] = [];
let esConstructor: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sources = [];
  esConstructor = vi.fn(function (url: string) {
    const es = makeMockEventSource(url);
    sources.push(es);
    return es;
  });
  (esConstructor as unknown as { CLOSED: number }).CLOSED = 2;
  vi.stubGlobal("EventSource", esConstructor);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Build a `load_page` job wire frame — the public `Job` model + `event`. */
function loadPageFrame(overrides: {
  status: string;
  progress?: { current?: number; total?: number; message?: string };
  error_message?: string | null;
  event?: string;
}) {
  return {
    id: "job-load-1",
    type: "load_page",
    project_id: "p1",
    status: overrides.status,
    progress: { current: 0, total: 2, message: "", ...overrides.progress },
    error_message: overrides.error_message ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: overrides.event ?? overrides.status,
    result: null,
  };
}

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

/** A pending page — the GET returned immediately with a `load_page` job in
 * flight (store miss). No text yet; `page_load_job_id` set. */
function pendingPageFixture() {
  return {
    project_id: "p1",
    page_index: 0,
    page_record: null,
    line_matches: [],
    line_filter: "all",
    image_url: "/api/projects/p1/image/0",
    generation: 1,
    page_text_ocr: null,
    page_text_gt: null,
    page_load_error: null as { error: string; message: string } | null,
    page_load_job_id: "job-load-1" as string | null,
    image_drift: null,
    extra: {},
  };
}

/** The same page once the `load_page` job has completed — a store hit, no
 * job id, real OCR text. */
function loadedPageFixture() {
  return {
    ...pendingPageFixture(),
    page_record: {
      page_index: 0,
      page_number: 1,
      image_path: "/data/p1/page_001.png",
      page_source: "ocr",
      ocr_failed: false,
      rotation_degrees: 0,
      rotation_source: null,
    },
    page_text_ocr: "ocr text",
    page_text_gt: "gt text",
    page_load_job_id: null,
  };
}

/** A page served straight from the store — no job ever created. */
function warmPageFixture() {
  return { ...loadedPageFixture() };
}

beforeEach(() => {
  dialogStore.reset();
  useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
});

describe("ProjectPage — on-demand page-OCR job progress (2026-08-08)", () => {
  it("AC1: shows the job's stage text within the first SSE frame", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pendingPageFixture())),
    );
    renderProjectPage();
    await screen.findByTestId("project-page");

    await waitFor(() => expect(sources).toHaveLength(1));
    expect(sources[0]?.url).toBe("/api/jobs/job-load-1/events");

    act(() => {
      sources[0]?._emit(
        "snapshot",
        loadPageFrame({
          status: "running",
          progress: { current: 0, total: 2, message: "Stored page not found — running OCR." },
          event: "snapshot",
        }),
      );
    });

    const status = await screen.findByTestId("page-load-status");
    expect(status.textContent).toContain("Stored page not found — running OCR.");
  });

  it("AC1: updates the stage text as later frames arrive", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pendingPageFixture())),
    );
    renderProjectPage();
    await waitFor(() => expect(sources).toHaveLength(1));

    act(() => {
      sources[0]?._emit(
        "snapshot",
        loadPageFrame({
          status: "running",
          progress: { current: 0, total: 2, message: "Stored page not found — running OCR." },
          event: "snapshot",
        }),
      );
    });
    await screen.findByText("Stored page not found — running OCR.");

    act(() => {
      sources[0]?._emit(
        "progress",
        loadPageFrame({
          status: "running",
          progress: {
            current: 1,
            total: 2,
            message: "Preparing the OCR engine and running OCR — cpu.",
          },
        }),
      );
    });
    await screen.findByText("Preparing the OCR engine and running OCR — cpu.");
    expect(screen.queryByText("Stored page not found — running OCR.")).toBeNull();
  });

  it("AC1: re-fetches the page once the job completes, so the OCR'd words appear", async () => {
    let pageCalls = 0;
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => {
        pageCalls += 1;
        return HttpResponse.json(pageCalls === 1 ? pendingPageFixture() : loadedPageFixture());
      }),
    );
    renderProjectPage();
    await screen.findByTestId("page-load-status");
    expect(pageCalls).toBe(1);

    act(() => {
      sources[0]?._emit(
        "complete",
        loadPageFrame({
          status: "complete",
          progress: { current: 2, total: 2, message: "Page loaded." },
        }),
      );
    });

    await waitFor(() => expect(pageCalls).toBe(2));
    await waitFor(() => expect(screen.queryByTestId("page-load-status")).toBeNull());
  });

  it("AC2: the toolbar and worklist column stay interactive while the status is shown (region-scoped, not full-viewport)", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pendingPageFixture())),
    );
    renderProjectPage();
    const status = await screen.findByTestId("page-load-status");

    // No full-viewport overlay covers the shell for this wait.
    expect(screen.queryByTestId("project-loading-overlay")).toBeNull();
    expect(screen.queryByTestId("busy-overlay")).toBeNull();

    // The status is confined to image-pane...
    const imagePane = screen.getByTestId("image-pane");
    expect(imagePane.contains(status)).toBe(true);

    // ...and does not reach into the worklist / toolbar regions, which stay
    // present and un-obscured.
    const worklistColumn = screen.getByTestId("project-worklist-column");
    expect(worklistColumn.contains(status)).toBe(false);
    const toolbar = screen.getByTestId("workspace-toolbar");
    expect(toolbar.contains(status)).toBe(false);
    expect(screen.getByTestId("nav-next-button")).toBeInTheDocument();
  });

  it("AC3: the project-loading overlay does not persist through the page-load job wait", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pendingPageFixture())),
    );
    renderProjectPage();
    // The page-load job status is up (the page fetch itself already
    // resolved — the wait moved into the job) while the project-loading
    // overlay, which used to track the same `pageQ.isLoading` flag, must
    // not be showing "Loading project" for it.
    await screen.findByTestId("page-load-status");
    expect(screen.queryByTestId("project-loading-overlay")).toBeNull();
  });

  it("AC4: a terminal job error renders in the page region, distinct from the synchronous banner", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pendingPageFixture())),
    );
    renderProjectPage();
    await waitFor(() => expect(sources).toHaveLength(1));

    act(() => {
      sources[0]?._emit(
        "error",
        loadPageFrame({
          status: "error",
          progress: {
            current: 1,
            total: 2,
            message: "Preparing the OCR engine and running OCR — cpu.",
          },
          error_message: "OCR engine crashed",
        }),
      );
    });

    const error = await screen.findByTestId("page-load-error");
    expect(error.textContent).toContain("OCR engine crashed");
    // The synchronous `page_load_error` banner is a different signal (the
    // fixture's `page_load_error` is null) — it must stay off.
    expect(screen.queryByTestId("banner-ocr-failed")).toBeNull();
    expect(screen.queryByTestId("page-load-status")).toBeNull();
  });

  it("AC5: a page served from the store shows no progress UI and opens no EventSource", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(warmPageFixture())),
    );
    renderProjectPage();
    await screen.findByTestId("project-page");
    // Give any errant async job-tracking effect a tick to fire before
    // asserting the negative.
    await waitFor(() => expect(screen.getByTestId("project-page")).toBeInTheDocument());

    expect(screen.queryByTestId("page-load-status")).toBeNull();
    expect(screen.queryByTestId("page-load-error")).toBeNull();
    expect(esConstructor).not.toHaveBeenCalled();
  });

  it("2026-09-17 review: gates the Save-page hotkey while the load job is in flight", async () => {
    // While `page-load-status` is showing, `pagePayload` has no
    // `page_record` / `line_matches` yet — Mod+S must be a no-op, the same
    // as it is during any other in-flight mutation (isAnyMutationPending).
    // Un-gates once the job completes and the page has real content.
    let saveCalls = 0;
    let pageCalls = 0;
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => {
        pageCalls += 1;
        return HttpResponse.json(pageCalls === 1 ? pendingPageFixture() : loadedPageFixture());
      }),
      http.post("/api/projects/:pid/pages/:idx/save", () => {
        saveCalls += 1;
        return HttpResponse.json({ saved: true, page_source: "labeled" });
      }),
    );
    renderProjectPage();
    await screen.findByTestId("page-load-status");

    fireEvent.keyDown(document, { key: "s", code: "KeyS", ctrlKey: true });
    // Give a wrongly-fired mutation a real chance to land before asserting
    // the negative — `waitFor` alone can't prove an absence.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(saveCalls).toBe(0);

    // Complete the job — the page refetches and the gate lifts.
    act(() => {
      sources[0]?._emit(
        "complete",
        loadPageFrame({
          status: "complete",
          progress: { current: 2, total: 2, message: "Page loaded." },
        }),
      );
    });
    await waitFor(() => expect(screen.queryByTestId("page-load-status")).toBeNull());

    fireEvent.keyDown(document, { key: "s", code: "KeyS", ctrlKey: true });
    await waitFor(() => expect(saveCalls).toBe(1));
  });
});
