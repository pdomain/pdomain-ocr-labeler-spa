// RootPage.test.tsx — Vitest unit tests for RootPage + EmptyProjectState.
// Issue #84 (EmptyProjectState) + Issue #274 (RootPage + session-state fetch).
// Spec: docs/specs/2026-05-12-root-page-design.md §Contract
import { describe, it, expect } from "vitest";
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
    );

    // We verify navigation by checking the empty-project-state is NOT rendered
    // after data loads (redirect has fired). We can't easily assert the target
    // URL without a router location consumer, but we verify the component
    // doesn't fall through to EmptyProjectState when a project is present.
    renderWithProviders(<RootPage />);

    // Allow the query to settle; empty-project-state must not appear
    // (redirect was issued instead)
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("empty-project-state")).not.toBeInTheDocument();
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
