// QuickSearch.test.tsx — unit tests for the header ⌘K search field.
// Covers: B-SHELL-004, B-SHELL-010, B-ACTIONS-007
// P1.c (Gap 6): placeholder input + keycap chip.
// S6.4: keycap chip focuses the input (not opens hotkey help); ? opens help.
//
// Tests:
//   - Renders the outer wrapper (data-testid="quick-search").
//   - Renders the search input (data-testid="quick-search-input").
//   - Renders the ⌘K keycap chip (data-testid="quick-search-keycap").
//   - Input has the correct placeholder text.
//   - Clicking the keycap chip focuses the input (S6.4 — NOT hotkeyHelp open).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickSearch } from "./QuickSearch";
import { dialogStore } from "../../stores/dialog-store";
import { worklistStore } from "../../stores/worklist-store";

beforeEach(() => {
  dialogStore.reset();
  worklistStore.reset();
});

describe("QuickSearch: testids (P1.c)", () => {
  it("renders the quick-search container", () => {
    render(<QuickSearch />);
    expect(screen.getByTestId("quick-search")).toBeInTheDocument();
  });

  it("renders the search input", () => {
    render(<QuickSearch />);
    expect(screen.getByTestId("quick-search-input")).toBeInTheDocument();
  });

  it("renders the ⌘K keycap chip", () => {
    render(<QuickSearch />);
    expect(screen.getByTestId("quick-search-keycap")).toBeInTheDocument();
  });

  it("input has 'Search…' placeholder", () => {
    render(<QuickSearch />);
    const input = screen.getByTestId("quick-search-input");
    expect(input.placeholder).toBe("Search…");
  });
});

// S6.4: keycap now focuses the input (not opens hotkey help — that's the ? key).
describe("QuickSearch: S6.4 keycap focuses input (not opens hotkey overlay)", () => {
  it("clicking the ⌘K keycap focuses the search input", async () => {
    const user = userEvent.setup();
    render(<QuickSearch />);

    const input = screen.getByTestId("quick-search-input");
    // Input should not be focused initially
    expect(document.activeElement).not.toBe(input);
    await user.click(screen.getByTestId("quick-search-keycap"));
    // Input should now be focused
    expect(document.activeElement).toBe(input);
  });

  it("clicking the ⌘K keycap does NOT open the hotkeyHelp dialog", async () => {
    const user = userEvent.setup();
    render(<QuickSearch />);

    expect(dialogStore.getState().hotkeyHelp.open).toBe(false);
    await user.click(screen.getByTestId("quick-search-keycap"));
    // hotkeyHelp must remain closed — ⌘K focuses search, not opens help
    expect(dialogStore.getState().hotkeyHelp.open).toBe(false);
  });
});

describe("QuickSearch: search wiring (Task 5)", () => {
  it("typing in the input updates worklistStore.searchQuery", async () => {
    const user = userEvent.setup();
    render(<QuickSearch />);
    const input = screen.getByTestId("quick-search-input");
    await user.type(input, "foo");
    expect(worklistStore.getState().searchQuery).toBe("foo");
  });

  it("pressing Escape clears the query and worklistStore", async () => {
    const user = userEvent.setup();
    render(<QuickSearch />);
    const input = screen.getByTestId("quick-search-input");
    await user.type(input, "bar");
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("");
    expect(worklistStore.getState().searchQuery).toBe("");
  });

  it("input is no longer readOnly", () => {
    render(<QuickSearch />);
    const input = screen.getByTestId("quick-search-input");
    expect(input).not.toHaveAttribute("readOnly");
  });
});
