// PageActionsCompact.test.tsx — unit tests for the compact header action bar.
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
