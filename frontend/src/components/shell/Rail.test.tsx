// Rail.test.tsx — Tests for the Rail target/mode selector panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Rail } from "./Rail";
import { railStore } from "../../stores/rail-store";

describe("Rail — target + mode selectors (Slice 10)", () => {
  beforeEach(() => {
    railStore.reset();
    localStorage.clear();
  });

  it("renders the rail with data-testid", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail")).toBeInTheDocument();
  });

  it("renders B / L / W target buttons", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-target-block")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-line")).toBeInTheDocument();
    expect(screen.getByTestId("rail-target-word")).toBeInTheDocument();
  });

  it("renders V / R / A / E mode buttons", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-mode-view")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-region")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-annotate")).toBeInTheDocument();
    expect(screen.getByTestId("rail-mode-erase")).toBeInTheDocument();
  });

  it("active target button reflects initial store state (word)", () => {
    render(<Rail />);
    const wordBtn = screen.getByTestId("rail-target-word");
    expect(wordBtn).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-target-block")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking B target button updates store to block", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(railStore.getState().target).toBe("block");
  });

  it("clicking L target button updates store to line", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-line"));
    expect(railStore.getState().target).toBe("line");
  });

  it("clicking active target re-renders with that target still active", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-block"));
    expect(screen.getByTestId("rail-target-block")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-target-word")).not.toHaveAttribute("data-active", "true");
  });

  it("clicking a mode button updates store mode", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-mode-annotate"));
    expect(railStore.getState().mode).toBe("annotate");
  });

  it("active mode button reflects store state", () => {
    render(<Rail />);
    expect(screen.getByTestId("rail-mode-view")).toHaveAttribute("data-active", "true");
    fireEvent.click(screen.getByTestId("rail-mode-erase"));
    expect(screen.getByTestId("rail-mode-erase")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("rail-mode-view")).not.toHaveAttribute("data-active", "true");
  });

  it("rail container uses bg-bg-surface not bg-background", () => {
    render(<Rail />);
    const rail = screen.getByTestId("rail");
    expect(rail.className).toContain("bg-bg-surface");
    expect(rail.className).not.toContain("bg-background");
  });

  it("active target button has layer-color border class", () => {
    render(<Rail />);
    // Default active is 'word'
    const wordBtn = screen.getByTestId("rail-target-word");
    expect(wordBtn.className).toContain("border-layer-word");
    // Block not active — should not have layer-block border
    const blockBtn = screen.getByTestId("rail-target-block");
    expect(blockBtn.className).not.toContain("border-layer-block");
  });

  it("switching target updates layer-color border to new target", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-block"));
    const blockBtn = screen.getByTestId("rail-target-block");
    expect(blockBtn.className).toContain("border-layer-block");
    const wordBtn = screen.getByTestId("rail-target-word");
    expect(wordBtn.className).not.toContain("border-layer-word");
  });

  it("active line target has border-layer-line class", () => {
    render(<Rail />);
    fireEvent.click(screen.getByTestId("rail-target-line"));
    const lineBtn = screen.getByTestId("rail-target-line");
    expect(lineBtn.className).toContain("border-layer-line");
  });
});
