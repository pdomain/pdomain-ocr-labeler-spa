// ProjectPage.test.tsx — Vitest unit tests for the real ProjectPage shell.
// Covers: B-PROJECT-001, B-PROJECT-004, B-PROJECT-005, B-PROJECT-006, B-PROJECT-007
// Covers: B-DRIVER-003, B-ACTIONS-009
//
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §4 (Data flow),
//       §10 (Driver-contract preservation), §11 (Notifications), §12 (Acceptance).
// Issue #314 (spec-22-C).
//
// These tests verify the assembled shell:
//   - All major child components render when a payload is provided.
//   - Hooks (useProject, usePage) are called and consumed correctly.
//   - Splitter is mounted; image-pane and text-pane regions present.
//   - PageActions / ToolbarActionGrid / ImageTabsHeader / TextTabs mount.
//   - ConfirmDialog is mounted closed by default; word editing lives in RightPanel.
//   - Loading state shows ProjectLoadingOverlay; no `display:none` stubs
//     inside ProjectPage (those moved to HeaderBar per spec §10).
//
// react-konva is mocked module-wide so the PageImageCanvas tree renders
// as simple divs under jsdom (no canvas backend).
//
// react-hotkeys-hook 5 matches against the physical `KeyboardEvent.code`
// (e.g. "KeyS"), not `.key` — fireEvent.keyDown must set `code` explicitly,
// jsdom does not derive it from `key`.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { clearSelection, selectLine, selectWord, selectionStore } from "../stores/selection-store";

// ─── IS-1: mock useNavigate ──────────────────────────────────────────────────
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ─── Mocks ──────────────────────────────────────────────────────────────────
// Phase 2.2: PageImageCanvas now imports @pdomain/pdomain-ui/canvas which
// bundles react-konva. Mock pdomain-ui/canvas first to prevent konva's Node.js
// entry from trying to require('canvas'), a native addon not in jsdom.
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
// Mock react-konva for any remaining transitive imports.
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

// `use-image` is referenced by PageImageCanvas; stub it.
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

// Minimal project + page payload fixtures.
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
    line_matches: [],
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
    page_text_ocr: "ocr text",
    page_text_gt: "gt text",
    page_load_error: null as { error: string; message: string } | null,
    extra: {},
  };
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("ProjectPage — real shell (spec 22 §3, #314)", () => {
  beforeEach(() => {
    dialogStore.reset();
    mockNavigate.mockReset();
    // IS-3/IS-6: Reset drawer + right panel prefs to defaults between tests
    // so store mutations in one test don't bleed into the next.
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    // Default success handlers for project + page.
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
    );
  });

  it("renders the project-page root container", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("project-page")).toBeInTheDocument();
  });

  it("renders the project workspace without the nested local StudioShell", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("project-workspace")).toBeInTheDocument();
    expect(screen.queryByTestId("studio-shell")).toBeNull();
    expect(screen.getByTestId("project-canvas-column")).toBeInTheDocument();
    expect(screen.getByTestId("project-worklist-column")).toBeInTheDocument();
    expect(screen.getByTestId("project-detail-column")).toBeInTheDocument();
  });

  it("removes the legacy source-folder + nav stubs from inside ProjectPage", async () => {
    const { container } = renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      // The specific stub blocks from the legacy 76-LOC stub must NOT live
      // inside the project-page root anymore — they relocated to HeaderBar
      // per spec §10. ToolbarActionGrid still emits `data-testid-stub` for
      // its absent grid cells, which is correct (spec §6 of the toolbar
      // design); those are not the legacy stub blocks.
      const legacyStubIds = [
        "nav-prev-button",
        "nav-next-button",
        "nav-goto-button",
        "nav-page-input",
        "nav-page-total-label",
        "source-folder-current-path-label",
        "source-folder-path-input",
        "source-folder-home-button",
        "source-folder-up-button",
        "source-folder-open-typed-button",
        "source-folder-use-current-button",
        "source-folder-cancel-button",
        "source-folder-apply-button",
      ];
      for (const tid of legacyStubIds) {
        const stubMatch = container.querySelector(
          `[data-testid="project-page"] [data-testid="${tid}"][data-testid-stub="true"]`,
        );
        expect(stubMatch, `legacy stub for ${tid} should not be inside project-page`).toBeNull();
      }
    });
  });

  it("D-047: ProjectNavigationControls renders inside the WorkspaceToolbar band", async () => {
    // D-047 reverses IS-2: the chrome header is document-control-free, so
    // ProjectNavigationControls now lives in the WorkspaceToolbar band at the
    // top of the project route body (leftSlot). The band carries
    // data-testid="workspace-toolbar".
    renderProjectPage();
    await screen.findByTestId("project-page");
    const toolbar = await screen.findByTestId("workspace-toolbar");
    expect(toolbar.querySelector('[data-testid="project-navigation-controls"]')).not.toBeNull();
  });

  it("D-047: PageActionsCompact renders inside the WorkspaceToolbar centerSlot", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    const toolbar = await screen.findByTestId("workspace-toolbar");
    expect(toolbar.querySelector('[data-testid="page-actions-compact"]')).not.toBeNull();
  });

  it("D-050: PageActions §2.5 testids are visible in PageActionsCompact", async () => {
    // D-050: Hidden PageActions stub removed. §2.5 testids are now the canonical
    // testids on visible PageActionsCompact buttons inside page-actions-bar.
    renderProjectPage();
    expect(await screen.findByTestId("page-actions-bar")).toBeInTheDocument();
    expect(screen.getByTestId("reload-ocr-button")).toBeInTheDocument();
    expect(screen.getByTestId("save-page-button")).toBeInTheDocument();
    // save-project-button is in the overflow menu — check it's in DOM
    expect(screen.getByTestId("page-actions-compact-overflow")).toBeInTheDocument();
  });

  it("GRID-1: ToolbarActionGrid is visible (not inside display:none subtree)", async () => {
    // GRID-1: After Slice C the grid must be visible in the canvas column, not
    // hidden inside the canvas-hidden-stubs wrapper.
    renderProjectPage();
    expect(await screen.findByTestId("toolbar-action-grid")).toBeInTheDocument();
    // Must NOT be inside the old canvas-hidden-stubs container.
    const grid = screen.getByTestId("toolbar-action-grid");
    const hiddenContainer = grid.closest("[data-testid-stub='canvas-hidden-stubs']");
    expect(hiddenContainer, "grid must not be inside display:none stub container").toBeNull();
    // The collapse toggle must be present.
    expect(screen.getByTestId("toolbar-grid-collapse")).toBeInTheDocument();
  });

  it("IS-4: Splitter is removed from visible canvas", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    // The splitter is gone from the canvas — image-pane is now direct child of canvas.
    expect(screen.queryByTestId("splitter")).toBeNull();
  });

  it("does not mount duplicate ImageTabsHeader chrome above the image", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("image-pane")).toBeInTheDocument();
    expect(screen.queryByTestId("image-tabs-header")).toBeNull();
  });

  it("IS-4: PageImageCanvas viewport is inside image-pane in the canvas", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("image-viewport")).toBeInTheDocument();
    const imagePaneEl = screen.getByTestId("image-pane");
    expect(imagePaneEl.contains(screen.getByTestId("image-viewport"))).toBe(true);
  });

  it("IS-4: TextTabs testids are reachable in hidden stubs (driver-contract §2.7)", async () => {
    // TextTabs kept hidden for driver testid preservation.
    renderProjectPage();
    expect(await screen.findByTestId("text-tab-matches")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ground-truth")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ocr")).toBeInTheDocument();
  });

  it("IS-4: match filter testids reachable in hidden stubs (driver-contract §2.7)", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("match-filter-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-unvalidated")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-mismatched")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-all")).toBeInTheDocument();
  });

  it("IS-4: WordMatchView reachable in hidden stubs (driver-contract §2.8)", async () => {
    renderProjectPage();
    // line_matches is [] in the fixture → the empty-state span is shown.
    expect(await screen.findByTestId("word-match-view")).toBeInTheDocument();
  });

  it("mounts the InlineBanners region (always present even when no banner is active)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    // The banner region exists; individual banner testids only render when
    // their condition is true. We assert the region container.
    expect(screen.getByTestId("inline-banners")).toBeInTheDocument();
  });

  it("does not mount the retired word-edit modal", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    expect(screen.queryByTestId("word-edit-dialog")).toBeNull();
  });

  it("does NOT mount the ConfirmDialog when closed (default)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    expect(screen.queryByTestId("confirm-dialog")).toBeNull();
  });

  it("shows the ProjectLoadingOverlay while usePage is loading", async () => {
    // Override page handler to never resolve — keeps the query in loading state.
    server.use(
      http.get("/api/projects/:pid/pages/:idx", () => new Promise(() => {})),
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
    );
    renderProjectPage();
    expect(await screen.findByTestId("project-loading-overlay")).toBeInTheDocument();
  });

  it("does not render OcrFailedBanner from the unused page_record.ocr_failed flag", async () => {
    // page_record.ocr_failed comes from pdomain_ops.PageRecord (an upstream
    // dependency) and nothing in this backend ever sets it — the real
    // signal is PagePayload.page_load_error (issue
    // 2026-08-08-get-page-hides-ocr-failures). ProjectPage must not read
    // the dead flag; see "renders OcrFailedBanner with the loader message
    // when page_load_error is set" for the real trigger.
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => {
        const page = pageFixture();
        page.page_record.ocr_failed = true;
        return HttpResponse.json(page);
      }),
    );
    renderProjectPage();
    // Wait for the page fetch to actually resolve (page-name-label only
    // renders once pageQ.data?.page_record is present) rather than asserting
    // absence the instant "project-page" mounts, which would pass
    // vacuously before the mocked fetch even settles.
    await screen.findByTestId("page-name-label");
    expect(screen.queryByTestId("banner-ocr-failed")).toBeNull();
  });

  it("does not render OcrFailedBanner for a page with no text and no page_load_error", async () => {
    // issue 2026-08-08-get-page-hides-ocr-failures: a page that genuinely
    // has no OCR text (the default fixture: empty line_matches, no
    // page_load_error) must render exactly as it does today — no banner.
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
    );
    renderProjectPage();
    await screen.findByTestId("project-page");
    expect(screen.queryByTestId("banner-ocr-failed")).toBeNull();
  });

  it("renders OcrFailedBanner with the loader message when page_load_error is set", async () => {
    // issue 2026-08-08-get-page-hides-ocr-failures: a genuine loader
    // failure must be visible, distinct from "OCR ran and found no text".
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => {
        const page = pageFixture();
        page.page_load_error = { error: "ocr_load_failed", message: "doctr predictor unavailable" };
        return HttpResponse.json(page);
      }),
    );
    renderProjectPage();
    const banner = await screen.findByTestId("banner-ocr-failed");
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toContain("doctr predictor unavailable");
  });

  it("IS-1: auto-redirects to / and does NOT render ProjectNotFoundBanner when project 404s", async () => {
    server.use(
      http.get("/api/projects/:pid", () =>
        HttpResponse.json({ message: "Not found" }, { status: 404 }),
      ),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
    );
    renderProjectPage();
    // Wait for the redirect effect to fire.
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/", {
        replace: true,
        state: { skipSessionRedirect: true },
      });
    });
    // Banner is no longer rendered (navigate replaces it).
    expect(screen.queryByTestId("banner-project-not-found")).toBeNull();
  });

  it("mounts BusyOverlay inside image-pane and shows it while a save mutation is in-flight (#293)", async () => {
    // Keep the save endpoint hanging so isMutating stays true long enough to assert.
    server.use(http.post("/api/projects/:pid/pages/:idx/save", () => new Promise(() => {})));
    renderProjectPage();
    // Wait for the page to fully render.
    await screen.findByTestId("project-workspace");
    // D-050: save-page-button is in PageActionsCompact (own useSavePage hook).
    // Trigger ProjectPage's own save mutation via Ctrl+S hotkey so that
    // ProjectPage's isMutating flag rises (drives BusyOverlay).
    fireEvent.keyDown(document, { key: "s", code: "KeyS", ctrlKey: true });
    // BusyOverlay renders inside the image-pane while the mutation is pending.
    // IS-4: image-pane is now a direct flex child of the canvas column (no splitter).
    expect(await screen.findByTestId("busy-overlay")).toBeInTheDocument();
    const imagePaneEl = screen.getByTestId("image-pane");
    expect(imagePaneEl.contains(screen.getByTestId("busy-overlay"))).toBe(true);
  });

  it("IS-4: inline-banners is in the canvas column (sibling of image-pane after IS-4 strip)", async () => {
    renderProjectPage();
    // inline-banners container is always present (even with no active banners).
    const bannersEl = await screen.findByTestId("inline-banners");
    expect(bannersEl).toBeInTheDocument();
    const canvasZone = screen.getByTestId("project-canvas-column");
    expect(canvasZone.contains(bannersEl)).toBe(true);
  });

  it("IS-3: Drawer renders with data-testid='drawer' (wired into ProjectPage)", async () => {
    renderProjectPage();
    // Drawer is now wired with real lineMatches + page props.
    // Default drawerOpen is true, so the drawer is visible.
    expect(await screen.findByTestId("drawer")).toBeInTheDocument();
  });

  it("IS-3: the worklist column reflects drawerOpen from useUiPrefs", async () => {
    renderProjectPage();
    await screen.findByTestId("project-worklist-column");
    expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "true");
  });

  it("IS-6: clicking drawer-collapse-btn collapses the right-side worklist", async () => {
    renderProjectPage();
    await screen.findByTestId("drawer");
    // Default: open. Collapse button is inside the Drawer header.
    const collapseBtn = screen.getByTestId("drawer-collapse-btn");
    fireEvent.click(collapseBtn);
    await waitFor(() => {
      expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "false");
    });
  });

  it("IS-6: clicking drawer-expand-btn after collapse re-opens the drawer", async () => {
    renderProjectPage();
    await screen.findByTestId("drawer");
    // Collapse first.
    fireEvent.click(screen.getByTestId("drawer-collapse-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("drawer-expand-btn")).toBeInTheDocument();
    });
    // Expand.
    fireEvent.click(screen.getByTestId("drawer-expand-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "true");
    });
  });

  it("IS-6: clicking right-panel-collapse hides the right zone", async () => {
    renderProjectPage();
    await screen.findByTestId("right-panel");
    const collapseBtn = screen.getByTestId("right-panel-collapse");
    fireEvent.click(collapseBtn);
    await waitFor(() => {
      // When rightPanelOpen=false, rightSlot is null → RightPanel not in DOM.
      expect(screen.queryByTestId("right-panel")).toBeNull();
    });
  });

  it("GAP-3: fires POST /current-page-index (debounced) when page index changes", async () => {
    // Track POST calls to the cursor endpoint.
    const calls: { projectId: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/current-page-index", async ({ params, request }) => {
        calls.push({ projectId: params["pid"] as string, body: await request.json() });
        return HttpResponse.json({});
      }),
    );

    // Render on page 1 (idx0 = 0).
    renderProjectPage("/projects/p1/pages/pageno/1");
    await screen.findByTestId("project-page");

    // Wait for the debounced POST (300 ms timer fires; fake timers not used
    // here so we rely on waitFor polling).
    await waitFor(
      () => {
        expect(calls.length).toBeGreaterThanOrEqual(1);
      },
      { timeout: 1000 },
    );

    const lastCall = calls[calls.length - 1];
    expect(lastCall.projectId).toBe("p1");
    expect(lastCall.body).toEqual({ page_index: 0 });
  });

  // ── BUG-KBD-2: useGlobalHotkeys wired in ProjectPage ──────────────────────

  describe("BUG-KBD-2: useGlobalHotkeys wired (Ctrl+S fires save-page)", () => {
    it("Ctrl+S fires POST /save (save-page mutation)", async () => {
      const saveCalls: unknown[] = [];
      server.use(
        http.post("/api/projects/:pid/pages/:idx/save", async ({ request }) => {
          saveCalls.push(await request.text());
          return HttpResponse.json({});
        }),
      );
      renderProjectPage();
      await screen.findByTestId("project-page");
      // Wait for data to settle so isMutating=false and hotkeys are active.
      await screen.findByTestId("save-page-button");

      fireEvent.keyDown(document, { key: "s", code: "KeyS", ctrlKey: true, bubbles: true });
      await waitFor(() => {
        expect(saveCalls.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("F-035: Ctrl+G opens confirm dialog (does NOT fire mutation directly)", async () => {
      // After F-035 fix, Mod+G routes through the confirm dialog.
      // The mutation must NOT fire until the user confirms.
      const rematchCalls: unknown[] = [];
      server.use(
        http.post("/api/projects/:pid/pages/:idx/rematch-gt", async ({ request }) => {
          rematchCalls.push(await request.text());
          return HttpResponse.json({});
        }),
      );
      renderProjectPage();
      await screen.findByTestId("project-page");

      fireEvent.keyDown(document, { key: "g", code: "KeyG", ctrlKey: true, bubbles: true });

      // Dialog should be visible now.
      await waitFor(() => {
        expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
      });

      // Mutation must NOT have fired yet.
      expect(rematchCalls.length).toBe(0);

      // Confirm → mutation fires.
      fireEvent.click(screen.getByTestId("confirm-dialog-confirm"));
      await waitFor(() => {
        expect(rematchCalls.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("F-035: Ctrl+G confirm dialog cancel leaves mutation unfired", async () => {
      const rematchCalls: unknown[] = [];
      server.use(
        http.post("/api/projects/:pid/pages/:idx/rematch-gt", async ({ request }) => {
          rematchCalls.push(await request.text());
          return HttpResponse.json({});
        }),
      );
      renderProjectPage();
      await screen.findByTestId("project-page");

      fireEvent.keyDown(document, { key: "g", code: "KeyG", ctrlKey: true, bubbles: true });
      await waitFor(() => {
        expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
      });

      // Cancel — dialog should close and mutation must not fire.
      fireEvent.click(screen.getByTestId("confirm-dialog-cancel"));
      await waitFor(() => {
        expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
      });
      expect(rematchCalls.length).toBe(0);
    });
  });

  // ── BUG-KBD-3 / P1-MATCH-NAV: useMatchesHotkeys wired in ProjectPage ───────
  // docs/issues/2026-07-21-match-nav-selection-desync.md — J/K must take the
  // same `focusWorklistLine` path as a Worklist row click, so the worklist
  // highlight and the hierarchical selection (canvas / breadcrumb / right
  // panel) cannot drift apart.

  describe("BUG-KBD-3 / P1-MATCH-NAV: J/K navigate the worklist with no lines", () => {
    it("J key is a no-op when the page has no lines (nothing to select)", async () => {
      // Default `pageFixture()` has line_matches: [] — there is no line 0 to
      // focus, so J must leave both stores untouched rather than pointing
      // the worklist and selectionStore at a line index that does not exist.
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(null);
      clearSelection();

      renderProjectPage();
      await screen.findByTestId("project-page");

      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });

      // Give the hotkey handler a tick to (not) run, then assert no change.
      await waitFor(() => {
        expect(screen.getByTestId("project-page")).toBeInTheDocument();
      });
      expect(wl.getState().selectedLineIndex).toBeNull();
      expect(selectionStore.getState().level).toBe("none");
    });

    it("K key is a no-op when the page has no lines", async () => {
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(null);
      clearSelection();

      renderProjectPage();
      await screen.findByTestId("project-page");

      fireEvent.keyDown(document, { key: "k", code: "KeyK", bubbles: true });

      await waitFor(() => {
        expect(screen.getByTestId("project-page")).toBeInTheDocument();
      });
      expect(wl.getState().selectedLineIndex).toBeNull();
      expect(selectionStore.getState().level).toBe("none");
    });
  });

  describe("P1-MATCH-NAV: J/K keep worklistStore and selectionStore in sync", () => {
    // Two-line fixture so navigation has somewhere to go and a "next" line
    // for the stale-index recovery test below.
    function matchesNavLine(lineIndex: number) {
      return {
        line_index: lineIndex,
        paragraph_index: 0,
        ocr_line_text: `ocr ${lineIndex}`,
        ground_truth_line_text: `gt ${lineIndex}`,
        word_matches: [],
        overall_match_status: "exact" as const,
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: false,
      };
    }

    function matchesNavPageFixture() {
      return { ...pageFixture(), line_matches: [matchesNavLine(0), matchesNavLine(1)] };
    }

    beforeEach(async () => {
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(null);
      clearSelection();
      server.use(
        http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
        http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(matchesNavPageFixture())),
      );
    });

    // Firing a hotkey before the 2-line fixture has actually loaded would
    // race the empty-page ([]) guard in onLineNav (lines.length === 0 is a
    // deliberate no-op) — wait for WordMatchView's empty-state span to be
    // gone so `lines` really has the fixture's two entries first.
    async function waitForLinesLoaded() {
      await screen.findByTestId("project-page");
      await waitFor(() => {
        expect(screen.queryByTestId("word-match-empty")).toBeNull();
      });
    }

    it("J advances worklistStore.selectedLineIndex AND selects the same line in selectionStore", async () => {
      const { worklistStore: wl } = await import("../stores/worklist-store");

      renderProjectPage();
      await waitForLinesLoaded();

      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });
      await waitFor(() => {
        expect(wl.getState().selectedLineIndex).toBe(0);
      });
      // Same triple a Worklist row click writes: selectedLines, level, path.
      expect(selectionStore.getState().selectedLines).toEqual([0]);
      expect(selectionStore.getState().level).toBe("line");
      expect(selectionStore.getState().path.lineId).toBe(0);
    });

    it("K decrements worklistStore.selectedLineIndex AND selects the same line in selectionStore", async () => {
      const { worklistStore: wl } = await import("../stores/worklist-store");

      renderProjectPage();
      await waitForLinesLoaded();

      // K from null → clamped to 0, same as J.
      fireEvent.keyDown(document, { key: "k", code: "KeyK", bubbles: true });
      await waitFor(() => {
        expect(wl.getState().selectedLineIndex).toBe(0);
      });
      expect(selectionStore.getState().selectedLines).toEqual([0]);
      expect(selectionStore.getState().level).toBe("line");
      expect(selectionStore.getState().path.lineId).toBe(0);
    });

    it("J opens the right panel, matching the Worklist row-click behavior (STB-4)", async () => {
      useUiPrefs.setState({ rightPanelOpen: false });

      renderProjectPage();
      await waitForLinesLoaded();

      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });
      await waitFor(() => {
        expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
      });
    });

    it("J replaces an existing word selection, the same way a row click would", async () => {
      // A person mid-word-edit on the canvas presses J. A row click would
      // clobber that selection too (it always calls selectLine); J/K must
      // not special-case this into leaving the word selection in place.
      selectWord(0, 0);
      expect(selectionStore.getState().level).toBe("word");

      renderProjectPage();
      await waitForLinesLoaded();

      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });
      await waitFor(() => {
        expect(selectionStore.getState().level).toBe("line");
      });
      expect(selectionStore.getState().selectedWords).toEqual([]);
      expect(selectionStore.getState().path.lineId).toBe(0);
    });

    it("recovers when worklistStore.selectedLineIndex is stale after the page refetches with fewer lines", async () => {
      // Simulate a line index left over from before a delete/refetch shrank
      // line_matches to 2 entries (valid indices 0, 1).
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(5);

      renderProjectPage();
      await waitForLinesLoaded();

      fireEvent.keyDown(document, { key: "k", code: "KeyK", bubbles: true });
      await waitFor(() => {
        // Clamped into the current [0, 1] range, not left dangling at 4.
        expect(wl.getState().selectedLineIndex).toBe(1);
      });
      expect(selectionStore.getState().path.lineId).toBe(1);
      expect(selectionStore.getState().level).toBe("line");
    });

    it("an action hotkey (V) validates the line the person just navigated to with J", async () => {
      const calls: { body: unknown }[] = [];
      server.use(
        http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
          calls.push({ body: await request.json() });
          return HttpResponse.json(matchesNavPageFixture());
        }),
      );
      const { worklistStore: wl } = await import("../stores/worklist-store");

      renderProjectPage();
      await waitForLinesLoaded();

      // J, J → worklist line 1 (0 → 1).
      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });
      await waitFor(() => {
        expect(wl.getState().selectedLineIndex).toBe(0);
      });
      fireEvent.keyDown(document, { key: "j", code: "KeyJ", bubbles: true });
      await waitFor(() => {
        expect(wl.getState().selectedLineIndex).toBe(1);
      });
      // The selection the rest of the UI shows must agree before the mutation fires.
      expect(selectionStore.getState().path.lineId).toBe(1);

      fireEvent.keyDown(document, { key: "v", code: "KeyV", bubbles: true });
      await waitFor(() => {
        expect(calls.length).toBeGreaterThanOrEqual(1);
      });
      expect(calls[0]!.body).toEqual(
        expect.objectContaining({ scope: "line", line_indices: [1], validated: true }),
      );
    });
  });

  // ── GRID-1/2/3: ToolbarActionGrid collapsible canvas bar (Slice C) ─────────

  describe("GRID-1/2/3: ToolbarActionGrid visible collapsible bar", () => {
    // Page fixture with one unvalidated line so cells can be enabled.
    function gridPageFixture() {
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

    beforeEach(() => {
      clearSelection();
      useUiPrefs.setState({
        drawerOpen: true,
        rightPanelOpen: true,
        selectionMode: "line",
        // Ensure collapsed flag is reset to default (expanded).
        toolbarGridCollapsed: false,
      } as Parameters<typeof useUiPrefs.setState>[0]);
      server.use(
        http.get("/api/projects/:pid", () =>
          HttpResponse.json({
            project: {
              project_id: "p1",
              project_root: "/data/p1",
              image_paths: ["page_001.png"],
              ground_truth_map: {},
            },
            current_page_index: 0,
            generation: 1,
          }),
        ),
        http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(gridPageFixture())),
        http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
      );
    });

    it("GRID-1: grid renders outside any display:none subtree and collapse toggle exists", async () => {
      renderProjectPage();
      await screen.findByTestId("project-page");
      const grid = await screen.findByTestId("toolbar-action-grid");

      // Must NOT be inside the old canvas-hidden-stubs container.
      const hiddenContainer = grid.closest("[data-testid-stub='canvas-hidden-stubs']");
      expect(hiddenContainer, "grid must not be inside hidden-stubs wrapper").toBeNull();

      // Collapse toggle must be present.
      expect(screen.getByTestId("toolbar-grid-collapse")).toBeInTheDocument();
    });

    it("GRID-2: clicking toolbar-grid-collapse toggles grid visibility", async () => {
      renderProjectPage();
      await screen.findByTestId("toolbar-action-grid");

      // Default: expanded — grid is visible (not hidden by CSS).
      const grid = screen.getByTestId("toolbar-action-grid");
      // The grid must not have display:none on itself or a direct ancestor inside
      // the collapsible container. We check the parent collapse-body wrapper.
      const collapseBody = document.querySelector("[data-testid='toolbar-grid-body']");
      // Before collapsing, the body wrapper should be present and not hidden.
      expect(collapseBody).not.toBeNull();
      expect(collapseBody).toBeVisible();
      expect(grid).toBeVisible();

      // Click collapse toggle to hide the grid.
      fireEvent.click(screen.getByTestId("toolbar-grid-collapse"));
      await waitFor(() => {
        // After collapsing, the body is hidden (display:none or not rendered).
        const body = document.querySelector("[data-testid='toolbar-grid-body']");
        // Either removed from DOM or hidden.
        if (body) {
          expect(body).not.toBeVisible();
        } else {
          // Conditionally rendered — acceptable.
          expect(body).toBeNull();
        }
      });

      // Click again to expand.
      fireEvent.click(screen.getByTestId("toolbar-grid-collapse"));
      await waitFor(() => {
        expect(screen.getByTestId("toolbar-action-grid")).toBeVisible();
      });
    });

    it("GRID-3: clicking an enabled grid cell dispatches its mutation (grid now visible)", async () => {
      const calls: { url: string; body: unknown }[] = [];
      server.use(
        http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
          calls.push({ url: request.url, body: await request.json() });
          return HttpResponse.json(gridPageFixture());
        }),
      );

      renderProjectPage();
      await screen.findByTestId("project-page");
      // Wait for page data to settle so line_matches feed the grid.
      await screen.findByTestId("toolbar-line-validate");

      // Select line 0 so the line/validate cell becomes enabled.
      selectLine(0);
      await waitFor(() => {
        // The cell should now be enabled (not disabled).
        const cell = screen.getByTestId("toolbar-line-validate");
        expect(cell).not.toBeDisabled();
      });

      // Grid is now visible — both fireEvent and userEvent would work.
      fireEvent.click(screen.getByTestId("toolbar-line-validate"));

      await waitFor(() => {
        expect(calls.length).toBeGreaterThanOrEqual(1);
      });
      expect(calls[0]!.url).toContain("/words/validate-batch");
      expect(calls[0]!.body).toEqual(expect.objectContaining({ scope: "line", validated: true }));
    });
  });

  // ── AG-3: R/Shift+R hotkeys fire refine mutation ─────────────────────────

  describe("AG-3: R and Shift+R hotkeys fire refine/expand-refine endpoint", () => {
    it("R key fires POST /refine with scope=line mode=refine when a line is selected", async () => {
      const calls: { url: string; body: unknown }[] = [];
      const refineResponse = { project_id: "p1", page_index: 0, line_matches: [] };
      server.use(
        http.post("/api/projects/:pid/pages/:idx/refine", async ({ request }) => {
          calls.push({ url: request.url, body: await request.json() });
          return HttpResponse.json(refineResponse);
        }),
      );

      renderProjectPage();
      await screen.findByTestId("project-page");

      // Select line 0 so the dispatch has a non-empty selected_lines
      selectLine(0);

      fireEvent.keyDown(document, { key: "r", code: "KeyR", bubbles: true });

      await waitFor(() => {
        expect(calls.length).toBeGreaterThanOrEqual(1);
      });
      expect(calls[0]!.url).toContain("/refine");
      expect(calls[0]!.body).toEqual(expect.objectContaining({ scope: "line", mode: "refine" }));
    });

    it("Shift+R key fires POST /refine with scope=line mode=expand_then_refine", async () => {
      const calls: { url: string; body: unknown }[] = [];
      const refineResponse = { project_id: "p1", page_index: 0, line_matches: [] };
      server.use(
        http.post("/api/projects/:pid/pages/:idx/refine", async ({ request }) => {
          calls.push({ url: request.url, body: await request.json() });
          return HttpResponse.json(refineResponse);
        }),
      );

      renderProjectPage();
      await screen.findByTestId("project-page");

      selectLine(0);

      fireEvent.keyDown(document, { key: "R", code: "KeyR", shiftKey: true, bubbles: true });

      await waitFor(() => {
        expect(calls.length).toBeGreaterThanOrEqual(1);
      });
      expect(calls[0]!.url).toContain("/refine");
      expect(calls[0]!.body).toEqual(
        expect.objectContaining({ scope: "line", mode: "expand_then_refine" }),
      );
    });
  });

  // ── Bug-1: toolbar-grid-collapse chevron direction ───────────────────────────

  describe("Bug-1 — Actions panel chevron reflects open state", () => {
    it("toolbar-grid-collapse renders UP chevron (polyline 18 15 12 9 6 15) when panel is CLOSED", async () => {
      // When toolbarGridCollapsed=true the chevron should point UP (∧) to
      // indicate the panel can be expanded (content revealed below).
      useUiPrefs.setState({ toolbarGridCollapsed: true });
      renderProjectPage();
      await screen.findByTestId("toolbar-grid-collapse");
      const btn = screen.getByTestId("toolbar-grid-collapse");
      // The UP chevron polyline points are "18 15 12 9 6 15".
      const polyline = btn.querySelector("polyline");
      expect(polyline).not.toBeNull();
      expect(polyline!.getAttribute("points")).toBe("18 15 12 9 6 15");
    });

    it("toolbar-grid-collapse renders DOWN chevron (polyline 6 9 12 15 18 9) when panel is OPEN", async () => {
      // When toolbarGridCollapsed=false (open) the chevron should point DOWN (∨)
      // to indicate the panel is open and can be collapsed.
      useUiPrefs.setState({ toolbarGridCollapsed: false });
      renderProjectPage();
      await screen.findByTestId("toolbar-grid-collapse");
      const btn = screen.getByTestId("toolbar-grid-collapse");
      // The DOWN chevron polyline points are "6 9 12 15 18 9".
      const polyline = btn.querySelector("polyline");
      expect(polyline).not.toBeNull();
      expect(polyline!.getAttribute("points")).toBe("6 9 12 15 18 9");
    });
  });

  // ── Bug-2b: right panel always has a re-open control ─────────────────────────

  describe("Bug-2b — right panel re-open control always present", () => {
    it("right-panel-expand-btn is in the DOM when rightPanelOpen is false", async () => {
      useUiPrefs.setState({ rightPanelOpen: false });
      renderProjectPage();
      await screen.findByTestId("project-page");
      expect(screen.getByTestId("right-panel-expand-btn")).toBeInTheDocument();
    });

    it("clicking right-panel-expand-btn sets rightPanelOpen to true", async () => {
      useUiPrefs.setState({ rightPanelOpen: false });
      renderProjectPage();
      await screen.findByTestId("project-page");
      fireEvent.click(screen.getByTestId("right-panel-expand-btn"));
      await waitFor(() => {
        expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
      });
    });

    it("right-panel-expand-btn is NOT in the DOM when rightPanelOpen is true", async () => {
      useUiPrefs.setState({ rightPanelOpen: true });
      renderProjectPage();
      await screen.findByTestId("right-panel");
      expect(screen.queryByTestId("right-panel-expand-btn")).toBeNull();
    });

    it("project-detail-column always has content (re-open tab) when right panel is collapsed", async () => {
      useUiPrefs.setState({ rightPanelOpen: false });
      renderProjectPage();
      await screen.findByTestId("project-page");
      const detailCol = screen.getByTestId("project-detail-column");
      // The column must not be empty — it now contains the re-open tab button.
      expect(detailCol.children.length).toBeGreaterThan(0);
    });
  });

  // ── Book review queue design: Queue tab count badge ───────────────────────

  describe("Queue drawer tab — count badge fed from the review queue", () => {
    it("drawer-tab-count-queue reflects the review queue's total_undecided", async () => {
      server.use(
        http.get("/api/projects/:pid/regions/review-queue", () =>
          HttpResponse.json({ total_undecided: 5, pages: [], items: [] }),
        ),
      );
      renderProjectPage();
      await screen.findByTestId("drawer-tab-queue");
      await waitFor(() => {
        expect(screen.getByTestId("drawer-tab-count-queue")).toHaveTextContent("5");
      });
    });

    it("no count badge when the review queue has no undecided proposals", async () => {
      server.use(
        http.get("/api/projects/:pid/regions/review-queue", () =>
          HttpResponse.json({ total_undecided: 0, pages: [], items: [] }),
        ),
      );
      renderProjectPage();
      await screen.findByTestId("drawer-tab-queue");
      await waitFor(() => {
        expect(screen.queryByTestId("drawer-tab-count-queue")).not.toBeInTheDocument();
      });
    });
  });
});
