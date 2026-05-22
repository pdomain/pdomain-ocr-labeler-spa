// SourceFolderDialog.test.tsx — unit tests for the file-browser-style source-folder dialog.
// Issue #294 (spec 22 §10 / driver-contract 13 §2.2).
//
// Tests:
//   - Renders when open, not rendered when closed.
//   - All 9 driver-contract testids present when open.
//   - Home button resets both currentPath and inputPath to "~".
//   - Up button navigates to parent directory.
//   - Open-typed button sets currentPath to inputPath value.
//   - Use-current button copies currentPath into inputPath.
//   - Apply button POSTs inputPath to /api/projects/source-root and closes.
//   - Apply posts typed path directly (no "Open Typed Path" needed) — regression for the
//     bug where typing a path and clicking Apply submitted currentPath ("~") instead.
//   - Dialog initializes currentPath/inputPath from projects_root API response on open.
//   - Cancel closes without API call.
//   - Enter key in path-input triggers open-typed (not apply).

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { SourceFolderDialog } from "./SourceFolderDialog";

// --- helpers -----------------------------------------------------------------

function renderDialog(open: boolean, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SourceFolderDialog open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
}

// --- render gating -----------------------------------------------------------

describe("SourceFolderDialog: render gating", () => {
  it("renders nothing when open=false", () => {
    renderDialog(false);
    expect(screen.queryByTestId("source-folder-dialog")).toBeNull();
  });

  it("renders the dialog when open=true", () => {
    renderDialog(true);
    expect(screen.getByTestId("source-folder-dialog")).toBeInTheDocument();
  });
});

// --- required testids --------------------------------------------------------

describe("SourceFolderDialog: driver-contract testids", () => {
  it("shows all 9 driver-contract testids when open", () => {
    renderDialog(true);
    const ids = [
      "source-folder-dialog",
      "source-folder-current-path-label",
      "source-folder-path-input",
      "source-folder-home-button",
      "source-folder-up-button",
      "source-folder-open-typed-button",
      "source-folder-use-current-button",
      "source-folder-apply-button",
      "source-folder-cancel-button",
    ];
    for (const id of ids) {
      expect(screen.getByTestId(id), `testid ${id} should be present`).toBeInTheDocument();
    }
  });

  it("shows initial currentPath as ~ in current-path-label", () => {
    renderDialog(true);
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("~");
  });

  it("shows initial inputPath as ~ in path-input", () => {
    renderDialog(true);
    expect(screen.getByTestId("source-folder-path-input")).toHaveValue("~");
  });
});

// --- Initialization from API -------------------------------------------------

describe("SourceFolderDialog: initialization from current source root", () => {
  it("pre-populates paths from projects_root when the API returns one", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json({
          projects: [],
          projects_root: "/data/projects",
          selected: null,
          config_source: "yaml",
        }),
      ),
    );

    renderDialog(true);

    await waitFor(() => {
      expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent(
        "/data/projects",
      );
    });
    expect(screen.getByTestId("source-folder-path-input")).toHaveValue("/data/projects");
  });

  it("falls back to ~ when projects_root is empty", async () => {
    // Default handler returns projects_root: "" — paths should stay at ~.
    renderDialog(true);

    // Give the async fetch a moment to settle.
    await new Promise((r) => setTimeout(r, 20));

    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("~");
    expect(screen.getByTestId("source-folder-path-input")).toHaveValue("~");
  });
});

// --- Home button -------------------------------------------------------------

describe("SourceFolderDialog: Home button", () => {
  it("resets currentPath to ~ in the label", () => {
    renderDialog(true);

    // First navigate away by typing and opening a typed path.
    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/some/deep/path" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent(
      "/some/deep/path",
    );

    // Now click Home.
    fireEvent.click(screen.getByTestId("source-folder-home-button"));
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("~");
  });

  it("resets inputPath to ~ in the text input", () => {
    renderDialog(true);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/some/deep/path" } });
    fireEvent.click(screen.getByTestId("source-folder-home-button"));
    expect(input.value).toBe("~");
  });
});

// --- Up button ---------------------------------------------------------------

describe("SourceFolderDialog: Up button", () => {
  it("navigates to the parent directory", () => {
    renderDialog(true);

    // Set a path to navigate up from.
    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/data/projects/mybook" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent(
      "/data/projects/mybook",
    );

    // Click Up.
    fireEvent.click(screen.getByTestId("source-folder-up-button"));
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent(
      "/data/projects",
    );
    expect(screen.getByTestId("source-folder-path-input")).toHaveValue("/data/projects");
  });

  it("navigates to / when already at a top-level directory", () => {
    renderDialog(true);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/data" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));

    fireEvent.click(screen.getByTestId("source-folder-up-button"));
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("/");
    expect(input.value).toBe("/");
  });

  it("navigates up from ~ (treated as /home/user)", () => {
    renderDialog(true);
    // Initial state is "~".
    fireEvent.click(screen.getByTestId("source-folder-up-button"));
    // "~" expands to "/home/user"; parent is "/home".
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("/home");
  });
});

// --- Open-typed button -------------------------------------------------------

describe("SourceFolderDialog: Open-typed button", () => {
  it("sets currentPath to the value in path-input", () => {
    renderDialog(true);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/custom/path" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));

    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent(
      "/custom/path",
    );
  });

  it("Enter key in path-input triggers open-typed (not apply)", () => {
    renderDialog(true);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/typed/path" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // currentPath label should update (open-typed fired)...
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("/typed/path");
    // ...and the dialog should still be open (no API call, no close).
    expect(screen.getByTestId("source-folder-dialog")).toBeInTheDocument();
  });
});

// --- Use-current button ------------------------------------------------------

describe("SourceFolderDialog: Use-current button", () => {
  it("copies currentPath into path-input", () => {
    renderDialog(true);

    // Navigate to a path first.
    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/nav/path" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));

    // Modify the input to something else.
    fireEvent.change(input, { target: { value: "/different" } });
    expect(input.value).toBe("/different");

    // Click Use-current — should restore input to currentPath.
    fireEvent.click(screen.getByTestId("source-folder-use-current-button"));
    expect(input.value).toBe("/nav/path");
  });
});

// --- Apply button ------------------------------------------------------------

describe("SourceFolderDialog: Apply POSTs inputPath and closes", () => {
  it("POSTs the inputPath to source-root and calls onClose", async () => {
    const capturedBodies: unknown[] = [];

    server.use(
      http.post("/api/projects/source-root", async ({ request }) => {
        const body: unknown = await request.json();
        capturedBodies.push(body);
        return HttpResponse.json(
          { projects_root: "/data/projects", projects: [] },
          { status: 200 },
        );
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, { target: { value: "/data/projects" } });

    fireEvent.click(screen.getByTestId("source-folder-apply-button"));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(capturedBodies).toHaveLength(1);
    expect(capturedBodies[0]).toMatchObject({ path: "/data/projects" });
  });

  it("regression: typing path and clicking Apply directly submits typed path (no Open-Typed needed)", async () => {
    // This was the original failure: user types a path and clicks Apply without
    // clicking "Open Typed Path" first. The old code submitted currentPath ("~"),
    // not inputPath. The fix: Apply always submits inputPath.
    const capturedBodies: unknown[] = [];

    server.use(
      http.post("/api/projects/source-root", async ({ request }) => {
        const body: unknown = await request.json();
        capturedBodies.push(body);
        return HttpResponse.json(
          { projects_root: "/workspaces/ocr-container/source-pgdp-data/output", projects: [] },
          { status: 200 },
        );
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    // Type the path — do NOT click "Open Typed Path".
    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.change(input, {
      target: { value: "/workspaces/ocr-container/source-pgdp-data/output" },
    });

    // currentPath label still shows "~" — only inputPath changed.
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("~");

    // Click Apply directly.
    fireEvent.click(screen.getByTestId("source-folder-apply-button"));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    // Must have posted the typed path, NOT "~".
    expect(capturedBodies[0]).toMatchObject({
      path: "/workspaces/ocr-container/source-pgdp-data/output",
    });
  });

  it("Apply posts inputPath even when currentPath and inputPath differ", async () => {
    const capturedBodies: unknown[] = [];

    server.use(
      http.post("/api/projects/source-root", async ({ request }) => {
        const body: unknown = await request.json();
        capturedBodies.push(body);
        return HttpResponse.json({ projects_root: "/typed/path", projects: [] }, { status: 200 });
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    const input = screen.getByTestId("source-folder-path-input");
    // Navigate currentPath to /nav/path.
    fireEvent.change(input, { target: { value: "/nav/path" } });
    fireEvent.click(screen.getByTestId("source-folder-open-typed-button"));
    // Now type a different path into input without navigating.
    fireEvent.change(input, { target: { value: "/typed/path" } });

    fireEvent.click(screen.getByTestId("source-folder-apply-button"));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    // Should have posted the input value, not the navigated path.
    expect(capturedBodies[0]).toMatchObject({ path: "/typed/path" });
  });

  it("shows loading state while POST is in flight", async () => {
    let resolvePost!: () => void;
    server.use(
      http.post("/api/projects/source-root", () => {
        return new Promise<Response>((resolve) => {
          resolvePost = () =>
            resolve(
              HttpResponse.json({ projects_root: "/data/projects", projects: [] }, { status: 200 }),
            );
        });
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    fireEvent.click(screen.getByTestId("source-folder-apply-button"));

    await waitFor(() => {
      expect(screen.getByTestId("source-folder-apply-button")).toHaveTextContent(/Setting/i);
    });
    expect(screen.getByTestId("source-folder-apply-button")).toBeDisabled();
    expect(screen.getByTestId("source-folder-cancel-button")).toBeDisabled();

    act(() => {
      resolvePost();
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("shows error message on API failure and does NOT close", async () => {
    server.use(
      http.post("/api/projects/source-root", () =>
        HttpResponse.json(
          { error: "invalid_path", message: "Path does not exist" },
          { status: 400 },
        ),
      ),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    fireEvent.click(screen.getByTestId("source-folder-apply-button"));

    await waitFor(() => {
      expect(screen.getByText(/Path does not exist/i)).toBeInTheDocument();
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});

// --- Directory listing -------------------------------------------------------

describe("SourceFolderDialog: directory listing", () => {
  it("renders subdirectory entries fetched from GET /api/fs/ls", async () => {
    server.use(
      http.get("/api/fs/ls", () =>
        HttpResponse.json({
          path: "/home/user",
          entries: [
            { name: "projects", is_dir: true },
            { name: "books", is_dir: true },
          ],
        }),
      ),
    );

    renderDialog(true);

    // Entries should appear after the async fetch resolves.
    await waitFor(() => {
      expect(screen.getByTestId("fs-ls-entry-projects")).toBeInTheDocument();
    });
    expect(screen.getByTestId("fs-ls-entry-books")).toBeInTheDocument();
  });

  it("clicking a directory entry updates currentPath and inputPath", async () => {
    server.use(
      http.get("/api/fs/ls", () =>
        HttpResponse.json({
          path: "/home/user",
          entries: [{ name: "mybooks", is_dir: true }],
        }),
      ),
    );

    renderDialog(true);

    // Wait for entry to render.
    await waitFor(() => {
      expect(screen.getByTestId("fs-ls-entry-mybooks")).toBeInTheDocument();
    });

    // Click the entry.
    fireEvent.click(screen.getByTestId("fs-ls-entry-mybooks"));

    // currentPath label should now include the directory name.
    expect(screen.getByTestId("source-folder-current-path-label")).toHaveTextContent("~/mybooks");
    expect(screen.getByTestId("source-folder-path-input")).toHaveValue("~/mybooks");
  });

  it("shows empty state when no entries returned", async () => {
    // Default handler already returns empty entries; just verify the message.
    renderDialog(true);

    await waitFor(() => {
      expect(screen.getByText(/No subdirectories/i)).toBeInTheDocument();
    });
  });
});

// --- Cancel button -----------------------------------------------------------

describe("SourceFolderDialog: Cancel closes without API call", () => {
  it("clicking Cancel calls onClose without making an API call", async () => {
    let postCalled = false;
    server.use(
      http.post("/api/projects/source-root", () => {
        postCalled = true;
        return HttpResponse.json({});
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    fireEvent.click(screen.getByTestId("source-folder-cancel-button"));

    expect(onClose).toHaveBeenCalledTimes(1);
    // Give any accidental async POST a tick to land.
    await new Promise((r) => setTimeout(r, 20));
    expect(postCalled).toBe(false);
  });

  it("Escape key in path-input calls onClose", () => {
    const onClose = vi.fn();
    renderDialog(true, onClose);

    const input = screen.getByTestId("source-folder-path-input");
    fireEvent.keyDown(input, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
