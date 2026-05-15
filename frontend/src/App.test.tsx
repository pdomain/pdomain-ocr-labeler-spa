// App.test.tsx — Vitest tests for App shell routing.
// Issue #240: React Router routes, QueryClient provider wiring.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Routing
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "./test/server";

// App.tsx statically imports ProjectPage, which transitively imports
// react-konva (via PageImageCanvas). jsdom can't construct an
// HTMLCanvasElement so Konva's node entry tries to `require('canvas')`
// and fails at module-load. Mock react-konva module-wide so the import
// resolves to plain divs.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": tid,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div data-testid={tid ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div data-testid="konva-rect" />,
  Image: () => <div data-testid="konva-image" />,
}));
vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

import App from "./App";

// Helper: setup session-state mock (null = no project loaded)
function withNoSession() {
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
}

describe("App: routing shell", () => {
  it("renders header-bar on the root route", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
    });
  });

  it("renders project-list view on / when no session (Slice 27)", async () => {
    withNoSession();
    render(<App />);
    await waitFor(() => {
      // ProjectListView includes the header bar and project list
      expect(screen.getByTestId("header-bar")).toBeInTheDocument();
      // With no projects, we expect the "No projects found" message or open folder button
      expect(screen.getByRole("button", { name: /open.*folder/i })).toBeInTheDocument();
    });
  });
});
