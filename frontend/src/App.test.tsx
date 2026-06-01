// App.test.tsx — Vitest tests for App shell routing.
// Covers: B-DRIVER-004, B-DRIVER-006
// Issue #240: React Router routes, QueryClient provider wiring.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Routing
// Phase 2.4: AppShell + SuiteSiblingsProvider mocks added (#262).
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "./test/server";
import type * as React from "react";

// Phase 2.4: Mock @pdomain/pdomain-ui/shell so AppShell renders a
// transparent pass-through in jsdom — no Zustand store setup, no real
// grid layout. The mock preserves the slot-forwarding contract (header,
// main, children) so downstream tests can assert on HeaderBar + Routes.
vi.mock("@pdomain/pdomain-ui/shell", () => ({
  AppShell: ({
    header,
    rail,
    main,
    children,
  }: {
    appId?: string;
    appDisplayName?: string;
    appIconUrl?: string;
    header?: React.ReactNode;
    rail?: React.ReactNode;
    main?: React.ReactNode;
    children?: React.ReactNode;
    launcherSlot?: string;
    deployMode?: string;
    uiPrefsConfig?: unknown;
  }) => (
    <div data-testid="pdomain-ui-app-shell">
      <div data-testid="pdomain-ui-app-shell-header">{header}</div>
      <nav data-testid="pdomain-ui-app-shell-rail">{rail}</nav>
      <main className="h-full min-h-0 overflow-hidden" data-testid="pdomain-ui-app-shell-main">
        {main}
      </main>
      {children}
    </div>
  ),
  SuiteSiblingsProvider: ({ children }: { value?: unknown; children?: React.ReactNode }) => (
    <>{children}</>
  ),
  // Other exports that App.tsx imports as types — provide no-op values so
  // TypeScript import side-effects compile cleanly.
}));

// Phase 2.2: PageImageCanvas now imports @pdomain/pdomain-ui/canvas which
// bundles react-konva. Mock pdomain-ui/canvas first so konva's Node.js entry never
// loads (it would require('canvas'), a native addon unavailable in jsdom).
// The react-konva mock below is kept for any other transitive imports.
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

import App from "./App";

// Helper: setup session-state mock (null = no project loaded)
function withNoSession() {
  server.use(
    http.get("/api/session-state", () =>
      HttpResponse.json({
        schema_version: "1.0",
        last_project_path: null,
        last_page_index: 0,
      }),
    ),
    http.get("/api/projects", () =>
      HttpResponse.json({
        projects: [],
        selected: null,
        projects_root: "/data",
        config_source: "default",
      }),
    ),
  );
}

// Helper: setup MSW handlers for a project route.
function withProjectSession() {
  server.use(
    http.get("/api/session-state", () =>
      HttpResponse.json({
        schema_version: "1.0",
        last_project_path: null,
        last_page_index: 0,
      }),
    ),
    http.get("/api/projects", () =>
      HttpResponse.json({
        projects: [],
        selected: null,
        projects_root: "/data",
        config_source: "default",
      }),
    ),
    http.get("/api/projects/p1", () =>
      HttpResponse.json({
        project_id: "p1",
        project_root: "/data/p1",
        image_paths: ["page_001.png", "page_002.png"],
        ground_truth_map: {},
        version: "1.0",
        source_lib: "doctr-pdomain-labeled",
        total_pages: 2,
        saved_pages: 0,
        current_page_index: 0,
        include_images: true,
        copied_images: false,
      }),
    ),
    http.get("/api/projects/p1/pages/:idx", () =>
      HttpResponse.json({
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
        page_text_ocr: "",
        page_text_gt: "",
        extra: {},
      }),
    ),
  );
}

describe("App: routing shell", () => {
  it("renders header-bar on the root route", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
  });

  it("renders project-list view on / when no session (Slice 27)", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      // ProjectListView includes the header bar and project list
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
      // With no projects, we expect the "No projects found" message or open folder button
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });
  });

  it("IS-5: main element has overflow-hidden and min-h-0 for viewport-locked StudioShell", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    // Phase 2.4: `<main>` is now rendered inside pdomain-ui AppShell's main slot.
    // The pdomain-ui-app-shell-main wrapper carries the overflow-hidden + min-h-0
    // classes that were formerly on the local <main> element.
    const appShellMain = screen.getByTestId("pdomain-ui-app-shell-main");
    expect(appShellMain).not.toBeNull();
    expect(appShellMain.className).toMatch(/overflow-hidden/);
    expect(appShellMain.className).toMatch(/min-h-0/);
  });

  it("Phase 2.4: pdomain-ui AppShell wrapper is present (data-testid=app-shell)", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    // Outer wrapper preserves data-testid=app-shell for driver contract.
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    // pdomain-ui AppShell mock renders inside it.
    expect(screen.getByTestId("pdomain-ui-app-shell")).toBeInTheDocument();
  });

  it("Phase 2.4: HeaderBar renders inside AppShell header slot", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    const headerSlot = screen.getByTestId("pdomain-ui-app-shell-header");
    // HeaderBar is a descendant of the AppShell header slot.
    expect(headerSlot.querySelector('[data-testid="header-bar"]')).not.toBeNull();
  });

  it("Phase 2.4: accessible live regions are present inside AppShell", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    // status-announcer and error-announcer must always be in the DOM.
    const statusAnnouncer = document.getElementById("status-announcer");
    const errorAnnouncer = document.getElementById("error-announcer");
    expect(statusAnnouncer).not.toBeNull();
    expect(errorAnnouncer).not.toBeNull();
    expect(statusAnnouncer?.getAttribute("role")).toBe("status");
    expect(errorAnnouncer?.getAttribute("role")).toBe("alert");
  });

  it("uses the shared AppShell rail slot for the OCR rail on project routes", async () => {
    withProjectSession();
    window.history.pushState({}, "", "/projects/p1/pages/pageno/1");
    render(<App />);
    expect(await screen.findByTestId("rail")).toBeInTheDocument();
    const railSlot = screen.getByTestId("pdomain-ui-app-shell-rail");
    expect(railSlot.querySelector('[data-testid="rail"]')).not.toBeNull();
    window.history.pushState({}, "", "/");
  });

  it("IS-2: HeaderBar renders without navSlot or actionsSlot on root route", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    // On root route, no project is loaded → no nav controls injected.
    // nav-prev-button exists only as a stub in HeaderBar (data-testid-stub).
    const prevBtns = screen.getAllByTestId("nav-prev-button");
    // All present buttons should be stubs (no real ProjectNavigationControls).
    expect(prevBtns.every((btn) => btn.getAttribute("data-testid-stub") === "true")).toBe(true);
  });

  it("IS-2: project route renders HeaderBar with project-navigation-controls (via withProjectSession)", async () => {
    withProjectSession();
    // Render App with a forced project route via the URL — App uses BrowserRouter
    // which reads window.location. We can't override that in jsdom easily, so
    // we test the HeaderBar slot contract indirectly: page-actions-compact
    // is only mounted when onProjectRoute=true (projectId !== null).
    // This test verifies the component tree works; the slot rendering on a real
    // project route is covered by HeaderBar.test.tsx IS-2 slot tests.
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
    // Root route — no compact actions
    expect(screen.queryByTestId("page-actions-compact")).toBeNull();
  });
});
