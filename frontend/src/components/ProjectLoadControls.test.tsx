// ProjectLoadControls.test.tsx — unit tests for the project dropdown + buttons.
// Issue #294 (source-folder-button wires dialogStore.open("sourceFolder")).
//
// Tests:
//   - source-folder-button is rendered.
//   - Clicking source-folder-button opens sourceFolder in the dialog store.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import ProjectLoadControls from "./ProjectLoadControls";
import { dialogStore } from "../stores/dialog-store";

// --- helpers -----------------------------------------------------------------

function renderControls() {
  return render(<ProjectLoadControls />);
}

function mockEmptyProjects() {
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

// --- tests -------------------------------------------------------------------

beforeEach(() => {
  dialogStore.reset();
});

describe("ProjectLoadControls: source-folder-button", () => {
  it("renders the source-folder-button", async () => {
    mockEmptyProjects();
    renderControls();
    expect(await screen.findByTestId("source-folder-button")).toBeInTheDocument();
  });

  it("clicking source-folder-button opens sourceFolder in the dialog store", async () => {
    mockEmptyProjects();
    renderControls();

    const btn = await screen.findByTestId("source-folder-button");
    expect(dialogStore.getState().sourceFolder.open).toBe(false);

    fireEvent.click(btn);

    await waitFor(() => {
      expect(dialogStore.getState().sourceFolder.open).toBe(true);
    });
  });
});
