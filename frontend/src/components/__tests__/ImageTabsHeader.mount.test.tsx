// ImageTabsHeader.mount.test.tsx — Lane C / Task C1.
//
// Asserts that ProjectPage no longer mounts the ImageTabsHeader viewport-chrome
// bar above the canvas.
//
// react-konva / pdomain-ui canvas mocked module-wide (same pattern as
// ProjectPage.test.tsx) so the canvas tree renders as plain divs in jsdom.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../../test/server";
import { ROUTES } from "../../lib/routes";
import { dialogStore } from "../../stores/dialog-store";
import { useUiPrefs } from "../../stores/ui-prefs";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (b: { x: number; y: number; width: number; height: number }) => b,
  rectItemsToDisplay: <T,>(items: T[]) => items,
  RectOverlayLayer: () => <div data-testid="bbox-overlay" />,
  PageImageCanvas: () => <div data-testid="image-viewport" tabIndex={0} />,
}));
vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div />,
  Image: () => <div />,
}));
vi.mock("use-image", () => ({ __esModule: true, default: () => [null, "loaded"] }));

import ProjectPage from "../../pages/ProjectPage";

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

describe("ImageTabsHeader ProjectPage mount", () => {
  beforeEach(() => {
    dialogStore.reset();
    mockNavigate.mockReset();
    // Reset layer visibility prefs to defaults between tests.
    useUiPrefs.setState({
      drawerOpen: true,
      rightPanelOpen: true,
      layerVisibility: { block: true, paragraph: true, line: true, word: true },
      selectionMode: "paragraph",
    });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
    );
  });

  it("does not mount the duplicate viewport chrome controls above the canvas", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    expect(screen.queryByTestId("image-tabs-header")).toBeNull();
    expect(screen.queryByTestId("selection-mode-word")).toBeNull();
  });
});
