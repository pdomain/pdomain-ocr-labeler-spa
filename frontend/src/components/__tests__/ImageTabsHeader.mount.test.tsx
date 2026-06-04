// ImageTabsHeader.mount.test.tsx — Lane C / Task C1.
//
// Asserts that ProjectPage mounts the ImageTabsHeader viewport-chrome bar
// above the canvas, wired to the SAME useUiPrefs / viewport store the Rail
// uses (single source of truth). The header was fully built but never mounted
// (only commented out at ProjectPage.tsx:18) before this task.
//
// Acceptance (plan §Lane C / C1):
//   - layer-paragraphs-checkbox, selection-mode-word, erase-pixels-button,
//     legend-chip-line are all in the document.
//   - toggling layer-words-checkbox updates the words-layer visibility pref.
//
// react-konva / pdomain-ui canvas mocked module-wide (same pattern as
// ProjectPage.test.tsx) so the canvas tree renders as plain divs in jsdom.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

describe("ImageTabsHeader mount (Lane C / C1)", () => {
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

  it("mounts the viewport chrome controls above the canvas", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.getByTestId("image-tabs-header")).toBeInTheDocument();
    });
    expect(screen.getByTestId("layer-paragraphs-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("selection-mode-word")).toBeInTheDocument();
    expect(screen.getByTestId("erase-pixels-button")).toBeInTheDocument();
    expect(screen.getByTestId("legend-chip-line")).toBeInTheDocument();
  });

  it("toggling layer-words-checkbox updates the words-layer visibility pref", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    const wordsCb = await screen.findByTestId("layer-words-checkbox");
    expect(useUiPrefs.getState().layerVisibility.word).toBe(true);

    fireEvent.click(wordsCb);

    await waitFor(() => {
      expect(useUiPrefs.getState().layerVisibility.word).toBe(false);
    });
    // DOM assertion: the checkbox itself must reflect the updated state so that
    // a missing notifyUiPrefs() bridge (which prevents re-render) would fail here.
    await waitFor(() => {
      expect(wordsCb).not.toBeChecked();
    });
  });

  it("erase button reflects viewport-store erase mode (single source of truth)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    const eraseBtn = await screen.findByTestId("erase-pixels-button");
    expect(eraseBtn).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(eraseBtn);

    await waitFor(() => {
      expect(screen.getByTestId("erase-pixels-button")).toHaveAttribute("aria-pressed", "true");
    });
  });
});
