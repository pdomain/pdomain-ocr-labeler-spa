// GlyphAnnotationPanel.test.tsx — unit tests for the GlyphAnnotationPanel component.
// Spec: specs/20-glyph-annotations.md §5.1
// Issue #269

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { GlyphAnnotationPanel } from "./GlyphAnnotationPanel";
import type { components } from "../../api/types";

type GlyphAnnotationsModel = components["schemas"]["GlyphAnnotationsModel"];

const emptyAnnotations: GlyphAnnotationsModel = {
  ligatures: [],
  long_s_positions: [],
  swash: false,
  source: "human",
};

const withCt: GlyphAnnotationsModel = {
  ligatures: [{ kind: "ct", char_span: [1, 3] }],
  long_s_positions: [],
  swash: false,
  source: "human",
};

describe("GlyphAnnotationPanel", () => {
  it("renders with correct panel testid", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={2}
        gtText="action"
        annotations={emptyAnnotations}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    expect(screen.getByTestId("glyph-panel-0-2")).toBeTruthy();
  });

  it("shows 'Mark reviewed (no marks)' button when annotations have no marks", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="the"
        annotations={null}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    expect(screen.getByTestId("glyph-panel-mark-reviewed-empty")).toBeTruthy();
  });

  it("shows Reset button when annotations are set", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="action"
        annotations={withCt}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    expect(screen.getByTestId("glyph-panel-reset")).toBeTruthy();
  });

  it("calls onSetAnnotations with null when Reset clicked", () => {
    const handleSet = vi.fn();
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="action"
        annotations={withCt}
        predictions={null}
        onSetAnnotations={handleSet}
        onAcceptPrediction={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("glyph-panel-reset"));
    expect(handleSet).toHaveBeenCalledWith(null);
  });

  it("calls onSetAnnotations with empty object when 'Mark reviewed (no marks)' clicked", () => {
    const handleSet = vi.fn();
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="the"
        annotations={null}
        predictions={null}
        onSetAnnotations={handleSet}
        onAcceptPrediction={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("glyph-panel-mark-reviewed-empty"));
    expect(handleSet).toHaveBeenCalledWith(
      expect.objectContaining({ ligatures: [], long_s_positions: [], swash: false }),
    );
  });

  it("renders swash checkbox with correct testid", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={1}
        wordIndex={3}
        gtText="Test"
        annotations={emptyAnnotations}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    expect(screen.getByTestId("glyph-panel-swash-checkbox")).toBeTruthy();
  });

  it("renders add-ligature button with correct testid", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="action"
        annotations={emptyAnnotations}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    expect(screen.getByTestId("glyph-panel-add-ligature")).toBeTruthy();
  });

  it("renders char-span cells for each character of gtText", () => {
    render(
      <GlyphAnnotationPanel
        lineIndex={0}
        wordIndex={0}
        gtText="act"
        annotations={emptyAnnotations}
        predictions={null}
        onSetAnnotations={vi.fn()}
        onAcceptPrediction={vi.fn()}
      />,
    );
    // "act" has 3 chars → 3 cells
    expect(screen.getByTestId("glyph-panel-charspan-cell-0")).toBeTruthy();
    expect(screen.getByTestId("glyph-panel-charspan-cell-1")).toBeTruthy();
    expect(screen.getByTestId("glyph-panel-charspan-cell-2")).toBeTruthy();
  });
});
