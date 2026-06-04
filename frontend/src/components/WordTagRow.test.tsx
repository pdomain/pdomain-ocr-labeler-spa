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
//   - Without explicit styleOptions/componentOptions, canonical vocab is used
//     (not the former hardcoded non-canonical defaults).

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WordTagRow } from "./WordTagRow";

// Non-canonical values that MUST NOT appear when no props are given.
const NON_CANONICAL_STYLES = ["italic", "small_caps", "bold_italic", "antiqua", "gesperrt"];
const NON_CANONICAL_COMPONENTS = ["footnote", "drop_cap", "sidenote", "page_number", "catchword"];

// Canonical values that MUST appear when no props are given (from FALLBACK_* in useLabelVocabulary).
const CANONICAL_STYLE = "italics"; // canonical spelling — note: NOT "italic"
const CANONICAL_COMPONENT = "footnote marker"; // canonical — NOT "footnote" or "footnote_marker"
const CANONICAL_COMPONENT_2 = "drop cap"; // canonical — NOT "drop_cap"

// Explicit override props used by tests that don't care about canonical vocab.
const STYLES = ["italic", "bold", "small_caps"];
const COMPONENTS = ["footnote", "drop_cap"];

// Wrap any render that needs a QueryClient (i.e. when WordTagRow calls useLabelVocabulary).
function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

function renderWithQC(ui: React.ReactElement) {
  return render(ui, { wrapper: makeWrapper() });
}

// ---------------------------------------------------------------------------
// Existing tests — explicit styleOptions/componentOptions overrides
// These pass props so the hook fallback is bypassed; they must still pass.
// ---------------------------------------------------------------------------

describe("WordTagRow — explicit props override", () => {
  it("renders all testid elements", () => {
    renderWithQC(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    expect(screen.getByTestId("dialog-style-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-scope-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-component-select")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-style-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-apply-component-button")).toBeTruthy();
    expect(screen.getByTestId("dialog-clear-component-button")).toBeTruthy();
  });

  it("style select defaults to first option", () => {
    renderWithQC(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    const sel = screen.getByTestId("dialog-style-select") as HTMLSelectElement;
    expect(sel.value).toBe("italic");
  });

  it("scope select defaults to 'whole'", () => {
    renderWithQC(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    const sel = screen.getByTestId("dialog-scope-select") as HTMLSelectElement;
    expect(sel.value).toBe("whole");
  });

  it("Apply Style fires onApplyStyle with current style+scope", async () => {
    const onApplyStyle = vi.fn().mockResolvedValue(undefined);
    renderWithQC(
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
    renderWithQC(
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
    renderWithQC(
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
    renderWithQC(<WordTagRow styleOptions={STYLES} componentOptions={COMPONENTS} />);
    fireEvent.click(screen.getByTestId("dialog-apply-style-button"));
    fireEvent.click(screen.getByTestId("dialog-apply-component-button"));
    fireEvent.click(screen.getByTestId("dialog-clear-component-button"));
    // no error thrown
    expect(screen.getByTestId("dialog-apply-style-button")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// New tests — canonical vocab sourced from useLabelVocabulary when no props
// ---------------------------------------------------------------------------

describe("WordTagRow — canonical vocab (no explicit props)", () => {
  it("style select contains canonical 'italics' (not legacy 'italic')", () => {
    // RED: old code uses DEFAULT_STYLES which has "italic" not "italics".
    // GREEN: hook fallback FALLBACK_STYLES has "italics".
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-style-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    expect(options).toContain(CANONICAL_STYLE);
    expect(options).not.toContain("italic"); // non-canonical legacy value
  });

  it("style select does NOT contain non-canonical 'small_caps'", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-style-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    expect(options).not.toContain("small_caps");
    expect(options).toContain("small caps"); // canonical form
  });

  it("style select contains only canonical values (no underscore legacy labels)", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-style-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    for (const bad of NON_CANONICAL_STYLES) {
      expect(options).not.toContain(bad);
    }
  });

  it("component select contains canonical 'footnote marker' (not legacy 'footnote' or 'footnote_marker')", () => {
    // RED: old code uses DEFAULT_COMPONENTS which has "footnote"/"footnote_marker".
    // GREEN: hook fallback FALLBACK_COMPONENTS has "footnote marker".
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-component-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    expect(options).toContain(CANONICAL_COMPONENT);
    expect(options).not.toContain("footnote");
    expect(options).not.toContain("footnote_marker");
  });

  it("component select contains canonical 'drop cap' (not legacy 'drop_cap')", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-component-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    expect(options).toContain(CANONICAL_COMPONENT_2);
    expect(options).not.toContain("drop_cap");
  });

  it("component select contains only canonical values (no underscore or missing-space legacy labels)", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-component-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    for (const bad of NON_CANONICAL_COMPONENTS) {
      expect(options).not.toContain(bad);
    }
  });

  it("style select default value is a canonical label (not an underscore legacy label)", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-style-select") as HTMLSelectElement;
    // The selected value must NOT be any known non-canonical value.
    for (const bad of NON_CANONICAL_STYLES) {
      expect(sel.value).not.toBe(bad);
    }
  });

  it("component select default value is a canonical label", () => {
    renderWithQC(<WordTagRow />);
    const sel = screen.getByTestId("dialog-component-select") as HTMLSelectElement;
    for (const bad of NON_CANONICAL_COMPONENTS) {
      expect(sel.value).not.toBe(bad);
    }
  });
});
