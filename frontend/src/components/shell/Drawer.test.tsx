// Drawer.test.tsx — Tests for the Drawer shell (Slice 11).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Drawer } from "./Drawer";
import { useUiPrefs } from "../../stores/ui-prefs";

function resetPrefs() {
  useUiPrefs.setState({
    drawerOpen: true,
    drawerTab: "worklist",
  });
}

describe("Drawer (Slice 11)", () => {
  beforeEach(() => {
    resetPrefs();
  });

  it("renders with data-testid=drawer", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer")).toBeInTheDocument();
  });

  it("shows open state by default", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "true");
  });

  it("renders Worklist and Hierarchy tabs in the header", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer-tab-worklist")).toBeInTheDocument();
    expect(screen.getByTestId("drawer-tab-hierarchy")).toBeInTheDocument();
  });

  it("worklist tab is active by default", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer-tab-worklist")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("drawer-tab-hierarchy")).not.toHaveAttribute("data-active", "true");
  });

  it("switching to Hierarchy tab shows placeholder", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-tab-hierarchy"));
    expect(screen.getByTestId("drawer-hierarchy-placeholder")).toBeInTheDocument();
  });

  it("switching to Hierarchy tab persists to useUiPrefs.drawerTab", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-tab-hierarchy"));
    expect(useUiPrefs.getState().drawerTab).toBe("hierarchy");
  });

  it("switching back to Worklist tab works", async () => {
    const user = userEvent.setup();
    useUiPrefs.setState({ drawerTab: "hierarchy" });
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-tab-worklist"));
    expect(useUiPrefs.getState().drawerTab).toBe("worklist");
  });

  it("collapse button collapses the drawer", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-collapse-btn"));
    expect(useUiPrefs.getState().drawerOpen).toBe(false);
  });

  it("collapsed drawer shows expand button", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-collapse-btn"));
    // useSyncExternalStore subscription drives re-render; no extra render needed.
    expect(screen.getByTestId("drawer-expand-btn")).toBeInTheDocument();
  });

  it("expand button re-opens the drawer", async () => {
    const user = userEvent.setup();
    useUiPrefs.setState({ drawerOpen: false });
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-expand-btn"));
    expect(useUiPrefs.getState().drawerOpen).toBe(true);
  });

  it("collapsed state persists to useUiPrefs.drawerOpen", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-collapse-btn"));
    expect(useUiPrefs.getState().drawerOpen).toBe(false);
  });

  it("renders Worklist when tab is worklist", () => {
    render(<Drawer />);
    expect(screen.getByTestId("worklist")).toBeInTheDocument();
  });
});
