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
import userEvent from "@testing-library/user-event";
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

// --- #326: breadcrumb mode on project routes ------------------------------------

describe("HeaderBar: #326 — project breadcrumb on project routes", () => {
  it("shows project-breadcrumb when project data is loaded", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
      http.get("/api/projects/proj-1", () =>
        HttpResponse.json({
          project_id: "proj-1",
          project_root: "/data/proj-1",
          image_paths: [],
          ground_truth_map: {},
          version: "1.0",
          source_lib: "doctr-pd-labeled",
          total_pages: 5,
          saved_pages: 2,
          current_page_index: 0,
          include_images: true,
          copied_images: false,
        }),
      ),
    );

    renderHeaderBar({ route: "/projects/proj-1/pages/pageno/1" });

    // Breadcrumb appears once project query resolves.
    await waitFor(() => {
      expect(screen.getByTestId("project-breadcrumb")).toBeInTheDocument();
    });

    // Shows the last segment of project_root as the label.
    expect(screen.getByTestId("project-breadcrumb")).toHaveTextContent("proj-1");

    // change-project-button is present.
    expect(screen.getByTestId("change-project-button")).toBeInTheDocument();

    // Driver-contract testids remain in the DOM (sr-only hidden).
    expect(screen.getByTestId("project-select")).toBeInTheDocument();
    expect(screen.getByTestId("load-project-button")).toBeInTheDocument();
  });

  it("does not show breadcrumb on root route (no project)", async () => {
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

    renderHeaderBar({ route: "/" });

    await screen.findByTestId("header-bar");

    expect(screen.queryByTestId("project-breadcrumb")).not.toBeInTheDocument();
    // Select should be visible on root route.
    expect(screen.getByTestId("project-select")).toBeInTheDocument();
  });
});

// --- P1.a Gap 3: Projects / <name> breadcrumb prefix --------------------------

describe("HeaderBar: P1.a — breadcrumb shows 'Projects / <name>'", () => {
  it("project-breadcrumb contains 'Projects' prefix and project name", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
      http.get("/api/projects/proj-1", () =>
        HttpResponse.json({
          project_id: "proj-1",
          project_root: "/data/my-project",
          image_paths: ["p1.png"],
          ground_truth_map: {},
          version: "1.0",
          source_lib: "doctr-pd-labeled",
          total_pages: 1,
          saved_pages: 0,
          current_page_index: 0,
          include_images: true,
          copied_images: false,
        }),
      ),
    );

    renderHeaderBar({ route: "/projects/proj-1/pages/pageno/1" });

    await waitFor(() => {
      expect(screen.getByTestId("project-breadcrumb")).toBeInTheDocument();
    });

    const crumb = screen.getByTestId("project-breadcrumb");
    expect(crumb).toHaveTextContent("Projects");
    expect(crumb).toHaveTextContent("my-project");
  });
});

// --- P1.a Gap 5: MetricsStrip -------------------------------------------------

describe("HeaderBar: P1.a — MetricsStrip (Gap 5)", () => {
  it("metrics-strip appears when on a page route with line_matches", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "",
          config_source: "default",
        }),
      ),
      http.get("/api/projects/proj-1", () =>
        HttpResponse.json({
          project_id: "proj-1",
          project_root: "/data/proj-1",
          image_paths: ["p1.png"],
          ground_truth_map: {},
          version: "1.0",
          source_lib: "doctr-pd-labeled",
          total_pages: 1,
          saved_pages: 0,
          current_page_index: 0,
          include_images: true,
          copied_images: false,
        }),
      ),
      http.get("/api/projects/proj-1/pages/0", () =>
        HttpResponse.json({
          project_id: "proj-1",
          page_index: 0,
          line_filter: "all",
          generation: 1,
          line_matches: [
            {
              line_index: 0,
              paragraph_index: 0,
              ocr_line_text: "hello world",
              ground_truth_line_text: "hello world",
              word_matches: [],
              overall_match_status: "exact",
              exact_count: 2,
              fuzzy_count: 1,
              mismatch_count: 0,
              unmatched_gt_count: 0,
              unmatched_ocr_count: 0,
              validated_word_count: 1,
              total_word_count: 3,
              is_fully_validated: false,
            },
          ],
        }),
      ),
    );

    renderHeaderBar({ route: "/projects/proj-1/pages/pageno/1" });

    await waitFor(() => {
      expect(screen.getByTestId("metrics-strip")).toBeInTheDocument();
    });

    const strip = screen.getByTestId("metrics-strip");
    // aria-label aggregates all counts
    expect(strip.getAttribute("aria-label")).toMatch(/3 words/);
    expect(strip.getAttribute("aria-label")).toMatch(/2 exact/);
    expect(strip.getAttribute("aria-label")).toMatch(/1 fuzzy/);
    expect(strip.getAttribute("aria-label")).toMatch(/0 mismatched/);
    expect(strip.getAttribute("aria-label")).toMatch(/1 of 3 validated/);
  });

  it("metrics-strip is absent on root route (no page)", async () => {
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
    renderHeaderBar({ route: "/" });
    await screen.findByTestId("header-bar");
    expect(screen.queryByTestId("metrics-strip")).not.toBeInTheDocument();
  });
});

// --- IS-2: navSlot + actionsSlot props ----------------------------------------

describe("HeaderBar: IS-2 — navSlot and actionsSlot (integration slots)", () => {
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

  it("renders navSlot content when provided", async () => {
    withEmptyProjects();
    const qc = makeQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <HeaderBar navSlot={<span data-testid="nav-slot-content">Nav</span>} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByTestId("header-bar");
    expect(screen.getByTestId("nav-slot-content")).toBeInTheDocument();
  });

  it("does not render navSlot content when navSlot is not provided", async () => {
    withEmptyProjects();
    renderHeaderBar();
    await screen.findByTestId("header-bar");
    expect(screen.queryByTestId("nav-slot-content")).toBeNull();
  });

  it("renders actionsSlot content when provided", async () => {
    withEmptyProjects();
    const qc = makeQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <HeaderBar actionsSlot={<span data-testid="actions-slot-content">Actions</span>} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByTestId("header-bar");
    expect(screen.getByTestId("actions-slot-content")).toBeInTheDocument();
  });

  it("does not render actionsSlot content when actionsSlot is not provided", async () => {
    withEmptyProjects();
    renderHeaderBar();
    await screen.findByTestId("header-bar");
    expect(screen.queryByTestId("actions-slot-content")).toBeNull();
  });
});

// --- Slice 9: 40px top chrome ------------------------------------------------

describe("HeaderBar: Slice 9 — 40px chrome evolution", () => {
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

  it("header root has h-14 height class (56px — Gap 1)", async () => {
    withEmptyProjects();
    renderHeaderBar();
    const header = await screen.findByTestId("header-bar");
    expect(header.className).toMatch(/h-14/);
  });

  it("renders logo testid", async () => {
    withEmptyProjects();
    renderHeaderBar();
    await screen.findByTestId("header-bar");
    expect(screen.getByTestId("header-logo")).toBeInTheDocument();
  });

  it("logo click navigates to root route", async () => {
    withEmptyProjects();
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    const logo = await screen.findByTestId("header-logo");
    expect(logo.tagName.toLowerCase()).toBe("a");
    expect(logo).toHaveAttribute("href", "/");
  });

  it("renders user-menu trigger button", async () => {
    withEmptyProjects();
    renderHeaderBar();
    await screen.findByTestId("header-bar");
    expect(screen.getByTestId("user-menu-trigger")).toBeInTheDocument();
  });

  it("user menu opens on click and shows theme + sign-out items", async () => {
    withEmptyProjects();
    renderHeaderBar();
    const trigger = await screen.findByTestId("user-menu-trigger");
    // Radix DropdownMenu requires userEvent (pointer events) to open
    await userEvent.click(trigger);
    await waitFor(() => {
      expect(screen.getByTestId("user-menu-theme-item")).toBeInTheDocument();
      expect(screen.getByTestId("user-menu-signout-item")).toBeInTheDocument();
    });
  });
});
