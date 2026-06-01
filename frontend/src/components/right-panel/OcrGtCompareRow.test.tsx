// OcrGtCompareRow.test.tsx — P2.c tests for the OCR/GT compare row.
// Covers: B-RIGHT-002

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
