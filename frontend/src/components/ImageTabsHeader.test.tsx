// ImageTabsHeader.test.tsx — tests for viewport header (layer checkboxes, mode radio, erase).
// Spec: docs/specs/2026-05-12-image-viewport-design.md §ImageTabsHeader
// Issue #196
// Issue #295: Mismatches-only toggle (mismatches-only-toggle)
//
// Acceptance:
//   - Renders layer checkboxes with correct data-testids
//   - Renders selection-mode radios with correct data-testids
//   - Renders erase-pixels-button
//   - onLayerToggle fires with layer name when checkbox clicked
//   - onSelectionModeChange fires with mode when radio clicked
//   - onEraseToggle fires when erase button clicked
//   - Renders mismatches-only-toggle with correct testid (#295)
//   - Toggle shows active state when matchFilterMode is "mismatches_only"
//   - onMatchFilterModeToggle fires when clicked
//   - Clicking again calls onMatchFilterModeToggle (caller manages toggle logic)

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ImageTabsHeader, type LayerVisibility } from "./ImageTabsHeader";

const defaultVisibility: LayerVisibility = {
  paragraph: true,
  line: true,
  word: true,
};

describe("ImageTabsHeader (#196)", () => {
  it("renders all three layer checkboxes", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("layer-paragraphs-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("layer-lines-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("layer-words-checkbox")).toBeInTheDocument();
  });

  it("renders selection-mode radio buttons", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("selection-mode-paragraph")).toBeInTheDocument();
    expect(screen.getByTestId("selection-mode-line")).toBeInTheDocument();
    expect(screen.getByTestId("selection-mode-word")).toBeInTheDocument();
  });

  it("renders erase-pixels-button", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("erase-pixels-button")).toBeInTheDocument();
  });

  it("layer checkboxes reflect layerVisibility prop", () => {
    render(
      <ImageTabsHeader
        layerVisibility={{ paragraph: true, line: false, word: true }}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("layer-paragraphs-checkbox")).toBeChecked();
    expect(screen.getByTestId("layer-lines-checkbox")).not.toBeChecked();
    expect(screen.getByTestId("layer-words-checkbox")).toBeChecked();
  });

  it("onLayerToggle fires with 'paragraph' when paragraphs checkbox clicked", () => {
    const onLayerToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={onLayerToggle}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("layer-paragraphs-checkbox"));
    expect(onLayerToggle).toHaveBeenCalledWith("paragraph");
  });

  it("onLayerToggle fires with 'line' when lines checkbox clicked", () => {
    const onLayerToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={onLayerToggle}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("layer-lines-checkbox"));
    expect(onLayerToggle).toHaveBeenCalledWith("line");
  });

  it("onSelectionModeChange fires with 'word' when word radio clicked", () => {
    const onSelectionModeChange = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="line"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={onSelectionModeChange}
        onEraseToggle={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("selection-mode-word"));
    expect(onSelectionModeChange).toHaveBeenCalledWith("word");
  });

  it("onEraseToggle fires when erase button clicked", () => {
    const onEraseToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={onEraseToggle}
      />,
    );
    fireEvent.click(screen.getByTestId("erase-pixels-button"));
    expect(onEraseToggle).toHaveBeenCalledOnce();
  });

  it("erase button shows active state when eraseActive=true", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={true}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("erase-pixels-button")).toHaveAttribute("aria-pressed", "true");
  });

  it("container uses design token classes (bg-bg-surface, border-border-1)", () => {
    const { container } = render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    const root = container.firstChild as HTMLElement;
    expect(root.className).toContain("bg-bg-surface");
    expect(root.className).toContain("border-border-1");
    // Must NOT use raw Tailwind color classes
    expect(root.className).not.toContain("bg-gray-50");
    expect(root.className).not.toContain("border-gray-200");
  });

  it("para checkbox uses text-layer-para and accent-layer-para tokens", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    const paraCheckbox = screen.getByTestId("layer-paragraphs-checkbox");
    expect(paraCheckbox.className).toContain("accent-layer-para");
    // The span label
    const paraLabel = paraCheckbox.closest("label");
    expect(paraLabel?.textContent).toContain("Para");
    const span = paraLabel?.querySelector("span");
    expect(span?.className).toContain("text-layer-para");
  });

  it("erase button uses bg-status-mismatch token when active", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={true}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    const btn = screen.getByTestId("erase-pixels-button");
    expect(btn.className).toContain("bg-status-mismatch");
    // Must NOT use raw orange classes
    expect(btn.className).not.toContain("bg-orange-500");
  });

  // Regression: paragraph radio must reflect selectionMode prop, not be hardcoded (bug #292)
  it("paragraph radio is checked when selectionMode is paragraph", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("selection-mode-paragraph")).toBeChecked();
    expect(screen.getByTestId("selection-mode-line")).not.toBeChecked();
    expect(screen.getByTestId("selection-mode-word")).not.toBeChecked();
  });

  it("paragraph radio is unchecked when selectionMode is line or word", () => {
    const { rerender } = render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="line"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("selection-mode-paragraph")).not.toBeChecked();
    expect(screen.getByTestId("selection-mode-line")).toBeChecked();

    rerender(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="word"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("selection-mode-paragraph")).not.toBeChecked();
    expect(screen.getByTestId("selection-mode-word")).toBeChecked();
  });

  // Regression: SelectionMode must be "paragraph"|"line"|"word", not "box" (bug #292)
  it("onSelectionModeChange fires with 'paragraph' when paragraph radio clicked", () => {
    const onSelectionModeChange = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="line"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={onSelectionModeChange}
        onEraseToggle={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("selection-mode-paragraph"));
    expect(onSelectionModeChange).toHaveBeenCalledWith("paragraph");
  });

  // P5.d (Gap 24): zoom buttons
  it("P5.d: renders zoom-fit-button and zoom-100-button", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("zoom-fit-button")).toBeInTheDocument();
    expect(screen.getByTestId("zoom-100-button")).toBeInTheDocument();
  });

  it("P5.d: onZoomFit fires when Fit button clicked", () => {
    const onZoomFit = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        onZoomFit={onZoomFit}
      />,
    );
    fireEvent.click(screen.getByTestId("zoom-fit-button"));
    expect(onZoomFit).toHaveBeenCalledOnce();
  });

  it("P5.d: onZoom100 fires when 100% button clicked", () => {
    const onZoom100 = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        onZoom100={onZoom100}
      />,
    );
    fireEvent.click(screen.getByTestId("zoom-100-button"));
    expect(onZoom100).toHaveBeenCalledOnce();
  });

  // ── Issue #295: Mismatches-only toggle ──────────────────────────────────────

  it("#295: renders mismatches-only-toggle with correct testid", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("mismatches-only-toggle")).toBeInTheDocument();
  });

  it("#295: toggle is not active when matchFilterMode is 'all' (default)", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="all"
      />,
    );
    expect(screen.getByTestId("mismatches-only-toggle")).toHaveAttribute("aria-pressed", "false");
  });

  it("#295: toggle shows active state when matchFilterMode is 'mismatches_only'", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="mismatches_only"
      />,
    );
    expect(screen.getByTestId("mismatches-only-toggle")).toHaveAttribute("aria-pressed", "true");
  });

  it("#295: active toggle uses accent color class", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="mismatches_only"
      />,
    );
    const btn = screen.getByTestId("mismatches-only-toggle");
    expect(btn.className).toContain("bg-accent");
  });

  it("#295: inactive toggle uses raised background class", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="all"
      />,
    );
    const btn = screen.getByTestId("mismatches-only-toggle");
    expect(btn.className).toContain("bg-bg-raised");
  });

  it("#295: onMatchFilterModeToggle fires when toggle clicked", () => {
    const onMatchFilterModeToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="all"
        onMatchFilterModeToggle={onMatchFilterModeToggle}
      />,
    );
    fireEvent.click(screen.getByTestId("mismatches-only-toggle"));
    expect(onMatchFilterModeToggle).toHaveBeenCalledOnce();
  });

  it("#295: onMatchFilterModeToggle fires when active toggle clicked (returns to 'all')", () => {
    const onMatchFilterModeToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
        matchFilterMode="mismatches_only"
        onMatchFilterModeToggle={onMatchFilterModeToggle}
      />,
    );
    fireEvent.click(screen.getByTestId("mismatches-only-toggle"));
    expect(onMatchFilterModeToggle).toHaveBeenCalledOnce();
  });

  // ── Erase button wiring ─────────────────────────────────────────────────────

  it("erase button click calls onEraseToggle", () => {
    const onEraseToggle = vi.fn();
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={onEraseToggle}
      />,
    );
    fireEvent.click(screen.getByTestId("erase-pixels-button"));
    expect(onEraseToggle).toHaveBeenCalledOnce();
  });

  it("eraseActive=true sets aria-pressed='true' on erase button", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={true}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("erase-pixels-button")).toHaveAttribute("aria-pressed", "true");
  });

  it("eraseActive=false sets aria-pressed='false' on erase button", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("erase-pixels-button")).toHaveAttribute("aria-pressed", "false");
  });

  // ── Legend chips (spec §2 item 4) ──────────────────────────────────────────

  it("renders layer-color-legend with three color chips", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    expect(screen.getByTestId("layer-color-legend")).toBeInTheDocument();
    expect(screen.getByTestId("legend-chip-para")).toBeInTheDocument();
    expect(screen.getByTestId("legend-chip-line")).toBeInTheDocument();
    expect(screen.getByTestId("legend-chip-word")).toBeInTheDocument();
  });

  it("legend chips use var(--layer-*) CSS variables for background", () => {
    render(
      <ImageTabsHeader
        layerVisibility={defaultVisibility}
        selectionMode="paragraph"
        eraseActive={false}
        onLayerToggle={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onEraseToggle={vi.fn()}
      />,
    );
    // jsdom exposes inline styles as-is
    const para = screen.getByTestId("legend-chip-para") as HTMLElement;
    const line = screen.getByTestId("legend-chip-line") as HTMLElement;
    const word = screen.getByTestId("legend-chip-word") as HTMLElement;
    expect(para.style.background).toBe("var(--layer-para)");
    expect(line.style.background).toBe("var(--layer-line)");
    expect(word.style.background).toBe("var(--layer-word)");
  });
});
