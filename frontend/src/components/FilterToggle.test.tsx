// FilterToggle.test.tsx — three-state cycling toggle for match filter.
//
// Spec: specs/22-page-surface-wireup.md §8.
// Issue #312 (spec-22-B3).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FilterToggle } from "./FilterToggle";
import { useUiPrefs } from "../stores/ui-prefs";

describe("FilterToggle", () => {
  beforeEach(() => {
    useUiPrefs.setMatchFilter("unvalidated");
  });

  it("renders a button with data-testid='match-filter-toggle'", () => {
    render(<FilterToggle />);
    expect(screen.getByTestId("match-filter-toggle")).toBeInTheDocument();
  });

  it("reflects the initial 'unvalidated' state via label and data-filter", () => {
    render(<FilterToggle />);
    const btn = screen.getByTestId("match-filter-toggle");
    expect(btn).toHaveTextContent("Unvalidated Lines");
    expect(btn).toHaveAttribute("data-filter", "unvalidated");
  });

  it("cycles unvalidated → mismatched on first click", () => {
    render(<FilterToggle />);
    const btn = screen.getByTestId("match-filter-toggle");
    fireEvent.click(btn);
    expect(useUiPrefs.getState().matchFilter).toBe("mismatched");
    expect(btn).toHaveTextContent("Mismatched Lines");
    expect(btn).toHaveAttribute("data-filter", "mismatched");
  });

  it("cycles mismatched → all on second click", () => {
    render(<FilterToggle />);
    const btn = screen.getByTestId("match-filter-toggle");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(useUiPrefs.getState().matchFilter).toBe("all");
    expect(btn).toHaveTextContent("All Lines");
    expect(btn).toHaveAttribute("data-filter", "all");
  });

  it("wraps all → unvalidated on third click", () => {
    render(<FilterToggle />);
    const btn = screen.getByTestId("match-filter-toggle");
    fireEvent.click(btn);
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(useUiPrefs.getState().matchFilter).toBe("unvalidated");
    expect(btn).toHaveTextContent("Unvalidated Lines");
  });

  it("starts at whatever the store currently holds (not always 'unvalidated')", () => {
    useUiPrefs.setMatchFilter("mismatched");
    render(<FilterToggle />);
    const btn = screen.getByTestId("match-filter-toggle");
    expect(btn).toHaveTextContent("Mismatched Lines");
  });
});
