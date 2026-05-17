// WordTagRow.test.tsx — Style/Component tag row (#212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      docs/architecture/07-word-edit-dialog.md §3.3
//
// Acceptance:
//   - dialog-style-select, dialog-scope-select, dialog-apply-style-button present
//   - dialog-component-select, dialog-apply-component-button, dialog-clear-component-button present
//   - Apply Style fires onApplyStyle with selected style+scope
//   - Apply Component fires onApplyComponent(component, true)
//   - Clear Component fires onApplyComponent(component, false)

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { WordTagRow } from "./WordTagRow";

const STYLES = ["italic", "bold", "small_caps"];
const COMPONENTS = ["footnote", "drop_cap"];

describe("WordTagRow", () => {
  it("renders all testid elements", () => {
    render(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    expect(screen.getByTestId("dialog-style-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-scope-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-component-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-style-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-component-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-clear-component-button")).toBeTruthy();
  });

  it("style select defaults to first option", () => {
    render(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    const sel = screen.getByTestId("dialog-style-select");
    expect(sel.value).toBe("italic");
  });

  it("scope select defaults to 'whole'", () => {
    render(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    const sel = screen.getByTestId("dialog-scope-select");
    expect(sel.value).toBe("whole");
  });

  it("Apply Style fires onApplyStyle with current style+scope", async () => {
    const onApplyStyle = vi.fn().mockResolvedValue(undefined);
    render(
      <WordTagRow
        styleOptions={STYLES}
        componentOptions={COMPONENTS}
        onApplyStyle={onApplyStyle}
      />,
    );
    fireEvent.change(screen.getByTestId("dialog-style-select"), { target: { value: "bold" } });
    fireEvent.change(screen.getByTestId("dialog-scope-select"), { target: { value: "part" } });
    fireEvent.click(screen.getByTestId("dialog-apply-style-button"));
    expect(onApplyStyle).toHaveBeenCalledWith("bold", "part");
  });

  it("Apply Component fires onApplyComponent(component, true)", async () => {
    const onApplyComponent = vi.fn().mockResolvedValue(undefined);
    render(
      <WordTagRow
        styleOptions={STYLES}
        componentOptions={COMPONENTS}
        onApplyComponent={onApplyComponent}
      />,
    );
    fireEvent.change(screen.getByTestId("dialog-component-select"), {
      target: { value: "drop_cap" },
    });
    fireEvent.click(screen.getByTestId("dialog-apply-component-button"));
    expect(onApplyComponent).toHaveBeenCalledWith("drop_cap", true);
  });

  it("Clear Component fires onApplyComponent(component, false)", async () => {
    const onApplyComponent = vi.fn().mockResolvedValue(undefined);
    render(
      <WordTagRow
        styleOptions={STYLES}
        componentOptions={COMPONENTS}
        onApplyComponent={onApplyComponent}
      />,
    );
    fireEvent.click(screen.getByTestId("dialog-clear-component-button"));
    expect(onApplyComponent).toHaveBeenCalledWith(COMPONENTS[0], false);
  });

  it("works without callbacks (no error)", () => {
    render(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    fireEvent.click(screen.getByTestId("dialog-apply-style-button"));
    fireEvent.click(screen.getByTestId("dialog-apply-component-button"));
    fireEvent.click(screen.getByTestId("dialog-clear-component-button"));
    // no error thrown
    expect(screen.getByTestId("dialog-apply-style-button")).toBeTruthy();
  });
});
