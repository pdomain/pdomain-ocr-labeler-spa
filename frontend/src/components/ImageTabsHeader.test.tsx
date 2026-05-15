// ImageTabsHeader.test.tsx — tests for viewport header (layer checkboxes, mode radio, erase).
// Spec: docs/specs/2026-05-12-image-viewport-design.md §ImageTabsHeader
// Issue #196
//
// Acceptance:
//   - Renders layer checkboxes with correct data-testids
//   - Renders selection-mode radios with correct data-testids
//   - Renders erase-pixels-button
//   - onLayerToggle fires with layer name when checkbox clicked
//   - onSelectionModeChange fires with mode when radio clicked
//   - onEraseToggle fires when erase button clicked

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
});
