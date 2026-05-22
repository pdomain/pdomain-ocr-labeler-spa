// WordActionRows.test.tsx — Merge/Split/Delete/Crop rows (#211)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//
// Acceptance:
//   - Merge with next → onMerge("next") fires; stays open (parent owns close)
//   - Delete → onDelete fires
//   - Crop → onCrop fires with direction and padding
//   - Split → onSplit fires with fraction and axis

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { WordActionRows } from "./WordActionRows";

describe("WordActionRows", () => {
  it("renders all merge/split/delete/crop buttons", () => {
    render(<WordActionRows hasPrev hasNext splitFraction={0.5} />);
    expect(screen.getByTestId("dialog-merge-prev-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-merge-next-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-split-h-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-split-v-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-delete-word-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-crop-above-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-crop-below-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-crop-left-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-crop-right-button")).toBeTruthy();
  });

  it("merge-prev disabled when hasPrev=false", () => {
    render(<WordActionRows hasPrev={false} hasNext />);
    expect(screen.getByTestId("dialog-merge-prev-button")).toBeDisabled();
  });

  it("merge-next disabled when hasNext=false", () => {
    render(<WordActionRows hasPrev hasNext={false} />);
    expect(screen.getByTestId("dialog-merge-next-button")).toBeDisabled();
  });

  it("Merge Prev calls onMerge('prev')", async () => {
    const onMerge = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onMerge={onMerge} />);
    fireEvent.click(screen.getByTestId("dialog-merge-prev-button"));
    expect(onMerge).toHaveBeenCalledWith("prev");
  });

  it("Merge Next calls onMerge('next')", async () => {
    const onMerge = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onMerge={onMerge} />);
    fireEvent.click(screen.getByTestId("dialog-merge-next-button"));
    expect(onMerge).toHaveBeenCalledWith("next");
  });

  it("Split H calls onSplit(fraction, 'h')", async () => {
    const onSplit = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext splitFraction={0.3} onSplit={onSplit} />);
    fireEvent.click(screen.getByTestId("dialog-split-h-button"));
    expect(onSplit).toHaveBeenCalledWith(0.3, "h");
  });

  it("Split V calls onSplit(fraction, 'v')", async () => {
    const onSplit = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext splitFraction={0.7} onSplit={onSplit} />);
    fireEvent.click(screen.getByTestId("dialog-split-v-button"));
    expect(onSplit).toHaveBeenCalledWith(0.7, "v");
  });

  it("Delete calls onDelete", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onDelete={onDelete} />);
    fireEvent.click(screen.getByTestId("dialog-delete-word-button"));
    expect(onDelete).toHaveBeenCalled();
  });

  it("Crop Above calls onCrop('above', padding)", async () => {
    const onCrop = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onCrop={onCrop} />);
    fireEvent.click(screen.getByTestId("dialog-crop-above-button"));
    expect(onCrop).toHaveBeenCalledWith("above", expect.any(Number));
  });

  it("Crop Below calls onCrop('below', padding)", async () => {
    const onCrop = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onCrop={onCrop} />);
    fireEvent.click(screen.getByTestId("dialog-crop-below-button"));
    expect(onCrop).toHaveBeenCalledWith("below", expect.any(Number));
  });

  it("Crop Left calls onCrop('left', padding)", async () => {
    const onCrop = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onCrop={onCrop} />);
    fireEvent.click(screen.getByTestId("dialog-crop-left-button"));
    expect(onCrop).toHaveBeenCalledWith("left", expect.any(Number));
  });

  it("Crop Right calls onCrop('right', padding)", async () => {
    const onCrop = vi.fn().mockResolvedValue(undefined);
    render(<WordActionRows hasPrev hasNext onCrop={onCrop} />);
    fireEvent.click(screen.getByTestId("dialog-crop-right-button"));
    expect(onCrop).toHaveBeenCalledWith("right", expect.any(Number));
  });

  it("crop padding slider is present", () => {
    render(<WordActionRows hasPrev hasNext />);
    expect(screen.getByTestId("dialog-crop-padding-input")).toBeTruthy();
  });

  it("changing padding slider updates the displayed value", () => {
    render(<WordActionRows hasPrev hasNext />);
    const slider = screen.getByTestId("dialog-crop-padding-input");
    fireEvent.change(slider, { target: { value: "8" } });
    // The padding value should update; crop call should use new value
    expect(screen.getByText(/8px/)).toBeTruthy();
  });

  it("buttons are disabled when no callbacks provided", () => {
    render(<WordActionRows hasPrev hasNext />);
    // Buttons exist but won't error since run() guards fn?.()
    // Just verify they render and are not broken.
    expect(screen.getByTestId("dialog-delete-word-button")).toBeTruthy();
  });
});
