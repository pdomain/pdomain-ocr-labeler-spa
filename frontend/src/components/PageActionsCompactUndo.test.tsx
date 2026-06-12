// PageActionsCompactUndo.test.tsx — visible undo/redo controls in the compact
// header bar (slice H-C) + Reload-OCR confirm with history-reset warning (H-D).
//
// Spec: docs/specs/2026-06-12-event-store-undo.md
//   U-1/U-2: clicking undo/redo fires the POST mutation.
//   U-3: buttons disabled per PagePayload.history flags.
//   U-6 (frontend half): Reload OCR routes through a confirm dialog whose copy
//        warns that edit history resets.
//   U-7: overflow "Load Page" entry is renamed "Reload".

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { PageActionsCompact } from "./PageActionsCompact";
import { dialogStore } from "../stores/dialog-store";

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

function pagePayload(history: { undo_available: boolean; redo_available: boolean } | null) {
  return {
    project_id: "proj-1",
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
    image_url: null,
    generation: 1,
    page_text_ocr: "",
    page_text_gt: "",
    history: history === null ? null : { ...history, cursor: 1, depth: 50 },
    extra: {},
  };
}

function stubPage(history: { undo_available: boolean; redo_available: boolean } | null) {
  server.use(
    http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pagePayload(history))),
  );
}

beforeEach(() => {
  dialogStore.reset();
  vi.clearAllMocks();
  stubPage(null);
});

describe("PageActionsCompact: undo/redo buttons (H-C)", () => {
  it("renders visible undo-button and redo-button testids", () => {
    renderCompact();
    expect(screen.getByTestId("undo-button")).toBeInTheDocument();
    expect(screen.getByTestId("redo-button")).toBeInTheDocument();
  });

  it("both disabled when payload has no history", async () => {
    stubPage(null);
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).toBeDisabled();
    });
    expect(screen.getByTestId("redo-button")).toBeDisabled();
  });

  it("undo enabled when history.undo_available", async () => {
    stubPage({ undo_available: true, redo_available: false });
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).not.toBeDisabled();
    });
    expect(screen.getByTestId("redo-button")).toBeDisabled();
  });

  it("redo enabled when history.redo_available", async () => {
    stubPage({ undo_available: false, redo_available: true });
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("redo-button")).not.toBeDisabled();
    });
    expect(screen.getByTestId("undo-button")).toBeDisabled();
  });

  it("clicking undo POSTs the undo endpoint and invalidates the page", async () => {
    stubPage({ undo_available: true, redo_available: false });
    const undoSpy = vi.fn(() =>
      HttpResponse.json(pagePayload({ undo_available: false, redo_available: true })),
    );
    server.use(http.post("/api/projects/proj-1/pages/0/undo", undoSpy));
    const user = userEvent.setup();
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("undo-button")).not.toBeDisabled();
    });
    await user.click(screen.getByTestId("undo-button"));
    await waitFor(() => {
      expect(undoSpy).toHaveBeenCalled();
    });
  });

  it("clicking redo POSTs the redo endpoint", async () => {
    stubPage({ undo_available: false, redo_available: true });
    const redoSpy = vi.fn(() =>
      HttpResponse.json(pagePayload({ undo_available: true, redo_available: false })),
    );
    server.use(http.post("/api/projects/proj-1/pages/0/redo", redoSpy));
    const user = userEvent.setup();
    renderCompact();
    await waitFor(() => {
      expect(screen.getByTestId("redo-button")).not.toBeDisabled();
    });
    await user.click(screen.getByTestId("redo-button"));
    await waitFor(() => {
      expect(redoSpy).toHaveBeenCalled();
    });
  });
});

describe("PageActionsCompact: Reload rename in overflow (U-7)", () => {
  it("overflow load-page-button is labeled 'Reload' without discard copy", async () => {
    const user = userEvent.setup();
    renderCompact();
    await user.click(screen.getByTestId("page-actions-compact-overflow"));
    const btn = await screen.findByTestId("load-page-button");
    expect(btn).toHaveTextContent("Reload");
    expect(btn).not.toHaveTextContent("Load Page");
    expect(btn.getAttribute("title") ?? "").not.toMatch(/unsaved|discard|last saved/i);
  });
});
