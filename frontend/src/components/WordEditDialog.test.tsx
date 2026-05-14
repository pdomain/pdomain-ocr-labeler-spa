// WordEditDialog.test.tsx — tests for dialog shell (#209)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md
// Acceptance:
//   - open dialog; next → target shifts to word+1; dialog stays open
//   - Apply&Close fires onApply; × fires onClose
//   - data-testids: dialog-header-label, dialog-apply-close-button, dialog-close-button

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// WordEditDialog now embeds a Konva Stage — mock react-konva to avoid canvas errors in jsdom.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
    [key: string]: unknown;
  }) => (
    <div data-testid={testId ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({
    "data-testid": testId,
    x,
    y,
    width,
    height,
  }: {
    "data-testid"?: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    [key: string]: unknown;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-x={x}
      data-y={y}
      data-width={width}
      data-height={height}
    />
  ),
}));

import { WordEditDialog } from "./WordEditDialog";

const baseTarget = { lineIndex: 2, wordIndex: 1 };
const lineWords = ["alpha", "beta", "gamma", "delta"];

describe("WordEditDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <WordEditDialog
        open={false}
        target={baseTarget}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders header label with correct line/word numbers", () => {
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 3, wordIndex: 2 }}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const label = screen.getByTestId("dialog-header-label");
    expect(label.textContent).toMatch(/Line 3/);
    expect(label.textContent).toMatch(/Word 2/);
  });

  it("renders apply-close and close buttons", () => {
    render(
      <WordEditDialog
        open={true}
        target={baseTarget}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("dialog-apply-close-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-close-button")).toBeTruthy();
  });

  it("Apply&Close button calls onApply then onClose", () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <WordEditDialog
        open={true}
        target={baseTarget}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={onApply}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-apply-close-button"));
    expect(onApply).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("× close button calls only onClose (no apply)", () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <WordEditDialog
        open={true}
        target={baseTarget}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={onApply}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-close-button"));
    expect(onApply).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("Next button calls onNavigate with wordIndex+1; dialog stays open", () => {
    const onNavigate = vi.fn();
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 2, wordIndex: 1 }}
        lineWords={lineWords}
        onNavigate={onNavigate}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-next-button"));
    expect(onNavigate).toHaveBeenCalledWith({ lineIndex: 2, wordIndex: 2 });
    // dialog still rendered
    expect(screen.getByTestId("dialog-header-label")).toBeTruthy();
  });

  it("Prev button calls onNavigate with wordIndex-1", () => {
    const onNavigate = vi.fn();
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 2, wordIndex: 2 }}
        lineWords={lineWords}
        onNavigate={onNavigate}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-prev-button"));
    expect(onNavigate).toHaveBeenCalledWith({ lineIndex: 2, wordIndex: 1 });
  });

  it("Prev disabled at word 0", () => {
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 2, wordIndex: 0 }}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("dialog-prev-button")).toBeDisabled();
  });

  it("Next disabled at last word", () => {
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 2, wordIndex: lineWords.length - 1 }}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("dialog-next-button")).toBeDisabled();
  });

  it("shows 3-column preview: prev word, current word (highlighted), next word", () => {
    render(
      <WordEditDialog
        open={true}
        target={{ lineIndex: 2, wordIndex: 1 }}
        lineWords={["alpha", "beta", "gamma", "delta"]}
        onNavigate={vi.fn()}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("dialog-prev-word")).toHaveTextContent("alpha");
    expect(screen.getByTestId("dialog-current-word")).toHaveTextContent("beta");
    expect(screen.getByTestId("dialog-next-word")).toHaveTextContent("gamma");
  });

  it("backdrop click calls onClose (no apply)", () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <WordEditDialog
        open={true}
        target={baseTarget}
        lineWords={lineWords}
        onNavigate={vi.fn()}
        onApply={onApply}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-backdrop"));
    expect(onApply).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
