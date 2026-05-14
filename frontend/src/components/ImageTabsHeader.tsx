// ImageTabsHeader.tsx — viewport header: layer checkboxes, selection-mode, erase.
// Spec: docs/specs/2026-05-12-image-viewport-design.md §ImageTabsHeader
// Issue #196
//
// data-testids (driver-contract invariants):
//   layer-paragraphs-checkbox, layer-lines-checkbox, layer-words-checkbox
//   selection-mode-paragraph, selection-mode-line, selection-mode-word
//   erase-pixels-button

export interface LayerVisibility {
  paragraph: boolean;
  line: boolean;
  word: boolean;
}

/** Selection mode values (matches ui-prefs store). */
export type SelectionMode = "box" | "line" | "word";

interface ImageTabsHeaderProps {
  layerVisibility: LayerVisibility;
  /** Which bounding-box unit is selected for drag-select. */
  selectionMode: SelectionMode;
  /** Whether Erase mode is currently active. */
  eraseActive: boolean;
  /** Called with the layer key ('paragraph' | 'line' | 'word') when toggled. */
  onLayerToggle: (layer: keyof LayerVisibility) => void;
  /**
   * Called with the new selection mode when a radio is clicked.
   * Maps: paragraph→"box", line→"line", word→"box" (word is the default box unit).
   * Callers can use this to set their own granularity state.
   */
  onSelectionModeChange: (mode: SelectionMode) => void;
  /** Called when the Erase Pixels button is clicked (toggle). */
  onEraseToggle: () => void;
}

/**
 * Header bar for the image viewport pane.
 *
 * Contains layer visibility checkboxes, selection-mode radio buttons,
 * and the Erase Pixels mode toggle.
 */
export function ImageTabsHeader({
  layerVisibility,
  selectionMode,
  eraseActive,
  onLayerToggle,
  onSelectionModeChange,
  onEraseToggle,
}: ImageTabsHeaderProps) {
  return (
    <div
      className="flex items-center gap-3 px-2 py-1 bg-gray-50 border-b border-gray-200 flex-wrap text-xs"
      aria-label="Viewport controls"
    >
      {/* Layer checkboxes */}
      <fieldset className="flex items-center gap-2 border-0 p-0 m-0">
        <legend className="sr-only">Visible layers</legend>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="layer-paragraphs-checkbox"
            checked={layerVisibility.paragraph}
            onChange={() => onLayerToggle("paragraph")}
            className="accent-green-600"
            aria-label="Show paragraphs layer"
          />
          <span className="text-green-700">Para</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="layer-lines-checkbox"
            checked={layerVisibility.line}
            onChange={() => onLayerToggle("line")}
            className="accent-pink-600"
            aria-label="Show lines layer"
          />
          <span className="text-pink-700">Lines</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="layer-words-checkbox"
            checked={layerVisibility.word}
            onChange={() => onLayerToggle("word")}
            className="accent-blue-600"
            aria-label="Show words layer"
          />
          <span className="text-blue-700">Words</span>
        </label>
      </fieldset>

      <div className="w-px h-4 bg-gray-300" aria-hidden="true" />

      {/* Selection-mode radio buttons */}
      <fieldset className="flex items-center gap-2 border-0 p-0 m-0">
        <legend className="sr-only">Selection mode</legend>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="radio"
            name="selection-mode"
            data-testid="selection-mode-paragraph"
            checked={selectionMode === "box" && false /* paragraph mode not yet mapped */}
            onChange={() => onSelectionModeChange("box")}
            aria-label="Select by paragraph"
          />
          <span>Para</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="radio"
            name="selection-mode"
            data-testid="selection-mode-line"
            checked={selectionMode === "line"}
            onChange={() => onSelectionModeChange("line")}
            aria-label="Select by line"
          />
          <span>Line</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="radio"
            name="selection-mode"
            data-testid="selection-mode-word"
            checked={selectionMode === "box" || selectionMode === "word"}
            onChange={() => onSelectionModeChange("box")}
            aria-label="Select by word"
          />
          <span>Word</span>
        </label>
      </fieldset>

      <div className="w-px h-4 bg-gray-300" aria-hidden="true" />

      {/* Erase Pixels mode toggle */}
      <button
        data-testid="erase-pixels-button"
        aria-pressed={eraseActive}
        onClick={onEraseToggle}
        title="Erase Pixels mode (Shift+E)"
        className={[
          "px-2 py-0.5 text-xs rounded border transition-colors",
          eraseActive
            ? "bg-orange-500 text-white border-orange-600 hover:bg-orange-600"
            : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50",
        ].join(" ")}
      >
        Erase
      </button>
    </div>
  );
}
