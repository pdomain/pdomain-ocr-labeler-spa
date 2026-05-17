// QuickSearch.test.tsx — unit tests for the header ⌘K search field.
// P1.c (Gap 6): placeholder input + keycap chip that opens the hotkey overlay.
//
// Tests:
//   - Renders the outer wrapper (data-testid="quick-search").
//   - Renders the search input (data-testid="quick-search-input").
//   - Renders the ⌘K keycap chip (data-testid="quick-search-keycap").
//   - Input has the correct placeholder text.
//   - Clicking the keycap chip opens the hotkey-help dialog (via dialogStore).

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

describe("QuickSearch: keycap opens hotkey overlay (P1.c)", () => {
  it("clicking the ⌘K keycap opens the hotkeyHelp dialog", async () => {
    const user = userEvent.setup();
    render(<QuickSearch />);

    expect(dialogStore.getState().hotkeyHelp.open).toBe(false);
    await user.click(screen.getByTestId("quick-search-keycap"));
    expect(dialogStore.getState().hotkeyHelp.open).toBe(true);
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
