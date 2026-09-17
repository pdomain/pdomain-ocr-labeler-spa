// Rail.test.tsx — Tests for the Rail target/mode selector panel.
// Covers: B-SHELL-001, B-SHELL-006, B-SHELL-007, B-SHELL-008
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
// Hi-fi gaps P1.d (Gaps 10,11,12), P1.e (Gaps 11,13,15), P1.f (Gap 14).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { Rail } from "./Rail";
import { railStore } from "../../stores/rail-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { server } from "../../test/server";

// Silence dialogStore open call (not wired in jsdom tests).
vi.mock("../../stores/dialog-store", () => ({
  dialogStore: { open: vi.fn() },
}));

// Rail now reads the book review queue (useReviewQueue) for its region
// undecided badge, so every render needs a QueryClientProvider ancestor —
// see the "region undecided badge" describe block below for the tests that
// exercise it directly.
function renderRail(projectId?: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Rail projectId={projectId} />
    </QueryClientProvider>,
  );
}

describe("Rail — target + mode selectors (Slice 10 / P1.d,e,f)", () => {
  beforeEach(() => {
    localStorage.clear(); // clear first so reset() reads the default "word" target
    railStore.reset();
    useUiPrefs.setState({
      layerVisibility: { block: true, paragraph: true, line: true, word: true },
    });
  });

  // ── Container ──────────────────────────────────────────────────────────────

  it("renders the rail with data-testid", () => {
    renderRail();
    expect(screen.getByTestId("rail")).toBeInTheDocument();
  });

  it("rail container uses bg-bg-surface", () => {
    renderRail();
    expect(screen.getByTestId("rail").className).toContain("bg-bg-surface");
  });

  // ── Section labels (Gap 13) ────────────────────────────────────────────────

  it("renders MODE section label", () => {
    renderRail();
    expect(screen.getByText("MODE")).toBeInTheDocument();
  });

  it("renders TARGET section label", () => {
    renderRail();
    expect(screen.getByText("TARGET")).toBeInTheDocument();
  });

  it("renders LAYERS section label", () => {
    renderRail();
    expect(screen.getByText("LAYERS")).toBeInTheDocument();
  });

  // ── Mode icon-cards (P1.d — Gaps 10, 11, 12) ──────────────────────────────

  it("renders all four mode buttons by testid", () => {
    renderRail();
    expect(screen.getByTestId("rail-mode-view")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-region")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-annotate")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-erase")).toBeInTheDocument();
  });

  it("mode buttons show text labels (not bare letters)", () => {
    renderRail();
    expect(screen.getByText("View")).toBeInTheDocument();
    expect(screen.getByText("Refine")).toBeInTheDocument();
    expect(screen.getByText("Annotate")).toBeInTheDocument();
    expect(screen.getByText("Erase")).toBeInTheDocument();
  });

  it("active mode button reflects store state (view by default)", () => {
    renderRail();
    expect(screen.getByTestId("rail-mode-view")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-mode-region")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking a mode button updates store mode", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-mode-annotate"));
    expect(railStore.getState().mode).toBe("annotate");
  });

  it("active mode button has bgSunk styling class", () => {
    renderRail();
    const viewBtn = screen.getByTestId("rail-mode-view");
    expect(viewBtn.className).toContain("bg-bg-sunk");
  });

  it("switching mode updates active state", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-mode-erase"));
    expect(screen.getByTestId("rail-mode-erase")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-mode-view")).not.toHaveAttribute("data-active", "true");
  });

  // ── Target cells (P1.d + P1.f — Gaps 11, 12, 14) ─────────────────────────

  it("renders all five target buttons (block, para, line, word, region)", () => {
    renderRail();
    expect(screen.getByTestId("rail-target-block")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-para")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-line")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-word")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-region")).toBeInTheDocument();
  });

  it("target buttons show text labels", () => {
    renderRail();
    // Use getAllByText since "Block"/"Line"/"Word" also appear in LAYERS section
    expect(screen.getAllByText("Block").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Line").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Word").length).toBeGreaterThanOrEqual(1);
    // "Para" appears in target + layers as "¶Para"
    expect(screen.getByText("Para")).toBeInTheDocument();
  });

  it("active target button reflects initial store state (word)", () => {
    renderRail();
    expect(screen.getByTestId("rail-target-word")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-target-block")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking block target updates store to block", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(railStore.getState().target).toBe("block");
  });

  it("clicking para target updates store to para", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-para"));
    expect(railStore.getState().target).toBe("para");
  });

  it("clicking line target updates store to line", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(railStore.getState().target).toBe("line");
  });

  it("clicking region target updates store to region", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-region"));
    expect(railStore.getState().target).toBe("region");
  });

  it("region target cell reads as active when the target is region", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-region"));
    expect(screen.getByTestId("rail-target-region")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-target-word")).not.toHaveAttribute("data-active", "true");
  });

  it("active target button has layer-color border class", () => {
    renderRail();
    // Default active is 'word'
    expect(screen.getByTestId("rail-target-word").className).toContain("border-layer-word");
    expect(screen.getByTestId("rail-target-block").className).not.toContain("border-layer-block");
  });

  it("switching to block adds layer-block border", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(screen.getByTestId("rail-target-block").className).toContain("border-layer-block");
    expect(screen.getByTestId("rail-target-word").className).not.toContain("border-layer-word");
  });

  it("switching to line adds layer-line border", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(screen.getByTestId("rail-target-line").className).toContain("border-layer-line");
  });

  it("switching to para adds layer-para border", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-para"));
    expect(screen.getByTestId("rail-target-para").className).toContain("border-layer-para");
  });

  // ── SEL-3 bidirectional sync: rail target → uiPrefs.selectionMode ─────────

  it("clicking para target sets selectionMode to 'paragraph'", () => {
    useUiPrefs.setState({ selectionMode: "word" });
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-para"));
    expect(useUiPrefs.getState().selectionMode).toBe("paragraph");
  });

  it("clicking line target sets selectionMode to 'line'", () => {
    useUiPrefs.setState({ selectionMode: "word" });
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(useUiPrefs.getState().selectionMode).toBe("line");
  });

  it("clicking word target sets selectionMode to 'word'", () => {
    useUiPrefs.setState({ selectionMode: "line" });
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-word"));
    expect(useUiPrefs.getState().selectionMode).toBe("word");
  });

  it("clicking block target leaves selectionMode unchanged (no radio counterpart)", () => {
    useUiPrefs.setState({ selectionMode: "line" });
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-block"));
    // railStore.target changes to block
    expect(railStore.getState().target).toBe("block");
    // selectionMode is unchanged — "block" has no radio equivalent
    expect(useUiPrefs.getState().selectionMode).toBe("line");
  });

  it("clicking block target still updates railStore target to block", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(railStore.getState().target).toBe("block");
  });

  // ── LAYERS visibility toggles (P1.e — Gap 15) ────────────────────────────

  it("renders clickable layer toggles for Block, Para, Line, Word", () => {
    renderRail();
    expect(screen.getByTestId("rail-layer-block")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-para")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-line")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-word")).toBeInTheDocument();
  });

  it("all layer toggles are enabled by default", () => {
    renderRail();
    expect(screen.getByTestId("rail-layer-block")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-para")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-line")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-word")).toHaveAttribute("aria-pressed", "true");
  });

  it("clicking a layer toggle updates layer visibility", () => {
    renderRail();
    fireEvent.click(screen.getByTestId("rail-layer-line"));
    expect(useUiPrefs.getState().layerVisibility.line).toBe(false);
    expect(screen.getByTestId("rail-layer-line")).toHaveAttribute("aria-pressed", "false");
  });

  // ── Footer buttons (P1.e — Gap 15) ────────────────────────────────────────

  it("renders Bulk button in footer", () => {
    renderRail();
    expect(screen.getByTestId("rail-bulk-button")).toBeInTheDocument();
    expect(screen.getByText("Bulk")).toBeInTheDocument();
  });

  it("renders Hotkeys button in footer", () => {
    renderRail();
    expect(screen.getByTestId("rail-hotkeys-button")).toBeInTheDocument();
    expect(screen.getByText("Hotkeys")).toBeInTheDocument();
  });

  it("Hotkeys button opens hotkey help dialog", async () => {
    const { dialogStore } = await import("../../stores/dialog-store");
    renderRail();
    fireEvent.click(screen.getByTestId("rail-hotkeys-button"));
    expect(dialogStore.open).toHaveBeenCalledWith("hotkeyHelp");
  });

  // ── Bulk button opens drawer to worklist tab ───────────────────────────────

  it("bulk button opens drawer to worklist tab", async () => {
    useUiPrefs.setState({ drawerOpen: false, drawerTab: "hierarchy" });
    renderRail();
    await userEvent.setup().click(screen.getByTestId("rail-bulk-button"));
    expect(useUiPrefs.getState().drawerOpen).toBe(true);
    expect(useUiPrefs.getState().drawerTab).toBe("worklist");
  });
});

// ─── Region undecided badge (book review queue design) ─────────────────────
// Design: docs/specs/2026-09-17-book-review-queue-design.md "A count stays
// visible" — the region target cell shows the book's undecided count as a
// small badge above 0, and hides it at 0.

describe("Rail — region undecided badge (book review queue)", () => {
  beforeEach(() => {
    localStorage.clear();
    railStore.reset();
    useUiPrefs.setState({
      layerVisibility: { block: true, paragraph: true, line: true, word: true },
    });
  });

  it("shows the undecided count badge when above 0, with an accessible label", async () => {
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({ total_undecided: 12, pages: [], items: [] }),
      ),
    );
    renderRail("proj-1");

    const badge = await screen.findByTestId("rail-region-undecided-badge");
    expect(badge).toHaveTextContent("12");
    expect(badge).toHaveAttribute("aria-label", "12 undecided proposals");
  });

  it("uses singular wording for a count of exactly 1", async () => {
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({ total_undecided: 1, pages: [], items: [] }),
      ),
    );
    renderRail("proj-1");

    const badge = await screen.findByTestId("rail-region-undecided-badge");
    expect(badge).toHaveAttribute("aria-label", "1 undecided proposal");
  });

  it("hides the badge when the count is 0", async () => {
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({ total_undecided: 0, pages: [], items: [] }),
      ),
    );
    renderRail("proj-1");

    // Give the query a tick to resolve before asserting absence, so this
    // isn't just "hasn't rendered yet".
    await waitFor(() => expect(screen.getByTestId("rail-target-region")).toBeInTheDocument());
    expect(screen.queryByTestId("rail-region-undecided-badge")).not.toBeInTheDocument();
  });

  it("hides the badge without a projectId (the query stays disabled)", () => {
    renderRail(undefined);
    expect(screen.queryByTestId("rail-region-undecided-badge")).not.toBeInTheDocument();
  });
});
