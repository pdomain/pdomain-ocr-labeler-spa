// PageActionsUndo.test.tsx — undo/redo buttons + "Reload" rename (slice H-C).
//
// Spec: docs/specs/2026-06-12-event-store-undo.md
//   U-3: undo-button / redo-button disabled per history flags and while busy.
//   U-7: "Load Page" renamed to "Reload"; `load-page-button` testid unchanged.

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PageActions } from "./PageActions";

describe("PageActions: undo/redo buttons (H-C)", () => {
  it("renders undo-button and redo-button testids", () => {
    render(<PageActions />);
    expect(screen.getByTestId("undo-button")).toBeInTheDocument();
    expect(screen.getByTestId("redo-button")).toBeInTheDocument();
  });

  it("both disabled by default (no history)", () => {
    render(<PageActions />);
    expect(screen.getByTestId("undo-button")).toBeDisabled();
    expect(screen.getByTestId("redo-button")).toBeDisabled();
  });

  it("undo enabled when undoAvailable; redo stays disabled", () => {
    render(<PageActions undoAvailable={true} />);
    expect(screen.getByTestId("undo-button")).not.toBeDisabled();
    expect(screen.getByTestId("redo-button")).toBeDisabled();
  });

  it("redo enabled when redoAvailable", () => {
    render(<PageActions redoAvailable={true} />);
    expect(screen.getByTestId("redo-button")).not.toBeDisabled();
  });

  it("both disabled while busy even when available (U-3)", () => {
    render(<PageActions isBusy={true} undoAvailable={true} redoAvailable={true} />);
    expect(screen.getByTestId("undo-button")).toBeDisabled();
    expect(screen.getByTestId("redo-button")).toBeDisabled();
  });

  it("click fires onUndo / onRedo", () => {
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    render(
      <PageActions undoAvailable={true} redoAvailable={true} onUndo={onUndo} onRedo={onRedo} />,
    );
    fireEvent.click(screen.getByTestId("undo-button"));
    expect(onUndo).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId("redo-button"));
    expect(onRedo).toHaveBeenCalledOnce();
  });

  it("disabled undo does NOT fire onUndo", () => {
    const onUndo = vi.fn();
    render(<PageActions undoAvailable={false} onUndo={onUndo} />);
    fireEvent.click(screen.getByTestId("undo-button"));
    expect(onUndo).not.toHaveBeenCalled();
  });
});

describe("PageActions: Load Page → Reload rename (U-7)", () => {
  it("load-page-button testid is unchanged and labeled 'Reload'", () => {
    render(<PageActions />);
    const btn = screen.getByTestId("load-page-button");
    expect(btn).toHaveTextContent("Reload");
    expect(btn).not.toHaveTextContent("Load Page");
  });

  it("tooltip no longer claims to discard unsaved edits", () => {
    render(<PageActions />);
    const btn = screen.getByTestId("load-page-button");
    expect(btn.getAttribute("title") ?? "").not.toMatch(/unsaved|discard/i);
  });
});
