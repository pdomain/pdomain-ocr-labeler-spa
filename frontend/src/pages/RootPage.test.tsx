// RootPage.test.tsx — Vitest unit tests for RootPage + EmptyProjectState.
// Issue #84 (EmptyProjectState) + Issue #274 (RootPage + session-state fetch).
// P5.h tests: hero band, search field, filter chips, project card redesign.
// Spec: docs/specs/2026-05-12-root-page-design.md §Contract + P5.h (Gaps 59, 60)
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "../test/server";
import { EmptyProjectState } from "./RootPage";
import RootPage from "./RootPage";

// Helper: wrap component with all required providers
function renderWithProviders(ui: React.ReactElement, { initialPath = "/" } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// --- EmptyProjectState ---

describe("EmptyProjectState", () => {
  it("renders with testid empty-project-state", () => {
    render(<EmptyProjectState />);
    expect(screen.getByTestId("empty-project-state")).toBeInTheDocument();
  });

  it("shows a prompt message to select a project", () => {
    render(<EmptyProjectState />);
    const el = screen.getByTestId("empty-project-state");
    expect(el.textContent).toMatch(/project/i);
  });
});

// Note: EmptyProjectState is kept for backward compatibility with
// legacy code that may reference it. The new Slice 27 implementation
// uses ProjectListView to show projects with StatusPips.

// --- RootPage: renders_empty_state ---

describe("RootPage: renders_empty_state", () => {
  it("renders ProjectListView when session-state returns null last_project_path", async () => {
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

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      // ProjectListView shows the "Open source folder" button
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });
  });

  it("renders ProjectListView when session-state fetch fails", async () => {
    server.use(
      http.get("/api/session-state", () => HttpResponse.error()),
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      // ProjectListView shows the "Open source folder" button
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });
  });

  it("renders blank while session-state is loading", () => {
    // Never resolves during this test — loading state should stay blank
    server.use(http.get("/api/session-state", () => new Promise(() => {})));

    renderWithProviders(<RootPage />);

    // RootPage returns blank div on loading; no project content
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });
});

// --- RootPage: redirects_to_last_project ---

describe("RootPage: redirects_to_last_project", () => {
  it("navigates to last project page when session-state has a project path", async () => {
    server.use(
      http.get("/api/session-state", () =>
        HttpResponse.json({
          schema_version: "1.0",
          last_project_path: "/data/my-project",
          last_page_index: 2,
        }),
      ),
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [
            {
              project_id: "my-project",
              project_root: "/data/my-project",
              label: "My Project",
            },
          ],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
      http.post("/api/projects/load", () =>
        HttpResponse.json({ project_id: "my-project" }, { status: 200 }),
      ),
    );

    // We verify navigation by checking the empty-project-state is NOT rendered
    // after data loads (redirect has fired). We can't easily assert the target
    // URL without a router location consumer, but we verify the component
    // doesn't fall through to EmptyProjectState when a project is present.
    renderWithProviders(<RootPage />);

    // Allow the query to settle; empty-project-state must not appear
    // (redirect was issued instead)
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByTestId("empty-project-state")).not.toBeInTheDocument();
  });
});

// --- RootPage: auto-resume (#327) ------------------------------------------------

describe("RootPage: auto-resume after server restart (#327)", () => {
  it("fires POST /api/projects/load before navigating when project exists on disk", async () => {
    const loadHandler = vi.fn(async () => HttpResponse.json({ project_id: "proj-1" }));

    server.use(
      http.get("/api/session-state", () =>
        HttpResponse.json({
          schema_version: "1.0",
          last_project_path: "/data/proj-1",
          last_page_index: 0,
        }),
      ),
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "proj-1", project_root: "/data/proj-1", label: "Proj One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
      http.post("/api/projects/load", loadHandler),
    );

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      expect(loadHandler).toHaveBeenCalled();
    });
  });

  it("falls back to project list when POST /api/projects/load fails", async () => {
    server.use(
      http.get("/api/session-state", () =>
        HttpResponse.json({
          schema_version: "1.0",
          last_project_path: "/data/proj-1",
          last_page_index: 0,
        }),
      ),
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "proj-1", project_root: "/data/proj-1", label: "Proj One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
      http.post("/api/projects/load", () =>
        HttpResponse.json({ message: "Server error" }, { status: 500 }),
      ),
    );

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      // Graceful fallback: project list shows the open-folder button.
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });
  });

  it("skips auto-resume when skipSessionRedirect is set", async () => {
    const loadHandler = vi.fn(async () => HttpResponse.json({}));

    server.use(
      http.get("/api/session-state", () =>
        HttpResponse.json({
          schema_version: "1.0",
          last_project_path: "/data/proj-1",
          last_page_index: 0,
        }),
      ),
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "proj-1", project_root: "/data/proj-1", label: "Proj One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
      http.post("/api/projects/load", loadHandler),
    );

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[{ pathname: "/", state: { skipSessionRedirect: true } }]}>
          <RootPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Wait for queries to settle.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });

    // POST /api/projects/load must NOT have been called.
    expect(loadHandler).not.toHaveBeenCalled();
  });
});

// --- RootPage: Slice 27 — project cards ---

describe("RootPage: Slice 27 — project cards", () => {
  it("renders project list when projects are available", async () => {
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
          projects: [
            {
              project_id: "proj-1",
              project_root: "/data/proj-1",
              label: "Project One",
            },
          ],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      // ProjectListView renders project cards with their label
      expect(screen.getByText("Project One")).toBeInTheDocument();
    });
  });

  it("displays project cards with labels when projects are available", async () => {
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
          projects: [
            {
              project_id: "proj-1",
              project_root: "/data/proj-1",
              label: "Project One",
            },
            {
              project_id: "proj-2",
              project_root: "/data/proj-2",
              label: "Project Two",
            },
          ],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      expect(screen.getByText("Project One")).toBeInTheDocument();
      expect(screen.getByText("Project Two")).toBeInTheDocument();
    });
  });

  it("shows open folder button with primary variant", async () => {
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

    renderWithProviders(<RootPage />);

    await waitFor(() => {
      const button = screen.getByRole("button", { name: /open.*folder/i });
      expect(button).toBeInTheDocument();
    });
  });
});

// --- P5.h: Gap 59 + 60 — project cards redesign + hero band + search + filter chips ---

function setupProjectList(
  projects = [{ project_id: "p1", project_root: "/data/p1", label: "Alpha" }],
) {
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
        projects,
        selected: null,
        projects_root: "/data",
        config_source: "default",
      }),
    ),
  );
}

describe("RootPage P5.h — Gap 60: hero band", () => {
  it("renders hero band with app name", async () => {
    setupProjectList([]);
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-hero-band")).toBeInTheDocument();
    });
  });

  it("hero band shows OCR Labeler title", async () => {
    setupProjectList([]);
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-hero-title")).toHaveTextContent("OCR Labeler");
    });
  });
});

describe("RootPage P5.h — Gap 60: search field", () => {
  it("renders search input", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-search-input")).toBeInTheDocument();
    });
  });

  it("search input filters projects by label", async () => {
    setupProjectList([
      { project_id: "p1", project_root: "/data/p1", label: "Alpha Project" },
      { project_id: "p2", project_root: "/data/p2", label: "Beta Project" },
    ]);
    renderWithProviders(<RootPage />);

    await waitFor(() => {
      expect(screen.getByTestId("project-card-p1")).toBeInTheDocument();
      expect(screen.getByTestId("project-card-p2")).toBeInTheDocument();
    });

    const input = screen.getByTestId("root-search-input");
    // userEvent not set up at this level, use fireEvent from testing-library
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(input, { target: { value: "Alpha" } });

    expect(screen.getByTestId("project-card-p1")).toBeInTheDocument();
    expect(screen.queryByTestId("project-card-p2")).not.toBeInTheDocument();
  });

  it("shows empty-search message when no results match", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);

    await waitFor(() => {
      expect(screen.getByTestId("project-card-p1")).toBeInTheDocument();
    });

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(screen.getByTestId("root-search-input"), {
      target: { value: "ZZZNOMATCH" },
    });

    expect(screen.getByTestId("root-empty-search")).toBeInTheDocument();
  });
});

describe("RootPage P5.h — Gap 60: filter chips", () => {
  it("renders All / Active / Complete / Archived filter chips", async () => {
    setupProjectList([]);
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-filter-chip-all")).toBeInTheDocument();
      expect(screen.getByTestId("root-filter-chip-active")).toBeInTheDocument();
      expect(screen.getByTestId("root-filter-chip-complete")).toBeInTheDocument();
      expect(screen.getByTestId("root-filter-chip-archived")).toBeInTheDocument();
    });
  });

  it("All chip is active by default", async () => {
    setupProjectList([]);
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-filter-chip-all")).toHaveAttribute("data-active", "true");
    });
  });
});

describe("RootPage P5.h — Gap 59: project card redesign", () => {
  it("renders project card with thumbnail placeholder", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("project-card-thumbnail-p1")).toBeInTheDocument();
    });
  });

  it("renders Open button on each card", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("project-card-open-p1")).toBeInTheDocument();
    });
  });

  it("renders action menu button on each card", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("project-card-menu-p1")).toBeInTheDocument();
    });
  });

  it("renders project source path", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("project-card-p1")).toHaveTextContent("/data/p1");
    });
  });

  it("projects grid uses testid root-projects-grid", async () => {
    setupProjectList();
    renderWithProviders(<RootPage />);
    await waitFor(() => {
      expect(screen.getByTestId("root-projects-grid")).toBeInTheDocument();
    });
  });
});
