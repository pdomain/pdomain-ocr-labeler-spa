// Rail.test.tsx — Tests for the Rail target/mode selector panel.
// Covers: B-SHELL-001, B-SHELL-006, B-SHELL-007, B-SHELL-008
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
// Hi-fi gaps P1.d (Gaps 10,11,12), P1.e (Gaps 11,13,15), P1.f (Gap 14).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Rail } from "./Rail";
import { railStore } from "../../stores/rail-store";
import { useUiPrefs } from "../../stores/ui-prefs";

// Silence dialogStore open call (not wired in jsdom tests).
vi.mock("../../stores/dialog-store", () => ({
  dialogStore: { open: vi.fn() },
}));

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
    render(<Rail />);
    expect(screen.getByTestId("rail")).toBeInTheDocument();
  });

  it("rail container uses bg-bg-surface", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail").className).toContain("bg-bg-surface");
  });

  // ── Section labels (Gap 13) ────────────────────────────────────────────────

  it("renders MODE section label", () => {
    render(<Rail />);
    expect(screen.getByText("MODE")).toBeInTheDocument();
  });

  it("renders TARGET section label", () => {
    render(<Rail />);
    expect(screen.getByText("TARGET")).toBeInTheDocument();
  });

  it("renders LAYERS section label", () => {
    render(<Rail />);
    expect(screen.getByText("LAYERS")).toBeInTheDocument();
  });

  // ── Mode icon-cards (P1.d — Gaps 10, 11, 12) ──────────────────────────────

  it("renders all four mode buttons by testid", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-mode-view")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-region")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-annotate")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-erase")).toBeInTheDocument();
  });

  it("mode buttons show text labels (not bare letters)", () => {
    render(<Rail />);
    expect(screen.getByText("View")).toBeInTheDocument();
    expect(screen.getByText("Refine")).toBeInTheDocument();
    expect(screen.getByText("Annotate")).toBeInTheDocument();
    expect(screen.getByText("Erase")).toBeInTheDocument();
  });

  it("active mode button reflects store state (view by default)", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-mode-view")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-mode-region")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking a mode button updates store mode", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-mode-annotate"));
    expect(railStore.getState().mode).toBe("annotate");
  });

  it("active mode button has bgSunk styling class", () => {
    render(<Rail />);
    const viewBtn = screen.getByTestId("rail-mode-view");
    expect(viewBtn.className).toContain("bg-bg-sunk");
  });

  it("switching mode updates active state", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-mode-erase"));
    expect(screen.getByTestId("rail-mode-erase")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-mode-view")).not.toHaveAttribute("data-active", "true");
  });

  // ── Target cells (P1.d + P1.f — Gaps 11, 12, 14) ─────────────────────────

  it("renders all four target buttons (block, para, line, word)", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-target-block")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-para")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-line")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-word")).toBeInTheDocument();
  });

  it("target buttons show text labels", () => {
    render(<Rail />);
    // Use getAllByText since "Block"/"Line"/"Word" also appear in LAYERS section
    expect(screen.getAllByText("Block").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Line").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Word").length).toBeGreaterThanOrEqual(1);
    // "Para" appears in target + layers as "¶Para"
    expect(screen.getByText("Para")).toBeInTheDocument();
  });

  it("active target button reflects initial store state (word)", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-target-word")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-target-block")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking block target updates store to block", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(railStore.getState().target).toBe("block");
  });

  it("clicking para target updates store to para", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-para"));
    expect(railStore.getState().target).toBe("para");
  });

  it("clicking line target updates store to line", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(railStore.getState().target).toBe("line");
  });

  it("active target button has layer-color border class", () => {
    render(<Rail />);
    // Default active is 'word'
    expect(screen.getByTestId("rail-target-word").className).toContain("border-layer-word");
    expect(screen.getByTestId("rail-target-block").className).not.toContain("border-layer-block");
  });

  it("switching to block adds layer-block border", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(screen.getByTestId("rail-target-block").className).toContain("border-layer-block");
    expect(screen.getByTestId("rail-target-word").className).not.toContain("border-layer-word");
  });

  it("switching to line adds layer-line border", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(screen.getByTestId("rail-target-line").className).toContain("border-layer-line");
  });

  it("switching to para adds layer-para border", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-para"));
    expect(screen.getByTestId("rail-target-para").className).toContain("border-layer-para");
  });

  // ── LAYERS visibility toggles (P1.e — Gap 15) ────────────────────────────

  it("renders clickable layer toggles for Block, Para, Line, Word", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-layer-block")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-para")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-line")).toBeInTheDocument();
    expect(screen.getByTestId("rail-layer-word")).toBeInTheDocument();
  });

  it("all layer toggles are enabled by default", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-layer-block")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-para")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-line")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-layer-word")).toHaveAttribute("aria-pressed", "true");
  });

  it("clicking a layer toggle updates layer visibility", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-layer-line"));
    expect(useUiPrefs.getState().layerVisibility.line).toBe(false);
    expect(screen.getByTestId("rail-layer-line")).toHaveAttribute("aria-pressed", "false");
  });

  // ── Footer buttons (P1.e — Gap 15) ────────────────────────────────────────

  it("renders Bulk button in footer", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-bulk-button")).toBeInTheDocument();
    expect(screen.getByText("Bulk")).toBeInTheDocument();
  });

  it("renders Hotkeys button in footer", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-hotkeys-button")).toBeInTheDocument();
    expect(screen.getByText("Hotkeys")).toBeInTheDocument();
  });

  it("Hotkeys button opens hotkey help dialog", async () => {
    const { dialogStore } = await import("../../stores/dialog-store");
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-hotkeys-button"));
    expect(dialogStore.open).toHaveBeenCalledWith("hotkeyHelp");
  });

  // ── Bulk button opens drawer to worklist tab ───────────────────────────────

  it("bulk button opens drawer to worklist tab", async () => {
    useUiPrefs.setState({ drawerOpen: false, drawerTab: "hierarchy" });
    render(<Rail />);
    await userEvent.setup().click(screen.getByTestId("rail-bulk-button"));
    expect(useUiPrefs.getState().drawerOpen).toBe(true);
    expect(useUiPrefs.getState().drawerTab).toBe("worklist");
  });
});
