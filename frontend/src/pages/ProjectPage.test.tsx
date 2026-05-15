// ProjectPage.test.tsx — Vitest unit tests for the real ProjectPage shell.
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
//   - WordEditDialog + ConfirmDialog are mounted (closed by default).
//   - Loading state shows ProjectLoadingOverlay; no `display:none` stubs
//     inside ProjectPage (those moved to HeaderBar per spec §10).
//
// react-konva is mocked module-wide so the PageImageCanvas tree renders
// as simple divs under jsdom (no canvas backend).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";

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
// Mock react-konva so the PageImageCanvas subtree renders as simple divs.
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

function renderProjectPage(path: string = "/projects/p1/pages/pageno/1") {
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

  it("renders the StudioShell wrapper with all 5 zones (Slice 8)", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("studio-shell")).toBeInTheDocument();
    expect(screen.getByTestId("studio-shell-header")).toBeInTheDocument();
    expect(screen.getByTestId("studio-shell-rail")).toBeInTheDocument();
    expect(screen.getByTestId("studio-shell-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("studio-shell-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("studio-shell-right")).toBeInTheDocument();
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

  it("mounts the ToolbarActionGrid", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("toolbar-action-grid")).toBeInTheDocument();
  });

  it("mounts the Splitter with left (image) and right (text) panes", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("splitter")).toBeInTheDocument();
    expect(screen.getByTestId("splitter-left")).toBeInTheDocument();
    expect(screen.getByTestId("splitter-right")).toBeInTheDocument();
    expect(screen.getByTestId("image-pane")).toBeInTheDocument();
    expect(screen.getByTestId("text-pane")).toBeInTheDocument();
  });

  it("mounts the ImageTabsHeader inside the image pane", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("layer-paragraphs-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("layer-lines-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("layer-words-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("selection-mode-paragraph")).toBeInTheDocument();
    expect(screen.getByTestId("erase-pixels-button")).toBeInTheDocument();
  });

  it("mounts the PageImageCanvas viewport inside the image pane", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("image-viewport")).toBeInTheDocument();
  });

  it("mounts the TextTabs (matches / ground-truth / ocr) inside the text pane", async () => {
    renderProjectPage();
    expect(await screen.findByTestId("text-tab-matches")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ground-truth")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ocr")).toBeInTheDocument();
  });

  it("mounts the match filter UI (testids match-filter-toggle + 3 sub-buttons)", async () => {
    // TextTabs (shipped #200) already renders the spec 22 §8 match-filter
    // testids; ProjectPage wires its value to `useUiPrefs.matchFilter`.
    renderProjectPage();
    expect(await screen.findByTestId("match-filter-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-unvalidated")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-mismatched")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-all")).toBeInTheDocument();
  });

  it("mounts the WordMatchView container (empty list with provided payload)", async () => {
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

  it("does NOT mount the WordEditDialog when closed (default)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    // WordEditDialog returns null when open=false → no dialog-backdrop.
    expect(screen.queryByTestId("dialog-backdrop")).toBeNull();
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
      expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true });
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
    expect(await screen.findByTestId("busy-overlay")).toBeInTheDocument();
    // Confirm it is inside the image-pane (not a sibling of the page root).
    const imagePaneEl = screen.getByTestId("image-pane");
    expect(imagePaneEl.contains(screen.getByTestId("busy-overlay"))).toBe(true);
  });

  it("mounts the inline-banners region inside image-pane and InlineBanners components are wired (#293)", async () => {
    renderProjectPage();
    // inline-banners container is always present (even with no active banners).
    const bannersEl = await screen.findByTestId("inline-banners");
    expect(bannersEl).toBeInTheDocument();
    // It must be inside the image-pane per spec 22 §3.
    const imagePaneEl = screen.getByTestId("image-pane");
    expect(imagePaneEl.contains(bannersEl)).toBe(true);
  });
});
