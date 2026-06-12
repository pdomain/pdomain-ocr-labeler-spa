// ProjectPage.undo.test.tsx — page-level undo/redo wiring (slice H-C/H-D).
//
// Spec: docs/specs/2026-06-12-event-store-undo.md
//   U-1/U-2: Mod+Z / Mod+Shift+Z dispatch the undo/redo mutations.
//   U-3: hotkeys gated on history availability.
//   U-7: "Reload" confirm copy no longer claims to discard unsaved edits.
//   U-10: Mod+Z with focus in a text field does NOT fire page undo.
//
// Mock setup mirrors ProjectPage.test.tsx (kept in a separate file so the
// undo slice does not collide with parallel work in the main test file).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

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
  rectItemsToDisplay: <T,>(items: T[]) => items,
  RectOverlayLayer: ({ layer }: { layer: string }) => <div data-testid={`bbox-overlay-${layer}`} />,
  PageImageCanvas: () => <div data-testid="image-viewport" />,
}));
vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div />,
  Image: () => <div />,
}));
vi.mock("use-image", () => ({ __esModule: true, default: () => [null, "loaded"] }));

import ProjectPage from "./ProjectPage";

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

function pageFixture(history: { undo_available: boolean; redo_available: boolean } | null) {
  return {
    project_id: "p1",
    page_index: 0,
    page_record: null,
    line_matches: [],
    selection: {
      selection_mode: "paragraph",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    },
    encoded_dims: null,
    line_filter: "all",
    image_url: "/api/projects/p1/pages/0/image",
    generation: 1,
    page_text_ocr: "",
    page_text_gt: "",
    history: history === null ? null : { ...history, cursor: 1, depth: 50 },
    extra: {},
  };
}

function stubBackend(history: { undo_available: boolean; redo_available: boolean } | null) {
  server.use(
    http.get("/api/projects/p1", () => HttpResponse.json(projectFixture())),
    http.get("/api/projects/p1/pages/0", () => HttpResponse.json(pageFixture(history))),
    http.post("/api/projects/p1/current-page-index", () => HttpResponse.json({})),
  );
}

beforeEach(() => {
  dialogStore.reset();
});

describe("ProjectPage: Mod+Z / Mod+Shift+Z dispatch undo/redo (H-C)", () => {
  it("Ctrl+Z POSTs /undo when history.undo_available", async () => {
    stubBackend({ undo_available: true, redo_available: false });
    const undoSpy = vi.fn(() =>
      HttpResponse.json(pageFixture({ undo_available: false, redo_available: true })),
    );
    server.use(http.post("/api/projects/p1/pages/0/undo", undoSpy));

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).not.toBeDisabled();
    });

    fireEvent.keyDown(document, { key: "z", ctrlKey: true, bubbles: true });
    await waitFor(() => {
      expect(undoSpy).toHaveBeenCalled();
    });
  });

  it("Ctrl+Z does NOT POST /undo when undo is unavailable (U-3)", async () => {
    stubBackend({ undo_available: false, redo_available: false });
    const undoSpy = vi.fn(() => HttpResponse.json(pageFixture(null)));
    server.use(http.post("/api/projects/p1/pages/0/undo", undoSpy));

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).toBeDisabled();
    });

    fireEvent.keyDown(document, { key: "z", ctrlKey: true, bubbles: true });
    // Give the (would-be) mutation a tick to fire.
    await new Promise((r) => setTimeout(r, 50));
    expect(undoSpy).not.toHaveBeenCalled();
  });

  it("Ctrl+Shift+Z POSTs /redo when history.redo_available", async () => {
    stubBackend({ undo_available: false, redo_available: true });
    const redoSpy = vi.fn(() =>
      HttpResponse.json(pageFixture({ undo_available: true, redo_available: false })),
    );
    server.use(http.post("/api/projects/p1/pages/0/redo", redoSpy));

    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.getByTestId("redo-button")).not.toBeDisabled();
    });

    fireEvent.keyDown(document, { key: "Z", ctrlKey: true, shiftKey: true, bubbles: true });
    await waitFor(() => {
      expect(redoSpy).toHaveBeenCalled();
    });
  });

  it("U-10: Ctrl+Z with focus in a text input does NOT fire page undo", async () => {
    stubBackend({ undo_available: true, redo_available: false });
    const undoSpy = vi.fn(() => HttpResponse.json(pageFixture(null)));
    server.use(http.post("/api/projects/p1/pages/0/undo", undoSpy));

    const page = renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).not.toBeDisabled();
    });

    // Inject a text input (stands in for any GT input) and focus it.
    const input = document.createElement("input");
    input.setAttribute("data-testid", "synthetic-gt-input");
    page.container.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: "z", ctrlKey: true, bubbles: true });
    await new Promise((r) => setTimeout(r, 50));
    expect(undoSpy).not.toHaveBeenCalled();
  });
});

describe("ProjectPage: Reload confirm copy (U-7)", () => {
  it("load-page confirm no longer claims unsaved edits; still gates the POST", async () => {
    stubBackend(null);
    const loadSpy = vi.fn(() => HttpResponse.json(pageFixture(null)));
    server.use(http.post("/api/projects/p1/pages/0/load", loadSpy));

    renderProjectPage();
    await screen.findByTestId("project-page");

    fireEvent.keyDown(document, { key: "l", ctrlKey: true, bubbles: true });
    await waitFor(() => {
      expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
    });
    const dialogText = screen.getByTestId("confirm-dialog").textContent ?? "";
    expect(dialogText).not.toMatch(/unsaved|discard/i);
    expect(dialogText).toMatch(/reload/i);

    expect(loadSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("confirm-dialog-confirm"));
    await waitFor(() => {
      expect(loadSpy).toHaveBeenCalled();
    });
  });
});

describe("ProjectPage: Reload-OCR confirm warns history resets (U-6/H-D)", () => {
  it("Mod+R opens a confirm whose copy mentions edit history; POST only on confirm", async () => {
    stubBackend(null);
    const reloadSpy = vi.fn(() => HttpResponse.json({ job_id: "j1" }, { status: 202 }));
    server.use(http.post("/api/projects/p1/pages/0/reload-ocr", reloadSpy));

    renderProjectPage();
    await screen.findByTestId("project-page");

    fireEvent.keyDown(document, { key: "r", ctrlKey: true, bubbles: true });
    await waitFor(() => {
      expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
    });
    const dialogText = screen.getByTestId("confirm-dialog").textContent ?? "";
    expect(dialogText).toMatch(/history/i);
    expect(reloadSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("confirm-dialog-confirm"));
    await waitFor(() => {
      expect(reloadSpy).toHaveBeenCalled();
    });
  });
});
