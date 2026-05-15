// SourceFolderDialog.test.tsx — unit tests for the source-folder picker dialog.
// Issue #294 (spec 22 §10 — real source-folder picker).
//
// Tests:
//   - Renders when open, not rendered when closed.
//   - Shows required driver-contract testids.
//   - Typing + clicking Confirm → POST /api/projects/source-root (via MSW).
//   - Cancel closes without making an API call.
//   - Loading state shown while POST is in flight.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { SourceFolderDialog } from "./SourceFolderDialog";

// --- helpers -----------------------------------------------------------------

function renderDialog(open: boolean, onClose = vi.fn()) {
  return render(<SourceFolderDialog open={open} onClose={onClose} />);
}

// --- tests -------------------------------------------------------------------

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

describe("SourceFolderDialog: required testids", () => {
  it("shows all four driver-contract testids when open", () => {
    renderDialog(true);
    expect(screen.getByTestId("source-folder-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("source-folder-input")).toBeInTheDocument();
    expect(screen.getByTestId("source-folder-confirm-button")).toBeInTheDocument();
    expect(screen.getByTestId("source-folder-cancel-button")).toBeInTheDocument();
  });
});

describe("SourceFolderDialog: confirm calls POST /api/projects/source-root", () => {
  it("typing a path and clicking Confirm calls source-root API", async () => {
    const capturedBodies: unknown[] = [];

    server.use(
      http.post("/api/projects/source-root", async ({ request }) => {
        const body: unknown = await request.json();
        capturedBodies.push(body);
        return HttpResponse.json(
          {
            projects_root: "/data/projects",
            projects: [],
          },
          { status: 200 },
        );
      }),
    );

    const onClose = vi.fn();
    renderDialog(true, onClose);

    const input = screen.getByTestId("source-folder-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "/data/projects" } });

    const confirmBtn = screen.getByTestId("source-folder-confirm-button");
    expect(confirmBtn).not.toBeDisabled();
    fireEvent.click(confirmBtn);

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(capturedBodies).toHaveLength(1);
    expect(capturedBodies[0]).toMatchObject({ path: "/data/projects" });
  });

  it("confirm button is disabled when input is empty", () => {
    renderDialog(true);
    const confirmBtn = screen.getByTestId("source-folder-confirm-button");
    expect(confirmBtn).toBeDisabled();
  });
});

describe("SourceFolderDialog: cancel", () => {
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

    const cancelBtn = screen.getByTestId("source-folder-cancel-button");
    fireEvent.click(cancelBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
    // Give any accidental async POST a tick to land.
    await new Promise((r) => setTimeout(r, 20));
    expect(postCalled).toBe(false);
  });
});

describe("SourceFolderDialog: loading state", () => {
  it("shows loading text on confirm button while POST is in flight", async () => {
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

    const input = screen.getByTestId("source-folder-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "/data/projects" } });

    fireEvent.click(screen.getByTestId("source-folder-confirm-button"));

    // After click the button should show loading text and be disabled.
    await waitFor(() => {
      expect(screen.getByTestId("source-folder-confirm-button")).toHaveTextContent(/Setting/i);
    });
    expect(screen.getByTestId("source-folder-confirm-button")).toBeDisabled();
    expect(screen.getByTestId("source-folder-cancel-button")).toBeDisabled();

    // Release the pending POST.
    act(() => {
      resolvePost();
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });
});

describe("SourceFolderDialog: error state", () => {
  it("shows error message on API failure", async () => {
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

    const input = screen.getByTestId("source-folder-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "/no/such/dir" } });
    fireEvent.click(screen.getByTestId("source-folder-confirm-button"));

    await waitFor(() => {
      expect(screen.getByText(/Path does not exist/i)).toBeInTheDocument();
    });
    // Dialog should NOT close on failure.
    expect(onClose).not.toHaveBeenCalled();
  });
});
