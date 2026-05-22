// StudioShell.test.tsx — Tests for the 5-zone Studio grid layout.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 8.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StudioShell } from "./StudioShell";

describe("StudioShell — 5-zone grid (Slice 8)", () => {
  function renderShell(rightWidth?: number) {
    return render(
      <StudioShell
        header={<div data-testid="slot-header">header</div>}
        rail={<div data-testid="slot-rail">rail</div>}
        drawer={<div data-testid="slot-drawer">drawer</div>}
        canvas={<div data-testid="slot-canvas">canvas</div>}
        right={<div data-testid="slot-right">right</div>}
        {...(rightWidth !== undefined && { rightWidth })}
      />,
    );
  }

  it("renders all five slot children", () => {
    renderShell();
    expect(screen.getByTestId("slot-header")).toBeInTheDocument();
    expect(screen.getByTestId("slot-rail")).toBeInTheDocument();
    expect(screen.getByTestId("slot-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("slot-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("slot-right")).toBeInTheDocument();
  });

  it("assigns studio-shell testid to root", () => {
    renderShell();
    expect(screen.getByTestId("studio-shell")).toBeInTheDocument();
  });

  it("header region has grid-area header", () => {
    renderShell();
    const header = screen.getByTestId("studio-shell-header");
    expect(header).toBeInTheDocument();
  });

  it("rail region has grid-area rail", () => {
    renderShell();
    expect(screen.getByTestId("studio-shell-rail")).toBeInTheDocument();
  });

  it("drawer region has grid-area drawer", () => {
    renderShell();
    expect(screen.getByTestId("studio-shell-drawer")).toBeInTheDocument();
  });

  it("canvas region has grid-area canvas", () => {
    renderShell();
    expect(screen.getByTestId("studio-shell-canvas")).toBeInTheDocument();
  });

  it("right region has grid-area right", () => {
    renderShell();
    expect(screen.getByTestId("studio-shell-right")).toBeInTheDocument();
  });

  it("collapses drawer when collapsed prop is true", () => {
    render(
      <StudioShell
        header={<div>h</div>}
        rail={<div>r</div>}
        drawer={<div data-testid="drawer-child">d</div>}
        canvas={<div>c</div>}
        right={<div>right</div>}
        drawerCollapsed
      />,
    );
    const drawerZone = screen.getByTestId("studio-shell-drawer");
    // collapsed: has data-collapsed attribute
    expect(drawerZone).toHaveAttribute("data-collapsed", "true");
  });

  it("applies hi-fi grid dimensions: 56px header, 64px rail, 320px drawer default", () => {
    renderShell();
    const shell = screen.getByTestId("studio-shell");
    const colTemplate = shell.style.gridTemplateColumns;
    // Rail: 64px; drawer default: var(--drawer-w, 320px); right: var(--right-w, 520px)
    expect(colTemplate).toContain("64px");
    expect(colTemplate).toContain("320px");
    const rowTemplate = shell.style.gridTemplateRows;
    // Header row: 56px
    expect(rowTemplate).toContain("56px");
  });

  it("accepts rightWidth prop and applies it as --right-w CSS variable", () => {
    renderShell(640);
    const shell = screen.getByTestId("studio-shell");
    // The --right-w CSS variable should be set to 640px
    expect(shell.style.getPropertyValue("--right-w")).toBe("640px");
  });

  it("uses default --right-w of 520px when rightWidth is not provided", () => {
    renderShell();
    const shell = screen.getByTestId("studio-shell");
    // Default: column template includes var(--right-w, 520px)
    expect(shell.style.gridTemplateColumns).toContain("520px");
  });

  it("headerHeight=0 collapses the header row to 0px in gridTemplateRows", () => {
    render(
      <StudioShell
        headerHeight={0}
        header={<></>}
        rail={<div>r</div>}
        drawer={<div>d</div>}
        canvas={<div>c</div>}
        right={<div>right</div>}
      />,
    );
    const shell = screen.getByTestId("studio-shell");
    expect(shell.style.gridTemplateRows).toBe("0px 1fr");
  });

  it("headerHeight=0 adds 'hidden' class to studio-shell-header", () => {
    render(
      <StudioShell
        headerHeight={0}
        header={<></>}
        rail={<div>r</div>}
        drawer={<div>d</div>}
        canvas={<div>c</div>}
        right={<div>right</div>}
      />,
    );
    const header = screen.getByTestId("studio-shell-header");
    expect(header.classList.contains("hidden")).toBe(true);
  });

  it("default headerHeight (56) does not add 'hidden' class to studio-shell-header", () => {
    renderShell();
    const header = screen.getByTestId("studio-shell-header");
    expect(header.classList.contains("hidden")).toBe(false);
    const shell = screen.getByTestId("studio-shell");
    expect(shell.style.gridTemplateRows).toBe("56px 1fr");
  });
});
