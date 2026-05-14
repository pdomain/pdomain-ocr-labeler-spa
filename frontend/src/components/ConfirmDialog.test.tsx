// ConfirmDialog.test.tsx — tests for the destructive-action confirmation dialog.
// Issue #236
//
// Acceptance:
//   - Renders with message prop when open=true
//   - Does not render when open=false
//   - onConfirm fires when Confirm button clicked
//   - onCancel fires when Cancel button clicked
//   - data-testid: confirm-dialog, confirm-dialog-confirm, confirm-dialog-cancel

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog (#236)", () => {
  it("renders when open=true", () => {
    render(
      <ConfirmDialog
        open={true}
        message="This will discard changes."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
    expect(screen.getByText("This will discard changes.")).toBeInTheDocument();
  });

  it("does not render when open=false", () => {
    render(<ConfirmDialog open={false} message="msg" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
  });

  it("onConfirm fires when Confirm clicked", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open={true} message="msg" onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId("confirm-dialog-confirm"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("onCancel fires when Cancel clicked", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog open={true} message="msg" onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByTestId("confirm-dialog-cancel"));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("renders custom title and labels", () => {
    render(
      <ConfirmDialog
        open={true}
        message="Proceed?"
        title="Warning"
        confirmLabel="Yes, proceed"
        cancelLabel="Go back"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-dialog-confirm")).toHaveTextContent("Yes, proceed");
    expect(screen.getByTestId("confirm-dialog-cancel")).toHaveTextContent("Go back");
  });
});
