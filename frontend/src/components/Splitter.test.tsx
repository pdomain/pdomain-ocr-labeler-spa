// Splitter.test.tsx — unit tests for the horizontal Splitter.
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §9 (Splitter).
// Issue #310 (spec-22-B1)

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Splitter } from "./Splitter";
import { useUiPrefs } from "../stores/ui-prefs";

// Helpers --------------------------------------------------------------------

function resetPrefs() {
  useUiPrefs.setState({
    lineFilter: null,
    layerVisibility: { paragraph: true, line: true, word: true },
    splitterRatio: 0.5,
    selectionMode: "paragraph",
  });
}

/**
 * Stub the container's bounding rect so that the splitter's pointer-math has
 * deterministic geometry. jsdom does not lay out elements, so
 * `getBoundingClientRect` returns zeros by default.
 */
function stubContainerRect(width = 1000, left = 0) {
  const original = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = () => ({
    x: left,
    y: 0,
    left,
    right: left + width,
    top: 0,
    bottom: 100,
    width,
    height: 100,
    toJSON() {
      return {};
    },
  });
  return () => {
    Element.prototype.getBoundingClientRect = original;
  };
}

// Tests ----------------------------------------------------------------------

describe("Splitter", () => {
  beforeEach(() => {
    resetPrefs();
  });

  it("renders left and right panes plus a divider", () => {
    render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
    expect(screen.getByTestId("splitter")).toBeTruthy();
    expect(screen.getByTestId("splitter-left")).toBeTruthy();
    expect(screen.getByTestId("splitter-right")).toBeTruthy();
    expect(screen.getByTestId("splitter-divider")).toBeTruthy();
  });

  it("initial pane widths reflect splitterRatio from the store", () => {
    useUiPrefs.setState({ splitterRatio: 0.4 });
    render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
    const left = screen.getByTestId("splitter-left");
    expect(left.style.width).toBe("40%");
  });

  it("dragging the divider updates splitterRatio", () => {
    const restore = stubContainerRect(1000, 0);
    try {
      render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
      const divider = screen.getByTestId("splitter-divider");

      fireEvent.mouseDown(divider, { clientX: 500 });
      fireEvent.mouseMove(window, { clientX: 700 });
      fireEvent.mouseUp(window, { clientX: 700 });

      // 700 / 1000 = 0.7, within clamp range
      expect(useUiPrefs.getState().splitterRatio).toBeCloseTo(0.7, 5);
    } finally {
      restore();
    }
  });

  it("clamps ratio to a minimum of 0.2 when dragging far left", () => {
    const restore = stubContainerRect(1000, 0);
    try {
      render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
      const divider = screen.getByTestId("splitter-divider");

      fireEvent.mouseDown(divider, { clientX: 500 });
      fireEvent.mouseMove(window, { clientX: 50 });
      fireEvent.mouseUp(window, { clientX: 50 });

      expect(useUiPrefs.getState().splitterRatio).toBe(0.2);
    } finally {
      restore();
    }
  });

  it("clamps ratio to a maximum of 0.8 when dragging far right", () => {
    const restore = stubContainerRect(1000, 0);
    try {
      render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
      const divider = screen.getByTestId("splitter-divider");

      fireEvent.mouseDown(divider, { clientX: 500 });
      fireEvent.mouseMove(window, { clientX: 999 });
      fireEvent.mouseUp(window, { clientX: 999 });

      expect(useUiPrefs.getState().splitterRatio).toBe(0.8);
    } finally {
      restore();
    }
  });

  it("does not update ratio when mouse moves without a prior mouseDown", () => {
    const restore = stubContainerRect(1000, 0);
    try {
      render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
      fireEvent.mouseMove(window, { clientX: 700 });
      expect(useUiPrefs.getState().splitterRatio).toBe(0.5);
    } finally {
      restore();
    }
  });

  it("stops updating after mouseUp releases the drag", () => {
    const restore = stubContainerRect(1000, 0);
    try {
      render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
      const divider = screen.getByTestId("splitter-divider");

      fireEvent.mouseDown(divider, { clientX: 500 });
      fireEvent.mouseMove(window, { clientX: 600 });
      fireEvent.mouseUp(window, { clientX: 600 });
      expect(useUiPrefs.getState().splitterRatio).toBeCloseTo(0.6, 5);

      // Subsequent movements without a new mousedown must not move the ratio.
      fireEvent.mouseMove(window, { clientX: 750 });
      expect(useUiPrefs.getState().splitterRatio).toBeCloseTo(0.6, 5);
    } finally {
      restore();
    }
  });

  it("double-click on the divider resets ratio to 0.5", () => {
    useUiPrefs.setState({ splitterRatio: 0.7 });
    render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
    const divider = screen.getByTestId("splitter-divider");

    fireEvent.doubleClick(divider);

    expect(useUiPrefs.getState().splitterRatio).toBe(0.5);
  });

  it("divider exposes a separator role with aria-orientation", () => {
    render(<Splitter direction="horizontal" left={<div>L</div>} right={<div>R</div>} />);
    const divider = screen.getByTestId("splitter-divider");
    expect(divider.getAttribute("role")).toBe("separator");
    expect(divider.getAttribute("aria-orientation")).toBe("vertical");
  });
});
