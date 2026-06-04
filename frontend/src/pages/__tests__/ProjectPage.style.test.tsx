// ProjectPage.style.test.tsx — Lane B / Task B2.
//
// Verifies the Apply-Style / Clear-Style / Component / Add-Word controls fire
// real mutations:
//   (a) apply-style-button POSTs .../words/{li}/{wi}/style with style + scope
//   (b) clear-style-button clears the style on the selected word(s)
//   (c) apply-component-button POSTs .../words/{li}/{wi}/component (enabled)
//   (d) clear-component-button POSTs the same with enabled:false
//   (e) drawing a box in add-word mode POSTs .../words/add
//
// The PageImageCanvas mock exposes a `canvas-add-word-trigger` button that
// invokes the `onAddWord` prop with a fixed rect so the add-word draw can be
// simulated under jsdom (Konva pointer events are not available).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../../test/server";
import { ROUTES } from "../../lib/routes";
import { dialogStore } from "../../stores/dialog-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { selectionStore, clearSelection, selectWord } from "../../stores/selection-store";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// Prevent konva's Node entry (requires the native `canvas` addon) from
// loading via any transitive import.
vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (b: unknown) => b,
  rectItemsToDisplay: (items: unknown) => items,
  RectOverlayLayer: () => null,
  PageImageCanvas: () => null,
}));
vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => null,
  Image: () => null,
}));
vi.mock("use-image", () => ({ __esModule: true, default: () => [null, "loaded"] }));

// Canvas mock: render an add-word trigger that calls the real `onAddWord`
// prop so the parent's add-word mutation wiring is exercised end-to-end.
vi.mock("../../components/PageImageCanvas", () => ({
  __esModule: true,
  default: ({
    onAddWord,
  }: {
    onAddWord?: (rect: { x: number; y: number; width: number; height: number }) => void;
  }) => (
    <div data-testid="image-viewport">
      <button
        data-testid="canvas-add-word-trigger"
        onClick={() => onAddWord?.({ x: 5, y: 6, width: 30, height: 12 })}
      >
        draw
      </button>
    </div>
  ),
}));

import ProjectPage from "../ProjectPage";

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

function projectFixture() {
  return {
    project: {
      project_id: "p1",
      project_root: "/data/p1",
      image_paths: ["page_001.png"],
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
      selection_mode: "word",
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

describe("ProjectPage — style / component / add-word wiring (Lane B / B2)", () => {
  beforeEach(() => {
    dialogStore.reset();
    mockNavigate.mockReset();
    clearSelection();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true, selectionMode: "word" });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  it("apply-style-button POSTs the chosen style + scope to the selected word", async () => {
    const calls: { url: string; body: Record<string, unknown> }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/style", async ({ request }) => {
        calls.push({
          url: request.url,
          body: (await request.json()) as Record<string, unknown>,
        });
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("apply-style-select");
    selectWord(0, 0);
    await waitFor(() => {
      expect(selectionStore.getState().selectedWords).toEqual([[0, 0]]);
    });

    // Q-B2-STYLE-LABELS: the canonical book-tools label is the plural "italics".
    fireEvent.change(screen.getByTestId("apply-style-select"), { target: { value: "italics" } });
    fireEvent.change(screen.getByTestId("scope-select"), { target: { value: "whole" } });
    fireEvent.click(screen.getByTestId("apply-style-button"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    expect(calls[0].url).toContain("/words/0/0/style");
    expect(calls[0].body).toEqual(expect.objectContaining({ style: "italics", scope: "whole" }));
  });

  it("clear-style-button clears the style on the selected word", async () => {
    const calls: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/style", async ({ request }) => {
        calls.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("clear-style-button");
    selectWord(0, 0);
    await waitFor(() => {
      expect(selectionStore.getState().selectedWords).toEqual([[0, 0]]);
    });

    fireEvent.click(screen.getByTestId("clear-style-button"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    // Clearing maps to applying the "regular" style (book-tools discards it).
    expect(calls[0]).toEqual(expect.objectContaining({ style: "regular" }));
  });

  it("apply-component-button POSTs component with enabled:true", async () => {
    const calls: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/component", async ({ request }) => {
        calls.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("apply-component-select");
    selectWord(0, 0);
    await waitFor(() => {
      expect(selectionStore.getState().selectedWords).toEqual([[0, 0]]);
    });

    fireEvent.change(screen.getByTestId("apply-component-select"), {
      target: { value: "footnote_marker" },
    });
    fireEvent.click(screen.getByTestId("apply-component-button"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    expect(calls[0]).toEqual(
      expect.objectContaining({ component: "footnote_marker", enabled: true }),
    );
  });

  it("clear-component-button POSTs component with enabled:false", async () => {
    const calls: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/component", async ({ request }) => {
        calls.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    await screen.findByTestId("clear-component-button");
    selectWord(0, 0);
    await waitFor(() => {
      expect(selectionStore.getState().selectedWords).toEqual([[0, 0]]);
    });

    fireEvent.change(screen.getByTestId("apply-component-select"), {
      target: { value: "footnote_marker" },
    });
    fireEvent.click(screen.getByTestId("clear-component-button"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    expect(calls[0]).toEqual(
      expect.objectContaining({ component: "footnote_marker", enabled: false }),
    );
  });

  it("drawing a box in add-word mode POSTs .../words/add", async () => {
    const calls: { url: string; body: Record<string, unknown> }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/add", async ({ request }) => {
        calls.push({
          url: request.url,
          body: (await request.json()) as Record<string, unknown>,
        });
        return HttpResponse.json(pageFixture());
      }),
    );

    renderProjectPage();
    // Enter add-word mode via the grid toggle.
    const toggle = await screen.findByTestId("word-add-button");
    fireEvent.click(toggle);

    // Simulate the canvas emitting a completed draw rect.
    fireEvent.click(screen.getByTestId("canvas-add-word-trigger"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    expect(calls[0].url).toContain("/words/add");
    expect(calls[0].body).toHaveProperty("bbox");
  });
});
