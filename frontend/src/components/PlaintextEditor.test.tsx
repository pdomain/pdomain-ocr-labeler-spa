// PlaintextEditor.test.tsx — read-only textarea for GT/OCR plain text panels.
//
// Spec: specs/22-page-surface-wireup.md §3.
// Issue #313 (spec-22-B4).

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlaintextEditor } from "./PlaintextEditor";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makePage(overrides: Partial<PagePayload> = {}): PagePayload {
  return {
    page_text_gt: "",
    page_text_ocr: "",
    ...overrides,
  } as PagePayload;
}

describe("PlaintextEditor", () => {
  it("source='gt' shows page_text_gt", () => {
    const page = makePage({ page_text_gt: "ground truth body", page_text_ocr: "ocr body" });
    render(<PlaintextEditor source="gt" page={page} />);
    const ta = screen.getByTestId("plaintext-editor-gt") as HTMLTextAreaElement;
    expect(ta.value).toBe("ground truth body");
  });

  it("source='ocr' shows page_text_ocr", () => {
    const page = makePage({ page_text_gt: "ground truth body", page_text_ocr: "ocr body" });
    render(<PlaintextEditor source="ocr" page={page} />);
    const ta = screen.getByTestId("plaintext-editor-ocr") as HTMLTextAreaElement;
    expect(ta.value).toBe("ocr body");
  });

  it("textarea is readOnly", () => {
    const page = makePage({ page_text_gt: "x", page_text_ocr: "y" });
    render(<PlaintextEditor source="gt" page={page} />);
    const ta = screen.getByTestId("plaintext-editor-gt") as HTMLTextAreaElement;
    expect(ta.readOnly).toBe(true);
  });

  it("renders empty textarea when page is null/undefined (no crash)", () => {
    const { rerender } = render(<PlaintextEditor source="gt" page={null} />);
    let ta = screen.getByTestId("plaintext-editor-gt") as HTMLTextAreaElement;
    expect(ta.value).toBe("");

    rerender(<PlaintextEditor source="ocr" page={undefined} />);
    ta = screen.getByTestId("plaintext-editor-ocr") as HTMLTextAreaElement;
    expect(ta.value).toBe("");
  });

  it("renders empty textarea when payload field is null", () => {
    const page = makePage({ page_text_gt: null, page_text_ocr: null });
    render(<PlaintextEditor source="gt" page={page} />);
    const ta = screen.getByTestId("plaintext-editor-gt") as HTMLTextAreaElement;
    expect(ta.value).toBe("");
  });
});
