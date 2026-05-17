// ProjectNavigationControls.test.tsx — unit tests for the real Prev/Next/GoTo
// navigation bar.
//
// Spec: specs/22-page-surface-wireup.md §7 (Navigation controls).
// Issue #311 (spec-22-B2).
//
// Contract:
//   - Renders all five existing nav testids: nav-prev-button, nav-next-button,
//     nav-goto-button, nav-page-input, nav-page-total-label.
//   - Prev / Next call navigate(`/projects/${projectId}/pages/pageno/${newPageNo}`).
//   - Prev disabled at page 1; Next disabled at last page.
//   - GoTo input — Enter or button click navigates to the typed page.
//   - Out-of-range GoTo (n < 1 or n > total) is rejected (no navigate fired).
//   - Total label reads `${currentPageNo} / ${project.total_pages}`.
//
// useProject is exercised via msw; useNavigate is mocked via vi.mock on
// react-router-dom (the standard pattern: spy on a real export).

import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import ProjectNavigationControls from "./ProjectNavigationControls";

// --- helpers ---------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

interface RenderOpts {
  projectId?: string;
  totalPages?: number;
  route?: string;
}

function mockProject(projectId: string, totalPages: number) {
  const image_paths = Array.from({ length: totalPages }, (_, i) => `page_${i + 1}.png`);
  // GET /api/projects/{id} returns a flat Project — not the LoadProjectResponse wrapper.
  server.use(
    http.get(`/api/projects/${projectId}`, () =>
      HttpResponse.json({
        project_id: projectId,
        project_root: `/data/${projectId}`,
        image_paths,
        ground_truth_map: {},
        version: "1.0",
        source_lib: "doctr-pd-labeled",
        total_pages: totalPages,
        saved_pages: 0,
        current_page_index: 0,
        include_images: true,
        copied_images: false,
      }),
    ),
  );
}

/**
 * Tiny spy component that mounts inside the router and writes the current
 * pathname into a `data-testid="current-url"` element. Used to assert
 * navigation outcomes without mocking `useNavigate`.
 */
function LocationSpy() {
  const loc = useLocation();
  return <span data-testid="current-url">{loc.pathname}</span>;
}

function renderControls({ projectId = "proj-1", totalPages = 5, route }: RenderOpts = {}) {
  // totalPages is referenced via the helper so eslint doesn't warn — caller
  // still needs to call mockProject() with the matching count.
  void totalPages;
  const qc = makeQueryClient();
  const initialPath = route ?? `/projects/${projectId}/pages/pageno/1`;
  // Extract pageNo from the initial path so we can pass it as a prop.
  const pageNoMatch = /\/pageno\/(\d+)/.exec(initialPath);
  const pageNo = pageNoMatch ? pageNoMatch[1] : "1";
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <LocationSpy />
        <Routes>
          <Route
            path="/projects/:projectId/pages/pageno/:pageNo"
            element={<ProjectNavigationControls projectId={projectId} pageNo={pageNo} />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function currentUrl(): string {
  return screen.getByTestId("current-url").textContent ?? "";
}

beforeEach(() => {
  // No global state to reset — each test scopes its own msw handlers
  // via `server.use(...)`, which the global afterEach clears.
});

// --- tests -----------------------------------------------------------------

describe("ProjectNavigationControls: testids", () => {
  it("renders all five nav testids", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", totalPages: 5 });

    expect(await screen.findByTestId("nav-prev-button")).toBeInTheDocument();
    expect(screen.getByTestId("nav-next-button")).toBeInTheDocument();
    expect(screen.getByTestId("nav-goto-button")).toBeInTheDocument();
    expect(screen.getByTestId("nav-page-input")).toBeInTheDocument();
    expect(screen.getByTestId("nav-page-total-label")).toBeInTheDocument();
  });

  it("nav-page-total-label shows '/ ${total_pages}' (P1.b: page shown in input)", async () => {
    mockProject("proj-1", 7);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/3" });

    const label = await screen.findByTestId("nav-page-total-label");
    // P1.b re-skin: total label shows "/ N" only; current page is shown in the input.
    await waitFor(() => expect(label.textContent).toMatch(/\/\s*7/));
  });

  it("nav-page-input shows the current page number when not editing", async () => {
    mockProject("proj-1", 7);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/3" });

    const input = await screen.findByTestId("nav-page-input");
    await waitFor(() => expect(input.value).toBe("3"));
  });
});

describe("ProjectNavigationControls: Prev / Next navigation", () => {
  it("clicking nav-prev-button navigates to previous page", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/3" });

    const prev = await screen.findByTestId("nav-prev-button");
    await waitFor(() => expect(prev).not.toBeDisabled());
    fireEvent.click(prev);

    await waitFor(() => {
      expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/2");
    });
  });

  it("clicking nav-next-button navigates to next page", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/3" });

    const next = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(next).not.toBeDisabled());
    fireEvent.click(next);

    await waitFor(() => {
      expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/4");
    });
  });

  it("nav-prev-button is disabled at page 1", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/1" });

    const prev = await screen.findByTestId("nav-prev-button");
    expect(prev).toBeDisabled();
  });

  it("nav-next-button is disabled on last page", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/5" });

    const next = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(next).toBeDisabled());
  });
});

describe("ProjectNavigationControls: GoTo", () => {
  it("clicking nav-goto-button with valid input navigates to that page", async () => {
    mockProject("proj-1", 10);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/2" });

    const input = await screen.findByTestId("nav-page-input");
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.click(screen.getByTestId("nav-goto-button"));

    await waitFor(() => {
      expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/7");
    });
  });

  it("pressing Enter in nav-page-input with valid value navigates", async () => {
    mockProject("proj-1", 10);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/2" });

    const input = await screen.findByTestId("nav-page-input");
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/4");
    });
  });

  it("rejects out-of-range GoTo (n > total_pages) — no navigation", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/2" });

    // wait for the project to load so the component knows total_pages
    await waitFor(() => {
      expect(screen.getByTestId("nav-page-total-label").textContent).toMatch(/\/\s*5/);
    });

    const input = await screen.findByTestId("nav-page-input");
    fireEvent.change(input, { target: { value: "99" } });
    fireEvent.click(screen.getByTestId("nav-goto-button"));

    // give react-router any pending microtask, then assert URL didn't change
    await new Promise((r) => setTimeout(r, 20));
    expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/2");
  });

  it("rejects out-of-range GoTo (n < 1) — no navigation", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/2" });

    await waitFor(() => {
      expect(screen.getByTestId("nav-page-total-label").textContent).toMatch(/\/\s*5/);
    });

    const input = await screen.findByTestId("nav-page-input");
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("nav-goto-button"));

    await new Promise((r) => setTimeout(r, 20));
    expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/2");
  });

  it("rejects non-numeric GoTo — no navigation", async () => {
    mockProject("proj-1", 5);
    renderControls({ projectId: "proj-1", route: "/projects/proj-1/pages/pageno/2" });

    await waitFor(() => {
      expect(screen.getByTestId("nav-page-total-label").textContent).toMatch(/\/\s*5/);
    });

    const input = await screen.findByTestId("nav-page-input");
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.click(screen.getByTestId("nav-goto-button"));

    await new Promise((r) => setTimeout(r, 20));
    expect(currentUrl()).toBe("/projects/proj-1/pages/pageno/2");
  });
});
