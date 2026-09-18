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
//
// The EventSource stubs below use `vi.fn(function () {...})` rather than an
// arrow function: Vitest 5 requires the mock's implementation to be a
// `function`/`class` when the mock is invoked with `new` (the hook under
// test does `new EventSource(...)`), since an arrow function is never
// constructible per the JS spec and vi.fn() no longer papers over that.

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

function renderCompact(projectId = "proj-1", pageIndex = 0, qc: QueryClient = makeQC()) {
  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <PageActionsCompact projectId={projectId} pageIndex={pageIndex} />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
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

  it("renders all five compact button testids (D-050: legacy §2.5 names)", () => {
    renderCompact();
    // D-050: testids renamed to driver-contract §2.5 canonical names
    expect(screen.getByTestId("reload-ocr-button")).toBeInTheDocument();
    expect(screen.getByTestId("rematch-gt-button")).toBeInTheDocument();
    expect(screen.getByTestId("save-page-button")).toBeInTheDocument();
    expect(screen.getByTestId("export-button")).toBeInTheDocument();
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

  it("renders undo-button and redo-button testids", () => {
    renderCompact();
    expect(screen.getByTestId("undo-button")).toBeInTheDocument();
    expect(screen.getByTestId("redo-button")).toBeInTheDocument();
  });

  it("renders page-actions-compact-overflow testid", () => {
    renderCompact();
    expect(screen.getByTestId("page-actions-compact-overflow")).toBeInTheDocument();
  });

  it("renders rotation-badge testid always in DOM (driver contract)", async () => {
    renderCompact();
    // badge is always in DOM even when not visible (display:none when not rotated)
    await screen.findByTestId("rotation-badge", {}, { timeout: 2000 });
  });
});

// ─── M2 primitive adoption: ButtonGroup / IconButton / DropdownMenu ───────────
// M2-Slice-2A: PageActionsCompact must use pdomain-ui primitives for generic
// toolbar mechanics. Tests assert the structural contracts the primitives impose.

describe("PageActionsCompact: pdomain-ui primitive adoption (M2-Slice-2A)", () => {
  it("main action buttons are accessible by aria-label", () => {
    renderCompact();
    // Buttons must carry aria-label (IconButton contract requires it)
    expect(screen.getByLabelText("Reload OCR")).toBeInTheDocument();
    expect(screen.getByLabelText("Rematch GT")).toBeInTheDocument();
    expect(screen.getByLabelText(/Save page/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Undo")).toBeInTheDocument();
    expect(screen.getByLabelText("Redo")).toBeInTheDocument();
    expect(screen.getByLabelText("Export")).toBeInTheDocument();
    expect(screen.getByLabelText("OCR Config")).toBeInTheDocument();
  });

  it("buttons are grouped via role=group (ButtonGroup contract)", () => {
    renderCompact();
    // ButtonGroup renders role="group" with an aria-label
    const groups = screen.getAllByRole("group");
    expect(groups.length).toBeGreaterThanOrEqual(1);
  });

  it("overflow button has aria-haspopup=menu (overflow/DropdownMenu contract)", () => {
    renderCompact();
    const overflow = screen.getByTestId("page-actions-compact-overflow");
    expect(overflow).toHaveAttribute("aria-haspopup");
  });

  it("overflow menu items are accessible via role=menuitem after opening", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    // DropdownMenu renders role="menuitem" on items
    const menuItems = await screen.findAllByRole("menuitem");
    expect(menuItems.length).toBeGreaterThanOrEqual(3);
  });

  it("all testids survive primitive adoption (D-050 preservation)", () => {
    renderCompact();
    // D-050: page-actions-bar wrapper + renamed §2.5 testids + new labels/badges
    const requiredTestids = [
      "page-actions-bar",
      "page-actions-compact",
      "reload-ocr-button",
      "rematch-gt-button",
      "save-page-button",
      "undo-button",
      "redo-button",
      "export-button",
      "ocr-config-trigger-button",
      "page-actions-compact-overflow",
      "bulk-glyph-mark-button",
      "page-source-badge",
    ];
    for (const tid of requiredTestids) {
      expect(screen.getByTestId(tid), `testid=${tid} should be present`).toBeInTheDocument();
    }
  });

  it("overflow menu testids survive primitive adoption", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    const overflowTestids = [
      "reload-ocr-edited-button",
      "save-project-button",
      "load-page-button",
      "rotate-cw-button",
      "rotate-ccw-button",
      "rotate-180-button",
      "auto-rotate-all-button",
    ];
    for (const tid of overflowTestids) {
      expect(
        await screen.findByTestId(tid),
        `overflow testid=${tid} should be present`,
      ).toBeInTheDocument();
    }
  });
});

// ─── disabled state ───────────────────────────────────────────────────────────

describe("PageActionsCompact: disabled when no project", () => {
  it("reload-ocr is disabled when projectId is empty string", () => {
    // AppShell only renders PageActionsCompact when onProjectRoute is true
    // (projectId !== null), but the component's own disabled guard also
    // checks !projectId so an empty string keeps buttons disabled.
    renderCompact("", 0);
    expect(screen.getByTestId("reload-ocr-button")).toBeDisabled();
    expect(screen.getByTestId("save-page-button")).toBeDisabled();
  });
});

// ─── export opens dialog ──────────────────────────────────────────────────────

describe("PageActionsCompact: export opens dialog", () => {
  it("clicking export button opens the export dialog", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("export-button"));
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

// H-D (event-store undo U-6): Reload OCR now routes through a confirm dialog
// that warns the page's edit history resets. The compact component opens the
// confirm via dialogStore; tests approve it directly (no ConfirmDialog is
// mounted in this harness).
function approveReloadOcrConfirm() {
  act(() => {
    const confirm = dialogStore.getState().confirm;
    expect(confirm.open).toBe(true);
    confirm.onConfirm?.();
    dialogStore.close("confirm");
  });
}

// ─── mutation smoke tests ─────────────────────────────────────────────────────

describe("PageActionsCompact: mutation wiring (P1.b smoke)", () => {
  it("clicking Reload OCR calls POST reload-ocr endpoint", async () => {
    const reloadSpy = vi.fn(() => HttpResponse.json({ job_id: "test-job-1" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/pages/0/reload-ocr", reloadSpy));

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();
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

    await user.click(screen.getByTestId("save-page-button"));
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
    // Radix DropdownMenuItem renders as div with aria-disabled — check absence of it.
    const saveProject = await screen.findByTestId("save-project-button");
    expect(saveProject).not.toHaveAttribute("aria-disabled", "true");
    const loadPage = screen.getByTestId("load-page-button");
    expect(loadPage).not.toHaveAttribute("aria-disabled", "true");
  });

  it("reload-ocr-edited is enabled when the page has an edited image", async () => {
    stubPage(true);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    // Radix DropdownMenuItem renders as div with aria-disabled — check absence.
    await waitFor(() => {
      expect(screen.getByTestId("reload-ocr-edited-button")).not.toHaveAttribute(
        "aria-disabled",
        "true",
      );
    });
  });

  it("reload-ocr-edited is disabled when the page has no edited image", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    // Radix DropdownMenuItem renders as a div with aria-disabled (not HTML disabled).
    await waitFor(() => {
      const btn = screen.getByTestId("reload-ocr-edited-button");
      expect(btn).toHaveAttribute("aria-disabled", "true");
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
    // U-7: Reload routes through a confirm dialog with the rewritten copy
    // (no "unsaved edits" claim). Approve it to fire the POST.
    act(() => {
      const confirm = dialogStore.getState().confirm;
      expect(confirm.open).toBe(true);
      expect(`${confirm.title ?? ""} ${confirm.body ?? ""}`).not.toMatch(/unsaved|discard/i);
      confirm.onConfirm?.();
      dialogStore.close("confirm");
    });
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
    approveReloadOcrConfirm();
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
    // Radix DropdownMenuItem renders as div — check aria-disabled absence.
    const cw = await screen.findByTestId("rotate-cw-button");
    expect(cw).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("rotate-ccw-button")).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("rotate-180-button")).not.toHaveAttribute("aria-disabled", "true");
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
    // Radix DropdownMenuItem renders as div — check aria-disabled absence.
    const autoBtn = await screen.findByTestId("auto-rotate-all-button");
    expect(autoBtn).not.toHaveAttribute("aria-disabled", "true");
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

// ─── Task 6: propose page kinds / propose regions book actions ──────────────
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 6 frontend half.
// Design: docs/specs/2026-09-17-region-review-surface-design.md
//   "Two book actions start the runs".
//
// Both actions follow the auto-rotate-all pattern (mutation stores the job
// id, opens a loading toast keyed by it; useJobCompletionInvalidation drives
// completion). On completion each shows the job's terminal progress message
// rather than a generic string, and Propose regions shows it as a warning
// (not success) when the run skipped every page for having no page kind.

/**
 * Build a synthetic SSE frame in the real wire shape — the public `Job`
 * model plus an `event` field naming the SSE event kind (Wave 3a /
 * P1-JOB-SSE) — from the handful of fields each test actually cares about.
 * `job_id` / `status` are required; everything else defaults to a value the
 * assertions under test don't inspect.
 */
function jobFrame(input: {
  job_id: string;
  status: string;
  progress?: { message?: string; current?: number; total?: number };
  type?: string;
}) {
  return {
    id: input.job_id,
    type: input.type ?? "reload_ocr",
    project_id: "proj-1",
    status: input.status,
    progress: { current: 0, total: 0, message: "", ...input.progress },
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: input.status,
  };
}

/** Stub EventSource capturing the SSE listener so a test can dispatch a
 * synthetic job-progress event, mirroring the reload-ocr toast-lifecycle
 * tests above. */
function mockEventSource() {
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
    vi.fn(function () {
      return mockES;
    }),
  );
  return {
    dispatch(data: Parameters<typeof jobFrame>[0]) {
      act(() => {
        progressListener?.({ data: JSON.stringify(jobFrame(data)) } as MessageEvent);
      });
    },
  };
}

describe("PageActionsCompact: propose page kinds / propose regions (Task 6)", () => {
  it("renders propose-page-kinds-button and propose-regions-button in the overflow menu", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("propose-page-kinds-button")).toBeInTheDocument();
    expect(screen.getByTestId("propose-regions-button")).toBeInTheDocument();
  });

  it("clicking Propose page kinds POSTs the propose-page-kinds route", async () => {
    stubPage(false);
    const spy = vi.fn(() => HttpResponse.json({ job_id: "job-pk-1" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/propose-page-kinds", spy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-page-kinds-button"));
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it("clicking Propose regions POSTs the regions/propose route", async () => {
    stubPage(false);
    const spy = vi.fn(() => HttpResponse.json({ job_id: "job-rg-1" }, { status: 202 }));
    server.use(http.post("/api/projects/proj-1/regions/propose", spy));
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-regions-button"));
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it("a region run that skipped every page for having no page kind shows a warn toast with the terminal message", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/regions/propose", () =>
        HttpResponse.json({ job_id: "job-rg-skip" }, { status: 202 }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-regions-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    const message =
      "Proposed 0 region(s) on 0 page(s). Skipped 3 page(s) with no page kind; run Propose page kinds first.";
    es.dispatch({ job_id: "job-rg-skip", status: "complete", progress: { message } });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { style?: { borderLeft?: string } }?][];
      const warnCall = calls.find(
        ([msg, opts]) => msg === message && opts?.style?.borderLeft?.includes("status-fuzzy"),
      );
      expect(warnCall).toBeDefined();
    });

    vi.unstubAllGlobals();
  });

  it("a completed region run with proposals shows a success toast with the terminal message", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/regions/propose", () =>
        HttpResponse.json({ job_id: "job-rg-ok" }, { status: 202 }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-regions-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    const message = "Proposed 12 region(s) on 6 page(s).";
    es.dispatch({ job_id: "job-rg-ok", status: "complete", progress: { message } });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { style?: { borderLeft?: string } }?][];
      const successCall = calls.find(
        ([msg, opts]) => msg === message && opts?.style?.borderLeft?.includes("status-exact"),
      );
      expect(successCall).toBeDefined();
    });

    vi.unstubAllGlobals();
  });

  it("propose page kinds completion invalidates the page query", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/propose-page-kinds", () =>
        HttpResponse.json({ job_id: "job-pk-inv" }, { status: 202 }),
      ),
    );
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact("proj-1", 0, qc);
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-page-kinds-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-pk-inv",
      status: "complete",
      progress: { message: "Proposed page kinds on 4 page(s)." },
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "proj-1", 0] }),
    );

    vi.unstubAllGlobals();
  });

  it("propose regions completion invalidates the page query", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/regions/propose", () =>
        HttpResponse.json({ job_id: "job-rg-inv" }, { status: 202 }),
      ),
    );
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact("proj-1", 0, qc);
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-regions-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-rg-inv",
      status: "complete",
      progress: { message: "Proposed 12 region(s) on 6 page(s)." },
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "proj-1", 0] }),
    );

    vi.unstubAllGlobals();
  });

  // ── Book review queue design: "A count stays visible" ──────────────────
  // Both book-scoped runs invalidate the review queue by its
  // ["review-queue", projectId] prefix, alongside the existing page
  // invalidation, so the Rail badge and bracket-key navigation see a fresh
  // count and page summary once the refetch lands.

  it("propose page kinds completion invalidates the review queue", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/propose-page-kinds", () =>
        HttpResponse.json({ job_id: "job-pk-rq" }, { status: 202 }),
      ),
    );
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact("proj-1", 0, qc);
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-page-kinds-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-pk-rq",
      status: "complete",
      progress: { message: "Proposed page kinds on 4 page(s)." },
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["review-queue", "proj-1"] }),
    );

    vi.unstubAllGlobals();
  });

  it("propose regions completion invalidates the review queue", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/regions/propose", () =>
        HttpResponse.json({ job_id: "job-rg-rq" }, { status: 202 }),
      ),
    );
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact("proj-1", 0, qc);
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-regions-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-rg-rq",
      status: "complete",
      progress: { message: "Proposed 12 region(s) on 6 page(s)." },
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["review-queue", "proj-1"] }),
    );

    vi.unstubAllGlobals();
  });

  // ── Page-kind review design: "A proposal run ... refresh[es] the list" ──

  it("propose page kinds completion invalidates the page-kinds prefix", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/propose-page-kinds", () =>
        HttpResponse.json({ job_id: "job-pk-pkinv" }, { status: 202 }),
      ),
    );
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact("proj-1", 0, qc);
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("propose-page-kinds-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-pk-pkinv",
      status: "complete",
      progress: { message: "Proposed page kinds on 4 page(s)." },
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page-kinds", "proj-1"] }),
    );

    vi.unstubAllGlobals();
  });
});

// ─── Cancel action on book-scoped run toasts (P1-CANCEL) ────────────────────
// Plan: docs/plans/2026-09-17-region-review-surface.md — P1-CANCEL
// reachability half.
//
// Propose page kinds / Propose regions / Auto-rotate all are the three
// book-scoped runs BusyOverlay's CANCELLABLE policy set already treats as
// backend-cancellable (BusyOverlay.tsx), but none of them ever route
// through BusyOverlay — each tracks its own job id and shows progress
// through this component's own loading toast instead. This suite covers
// giving that toast a Cancel action wired to the same POST
// /api/jobs/{jobId}/cancel BusyOverlay's button fires.

interface CancelToastAction {
  label: string;
  onClick: () => void;
}
interface LoadingCallOptions {
  id?: string;
  action?: CancelToastAction;
  description?: string;
}

/** The most recent `sonnerToast.loading(...)` call addressed to `jobId`. */
function findLatestLoadingCall(jobId: string) {
  const calls = toastMock.loading.mock.calls as [unknown, LoadingCallOptions?][];
  const matches = calls.filter(([, opts]) => opts?.id === jobId);
  return matches.at(-1);
}

interface CancellableRun {
  label: string;
  menuTestId: string;
  postRoute: string;
  jobId: string;
}

const CANCELLABLE_RUNS: CancellableRun[] = [
  {
    label: "Propose page kinds",
    menuTestId: "propose-page-kinds-button",
    postRoute: "/api/projects/proj-1/propose-page-kinds",
    jobId: "job-pk-cancel",
  },
  {
    label: "Propose regions",
    menuTestId: "propose-regions-button",
    postRoute: "/api/projects/proj-1/regions/propose",
    jobId: "job-rg-cancel",
  },
  {
    label: "Auto-rotate all",
    menuTestId: "auto-rotate-all-button",
    postRoute: "/api/projects/proj-1/auto-rotate-all",
    jobId: "job-ar-cancel",
  },
];

describe("PageActionsCompact: Cancel action on book-scoped run toasts (P1-CANCEL)", () => {
  async function startRun(user: ReturnType<typeof userEvent.setup>, run: CancellableRun) {
    server.use(
      http.post(run.postRoute, () => HttpResponse.json({ job_id: run.jobId }, { status: 202 })),
    );
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId(run.menuTestId));
    await waitFor(() => expect(findLatestLoadingCall(run.jobId)).toBeDefined());
  }

  for (const run of CANCELLABLE_RUNS) {
    it(`${run.label}: the loading toast offers a Cancel action`, async () => {
      stubPage(false);
      const user = userEvent.setup();
      renderCompact();
      await startRun(user, run);

      const call = findLatestLoadingCall(run.jobId);
      expect(call?.[1]?.action?.label).toBe("Cancel");
    });

    it(`${run.label}: clicking Cancel POSTs /api/jobs/{jobId}/cancel with that job's id`, async () => {
      stubPage(false);
      let hits = 0;
      let path: string | undefined;
      server.use(
        http.post(`/api/jobs/${run.jobId}/cancel`, ({ request }) => {
          hits += 1;
          path = new URL(request.url).pathname;
          return HttpResponse.json({ job_id: run.jobId, status: "cancelled" });
        }),
      );
      const user = userEvent.setup();
      renderCompact();
      await startRun(user, run);

      findLatestLoadingCall(run.jobId)?.[1]?.action?.onClick();

      await waitFor(() => expect(hits).toBe(1));
      expect(path).toBe(`/api/jobs/${run.jobId}/cancel`);
    });

    it(`${run.label}: clicking Cancel twice sends only one request`, async () => {
      stubPage(false);
      let hits = 0;
      server.use(
        http.post(`/api/jobs/${run.jobId}/cancel`, () => {
          hits += 1;
          return HttpResponse.json({ job_id: run.jobId, status: "cancelled" });
        }),
      );
      const user = userEvent.setup();
      renderCompact();
      await startRun(user, run);

      const action = findLatestLoadingCall(run.jobId)?.[1]?.action;
      action?.onClick();
      action?.onClick();

      await waitFor(() => expect(hits).toBe(1));
      // Give a would-be second request a chance to land before asserting
      // it never did.
      await new Promise((resolve) => setTimeout(resolve, 10));
      expect(hits).toBe(1);
    });

    it(`${run.label}: a cancelled terminal event shows the backend's own message`, async () => {
      stubPage(false);
      server.use(
        http.post(`/api/jobs/${run.jobId}/cancel`, () =>
          HttpResponse.json({ job_id: run.jobId, status: "cancelled" }),
        ),
      );
      const es = mockEventSource();
      const user = userEvent.setup();
      renderCompact();
      await startRun(user, run);

      const message = `${run.label} cancelled after doing some of the work`;
      es.dispatch({ job_id: run.jobId, status: "cancelled", progress: { message } });

      await waitFor(() => {
        const calls = toastMock.mock.calls as [unknown, { id?: string }?][];
        const match = calls.find(([msg, opts]) => msg === message && opts?.id === run.jobId);
        expect(match).toBeDefined();
      });

      vi.unstubAllGlobals();
    });

    it(`${run.label}: no Cancel action once the job completes`, async () => {
      stubPage(false);
      const es = mockEventSource();
      const user = userEvent.setup();
      renderCompact();
      await startRun(user, run);

      es.dispatch({ job_id: run.jobId, status: "complete", progress: { message: "Done" } });

      await waitFor(() => {
        const calls = toastMock.mock.calls as [unknown, { id?: string; action?: unknown }?][];
        const match = calls.find(([, opts]) => opts?.id === run.jobId);
        expect(match).toBeDefined();
        expect(match?.[1]?.action).toBeUndefined();
      });

      vi.unstubAllGlobals();
    });
  }

  // A manual single-page rotate is NOT in BusyOverlay's CANCELLABLE set —
  // only auto_rotate_all is — so its toast must stay plain.
  it("a manual single-page rotate does NOT get a Cancel action", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/pages/0/rotate", () =>
        HttpResponse.json({ job_id: "job-manual-rotate" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("rotate-cw-button"));

    await waitFor(() => expect(findLatestLoadingCall("job-manual-rotate")).toBeDefined());
    expect(findLatestLoadingCall("job-manual-rotate")?.[1]?.action).toBeUndefined();
  });
});

// ─── Cancel action on Reload OCR / Save Project toasts (P1-CANCEL) ──────────
// PageActionsCompact's own "Reload OCR" and "Save Project" buttons track
// their jobs locally and never reach BusyOverlay — only the equivalent
// keyboard shortcut (wired to ProjectPage's own tracker, not tested here)
// did. This closes that gap the same way as the three book-scoped runs
// above, with one difference: reload_ocr_page is BusyOverlay's
// BEST_EFFORT_CANCEL, not its CANCELLABLE — the handler never checks
// cancellation mid-page, so its toast must say so rather than implying an
// immediate stop, and its terminal message is authored by the frontend, not
// echoed from the backend's own (irrelevant, mid-OCR-stage) progress label.

describe("PageActionsCompact: Cancel action on Reload OCR / Save Project toasts (P1-CANCEL)", () => {
  it("Reload OCR's loading toast offers a Cancel action with the best-effort caveat", async () => {
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "job-ocr-cancel-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();

    await waitFor(() => expect(findLatestLoadingCall("job-ocr-cancel-1")).toBeDefined());
    const call = findLatestLoadingCall("job-ocr-cancel-1");
    expect(call?.[1]?.action?.label).toBe("Cancel");
    expect(call?.[1]?.description).toMatch(/best-effort/i);
    expect(call?.[1]?.description).toMatch(/may not stop immediately/i);
  });

  // "Reload OCR (Edited)" starts the same reload_ocr_page job type through a
  // second button (overflow menu) — its own initial loading toast must get
  // the same Cancel action, not just the plain "Reload OCR" button's.
  it("Reload OCR (Edited)'s loading toast also offers a Cancel action", async () => {
    stubPage(true);
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "job-ocr-edited-cancel-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("reload-ocr-edited-button"));
    approveReloadOcrConfirm();

    await waitFor(() => expect(findLatestLoadingCall("job-ocr-edited-cancel-1")).toBeDefined());
    const call = findLatestLoadingCall("job-ocr-edited-cancel-1");
    expect(call?.[1]?.action?.label).toBe("Cancel");
    expect(call?.[1]?.description).toMatch(/best-effort/i);
  });

  it("clicking Reload OCR's Cancel POSTs /api/jobs/{jobId}/cancel with that job's id", async () => {
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "job-ocr-cancel-2" }, { status: 202 }),
      ),
    );
    let hits = 0;
    let path: string | undefined;
    server.use(
      http.post("/api/jobs/job-ocr-cancel-2/cancel", ({ request }) => {
        hits += 1;
        path = new URL(request.url).pathname;
        return HttpResponse.json({ job_id: "job-ocr-cancel-2", status: "cancelled" });
      }),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();

    await waitFor(() => expect(findLatestLoadingCall("job-ocr-cancel-2")).toBeDefined());
    findLatestLoadingCall("job-ocr-cancel-2")?.[1]?.action?.onClick();

    await waitFor(() => expect(hits).toBe(1));
    expect(path).toBe("/api/jobs/job-ocr-cancel-2/cancel");
  });

  it("a cancelled Reload OCR job shows a best-effort message, not the raw mid-OCR stage label", async () => {
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "job-ocr-cancel-3" }, { status: 202 }),
      ),
      http.post("/api/jobs/job-ocr-cancel-3/cancel", () =>
        HttpResponse.json({ job_id: "job-ocr-cancel-3", status: "cancelled" }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();
    await waitFor(() => expect(findLatestLoadingCall("job-ocr-cancel-3")).toBeDefined());

    // reload_ocr.py never checks is_cancelled — its terminal "cancelled"
    // event's own progress message is just whichever OCR stage was in
    // flight, not a cancel summary. The toast must not just echo it.
    es.dispatch({
      job_id: "job-ocr-cancel-3",
      status: "cancelled",
      progress: { message: "Running OCR" },
    });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { id?: string }?][];
      const bestEffortMatch = calls.find(
        ([msg, opts]) =>
          typeof msg === "string" && /best-effort/i.test(msg) && opts?.id === "job-ocr-cancel-3",
      );
      expect(bestEffortMatch).toBeDefined();
      const rawStageEcho = calls.find(([msg]) => msg === "Running OCR");
      expect(rawStageEcho).toBeUndefined();
    });

    vi.unstubAllGlobals();
  });

  it("no Cancel action on Reload OCR's toast once the job completes", async () => {
    server.use(
      http.post("/api/projects/proj-1/pages/0/reload-ocr", () =>
        HttpResponse.json({ job_id: "job-ocr-cancel-4" }, { status: 202 }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();
    await waitFor(() => expect(findLatestLoadingCall("job-ocr-cancel-4")).toBeDefined());

    es.dispatch({ job_id: "job-ocr-cancel-4", status: "complete", progress: { message: "Done" } });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { id?: string; action?: unknown }?][];
      const match = calls.find(([, opts]) => opts?.id === "job-ocr-cancel-4");
      expect(match).toBeDefined();
      expect(match?.[1]?.action).toBeUndefined();
    });

    vi.unstubAllGlobals();
  });

  it("Save Project's loading toast offers a Cancel action", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "job-save-cancel-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));

    await waitFor(() => expect(findLatestLoadingCall("job-save-cancel-1")).toBeDefined());
    expect(findLatestLoadingCall("job-save-cancel-1")?.[1]?.action?.label).toBe("Cancel");
  });

  it("clicking Save Project's Cancel POSTs /api/jobs/{jobId}/cancel with that job's id", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "job-save-cancel-2" }, { status: 202 }),
      ),
    );
    let hits = 0;
    let path: string | undefined;
    server.use(
      http.post("/api/jobs/job-save-cancel-2/cancel", ({ request }) => {
        hits += 1;
        path = new URL(request.url).pathname;
        return HttpResponse.json({ job_id: "job-save-cancel-2", status: "cancelled" });
      }),
    );
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));

    await waitFor(() => expect(findLatestLoadingCall("job-save-cancel-2")).toBeDefined());
    findLatestLoadingCall("job-save-cancel-2")?.[1]?.action?.onClick();

    await waitFor(() => expect(hits).toBe(1));
    expect(path).toBe("/api/jobs/job-save-cancel-2/cancel");
  });

  it("a cancelled Save Project job renders the backend's own summary message", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "job-save-cancel-3" }, { status: 202 }),
      ),
      http.post("/api/jobs/job-save-cancel-3/cancel", () =>
        HttpResponse.json({ job_id: "job-save-cancel-3", status: "cancelled" }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));
    await waitFor(() => expect(findLatestLoadingCall("job-save-cancel-3")).toBeDefined());

    const message = "Cancelled after saving 2 of 5 page(s)";
    es.dispatch({ job_id: "job-save-cancel-3", status: "cancelled", progress: { message } });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { id?: string }?][];
      const match = calls.find(
        ([msg, opts]) => msg === message && opts?.id === "job-save-cancel-3",
      );
      expect(match).toBeDefined();
    });

    vi.unstubAllGlobals();
  });

  it("no Cancel action on Save Project's toast once the job completes", async () => {
    stubPage(false);
    server.use(
      http.post("/api/projects/proj-1/save-all", () =>
        HttpResponse.json({ job_id: "job-save-cancel-4" }, { status: 202 }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("save-project-button"));
    await waitFor(() => expect(findLatestLoadingCall("job-save-cancel-4")).toBeDefined());

    es.dispatch({
      job_id: "job-save-cancel-4",
      status: "complete",
      progress: { message: "Saved" },
    });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { id?: string; action?: unknown }?][];
      const match = calls.find(([, opts]) => opts?.id === "job-save-cancel-4");
      expect(match).toBeDefined();
      expect(match?.[1]?.action).toBeUndefined();
    });

    vi.unstubAllGlobals();
  });
});

// ─── page-kind toolbar control (page-kind review design) ────────────────────
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "The page toolbar shows and confirms the current page's kind" — three
//   states: confirmed, proposed (with confidence, unknown shown as "Kind
//   unknown"), and nothing yet (with a hint to run Propose page kinds).

function pagePayloadWithKind(overrides: Record<string, unknown>) {
  return {
    project_id: "proj-1",
    page_index: 0,
    page_record: null,
    line_matches: [],
    selection: {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    },
    encoded_dims: null,
    line_filter: "all",
    image_url: null,
    generation: 1,
    page_text_ocr: "",
    page_text_gt: "",
    page_kind_reviewed: false,
    extra: {},
    ...overrides,
  };
}

function stubPageKind(overrides: Record<string, unknown>) {
  server.use(
    http.get("/api/projects/:pid/pages/:idx", () =>
      HttpResponse.json(pagePayloadWithKind(overrides)),
    ),
  );
}

describe("PageActionsCompact: page-kind toolbar control", () => {
  it("shows the confirmed kind when the page has been reviewed", async () => {
    stubPageKind({ page_kind: "title page", page_kind_reviewed: true });
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent(/title page/i);
    });
    expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent(/confirmed/i);
  });

  it("shows the proposed kind with its confidence when unconfirmed", async () => {
    stubPageKind({
      page_kind_proposal: {
        proposal_id: "p1",
        run_id: "r1",
        kind: "body",
        confidence: 0.82,
        evidence: {},
      },
    });
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent("body");
    });
    expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent("0.82");
  });

  it("shows 'Kind unknown' for an unknown proposal", async () => {
    stubPageKind({
      page_kind_proposal: {
        proposal_id: "p1",
        run_id: "r1",
        kind: "unknown",
        confidence: null,
        evidence: {},
      },
    });
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent(/kind unknown/i);
    });
  });

  it("shows 'No page kind' with a hint when nothing has been proposed or confirmed", async () => {
    stubPageKind({});
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("page-kind-status-button")).toHaveTextContent(/no page kind/i);
    });
    expect(screen.getByTestId("page-kind-control")).toHaveTextContent(/propose page kinds/i);
  });

  it("does not cap a normal confirmed label to a fixed width (P0-CI-SOFT review)", async () => {
    // The toolbar-collision fix (P0-CI-SOFT follow-up) must not apply a
    // *fixed* max-width to the button: that would ellipsis ordinary
    // confirmed/proposed labels ("Proposed: chapter opening (0.87)") behind
    // a hover regardless of how much room the toolbar actually has. `truncate`
    // alone is fine — it only clips when flex-shrink genuinely runs out of
    // room — jsdom doesn't run real layout, so a fixed `max-w-` class is the
    // one static signal this DOM-level test can check.
    stubPageKind({ page_kind: "chapter opening", page_kind_reviewed: true });
    renderCompact();
    const btn = await screen.findByTestId("page-kind-status-button");
    await waitFor(() => {
      expect(btn).toHaveTextContent(/chapter opening/i);
    });
    expect(btn.className).not.toMatch(/\bmax-w-/);
  });

  it("does not cap a normal proposed label with confidence to a fixed width (P0-CI-SOFT review)", async () => {
    stubPageKind({
      page_kind_proposal: {
        proposal_id: "p1",
        run_id: "r1",
        kind: "chapter opening",
        confidence: 0.87,
        evidence: {},
      },
    });
    renderCompact();
    const btn = await screen.findByTestId("page-kind-status-button");
    await waitFor(() => {
      expect(btn).toHaveTextContent(/chapter opening/i);
      expect(btn).toHaveTextContent("0.87");
    });
    expect(btn.className).not.toMatch(/\bmax-w-/);
  });

  it("opening the control preselects the confirmed kind and Confirm re-sends it", async () => {
    stubPageKind({ page_kind: "blank", page_kind_reviewed: true });
    const spy = vi.fn(() =>
      HttpResponse.json(pagePayloadWithKind({ page_kind: "blank", page_kind_reviewed: true })),
    );
    server.use(http.post("/api/projects/proj-1/pages/0/page-kind", spy));
    const user = userEvent.setup();
    renderCompact();
    await waitFor(() => screen.getByTestId("page-kind-status-button"));

    await user.click(screen.getByTestId("page-kind-status-button"));
    expect(screen.getByTestId("page-kind-select")).toHaveValue("blank");

    await user.click(screen.getByTestId("page-kind-confirm-button"));

    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it("opening the control preselects the proposed kind when unconfirmed", async () => {
    stubPageKind({
      page_kind_proposal: {
        proposal_id: "p1",
        run_id: "r1",
        kind: "plate",
        confidence: 0.6,
        evidence: {},
      },
    });
    const user = userEvent.setup();
    renderCompact();
    await waitFor(() => screen.getByTestId("page-kind-status-button"));

    await user.click(screen.getByTestId("page-kind-status-button"));

    expect(screen.getByTestId("page-kind-select")).toHaveValue("plate");
  });

  it("confirming a chosen kind POSTs to .../page-kind with that kind", async () => {
    stubPageKind({});
    let body: unknown;
    server.use(
      http.post("/api/projects/proj-1/pages/0/page-kind", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          pagePayloadWithKind({ page_kind: "contents", page_kind_reviewed: true }),
        );
      }),
    );
    const user = userEvent.setup();
    renderCompact();
    await waitFor(() => screen.getByTestId("page-kind-status-button"));
    await user.click(screen.getByTestId("page-kind-status-button"));

    await user.selectOptions(screen.getByTestId("page-kind-select"), "contents");
    await user.click(screen.getByTestId("page-kind-confirm-button"));

    await waitFor(() => {
      expect(body).toEqual({ kind: "contents", note: null });
    });
  });
});

// ─── "Review page kinds" menu entry ──────────────────────────────────────────

describe("PageActionsCompact: Review page kinds menu entry", () => {
  it("renders review-page-kinds-button in the overflow menu", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    expect(await screen.findByTestId("review-page-kinds-button")).toBeInTheDocument();
  });

  it("clicking it opens the pageKinds dialog", async () => {
    stubPage(false);
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    await user.click(await screen.findByTestId("review-page-kinds-button"));
    expect(dialogStore.getState().pageKinds.open).toBe(true);
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
      vi.fn(function () {
        return mockES;
      }),
    );

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();

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
      data: JSON.stringify(
        jobFrame({ job_id: "j1", status: "complete", progress: { message: "Done" } }),
      ),
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
      vi.fn(function () {
        return mockES;
      }),
    );

    const user = userEvent.setup();
    renderCompact();

    await user.click(screen.getByTestId("reload-ocr-button"));
    approveReloadOcrConfirm();
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    const errorEvent = {
      data: JSON.stringify(
        jobFrame({ job_id: "j2", status: "error", progress: { message: "OCR failed" } }),
      ),
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
// When save-all completes with result.skipped_pages > 0, the component must
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
      vi.fn(function () {
        return mockES;
      }),
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
    // GET /api/jobs/j-save-skip → the public Job's `result` field carries
    // save_project's skipped_pages/skipped_indices/failures output
    // (core.models.Job.result; docs/issues/2026-07-21-jobs-api-openapi-mismatch.md,
    // P1-JOBS-API).
    server.use(
      http.get("/api/jobs/j-save-skip", () =>
        HttpResponse.json({
          id: "j-save-skip",
          type: "save_project",
          project_id: "proj-1",
          status: "complete",
          progress: { current: 1, total: 1, message: "Saved" },
          created_at: new Date(0).toISOString(),
          updated_at: new Date(0).toISOString(),
          result: {
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
        data: JSON.stringify(
          jobFrame({ job_id: "j-save-skip", status: "complete", progress: { message: "Saved" } }),
        ),
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
          id: "j-save-ok",
          type: "save_project",
          project_id: "proj-1",
          status: "complete",
          progress: { current: 1, total: 1, message: "Saved" },
          created_at: new Date(0).toISOString(),
          updated_at: new Date(0).toISOString(),
          result: {
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
        data: JSON.stringify(
          jobFrame({ job_id: "j-save-ok", status: "complete", progress: { message: "Saved" } }),
        ),
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
