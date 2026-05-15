// HeaderBar.test.tsx — Vitest tests for HeaderBar + ProjectLoadControls.
// Spec: specs/22-page-surface-wireup.md §3, §6 (issue #309)
// Original: issue #272 (four required testids + disabled-state contract).
//
// HeaderBar now hosts three dialog-trigger icon buttons in addition to
// ProjectLoadControls. The triggers must:
//   - render with the spec testids
//   - call `dialogStore.open(...)` on click
//   - be disabled when no project is loaded (URL has no projectId or
//     the useProject query returns nothing) — except hotkey-help, which
//     stays enabled per spec §6 (no `disabled` attribute in the example).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import HeaderBar from "./HeaderBar";
import { dialogStore } from "../stores/dialog-store";

// --- helpers -----------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

interface RenderOpts {
  route?: string;
}

function renderHeaderBar({ route = "/" }: RenderOpts = {}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <HeaderBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  dialogStore.reset();
});

// --- existing contract: project-load controls --------------------------------

describe("HeaderBar: renders_with_testids", () => {
  it("renders project-load controls + three dialog-trigger buttons", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
    );

    renderHeaderBar();

    await waitFor(() => {
      expect(screen.getByTestId("project-select")).toBeInTheDocument();
    });

    expect(screen.getByTestId("load-project-button")).toBeInTheDocument();
    expect(screen.getByTestId("source-folder-button")).toBeInTheDocument();
    expect(screen.getByTestId("ocr-config-trigger-button")).toBeInTheDocument();
    expect(screen.getByTestId("export-trigger-button")).toBeInTheDocument();
    expect(screen.getByTestId("hotkey-help-trigger-button")).toBeInTheDocument();
  });
});

describe("HeaderBar: load_disabled_before_selection", () => {
  it("load-project-button is disabled when no project is selected", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "proj-1", project_root: "/data/proj1", label: "Project One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );

    renderHeaderBar();

    await waitFor(() => {
      expect(screen.getByTestId("load-project-button")).toBeInTheDocument();
    });

    const loadBtn = screen.getByTestId("load-project-button");
    expect(loadBtn).toBeDisabled();
  });
});

describe("HeaderBar: load_enabled_after_selection", () => {
  it("load-project-button is enabled after a project is selected", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "proj-1", project_root: "/data/proj1", label: "Project One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );

    renderHeaderBar();

    await waitFor(() => {
      const select = screen.getByTestId("project-select") as HTMLSelectElement;
      expect(select.options.length).toBeGreaterThan(1);
    });

    const loadBtn = screen.getByTestId("load-project-button");
    expect(loadBtn).toBeDisabled();

    const select = screen.getByTestId("project-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "proj-1" } });

    await waitFor(() => {
      expect(screen.getByTestId("load-project-button")).not.toBeDisabled();
    });
  });
});

describe("HeaderBar: empty project list", () => {
  it("shows placeholder when project list is empty and keeps LOAD disabled", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
    );

    renderHeaderBar();

    await waitFor(() => {
      expect(screen.getByTestId("project-select")).toBeInTheDocument();
    });

    const select = screen.getByTestId("project-select");
    expect(select).toHaveTextContent("No projects found");

    const loadBtn = screen.getByTestId("load-project-button");
    expect(loadBtn).toBeDisabled();
  });
});

// --- new in #309: dialog trigger buttons -------------------------------------

describe("HeaderBar: dialog triggers (spec 22 §6)", () => {
  function withEmptyProjects() {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
    );
  }

  it("clicking ocr-config-trigger-button opens ocrConfig in the store", async () => {
    withEmptyProjects();
    // Route includes projectId so the buttons are enabled.
    // GET /api/projects/{id} returns flat Project (not LoadProjectResponse wrapper).
    server.use(
      http.get("/api/projects/proj-1", () =>
        HttpResponse.json({
          project_id: "proj-1",
          project_root: "/data/proj1",
          image_paths: [],
          ground_truth_map: {},
          version: "1.0",
          source_lib: "doctr-pd-labeled",
          total_pages: 0,
          saved_pages: 0,
          current_page_index: 0,
          include_images: true,
          copied_images: false,
        }),
      ),
    );

    renderHeaderBar({ route: "/projects/proj-1/pages/pageno/1" });

    const btn = await screen.findByTestId("ocr-config-trigger-button");
    await waitFor(() => expect(btn).not.toBeDisabled());

    fireEvent.click(btn);
    expect(dialogStore.getState().ocrConfig.open).toBe(true);
  });

  it("clicking export-trigger-button opens export in the store", async () => {
    withEmptyProjects();
    server.use(
      http.get("/api/projects/proj-1", () =>
        HttpResponse.json({
          project_id: "proj-1",
          project_root: "/data/proj1",
          image_paths: [],
          ground_truth_map: {},
          version: "1.0",
          source_lib: "doctr-pd-labeled",
          total_pages: 0,
          saved_pages: 0,
          current_page_index: 0,
          include_images: true,
          copied_images: false,
        }),
      ),
    );

    renderHeaderBar({ route: "/projects/proj-1/pages/pageno/1" });

    const btn = await screen.findByTestId("export-trigger-button");
    await waitFor(() => expect(btn).not.toBeDisabled());

    fireEvent.click(btn);
    expect(dialogStore.getState().export.open).toBe(true);
  });

  it("clicking hotkey-help-trigger-button opens hotkeyHelp in the store", async () => {
    withEmptyProjects();

    renderHeaderBar({ route: "/" });

    const btn = await screen.findByTestId("hotkey-help-trigger-button");
    // Hotkey help is always enabled (spec §6 — no `disabled` attribute).
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);
    expect(dialogStore.getState().hotkeyHelp.open).toBe(true);
  });

  it("ocr-config and export triggers are disabled on the root route (no project loaded)", async () => {
    withEmptyProjects();

    renderHeaderBar({ route: "/" });

    const ocrConfig = await screen.findByTestId("ocr-config-trigger-button");
    const exportBtn = await screen.findByTestId("export-trigger-button");

    expect(ocrConfig).toBeDisabled();
    expect(exportBtn).toBeDisabled();
  });

  it("ocr-config and export triggers are disabled while useProject is loading", async () => {
    withEmptyProjects();
    // Never resolves — keeps useProject in pending state.
    server.use(
      http.get("/api/projects/slow-proj", async () => {
        await new Promise(() => {});
        return HttpResponse.json({});
      }),
    );

    renderHeaderBar({ route: "/projects/slow-proj/pages/pageno/1" });

    const ocrConfig = await screen.findByTestId("ocr-config-trigger-button");
    expect(ocrConfig).toBeDisabled();
  });
});
