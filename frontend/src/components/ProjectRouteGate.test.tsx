// ProjectRouteGate.test.tsx — deep-link auto-load gate (P4.3, parity F14 / C57).
//
// A deep link to a project that exists on disk but is not loaded in server
// memory must trigger POST /api/projects/load instead of bouncing to the
// RootPage grid (legacy `_initialize_from_url` parity).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "../test/server";
import { ProjectRouteGate } from "./ProjectRouteGate";

const PROJECT = {
  project_id: "p1",
  project_root: "/data/p1",
  image_paths: ["001.png"],
  ground_truth_map: {},
  version: "1.0",
  source_lib: "doctr-pdomain-labeled",
  total_pages: 1,
  saved_pages: 0,
  current_page_index: 0,
  include_images: true,
  copied_images: false,
};

function LocationSpy() {
  const location = useLocation();
  const state = location.state as { skipSessionRedirect?: boolean } | null;
  return (
    <div data-testid="location-spy">
      path={location.pathname};skipSessionRedirect=
      {state?.skipSessionRedirect ? "true" : "false"}
    </div>
  );
}

function renderGate(initialPath = "/projects/p1/pages/pageno/1") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route
            path="/projects/:projectId/pages/pageno/:pageNo"
            element={
              <ProjectRouteGate>
                <div data-testid="gated-child" />
              </ProjectRouteGate>
            }
          />
          <Route path="*" element={<div data-testid="elsewhere" />} />
        </Routes>
        <LocationSpy />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectRouteGate (P4.3 — deep-link auto-load)", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [{ project_id: "p1", project_root: "/data/p1", label: "P One" }],
          selected: null,
          projects_root: "/data",
          config_source: "default",
        }),
      ),
    );
  });

  it("renders children when the project is already loaded", async () => {
    server.use(http.get("/api/projects/p1", () => HttpResponse.json(PROJECT)));
    renderGate();
    await waitFor(() => {
      expect(screen.getByTestId("gated-child")).toBeInTheDocument();
    });
  });

  it("auto-loads an unloaded project (404 -> POST /load -> children)", async () => {
    let loaded = false;
    let loadBody: unknown = null;
    server.use(
      http.get("/api/projects/p1", () =>
        loaded
          ? HttpResponse.json(PROJECT)
          : HttpResponse.json({ error: "project_not_found", message: "nope" }, { status: 404 }),
      ),
      http.post("/api/projects/load", async ({ request }) => {
        loadBody = await request.json();
        loaded = true;
        return HttpResponse.json({ project: PROJECT, current_page_index: 0, generation: 1 });
      }),
    );

    renderGate();

    // While loading, an overlay (not the children, not a bounce) shows.
    await waitFor(() => {
      expect(screen.getByTestId("project-autoload-overlay")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByTestId("gated-child")).toBeInTheDocument();
    });
    expect(loadBody).toMatchObject({ project_root: "/data/p1" });
    // No bounce happened.
    expect(screen.getByTestId("location-spy").textContent).toContain(
      "path=/projects/p1/pages/pageno/1",
    );
  });

  it("bounces to / with skipSessionRedirect when the project is unknown", async () => {
    server.use(
      http.get("/api/projects/ghost", () =>
        HttpResponse.json({ error: "project_not_found", message: "nope" }, { status: 404 }),
      ),
      // Listing does NOT contain "ghost" → auto-load cannot resolve it.
    );

    renderGate("/projects/ghost/pages/pageno/1");

    await waitFor(() => {
      const spy = screen.getByTestId("location-spy");
      expect(spy.textContent).toContain("path=/");
      expect(spy.textContent).toContain("skipSessionRedirect=true");
    });
    expect(screen.queryByTestId("gated-child")).not.toBeInTheDocument();
  });

  it("bounces to / when the auto-load POST fails", async () => {
    server.use(
      http.get("/api/projects/p1", () =>
        HttpResponse.json({ error: "project_not_found", message: "nope" }, { status: 404 }),
      ),
      http.post("/api/projects/load", () =>
        HttpResponse.json({ error: "invalid_project_dir", message: "bad" }, { status: 400 }),
      ),
    );

    renderGate();

    await waitFor(() => {
      const spy = screen.getByTestId("location-spy");
      expect(spy.textContent).toContain("path=/");
      expect(spy.textContent).toContain("skipSessionRedirect=true");
    });
  });

  // useProject retries non-404 errors up to 3 times (~7s with backoff) —
  // the hook-level retry fn overrides this test client's retry:false, so
  // give the waitFor (and the test) enough headroom.
  it(
    "renders children for non-404 errors (ProjectPage owns other error UX)",
    { timeout: 15_000 },
    async () => {
      server.use(
        http.get("/api/projects/p1", () =>
          HttpResponse.json({ error: "boom", message: "server broke" }, { status: 500 }),
        ),
      );
      renderGate();
      await waitFor(
        () => {
          expect(screen.getByTestId("gated-child")).toBeInTheDocument();
        },
        { timeout: 12_000 },
      );
    },
  );
});
