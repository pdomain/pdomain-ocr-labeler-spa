// PageActionsCompact.test.tsx — unit tests for the compact header action bar.
// Covers: B-ACTIONS-002, B-ACTIONS-003, B-ACTIONS-008, F-PAGE-ACTIONS-01
// P1.b (Gap 4, 7): Reload OCR | Rematch GT | ✓ Save page | Export ▾
//
// Tests:
//   - Renders all 4 compact buttons with correct data-testid attributes.
//   - Buttons are disabled when projectId is absent (no route param).
//   - Export button opens the export dialog.
//   - Reload OCR, Rematch GT, Save Page trigger their mutations (smoke).
//   - Toast lifecycle: loading toast on job start, success toast on complete.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { PageActionsCompact } from "./PageActionsCompact";
import { dialogStore } from "../stores/dialog-store";

// ─── sonner mock ──────────────────────────────────────────────────────────────
// We mock "sonner" at the module level so both the direct import in toast.ts
// (via ../lib/toast) and the dynamic import("sonner") in PageActionsCompact
// resolve to the same mock object.
// Use vi.hoisted so toastMock is available inside the vi.mock factory (which
// is hoisted to the top of the file by Vitest).
//
// Sonner's `toast` is a function with .loading/.success/.error methods attached.
// We need to replicate that shape so toast.ts (which calls sonnerToast(msg, opts)
// as a plain function) does not throw "toast is not a function".

const toastMock = vi.hoisted(() => {
  const fn = Object.assign(vi.fn(), {
    loading: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  });
  return fn;
});
vi.mock("sonner", () => ({
  toast: toastMock,
}));

// ─── helpers ──────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderCompact(projectId = "proj-1", pageIndex = 0) {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PageActionsCompact projectId={projectId} pageIndex={pageIndex} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubJobNoop() {
  server.use(
    http.get("/api/jobs/:jobId", () =>
      HttpResponse.json({ job_id: "j1", status: "complete", progress: 1 }),
    ),
  );
}

beforeEach(() => {
  dialogStore.reset();
  stubJobNoop();
  // Default page GET so the C2 usePage fetch resolves cleanly in every test
  // (per-test handlers registered after this override it via msw LIFO).
  server.use(
    http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pagePayload(false))),
  );
  vi.clearAllMocks();
});

// ─── testids ──────────────────────────────────────────────────────────────────

describe("PageActionsCompact: testids (P1.b)", () => {
  it("renders page-actions-compact container", () => {
    renderCompact();
    expect(screen.getByTestId("page-actions-compact")).toBeInTheDocument();
  });

  it("renders all five compact button testids", () => {
    renderCompact();
    expect(screen.getByTestId("page-actions-compact-reload-ocr")).toBeInTheDocument();
    expect(screen.getByTestId("page-actions-compact-rematch-gt")).toBeInTheDocument();
    expect(screen.getByTestId("page-actions-compact-save-page")).toBeInTheDocument();
    expect(screen.getByTestId("page-actions-compact-export")).toBeInTheDocument();
    // #405: ocr-config-trigger-button restored in PageActionsCompact (project-page context)
    expect(screen.getByTestId("ocr-config-trigger-button")).toBeInTheDocument();
  });

  it("renders bulk-glyph-mark-button with correct testid (spec §7)", () => {
    renderCompact();
    expect(screen.getByTestId("bulk-glyph-mark-button")).toBeInTheDocument();
  });

  it("shows labelled text on buttons", () => {
    renderCompact();
    expect(screen.getByText("Reload OCR")).toBeInTheDocument();
    expect(screen.getByText("Rematch")).toBeInTheDocument();
    expect(screen.getByText("Save page")).toBeInTheDocument();
    expect(screen.getByText("Export")).toBeInTheDocument();
    expect(screen.getByText("OCR Config")).toBeInTheDocument();
  });
});

// ─── disabled state ───────────────────────────────────────────────────────────

describe("PageActionsCompact: disabled when no project", () => {
  it("reload-ocr is disabled when projectId is empty string", () => {
    // AppShell only renders PageActionsCompact when onProjectRoute is true
    // (projectId !== null), but the component's own disabled guard also
    // checks !projectId so an empty string keeps buttons disabled.
    renderCompact("", 0);
    expect(screen.getByTestId("page-actions-compact-reload-ocr")).toBeDisabled();
    expect(screen.getByTestId("page-actions-compact-save-page")).toBeDisabled();
  });
});

// ─── export opens dialog ──────────────────────────────────────────────────────

describe("PageActionsCompact: export opens dialog", () => {
  it("clicking export button opens the export dialog", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-export"));
    expect(dialogStore.getState().export.open).toBe(true);
  });
});

// ─── ocr-config-trigger-button opens dialog (#405) ───────────────────────────

describe("PageActionsCompact: OCR config trigger (#405)", () => {
  it("ocr-config-trigger-button is present in project-page context", () => {
    renderCompact();
    expect(screen.getByTestId("ocr-config-trigger-button")).toBeInTheDocument();
  });

  it("clicking ocr-config-trigger-button opens the ocrConfig dialog", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("ocr-config-trigger-button"));
    expect(dialogStore.getState().ocrConfig.open).toBe(true);
  });
});

// ─── mutation smoke tests ─────────────────────────────────────────────────────

describe("PageActionsCompact: mutation wiring (P1.b smoke)", () => {
  it("clicking Reload OCR calls POST reload-ocr endpoint", async () => {
    const reloadSpy = vi.fn(() => HttpResponse.json({ job_id: "test-job-1" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/pages/0/reload-ocr", reloadSpy));

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("page-actions-compact-reload-ocr"));
    await waitFor(() => expect(reloadSpy).toHaveBeenCalled());
  });

  it("clicking Save page calls POST save-page endpoint", async () => {
    const saveSpy = vi.fn(() =>
      HttpResponse.json({
        project_id: "proj-1",
        page_index: 0,
        saved: true,
      }),
    );
    server.use(http.post("/api/projects/proj-1/pages/0/save", saveSpy));

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("page-actions-compact-save-page"));
    await waitFor(() => expect(saveSpy).toHaveBeenCalled());
  });
});

// ─── Lane C / Task C2: restored dropped action buttons ───────────────────────
// Reload OCR (Edited), Save Project, Load Page were previously only in the
// hidden full PageActions bar. C2 restores them in the compact bar (overflow
// menu). hasEditedImage is bound to the page payload's labeler extension flag.

function pagePayload(hasEditedImage = false, rotationDegrees = 0, rotationSource = "none") {
  return {
    project_id: "proj-1",
    page_index: 0,
    page_record: {
      page_index: 0,
      image_path: "/data/proj-1/page_001.png",
      source: "ocr",
      provenance_summary: "OCR via DocTR",
      rotation_degrees: rotationDegrees,
      rotation_source: rotationSource,
      extensions: {
        labeler: {
          page_number: 1,
          page_source: "ocr",
          has_edited_image: hasEditedImage,
        },
      },
    },
    line_matches: [],
    selection: {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    },
    encoded_dims: null,
    line_filter: "all",
    image_url: "/api/projects/proj-1/image/0",
    generation: 1,
    page_text_ocr: "",
    page_text_gt: "",
    extra: {},
  };
}

function stubPage(hasEditedImage = false) {
  server.use(
    http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pagePayload(hasEditedImage))),
  );
}

describe("PageActionsCompact: restored dropped buttons (Lane C / C2)", () => {
  it("renders save-project, load-page, and reload-ocr-edited buttons", async () => {
    stubPage(true);
    renderCompact();
    // The dropped buttons live in an overflow menu; open it first.
    const user = userEvent.setup();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("save-project-button")).toBeInTheDocument();
    expect(screen.getByTestId("load-page-button")).toBeInTheDocument();
    expect(screen.getByTestId("reload-ocr-edited-button")).toBeInTheDocument();
  });

  it("save-project and load-page are enabled with a real project", async () => {
    stubPage(true);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("save-project-button")).not.toBeDisabled();
    expect(screen.getByTestId("load-page-button")).not.toBeDisabled();
  });

  it("reload-ocr-edited is enabled when the page has an edited image", async () => {
    stubPage(true);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await waitFor(() => {
      expect(screen.getByTestId("reload-ocr-edited-button")).not.toBeDisabled();
    });
  });

  it("reload-ocr-edited is disabled when the page has no edited image", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await waitFor(() => {
      expect(screen.getByTestId("reload-ocr-edited-button")).toBeDisabled();
    });
  });

  it("clicking Save Project POSTs save-all", async () => {
    stubPage(true);
    const saveAllSpy = vi.fn(() => HttpResponse.json({ job_id: "j-save-all" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/save-all", saveAllSpy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));
    await waitFor(() => expect(saveAllSpy).toHaveBeenCalled());
  });

  it("clicking Load Page POSTs the load endpoint", async () => {
    stubPage(true);
    const loadSpy = vi.fn(() => HttpResponse.json(pagePayload(true)));
    server.use(http.post("/api/projects/proj-1/pages/0/load", loadSpy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("load-page-button"));
    await waitFor(() => expect(loadSpy).toHaveBeenCalled());
  });

  it("clicking Reload OCR (Edited) POSTs reload-ocr with use_edited_image=true", async () => {
    stubPage(true);
    let bodySeen: unknown = null;
    const reloadSpy = vi.fn(async ({ request }: { request: Request }) => {
      bodySeen = await request.json();
      return HttpResponse.json({ job_id: "j-edited" }, { status: 202 });
    });
    server.use(http.post("/api/projects/proj-1/pages/0/reload-ocr", reloadSpy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("reload-ocr-edited-button"));
    await waitFor(() => expect(reloadSpy).toHaveBeenCalled());
    expect(bodySeen).toMatchObject({ use_edited_image: true });
  });
});

// ─── P2: rotate buttons on the visible surface (parity-audit C28 link 1) ─────
// The rotate testids previously existed ONLY inside the display:none hidden
// PageActions wrapper in ProjectPage — invisible, so the feature was dead.
// They must render on the real visible surface (compact-bar overflow menu).

describe("PageActionsCompact: rotate buttons (P2 / C28)", () => {
  it("renders rotate-cw/ccw/180 buttons in the overflow menu, enabled", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("rotate-cw-button")).not.toBeDisabled();
    expect(screen.getByTestId("rotate-ccw-button")).not.toBeDisabled();
    expect(screen.getByTestId("rotate-180-button")).not.toBeDisabled();
  });

  it.each([
    ["rotate-cw-button", 90],
    ["rotate-ccw-button", -90],
    ["rotate-180-button", 180],
  ])("clicking %s POSTs rotate with degrees=%i and manual=true", async (testid, degrees) => {
    stubPage(false);
    let bodySeen: unknown = null;
    const rotateSpy = vi.fn(async ({ request }: { request: Request }) => {
      bodySeen = await request.json();
      return HttpResponse.json({ job_id: "j-rot" }, { status: 202 });
    });
    server.use(http.post("/api/projects/proj-1/pages/0/rotate", rotateSpy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId(testid));
    await waitFor(() => expect(rotateSpy).toHaveBeenCalled());
    expect(bodySeen).toMatchObject({ degrees, manual: true });
  });
});

// ─── P2: rotation badge (parity-audit C28 link 3, frontend side) ─────────────

describe("PageActionsCompact: rotation badge (P2 / C28)", () => {
  it("shows the rotation badge when the payload carries a manual rotation", async () => {
    server.use(
      http.get("/api/projects/:pid/pages/:idx", () =>
        HttpResponse.json(pagePayload(false, 90, "manual")),
      ),
    );
    renderCompact();
    const badge = await screen.findByTestId("rotation-badge");
    await waitFor(() => expect(badge).toBeVisible());
    expect(badge.textContent).toContain("90");
    expect(badge.textContent).toContain("manual");
  });

  it("hides the rotation badge when rotation_degrees is 0", async () => {
    stubPage(false);
    renderCompact();
    // Badge stays in the DOM (driver contract) but is display:none.
    const badge = await screen.findByTestId("rotation-badge", {}, { timeout: 2000 });
    expect(badge).not.toBeVisible();
  });
});

// ─── P2: auto-rotate-all trigger (parity-audit C29) ──────────────────────────
// C29: zero non-generated frontend references to auto-rotate-all — the batch
// job had no UI trigger at all.

describe("PageActionsCompact: auto-rotate-all trigger (P2 / C29)", () => {
  it("renders auto-rotate-all-button in the overflow menu, enabled", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("auto-rotate-all-button")).not.toBeDisabled();
  });

  it("clicking auto-rotate-all POSTs the project-level auto-rotate-all route", async () => {
    stubPage(false);
    const autoRotateSpy = vi.fn(() => HttpResponse.json({ job_id: "j-auto-rot" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/auto-rotate-all", autoRotateSpy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("auto-rotate-all-button"));
    await waitFor(() => expect(autoRotateSpy).toHaveBeenCalled());
  });

  it("shows an error toast when auto-rotate-all is unavailable (503)", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/auto-rotate-all", () =>
        HttpResponse.json(
          { error: "auto_rotate_unavailable", message: "rotation module missing" },
          { status: 503 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("auto-rotate-all-button"));
    await waitFor(() => {
      const calls = toastMock.mock.calls;
      const errCall = calls.find(
        ([msg]: [unknown, ...unknown[]]) =>
          typeof msg === "string" && msg.toLowerCase().includes("auto-rotate"),
      );
      expect(errCall).toBeDefined();
    });
  });
});

// ─── toast lifecycle tests ────────────────────────────────────────────────────

describe("PageActionsCompact: toast lifecycle for reload-ocr", () => {
  it("shows a loading toast when Reload OCR starts, then success toast on complete", async () => {
    // Stub the reload-ocr POST to return a job_id.
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "j1" }, { status: 202 }),
      ),
    );

    // Stub the SSE endpoint. We deliver a "complete" event synchronously by
    // capturing the EventSource listener and dispatching it in the test.
    let progressListener: ((e: MessageEvent) => void) | null = null;
    const mockES = {
      addEventListener: vi.fn((type: string, fn: unknown) => {
        if (type === "progress") progressListener = fn as (e: MessageEvent) => void;
      }),
      removeEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1 as number,
    };
    vi.stubGlobal(
      "EventSource",
      vi.fn(() => mockES),
    );

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("page-actions-compact-reload-ocr"));

    // Wait for the mutation to complete and loading toast to be called.
    // The dynamic import("sonner") call in handleReloadOcr fires sonnerToast.loading().
    await waitFor(() =>
      expect(toastMock.loading).toHaveBeenCalledWith(
        "Running OCR…",
        expect.objectContaining({ id: "j1" }),
      ),
    );

    // Simulate SSE "complete" event.
    const completeEvent = {
      data: JSON.stringify({ job_id: "j1", status: "complete", progress: { message: "Done" } }),
    } as MessageEvent;
    act(() => {
      progressListener?.(completeEvent);
    });

    // Success toast: useEffect calls toast.success (from ../lib/toast) which
    // calls sonnerToast(message, opts) — i.e. the base toastMock fn, not .success.
    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith("OCR complete", expect.objectContaining({ id: "j1" })),
    );

    vi.unstubAllGlobals();
  });

  it("shows an error toast when Reload OCR job fails via SSE", async () => {
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "j2" }, { status: 202 }),
      ),
    );

    let progressListener: ((e: MessageEvent) => void) | null = null;
    const mockES = {
      addEventListener: vi.fn((type: string, fn: unknown) => {
        if (type === "progress") progressListener = fn as (e: MessageEvent) => void;
      }),
      removeEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1 as number,
    };
    vi.stubGlobal(
      "EventSource",
      vi.fn(() => mockES),
    );

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("page-actions-compact-reload-ocr"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    const errorEvent = {
      data: JSON.stringify({ job_id: "j2", status: "error", progress: { message: "OCR failed" } }),
    } as MessageEvent;
    act(() => {
      progressListener?.(errorEvent);
    });

    // Error toast: useEffect calls toast.error (from ../lib/toast) which
    // calls sonnerToast(message, opts) — i.e. the base toastMock fn, not .error.
    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith("OCR failed", expect.objectContaining({ id: "j2" })),
    );

    vi.unstubAllGlobals();
  });
});

// ─── S5.2: Save-project skipped-page warning toast ───────────────────────────
// When save-all completes with payload.skipped_pages > 0, the component must
// show a warning toast (not a success toast) mentioning the skipped pages.
// Definition of done: skipping is never silent.

describe("PageActionsCompact: S5.2 save-project skipped-page warning", () => {
  function makeSaveProjectES(progressListener: { current: ((e: MessageEvent) => void) | null }) {
    const mockES = {
      addEventListener: vi.fn((type: string, fn: unknown) => {
        if (type === "progress") progressListener.current = fn as (e: MessageEvent) => void;
      }),
      removeEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1 as number,
    };
    vi.stubGlobal(
      "EventSource",
      vi.fn(() => mockES),
    );
    return mockES;
  }

  it("shows warning toast (not success) when save-all completes with skipped_pages > 0", async () => {
    stubPage(false);
    // POST save-all → returns a job_id.
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "j-save-skip" }, { status: 202 }),
      ),
    );
    // GET /api/jobs/j-save-skip → job result with skipped_pages: 1.
    server.use(
      http.get("/api/jobs/j-save-skip", () =>
        HttpResponse.json({
          job_id: "j-save-skip",
          job_type: "save_project",
          status: "complete",
          progress_current: 1,
          progress_total: 1,
          message: "Saved",
          payload: {
            failures: [],
            skipped_pages: 1,
            skipped_indices: [0],
          },
        }),
      ),
    );

    const progressListener = { current: null as ((e: MessageEvent) => void) | null };
    makeSaveProjectES(progressListener);

    const user = userEvent.setup();
    renderCompact();

    // Open overflow menu and click Save Project.
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));

    // Wait for the loading toast to be shown.
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    // Simulate SSE complete event.
    act(() => {
      progressListener.current?.({
        data: JSON.stringify({
          job_id: "j-save-skip",
          status: "complete",
          progress: { message: "Saved" },
        }),
      } as MessageEvent);
    });

    // The component must show a WARNING toast (not success) because skipped_pages > 0.
    // toast.warn() calls sonnerToast(message, opts) with a warn-styled borderLeft.
    // We assert: sonnerToast was called with a message mentioning skip/unsaved/warning,
    // and the id matches.
    await waitFor(() => {
      const calls = toastMock.mock.calls;
      const warnCall = calls.find(
        ([msg]: [unknown, ...unknown[]]) =>
          typeof msg === "string" &&
          (msg.toLowerCase().includes("skip") ||
            msg.toLowerCase().includes("unsaved") ||
            msg.toLowerCase().includes("page")),
      );
      expect(warnCall).toBeDefined();
    });

    vi.unstubAllGlobals();
  });

  it("shows success toast when save-all completes with skipped_pages == 0", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "j-save-ok" }, { status: 202 }),
      ),
    );
    server.use(
      http.get("/api/jobs/j-save-ok", () =>
        HttpResponse.json({
          job_id: "j-save-ok",
          job_type: "save_project",
          status: "complete",
          progress_current: 1,
          progress_total: 1,
          message: "Saved",
          payload: {
            failures: [],
            skipped_pages: 0,
            skipped_indices: [],
          },
        }),
      ),
    );

    const progressListener = { current: null as ((e: MessageEvent) => void) | null };
    makeSaveProjectES(progressListener);

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    act(() => {
      progressListener.current?.({
        data: JSON.stringify({
          job_id: "j-save-ok",
          status: "complete",
          progress: { message: "Saved" },
        }),
      } as MessageEvent);
    });

    // Success: toast.success() → sonnerToast("Project saved", {id, style:{borderLeft:...status-exact...}})
    await waitFor(() => {
      const calls = toastMock.mock.calls;
      const successCall = calls.find(
        ([msg]: [unknown, ...unknown[]]) =>
          typeof msg === "string" && msg.toLowerCase().includes("saved"),
      );
      expect(successCall).toBeDefined();
    });

    vi.unstubAllGlobals();
  });
});
