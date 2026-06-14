// Drawer.test.tsx — Tests for the Drawer shell (Slice 11).
// Covers: B-SHELL-003, B-SHELL-011, S2.2 (visible Text tab with GT/OCR)
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

  it("switching to Hierarchy tab shows hierarchy component", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    await user.click(screen.getByTestId("drawer-tab-hierarchy"));
    expect(screen.getByTestId("hierarchy")).toBeInTheDocument();
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

  it("useSyncExternalStore bridge via useUiPrefs.subscribe re-renders on setState", async () => {
    // Verifies #324: store.subscribe drives re-renders without a local bridge Set.
    // We render the Drawer, then call setState externally and confirm the component
    // reflects the new value — which only works if useSyncExternalStore is wired to
    // the real store.subscribe (not a disconnected local Set).
    const user = userEvent.setup();
    render(<Drawer />);
    expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "true");

    // External setState — simulates another component collapsing the drawer.
    useUiPrefs.setState({ drawerOpen: false });

    // The expand button is only rendered when collapsed.
    await screen.findByTestId("drawer-expand-btn");
    expect(screen.getByTestId("drawer")).toHaveAttribute("data-open", "false");

    // Restore via expand button.
    await user.click(screen.getByTestId("drawer-expand-btn"));
    expect(useUiPrefs.getState().drawerOpen).toBe(true);
  });
});

// --- M1 (D-047): worklist-header slot for relocated QuickSearch ---

describe("Drawer M1 — worklist-header slot (D-047)", () => {
  beforeEach(() => {
    resetPrefs();
  });

  it("renders drawer-worklist-header region containing injected content on the worklist tab", () => {
    render(<Drawer worklistHeader={<span data-testid="ws-header-content">search</span>} />);
    const header = screen.getByTestId("drawer-worklist-header");
    expect(header).toBeInTheDocument();
    expect(header.querySelector('[data-testid="ws-header-content"]')).not.toBeNull();
  });

  it("does not render drawer-worklist-header when no content is injected", () => {
    render(<Drawer />);
    expect(screen.queryByTestId("drawer-worklist-header")).not.toBeInTheDocument();
  });

  it("does not render drawer-worklist-header on the hierarchy tab", async () => {
    const user = userEvent.setup();
    render(<Drawer worklistHeader={<span data-testid="ws-header-content">search</span>} />);
    await user.click(screen.getByTestId("drawer-tab-hierarchy"));
    expect(screen.queryByTestId("drawer-worklist-header")).not.toBeInTheDocument();
  });
});

// --- Gap 18: tab icons + count badges + collapse chevron ---

describe("Drawer Gap 18 — tab icons + count badges", () => {
  beforeEach(() => {
    resetPrefs();
  });

  it("renders icon span for worklist tab", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer-tab-icon-worklist")).toBeInTheDocument();
  });

  it("renders icon span for hierarchy tab", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer-tab-icon-hierarchy")).toBeInTheDocument();
  });

  it("does not render count badge when tabCounts is not provided", () => {
    render(<Drawer />);
    expect(screen.queryByTestId("drawer-tab-count-worklist")).not.toBeInTheDocument();
    expect(screen.queryByTestId("drawer-tab-count-hierarchy")).not.toBeInTheDocument();
  });

  it("renders count badge for worklist when tabCounts.worklist > 0", () => {
    render(<Drawer tabCounts={{ worklist: 7 }} />);
    expect(screen.getByTestId("drawer-tab-count-worklist")).toHaveTextContent("7");
  });

  it("renders count badge for hierarchy when tabCounts.hierarchy > 0", () => {
    render(<Drawer tabCounts={{ hierarchy: 3 }} />);
    expect(screen.getByTestId("drawer-tab-count-hierarchy")).toHaveTextContent("3");
  });

  it("does not render count badge when count is 0", () => {
    render(<Drawer tabCounts={{ worklist: 0 }} />);
    expect(screen.queryByTestId("drawer-tab-count-worklist")).not.toBeInTheDocument();
  });

  it("renders collapse button with ChevronLeft", () => {
    render(<Drawer />);
    expect(screen.getByTestId("drawer-collapse-btn")).toBeInTheDocument();
  });
});

// --- S2.2: Visible full-page GT/OCR text view in Drawer Text tab ---

describe("Drawer S2.2 — Text tab visible GT/OCR view", () => {
  beforeEach(() => {
    useUiPrefs.setState({
      drawerOpen: true,
      drawerTab: "worklist",
    });
  });

  it("renders the drawer-tab-text tab button", () => {
    render(<Drawer pageTextGt="gt text" pageTextOcr="ocr text" />);
    expect(screen.getByTestId("drawer-tab-text")).toBeInTheDocument();
  });

  it("clicking drawer-tab-text sets drawerTab to 'text'", async () => {
    const user = userEvent.setup();
    render(<Drawer pageTextGt="gt text" pageTextOcr="ocr text" />);
    await user.click(screen.getByTestId("drawer-tab-text"));
    expect(useUiPrefs.getState().drawerTab).toBe("text");
  });

  it("Text tab shows drawer-text-panel-ground-truth that is visible", async () => {
    const user = userEvent.setup();
    render(<Drawer pageTextGt="the gt content" pageTextOcr="the ocr content" />);
    await user.click(screen.getByTestId("drawer-tab-text"));
    const gtPanel = screen.getByTestId("drawer-text-panel-ground-truth");
    expect(gtPanel).toBeVisible();
  });

  it("Text tab shows drawer-text-panel-ocr that is visible", async () => {
    const user = userEvent.setup();
    render(<Drawer pageTextGt="the gt content" pageTextOcr="the ocr content" />);
    await user.click(screen.getByTestId("drawer-tab-text"));
    const ocrPanel = screen.getByTestId("drawer-text-panel-ocr");
    expect(ocrPanel).toBeVisible();
  });

  it("GT panel contains the page GT text", async () => {
    const user = userEvent.setup();
    render(<Drawer pageTextGt="hello ground truth" pageTextOcr="hello ocr" />);
    await user.click(screen.getByTestId("drawer-tab-text"));
    expect(screen.getByTestId("drawer-text-panel-ground-truth")).toHaveValue("hello ground truth");
  });

  it("OCR panel contains the page OCR text", async () => {
    const user = userEvent.setup();
    render(<Drawer pageTextGt="hello ground truth" pageTextOcr="hello ocr" />);
    await user.click(screen.getByTestId("drawer-tab-text"));
    expect(screen.getByTestId("drawer-text-panel-ocr")).toHaveValue("hello ocr");
  });

  it("Text tab panels are NOT visible on other tabs (no display:none stubs added)", async () => {
    render(<Drawer pageTextGt="gt" pageTextOcr="ocr" />);
    // worklist is active — text panels should not be in DOM yet (hidden via tab panel)
    // (they render but within a hidden tabpanel — toBeVisible returns false)
    const gtPanel = screen.queryByTestId("drawer-text-panel-ground-truth");
    if (gtPanel) {
      expect(gtPanel).not.toBeVisible();
    }
  });
});
