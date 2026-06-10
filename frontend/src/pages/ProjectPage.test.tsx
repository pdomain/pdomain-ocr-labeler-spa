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

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { clearSelection, selectLine } from "../stores/selection-store";

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

  it("IS-2: ProjectNavigationControls is no longer inside ProjectPage (moved to App HeaderBar navSlot)", async () => {
    // After IS-2, ProjectNavigationControls is rendered via App.tsx HeaderBar
    // navSlot, not inside ProjectPage. ProjectPage.test renders ProjectPage in
    // isolation without the App wrapper, so nav-controls are not present here.
    // The driver contract preserves testids via stubs in HeaderBar.
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.queryByTestId("project-navigation-controls")).toBeNull();
    });
  });

  it("IS-2: PageActions bar is hidden (driver testids still reachable in DOM)", async () => {
    // PageActions is kept mounted as a hidden div for driver-contract §2.5
    // testid preservation. The testids are reachable but the element is hidden.
    renderProjectPage();
    expect(await screen.findByTestId("page-actions-bar")).toBeInTheDocument();
    expect(screen.getByTestId("reload-ocr-button")).toBeInTheDocument();
    expect(screen.getByTestId("save-page-button")).toBeInTheDocument();
    expect(screen.getByTestId("save-project-button")).toBeInTheDocument();
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

  it("renders the InlineBanners.OcrFailedBanner when page_record.ocr_failed is true", async () => {
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => {
        const page = pageFixture();
        page.page_record.ocr_failed = true;
        return HttpResponse.json(page);
      }),
    );
    renderProjectPage();
    expect(await screen.findByTestId("banner-ocr-failed")).toBeInTheDocument();
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
    const saveBtnEl = await screen.findByTestId("save-page-button");
    // IS-2: PageActions is in a hidden div; use fireEvent.click (not
    // userEvent.click which checks visibility) to trigger the mutation.
    fireEvent.click(saveBtnEl);
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

      fireEvent.keyDown(document, { key: "s", ctrlKey: true, bubbles: true });
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

      fireEvent.keyDown(document, { key: "g", ctrlKey: true, bubbles: true });

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

      fireEvent.keyDown(document, { key: "g", ctrlKey: true, bubbles: true });
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

  // ── BUG-KBD-3: useMatchesHotkeys wired in ProjectPage ─────────────────────

  describe("BUG-KBD-3: useMatchesHotkeys wired (J/K navigate worklist)", () => {
    it("J key advances worklistStore.selectedLineIndex by 1", async () => {
      // This import is inside the test so the store is reset between test runs.
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(null);

      renderProjectPage();
      await screen.findByTestId("project-page");

      fireEvent.keyDown(document, { key: "j", bubbles: true });
      await waitFor(() => {
        // null → null + 1 = 0 (clamped to 0 since lines=[]).
        expect(wl.getState().selectedLineIndex).toBe(0);
      });
    });

    it("K key decrements worklistStore.selectedLineIndex (does not go below 0)", async () => {
      const { worklistStore: wl } = await import("../stores/worklist-store");
      wl.setSelectedLineIndex(null);

      renderProjectPage();
      await screen.findByTestId("project-page");

      // K from null → clamped to 0.
      fireEvent.keyDown(document, { key: "k", bubbles: true });
      await waitFor(() => {
        expect(wl.getState().selectedLineIndex).toBe(0);
      });
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
});
