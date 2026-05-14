// WordRefineNudgeRows.test.tsx — Refine/Nudge/Apply rows (#212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      specs/07-word-edit-dialog.md §3.6, §3.7, §3.8
//
// Acceptance:
//   - Refine calls onRefine
//   - Expand+Refine calls onExpandRefine
//   - Nudge buttons accumulate local deltas
//   - Apply calls onApply with accumulated nudge + refineAfter=false
//   - Apply+Refine calls onApply with refineAfter=true
//   - Reset clears pending nudge and calls onReset
//   - Apply/Reset disabled when nudge is all-zero

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { WordRefineNudgeRows } from "./WordRefineNudgeRows";

describe("WordRefineNudgeRows", () => {
  it("renders all testid buttons", () => {
    render(<WordRefineNudgeRows />);
    expect(screen.getByTestId("dialog-refine-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-expand-refine-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-left-minus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-left-plus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-right-minus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-right-plus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-top-minus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-top-plus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-bottom-minus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-bottom-plus")).toBeTruthy();
    expect(screen.getByTestId("dialog-nudge-display")).toBeTruthy();
    expect(screen.getByTestId("dialog-reset-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-refine-button")).toBeTruthy();
  });

  it("Refine calls onRefine", async () => {
    const onRefine = vi.fn().mockResolvedValue(undefined);
    render(<WordRefineNudgeRows onRefine={onRefine} />);
    fireEvent.click(screen.getByTestId("dialog-refine-button"));
    expect(onRefine).toHaveBeenCalledOnce();
  });

  it("Expand+Refine calls onExpandRefine", async () => {
    const onExpandRefine = vi.fn().mockResolvedValue(undefined);
    render(<WordRefineNudgeRows onExpandRefine={onExpandRefine} />);
    fireEvent.click(screen.getByTestId("dialog-expand-refine-button"));
    expect(onExpandRefine).toHaveBeenCalledOnce();
  });

  it("Apply and Reset disabled when nudge is zero", () => {
    render(<WordRefineNudgeRows />);
    expect(screen.getByTestId("dialog-apply-button")).toBeDisabled();
    expect(screen.getByTestId("dialog-apply-refine-button")).toBeDisabled();
    expect(screen.getByTestId("dialog-reset-button")).toBeDisabled();
  });

  it("nudge display starts at L:0 R:0 T:0 B:0", () => {
    render(<WordRefineNudgeRows />);
    expect(screen.getByTestId("dialog-nudge-display")).toHaveTextContent("L:0 R:0 T:0 B:0");
  });

  it("nudge-left-plus increments left by stepPx", () => {
    render(<WordRefineNudgeRows stepPx={5} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-left-plus"));
    expect(screen.getByTestId("dialog-nudge-display")).toHaveTextContent("L:5");
  });

  it("nudge-left-minus decrements left by stepPx", () => {
    render(<WordRefineNudgeRows stepPx={5} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-left-minus"));
    expect(screen.getByTestId("dialog-nudge-display")).toHaveTextContent("L:-5");
  });

  it("multiple nudges accumulate", () => {
    render(<WordRefineNudgeRows stepPx={5} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-left-plus"));
    fireEvent.click(screen.getByTestId("dialog-nudge-left-plus"));
    fireEvent.click(screen.getByTestId("dialog-nudge-right-minus"));
    // L:10 R:-5 T:0 B:0
    const display = screen.getByTestId("dialog-nudge-display").textContent ?? "";
    expect(display).toContain("L:10");
    expect(display).toContain("R:-5");
  });

  it("Apply calls onApply with accumulated nudge and refineAfter=false", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    render(<WordRefineNudgeRows stepPx={5} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-top-plus"));
    fireEvent.click(screen.getByTestId("dialog-apply-button"));
    expect(onApply).toHaveBeenCalledWith({ left: 0, right: 0, top: 5, bottom: 0 }, false);
  });

  it("Apply+Refine calls onApply with refineAfter=true", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    render(<WordRefineNudgeRows stepPx={5} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-bottom-plus"));
    fireEvent.click(screen.getByTestId("dialog-apply-refine-button"));
    expect(onApply).toHaveBeenCalledWith({ left: 0, right: 0, top: 0, bottom: 5 }, true);
  });

  it("Apply resets nudge to zero after call", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    render(<WordRefineNudgeRows stepPx={5} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-left-plus"));
    fireEvent.click(screen.getByTestId("dialog-apply-button"));
    // Reset happens after the async onApply resolves
    await waitFor(() => {
      expect(screen.getByTestId("dialog-nudge-display")).toHaveTextContent("L:0 R:0 T:0 B:0");
    });
  });

  it("Reset clears nudge and calls onReset", () => {
    const onReset = vi.fn();
    render(<WordRefineNudgeRows stepPx={5} onReset={onReset} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-right-plus"));
    fireEvent.click(screen.getByTestId("dialog-reset-button"));
    expect(screen.getByTestId("dialog-nudge-display")).toHaveTextContent("L:0 R:0 T:0 B:0");
    expect(onReset).toHaveBeenCalledOnce();
  });

  it("Apply/Reset enabled after nudge accumulates", () => {
    render(<WordRefineNudgeRows stepPx={5} />);
    fireEvent.click(screen.getByTestId("dialog-nudge-top-minus"));
    expect(screen.getByTestId("dialog-apply-button")).not.toBeDisabled();
    expect(screen.getByTestId("dialog-reset-button")).not.toBeDisabled();
  });
});
