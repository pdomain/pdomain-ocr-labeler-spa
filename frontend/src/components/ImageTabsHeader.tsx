// ImageTabsHeader.tsx — viewport header: layer checkboxes, selection-mode, erase, zoom.
// Spec: docs/specs/2026-05-12-image-viewport-design.md §ImageTabsHeader
// Issue #196
// P5.d (Gap 24): added Fit and 100% zoom buttons.
// Issue #295: added Mismatches-only toggle (mismatches-only-toggle).
//
// data-testids (driver-contract invariants):
//   layer-paragraphs-checkbox, layer-lines-checkbox, layer-words-checkbox
//   selection-mode-paragraph, selection-mode-line, selection-mode-word
//   erase-pixels-button
//   zoom-fit-button, zoom-100-button (P5.d)
//   mismatches-only-toggle (#295)

export interface LayerVisibility {
  paragraph: boolean;
  line: boolean;
  word: boolean;
}

/** Selection mode values (matches ui-prefs store). Aligned with legacy
 * labeler — see specs/21-konva-renderer.md §8. */
export type SelectionMode = "paragraph" | "line" | "word";

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
   * Values are the selection-unit names: "paragraph" | "line" | "word".
   */
  onSelectionModeChange: (mode: SelectionMode) => void;
  /** Called when the Erase Pixels button is clicked (toggle). */
  onEraseToggle: () => void;
  /** Called when the Fit zoom button is clicked (P5.d). */
  onZoomFit?: () => void;
  /** Called when the 100% zoom button is clicked (P5.d). */
  onZoom100?: () => void;
  /**
   * Current bbox overlay filter mode — Issue #295.
   * When "mismatches_only", the word bbox overlay dims exact/validated words.
   */
  matchFilterMode?: "all" | "mismatches_only";
  /** Called when the Mismatches-only toggle is clicked — Issue #295. */
  onMatchFilterModeToggle?: () => void;
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
  onZoomFit,
  onZoom100,
  matchFilterMode = "all",
  onMatchFilterModeToggle,
}: ImageTabsHeaderProps) {
  return (
    <div
      className="flex items-center gap-3 px-2 py-1 bg-bg-surface border-b border-border-1 flex-wrap text-xs"
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
            onChange={() => {
              onLayerToggle("paragraph");
            }}
            className="accent-layer-para"
            aria-label="Show paragraphs layer"
          />
          <span className="text-layer-para">Para</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="layer-lines-checkbox"
            checked={layerVisibility.line}
            onChange={() => {
              onLayerToggle("line");
            }}
            className="accent-layer-line"
            aria-label="Show lines layer"
          />
          <span className="text-layer-line">Lines</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="layer-words-checkbox"
            checked={layerVisibility.word}
            onChange={() => {
              onLayerToggle("word");
            }}
            className="accent-layer-word"
            aria-label="Show words layer"
          />
          <span className="text-layer-word">Words</span>
        </label>
      </fieldset>

      <div className="w-px h-4 bg-border-2" aria-hidden="true" />

      {/* Selection-mode radio buttons */}
      <fieldset className="flex items-center gap-2 border-0 p-0 m-0">
        <legend className="sr-only">Selection mode</legend>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="radio"
            name="selection-mode"
            data-testid="selection-mode-paragraph"
            checked={selectionMode === "paragraph"}
            onChange={() => {
              onSelectionModeChange("paragraph");
            }}
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
            onChange={() => {
              onSelectionModeChange("line");
            }}
            aria-label="Select by line"
          />
          <span>Line</span>
        </label>

        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input
            type="radio"
            name="selection-mode"
            data-testid="selection-mode-word"
            checked={selectionMode === "word"}
            onChange={() => {
              onSelectionModeChange("word");
            }}
            aria-label="Select by word"
          />
          <span>Word</span>
        </label>
      </fieldset>

      <div className="w-px h-4 bg-border-2" aria-hidden="true" />

      {/* Erase Pixels mode toggle */}
      <button
        data-testid="erase-pixels-button"
        aria-pressed={eraseActive}
        onClick={onEraseToggle}
        title="Erase Pixels mode (Shift+E)"
        className={[
          "px-2 py-0.5 text-xs rounded border transition-colors",
          eraseActive
            ? "bg-status-mismatch text-ink-1 border-status-mismatch hover:opacity-90"
            : "bg-bg-raised text-ink-2 border-border-2 hover:bg-bg-raised/80",
        ].join(" ")}
      >
        Erase
      </button>

      {/* Mismatches-only bbox overlay toggle (Issue #295, Option C) */}
      <button
        data-testid="mismatches-only-toggle"
        aria-pressed={matchFilterMode === "mismatches_only"}
        onClick={onMatchFilterModeToggle}
        title="Show mismatches only — dims exact/validated word bboxes"
        className={[
          "px-2 py-0.5 text-xs rounded border transition-colors",
          matchFilterMode === "mismatches_only"
            ? "bg-accent text-ink-1 border-accent hover:opacity-90"
            : "bg-bg-raised text-ink-2 border-border-2 hover:bg-bg-raised/80",
        ].join(" ")}
      >
        Mismatches
      </button>

      {/* Layer color legend chips (spec §2 item 4) */}
      <div
        className="flex items-center gap-1.5 ml-1"
        aria-label="Layer colors"
        data-testid="layer-color-legend"
      >
        <span
          data-testid="legend-chip-para"
          className="inline-block w-3 h-3 rounded-sm"
          style={{ background: "var(--layer-para)" }}
          title="Paragraph layer"
        />
        <span
          data-testid="legend-chip-line"
          className="inline-block w-3 h-3 rounded-sm"
          style={{ background: "var(--layer-line)" }}
          title="Line layer"
        />
        <span
          data-testid="legend-chip-word"
          className="inline-block w-3 h-3 rounded-sm"
          style={{ background: "var(--layer-word)" }}
          title="Word layer"
        />
      </div>

      {/* Zoom buttons (P5.d, Gap 24) */}
      <div className="ml-auto flex items-center gap-1">
        <button
          data-testid="zoom-fit-button"
          type="button"
          onClick={onZoomFit}
          title="Fit page to pane"
          className="px-2 py-0.5 text-xs rounded border border-border-2 bg-bg-raised text-ink-2 hover:border-accent hover:text-ink-1 transition-colors"
        >
          Fit
        </button>
        <button
          data-testid="zoom-100-button"
          type="button"
          onClick={onZoom100}
          title="100% zoom"
          className="px-2 py-0.5 text-xs rounded border border-border-2 bg-bg-raised text-ink-2 hover:border-accent hover:text-ink-1 transition-colors"
        >
          100%
        </button>
      </div>
    </div>
  );
}
