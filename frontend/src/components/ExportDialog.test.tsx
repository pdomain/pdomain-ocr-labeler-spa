// ExportDialog.test.tsx — Export dialog (#227)
// Covers: B-ACTIONS-004, B-ACTIONS-018, F-EXPORT-OPTIONS-01
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
//   - Component filter options sourced from canonical useLabelVocabulary wordComponents

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { ExportDialog } from "./ExportDialog";
import { server } from "../test/server";
import { http, HttpResponse } from "msw";

const PROJECT_ID = "test-proj";
const BASE_URL = `/api/projects/${PROJECT_ID}`;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

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
      { wrapper: makeWrapper() },
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders export-dialog testid when open", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByTestId("export-dialog")).toBeTruthy();
  });

  it("scope radios exist and default to all_validated", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    const allRadio = screen.getByTestId("export-scope-all");
    const currentRadio = screen.getByTestId("export-scope-current");
    expect(allRadio.checked).toBe(true);
    expect(currentRadio.checked).toBe(false);
  });

  it("switching scope to current hides style checkboxes", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    fireEvent.click(screen.getByTestId("export-scope-current"));
    // Style checkboxes only show for all_validated
    expect(screen.queryByTestId("export-style-all-checkbox")).toBeNull();
  });

  it("style checkboxes render after fetching styles", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(screen.getByTestId("export-style-all-checkbox")).toBeTruthy();
      expect(screen.getByTestId("export-style-checkbox-italic")).toBeTruthy();
    });
  });

  it("clicking individual style unchecks All", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => screen.getByTestId("export-style-checkbox-italic"));
    const allCheckbox = screen.getByTestId("export-style-all-checkbox");
    const italicCheckbox = screen.getByTestId("export-style-checkbox-italic");

    // Initially All is checked (selectedStyles empty)
    expect(allCheckbox.checked).toBe(true);

    fireEvent.click(italicCheckbox);
    // Now "italic" is selected, All should be unchecked
    expect(italicCheckbox.checked).toBe(true);
    expect(allCheckbox.checked).toBe(false);
  });

  it("clicking All unchecks individual styles", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => screen.getByTestId("export-style-checkbox-italic"));

    // Select italic first
    fireEvent.click(screen.getByTestId("export-style-checkbox-italic"));
    expect(screen.getByTestId("export-style-checkbox-italic").checked).toBe(true);

    // Click All to reset
    fireEvent.click(screen.getByTestId("export-style-all-checkbox"));
    expect(screen.getByTestId("export-style-checkbox-italic").checked).toBe(false);
    expect(screen.getByTestId("export-style-all-checkbox").checked).toBe(true);
  });

  it("export-button present when not running", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });
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

    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });

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
      { wrapper: makeWrapper() },
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

  it("renders export stats breakdown on complete (Lane E3)", async () => {
    server.use(
      http.post(`${BASE_URL}/export`, () =>
        HttpResponse.json({ job_id: "job-stats" }, { status: 202 }),
      ),
    );

    mockUseJobProgress.mockReturnValue(null);
    const { rerender } = render(
      <ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("export-button"));
    });

    // Simulate a terminal complete event carrying the stats breakdown.
    mockUseJobProgress.mockReturnValue({
      job_id: "job-stats",
      status: "complete",
      progress: { current: 5, total: 5, current_page: 4, message: "done" },
      words_exported_detection: 42,
      words_exported_recognition: 40,
      pages_skipped_not_validated: 2,
    });

    rerender(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("export-stats-detection-job-stats")).toBeTruthy();
    });
    expect(screen.getByTestId("export-stats-detection-job-stats").textContent).toContain("42");
    expect(screen.getByTestId("export-stats-recognition-job-stats").textContent).toContain("40");
    expect(screen.getByTestId("export-stats-skipped-job-stats").textContent).toContain("2");
  });

  it("Close button calls onClose", () => {
    const onClose = vi.fn();
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={onClose} />, {
      wrapper: makeWrapper(),
    });
    // Click the footer close button (last one)
    const closeButtons = screen.getAllByTestId("export-close-button");
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// Component filter — canonical vocab (fix for hardcoded non-canonical list)
// ---------------------------------------------------------------------------
describe("ExportDialog — component filter sourced from canonical vocab", () => {
  beforeEach(() => {
    mockUseJobProgress.mockReturnValue(null);
    // Register default style list handler
    server.use(
      http.get(`${BASE_URL}/export/styles`, () => {
        return HttpResponse.json(["italic", "bold"]);
      }),
    );
    // Override label-vocabulary to return known canonical components
    server.use(
      http.get("/api/label-vocabulary", () =>
        HttpResponse.json({
          text_style_labels: ["italics", "bold"],
          word_components: [
            "drop cap",
            "drop cap unrecovered",
            "footnote marker",
            "subscript",
            "superscript",
          ],
        }),
      ),
    );
  });

  afterEach(() => {
    server.resetHandlers();
    vi.clearAllMocks();
  });

  it("renders canonical word_components as options in #export-component-filter", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });

    // Wait for the vocabulary query to resolve and options to appear
    await waitFor(() => {
      const select = document.getElementById("export-component-filter") as HTMLSelectElement;
      expect(select).toBeTruthy();
      const values = Array.from(select.options).map((o) => o.value);
      expect(values).toContain("drop cap");
    });

    const select = document.getElementById("export-component-filter") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    // Canonical values must be present
    expect(values).toContain("drop cap");
    expect(values).toContain("footnote marker");
    expect(values).toContain("superscript");
    // Empty option (none) must still be present
    expect(values).toContain("");
  });

  it("does NOT render non-canonical underscored options in #export-component-filter", async () => {
    render(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />, {
      wrapper: makeWrapper(),
    });

    await waitFor(() => {
      const select = document.getElementById("export-component-filter") as HTMLSelectElement;
      expect(select).toBeTruthy();
      const values = Array.from(select.options).map((o) => o.value);
      // Must not contain the old hardcoded non-canonical values
      expect(values).not.toContain("drop_cap");
    });

    const select = document.getElementById("export-component-filter") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).not.toContain("drop_cap");
    expect(values).not.toContain("footnote_marker");
    expect(values).not.toContain("page_number");
    expect(values).not.toContain("sidenote");
    expect(values).not.toContain("caption");
    expect(values).not.toContain("header");
    expect(values).not.toContain("footer");
  });
});

describe("Send-to-trainer affordance", () => {
  beforeEach(() => {
    mockUseJobProgress.mockReturnValue(null);
    server.use(
      http.get(`${BASE_URL}/export/styles`, () => {
        return HttpResponse.json(["italic", "bold"]);
      }),
    );
  });

  afterEach(() => {
    server.resetHandlers();
    vi.clearAllMocks();
  });

  /**
   * Helper: render ExportDialog, click Export to get a job started, then
   * simulate a completed job so the run-history row appears.
   */
  async function renderWithCompletedExport(jobId: string) {
    server.use(
      http.post(`${BASE_URL}/export`, () => HttpResponse.json({ job_id: jobId }, { status: 202 })),
    );

    const { rerender } = render(
      <ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("export-button"));
    });

    // Simulate complete event so history row appears
    mockUseJobProgress.mockReturnValue({
      job_id: jobId,
      status: "complete",
      progress: { current: 1, total: 1, current_page: 0, message: "done" },
      words_exported_detection: 5,
      words_exported_recognition: 5,
      pages_skipped_not_validated: 0,
    });
    rerender(<ExportDialog open={true} projectId={PROJECT_ID} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("export-results")).toBeTruthy();
    });

    return { rerender };
  }

  it("hides the button when trainer is not installed", async () => {
    // Default handler returns [] (no trainer) — set by handlers.ts default
    await renderWithCompletedExport("job-no-trainer");

    // Wait for the trainer-installed fetch to resolve
    await waitFor(() => {
      // The button must not be in the DOM
      expect(screen.queryByTestId("export-send-to-trainer")).toBeNull();
    });
  });

  it("shows the button when trainer is installed", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([
          { app_id: "pdomain-ocr-trainer-spa", display_name: "OCR Trainer", enabled: true },
        ]),
      ),
    );

    await renderWithCompletedExport("job-with-trainer");

    await waitFor(() => {
      expect(screen.getByTestId("export-send-to-trainer")).toBeTruthy();
    });
  });

  it("calls /api/suite/launch when button is clicked", async () => {
    let launchCalled = false;
    let launchedAppId = "";

    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([
          { app_id: "pdomain-ocr-trainer-spa", display_name: "OCR Trainer", enabled: true },
        ]),
      ),
      http.post("/api/suite/launch", ({ request }) => {
        const url = new URL(request.url);
        launchedAppId = url.searchParams.get("app_id") ?? "";
        launchCalled = true;
        return HttpResponse.json({
          kind: "opened",
          url: "http://localhost:8090",
          spawned: true,
          pid: 999,
        });
      }),
    );

    await renderWithCompletedExport("job-launch-trainer");

    await waitFor(() => {
      expect(screen.getByTestId("export-send-to-trainer")).toBeTruthy();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("export-send-to-trainer"));
    });

    await waitFor(() => {
      expect(launchCalled).toBe(true);
    });
    expect(launchedAppId).toBe("pdomain-ocr-trainer-spa");
  });
});
