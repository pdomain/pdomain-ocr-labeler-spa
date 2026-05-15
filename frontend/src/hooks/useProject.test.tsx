// useProject.test.tsx — unit tests for the useProject TanStack Query hook.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// GET /api/projects/{id} returns a flat Project model — NOT the
// LoadProjectResponse wrapper (which is only returned by POST /load).
// The mock here matches the real backend: api/projects.py:get_project_by_id
// returns `project.model_dump(mode="json")` directly.

import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import { useProject, type ProjectResponse } from "./useProject";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

/** Flat Project shape — matches Python Project.model_dump(mode="json"). */
const MOCK_PROJECT: ProjectResponse = {
  project_id: "proj-001",
  project_root: "/data/proj-001",
  image_paths: ["page_001.png", "page_002.png"],
  ground_truth_map: {},
  version: "1.0",
  source_lib: "doctr-pd-labeled",
  total_pages: 2,
  saved_pages: 0,
  current_page_index: 0,
  include_images: true,
  copied_images: false,
};

beforeEach(() => {
  server.use(
    http.get("/api/projects/:projectId", ({ params }) => {
      if (params.projectId === "proj-001") {
        return HttpResponse.json(MOCK_PROJECT);
      }
      return HttpResponse.json(
        { error: "project_not_found", message: "not found" },
        { status: 404 },
      );
    }),
  );
});

describe("useProject", () => {
  it("fetches project data for a valid projectId", async () => {
    const { result } = renderHook(() => useProject("proj-001"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // The hook returns the flat Project — top-level project_id, not data.project.project_id
    expect(result.current.data?.project_id).toBe("proj-001");
    expect(result.current.data?.image_paths).toHaveLength(2);
    expect(result.current.data?.total_pages).toBe(2);
    expect(result.current.data?.current_page_index).toBe(0);
  });

  it("data shape matches flat Project (no nested .project wrapper)", async () => {
    const { result } = renderHook(() => useProject("proj-001"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Confirm no nested wrapper — GET /api/projects/{id} is flat
    const data = result.current.data;
    expect(data).toBeDefined();
    expect((data as Record<string, unknown>)["project"]).toBeUndefined();
    expect(data?.project_id).toBe("proj-001");
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => useProject(undefined), {
      wrapper: makeWrapper(),
    });
    // Query should never fire — stays in pending/idle state
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when projectId is empty string", () => {
    const { result } = renderHook(() => useProject(""), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("surfaces an error for a missing project (404)", async () => {
    const { result } = renderHook(() => useProject("missing"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });

  it("uses the correct query key so cache is keyed by projectId", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result } = renderHook(() => useProject("proj-001"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData<ProjectResponse>(["project", "proj-001"]);
    expect(cached?.project_id).toBe("proj-001");
  });
});
