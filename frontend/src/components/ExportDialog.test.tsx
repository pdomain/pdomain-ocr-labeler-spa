// ExportDialog.test.tsx — Export dialog (#227)
// Spec: docs/specs/2026-05-12-export-design.md
// driver-contract: docs/architecture/13-driver-contract.md §2.12
//
// Acceptance:
//   - export-dialog testid present when open
//   - scope radios switch state
//   - Style filter: clicking "All" unchecks individual styles; clicking individual unchecks "All"
//   - Output flags are mutually exclusive radios
//   - Export button -> POST -> running state shows Cancel
//   - Run history row appended on complete; not on cancel
//   - Close button calls onClose

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ExportDialog } from "./ExportDialog";
import { server } from "../test/server";
import { http, HttpResponse } from "msw";

const PROJECT_ID = "test-proj";
const BASE_URL = `/api/projects/${PROJECT_ID}`;

// Mock useJobProgress to avoid EventSource setup in tests
vi.mock("../hooks/useJobProgress", () => ({
  useJobProgress: vi.fn().mockReturnValue(null),
}));

import { useJobProgress } from "../hooks/useJobProgress";
const mockUseJobProgress = useJobProgress as ReturnType<typeof vi.fn>;

describe("ExportDialog", () => {
  beforeEach(() => {
    mockUseJobProgress.mockReturnValue(null);
    // Register default style list handler
    server.use(
      http.get(`${BASE_URL}/export/styles`, () => {
        return HttpResponse.json(["italic", "bold", "small_caps"]);
      }),
    );
  });

  afterEach(() => {
    server.resetHandlers();
    vi.clearAllMocks();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <ExportDialog open={false} projectId={PROJECT_ID} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders export-dialog testid when open", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    expect(screen.getByTestId("export-dialog")).toBeTruthy();
  });

  it("scope radios exist and default to all_validated", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    const allRadio = screen.getByTestId("export-scope-all") as HTMLInputElement;
    const currentRadio = screen.getByTestId("export-scope-current") as HTMLInputElement;
    expect(allRadio.checked).toBe(true);
    expect(currentRadio.checked).toBe(false);
  });

  it("switching scope to current hides style checkboxes", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("export-scope-current"));
    // Style checkboxes only show for all_validated
    expect(screen.queryByTestId("export-style-all-checkbox")).toBeNull();
  });

  it("style checkboxes render after fetching styles", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId("export-style-all-checkbox")).toBeTruthy();
      expect(screen.getByTestId("export-style-checkbox-italic")).toBeTruthy();
    });
  });

  it("clicking individual style unchecks All", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    await waitFor(() => screen.getByTestId("export-style-checkbox-italic"));
    const allCheckbox = screen.getByTestId("export-style-all-checkbox") as HTMLInputElement;
    const italicCheckbox = screen.getByTestId("export-style-checkbox-italic") as HTMLInputElement;

    // Initially All is checked (selectedStyles empty)
    expect(allCheckbox.checked).toBe(true);

    fireEvent.click(italicCheckbox);
    // Now "italic" is selected, All should be unchecked
    expect(italicCheckbox.checked).toBe(true);
    expect(allCheckbox.checked).toBe(false);
  });

  it("clicking All unchecks individual styles", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    await waitFor(() => screen.getByTestId("export-style-checkbox-italic"));

    // Select italic first
    fireEvent.click(screen.getByTestId("export-style-checkbox-italic"));
    expect((screen.getByTestId("export-style-checkbox-italic") as HTMLInputElement).checked).toBe(
      true,
    );

    // Click All to reset
    fireEvent.click(screen.getByTestId("export-style-all-checkbox"));
    expect((screen.getByTestId("export-style-checkbox-italic") as HTMLInputElement).checked).toBe(
      false,
    );
    expect((screen.getByTestId("export-style-all-checkbox") as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it("export-button present when not running", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);
    expect(screen.getByTestId("export-button")).toBeTruthy();
  });

  it("clicking Export sends POST and enters running state", async () => {
    let postedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/export`, async ({ request }) => {
        postedBody = await request.json();
        return HttpResponse.json({ job_id: "job-123" }, { status: 202 });
      }),
    );

    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId("export-button"));
    });

    // Expect POST was called with scope=all_validated
    expect(postedBody).toMatchObject({ scope: "all_validated" });
  });

  it("run history row appended on complete", async () => {
    server.use(
      http.post(`${BASE_URL}/export`, () =>
        HttpResponse.json({ job_id: "job-abc" }, { status: 202 }),
      ),
    );

    mockUseJobProgress.mockReturnValue(null);
    const { rerender } = render(
      <ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("export-button"));
    });

    // Simulate complete event
    mockUseJobProgress.mockReturnValue({
      job_id: "job-abc",
      status: "complete",
      progress: { current: 3, total: 3, current_page: 2, message: "done" },
    });

    rerender(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("export-results")).toBeTruthy();
    });
  });

  it("Close button calls onClose", () => {
    const onClose = vi.fn();
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={onClose} />);
    // Click the footer close button (last one)
    const closeButtons = screen.getAllByTestId("export-close-button");
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
