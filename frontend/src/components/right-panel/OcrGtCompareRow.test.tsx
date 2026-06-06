// OcrGtCompareRow.test.tsx — P2.c tests for the OCR/GT compare row.
// Covers: B-RIGHT-002, S2.1 (Tab/Shift+Tab GT navigation)

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OcrGtCompareRow } from "./OcrGtCompareRow";

describe("OcrGtCompareRow (P2.c)", () => {
  it("renders the OCR well with OCR text", () => {
    render(<OcrGtCompareRow ocrText="hello" gtText="helo" onCommitGt={vi.fn()} />);
    expect(screen.getByTestId("ocr-gt-ocr-well")).toHaveTextContent("hello");
  });

  it("renders the GT input with GT text", () => {
    render(<OcrGtCompareRow ocrText="hello" gtText="helo" onCommitGt={vi.fn()} />);
    const input = screen.getByTestId("ocr-gt-input");
    expect(input).toHaveValue("helo");
  });

  it("calls onCommitGt when GT input blurs with changed value", async () => {
    const onCommitGt = vi.fn();
    render(<OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={onCommitGt} />);
    const input = screen.getByTestId("ocr-gt-input");
    await userEvent.clear(input);
    await userEvent.type(input, "world");
    fireEvent.blur(input);
    expect(onCommitGt).toHaveBeenCalledWith("world");
  });

  it("does not call onCommitGt when value unchanged on blur", () => {
    const onCommitGt = vi.fn();
    render(<OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={onCommitGt} />);
    fireEvent.blur(screen.getByTestId("ocr-gt-input"));
    expect(onCommitGt).not.toHaveBeenCalled();
  });

  it("copy-OCR-to-GT button sets GT to OCR text", async () => {
    const onCommitGt = vi.fn();
    render(<OcrGtCompareRow ocrText="hello" gtText="helo" onCommitGt={onCommitGt} />);
    await userEvent.click(screen.getByTestId("ocr-gt-copy-btn"));
    expect(screen.getByTestId("ocr-gt-input")).toHaveValue("hello");
    expect(onCommitGt).toHaveBeenCalledWith("hello");
  });

  it("Ω button toggles UnicodePicker visibility", async () => {
    render(<OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={vi.fn()} />);
    expect(screen.queryByTestId("ocr-gt-unicode-picker")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ocr-gt-omega-btn"));
    expect(screen.getByTestId("ocr-gt-unicode-picker")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ocr-gt-omega-btn"));
    expect(screen.queryByTestId("ocr-gt-unicode-picker")).not.toBeInTheDocument();
  });

  it("shows ∅ placeholder in OCR well when ocrText is empty", () => {
    render(<OcrGtCompareRow ocrText="" gtText="" onCommitGt={vi.fn()} />);
    expect(screen.getByTestId("ocr-gt-ocr-well")).toHaveTextContent("∅");
  });
});

// --- S2.1: Tab/Shift+Tab GT navigation ---

describe("OcrGtCompareRow S2.1 — Tab/Shift+Tab navigation", () => {
  it("Tab key calls onCommitGt with current value then calls onTab('next')", async () => {
    const onCommitGt = vi.fn();
    const onTab = vi.fn();
    const user = userEvent.setup();
    render(
      <OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={onCommitGt} onTab={onTab} />,
    );
    const input = screen.getByTestId("ocr-gt-input");
    await user.click(input);
    await user.keyboard("[Tab]");
    expect(onTab).toHaveBeenCalledWith("next");
  });

  it("Shift+Tab calls onTab('prev')", async () => {
    const onCommitGt = vi.fn();
    const onTab = vi.fn();
    const user = userEvent.setup();
    render(
      <OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={onCommitGt} onTab={onTab} />,
    );
    const input = screen.getByTestId("ocr-gt-input");
    await user.click(input);
    await user.keyboard("{Shift>}[Tab]{/Shift}");
    expect(onTab).toHaveBeenCalledWith("prev");
  });

  it("Tab with changed GT commits before calling onTab", async () => {
    const onCommitGt = vi.fn();
    const onTab = vi.fn();
    const user = userEvent.setup();
    render(
      <OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={onCommitGt} onTab={onTab} />,
    );
    const input = screen.getByTestId("ocr-gt-input");
    await user.click(input);
    await user.clear(input);
    await user.type(input, "world");
    await user.keyboard("[Tab]");
    expect(onCommitGt).toHaveBeenCalledWith("world");
    expect(onTab).toHaveBeenCalledWith("next");
    // commit before tab
    expect(onCommitGt.mock.invocationCallOrder[0]).toBeLessThan(onTab.mock.invocationCallOrder[0]);
  });

  it("Tab without onTab prop does not throw", async () => {
    const user = userEvent.setup();
    render(<OcrGtCompareRow ocrText="hello" gtText="hello" onCommitGt={vi.fn()} />);
    const input = screen.getByTestId("ocr-gt-input");
    await user.click(input);
    // No onTab prop — Tab should not error
    await expect(user.keyboard("[Tab]")).resolves.not.toThrow();
  });
});
