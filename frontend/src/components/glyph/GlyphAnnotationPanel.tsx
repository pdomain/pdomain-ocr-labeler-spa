// GlyphAnnotationPanel.tsx — Typography annotation section for a word.
// Spec: specs/20-glyph-annotations.md §5.1
// Issue #269
//
// data-testids (spec §7):
//   glyph-panel-{line}-{word}          — outer panel container
//   glyph-panel-add-ligature           — "Add ligature" button
//   glyph-panel-ligature-kind-select   — ligature kind picker
//   glyph-panel-charspan-cell-{i}      — i-th char cell in span picker
//   glyph-panel-long-s-cell-{i}        — i-th char cell in long-s picker
//   glyph-panel-swash-checkbox         — swash toggle
//   glyph-panel-mark-reviewed-empty    — "Mark reviewed (no marks)"
//   glyph-panel-reset                  — "Reset" to null
//   glyph-panel-accept-prediction-{kind}
//   glyph-panel-reject-prediction-{kind}

import { useState } from "react";
import type { components } from "../../api/types";

type GlyphAnnotationsModel = components["schemas"]["GlyphAnnotationsModel"];
type LigatureMarkModel = components["schemas"]["LigatureMarkModel"];

export interface GlyphAnnotationPanelProps {
  lineIndex: number;
  wordIndex: number;
  gtText: string;
  annotations: GlyphAnnotationsModel | null;
  predictions: GlyphAnnotationsModel | null;
  onSetAnnotations: (ann: GlyphAnnotationsModel | null) => void;
  onAcceptPrediction?: (() => void) | undefined;
}

const LIGATURE_KINDS = ["ct", "st", "fi", "fl", "ff", "ffi", "ffl"] as const;

/**
 * Panel section for viewing and editing glyph annotations for a single word.
 * Panel content for word-level typography editing.
 */
export function GlyphAnnotationPanel({
  lineIndex,
  wordIndex,
  gtText,
  annotations,
  predictions,
  onSetAnnotations,
  onAcceptPrediction,
}: GlyphAnnotationPanelProps) {
  const [newKind, setNewKind] = useState<string>("ct");
  const [selectedSpan, setSelectedSpan] = useState<[number, number] | null>(null);

  const chars = gtText.split("");

  function handleMarkReviewed() {
    onSetAnnotations({
      ligatures: [],
      long_s_positions: [],
      swash: false,
      source: "human",
    });
  }

  function handleReset() {
    onSetAnnotations(null);
  }

  function handleSwashChange(checked: boolean) {
    const base = annotations ?? {
      ligatures: [],
      long_s_positions: [],
      swash: false,
      source: "human" as const,
    };
    onSetAnnotations({ ...base, swash: checked });
  }

  function handleAddLigature() {
    const base = annotations ?? {
      ligatures: [],
      long_s_positions: [],
      swash: false,
      source: "human" as const,
    };
    const newMark: LigatureMarkModel = {
      kind: newKind,
      char_span: selectedSpan,
    };
    onSetAnnotations({ ...base, ligatures: [...(base.ligatures ?? []), newMark] });
    setSelectedSpan(null);
  }

  function handleRemoveLigature(index: number) {
    if (!annotations) return;
    const updated = (annotations.ligatures ?? []).filter((_, i) => i !== index);
    onSetAnnotations({ ...annotations, ligatures: updated });
  }

  function handleToggleLongS(charIdx: number) {
    const base = annotations ?? {
      ligatures: [],
      long_s_positions: [],
      swash: false,
      source: "human" as const,
    };
    const basePositions = base.long_s_positions ?? [];
    const positions = basePositions.includes(charIdx)
      ? basePositions.filter((p) => p !== charIdx)
      : [...basePositions, charIdx].sort((a, b) => a - b);
    onSetAnnotations({ ...base, long_s_positions: positions });
  }

  function handleCharSpanClick(i: number, shiftKey = false) {
    if (selectedSpan === null || !shiftKey) {
      // First click (or unshifted click): set anchor at this position.
      setSelectedSpan([i, i + 1]);
    } else {
      // Shift-click: extend span from anchor to include i.
      const [start] = selectedSpan;
      if (i < start) {
        setSelectedSpan([i, start + 1]);
      } else {
        setSelectedSpan([start, i + 1]);
      }
    }
  }

  const hasMarks =
    annotations !== null &&
    ((annotations.ligatures?.length ?? 0) > 0 ||
      (annotations.long_s_positions?.length ?? 0) > 0 ||
      annotations.swash);

  return (
    <div
      data-testid={`glyph-panel-${lineIndex}-${wordIndex}`}
      className="flex flex-col gap-2 p-2 text-xs border border-border-1 rounded"
    >
      <div className="font-semibold text-ink-2">Typography</div>

      {/* Ligatures section */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-ink-3">Ligatures</span>
          <button
            data-testid="glyph-panel-add-ligature"
            onClick={handleAddLigature}
            className="px-1 py-0 text-[10px] border border-border-1 rounded hover:bg-surface-2"
            type="button"
          >
            + Add
          </button>
        </div>

        {/* Kind select */}
        <select
          data-testid="glyph-panel-ligature-kind-select"
          value={newKind}
          onChange={(e) => setNewKind(e.target.value)}
          className="text-[10px] border border-border-1 rounded px-1 mb-1 bg-surface-1"
        >
          {LIGATURE_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>

        {/* Char-span picker */}
        {chars.length > 0 && (
          <div className="flex gap-0.5 flex-wrap">
            {chars.map((ch, i) => (
              <button
                key={i}
                data-testid={`glyph-panel-charspan-cell-${i}`}
                onClick={(e) => handleCharSpanClick(i, e.shiftKey)}
                className={[
                  "w-5 h-5 text-[10px] font-mono border rounded cursor-pointer",
                  selectedSpan !== null && i >= selectedSpan[0] && i < selectedSpan[1]
                    ? "bg-accent text-white border-accent"
                    : "border-border-1 hover:bg-surface-2",
                ].join(" ")}
                type="button"
                title={`char ${i}: ${ch}`}
              >
                {ch}
              </button>
            ))}
          </div>
        )}

        {/* Existing ligature marks */}
        {(annotations?.ligatures ?? []).map((lig, idx) => {
          const isPredicted =
            (predictions?.ligatures ?? []).some((p) => p.kind === lig.kind) &&
            (annotations === null || annotations.source === "predicted");
          return (
            <div key={idx} className="flex items-center gap-1 mt-0.5">
              <span className={isPredicted ? "text-ink-4" : "text-ink-1"}>
                {isPredicted ? "◌" : "•"} {lig.kind}
                {lig.char_span ? ` [${lig.char_span[0]}-${lig.char_span[1]}]` : ""}
              </span>
              <button
                onClick={() => handleRemoveLigature(idx)}
                className="text-[10px] text-red-500 hover:text-red-700 ml-auto"
                type="button"
                aria-label={`Remove ${lig.kind} ligature`}
              >
                ×
              </button>
            </div>
          );
        })}

        {/* Predicted ligatures with accept/reject */}
        {(predictions?.ligatures ?? []).map((pred) => (
          <div key={pred.kind} className="flex items-center gap-1 mt-0.5 text-ink-4">
            <span>◌ {pred.kind} (predicted)</span>
            <button
              data-testid={`glyph-panel-accept-prediction-${pred.kind}`}
              onClick={() => onAcceptPrediction?.()}
              className="text-[10px] text-green-600 hover:text-green-800 ml-auto"
              type="button"
            >
              ✓ accept
            </button>
            <button
              data-testid={`glyph-panel-reject-prediction-${pred.kind}`}
              onClick={() =>
                onSetAnnotations(
                  annotations ?? {
                    ligatures: [],
                    long_s_positions: [],
                    swash: false,
                    source: "human",
                  },
                )
              }
              className="text-[10px] text-red-500 hover:text-red-700"
              type="button"
            >
              × reject
            </button>
          </div>
        ))}
      </div>

      {/* Long-s positions */}
      <div>
        <div className="text-ink-3 mb-1">Long-s positions</div>
        {chars.length > 0 && (
          <div className="flex gap-0.5 flex-wrap">
            {chars.map((ch, i) => (
              <button
                key={i}
                data-testid={`glyph-panel-long-s-cell-${i}`}
                onClick={() => handleToggleLongS(i)}
                className={[
                  "w-5 h-5 text-[10px] font-mono border rounded cursor-pointer",
                  (annotations?.long_s_positions ?? []).includes(i)
                    ? "bg-accent text-white border-accent"
                    : "border-border-1 hover:bg-surface-2",
                ].join(" ")}
                type="button"
                title={`char ${i}: ${ch}`}
              >
                {ch}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Swash */}
      <label className="flex items-center gap-1 cursor-pointer">
        <input
          data-testid="glyph-panel-swash-checkbox"
          type="checkbox"
          checked={annotations?.swash ?? false}
          onChange={(e) => handleSwashChange(e.target.checked)}
          className="cursor-pointer"
        />
        <span>Swash</span>
      </label>

      {/* Footer buttons */}
      <div className="flex gap-1 mt-1 pt-1 border-t border-border-1">
        {!hasMarks && (
          <button
            data-testid="glyph-panel-mark-reviewed-empty"
            onClick={handleMarkReviewed}
            className="text-[10px] px-2 py-0.5 border border-border-1 rounded hover:bg-surface-2"
            type="button"
          >
            Mark reviewed (no marks)
          </button>
        )}
        {annotations !== null && (
          <button
            data-testid="glyph-panel-reset"
            onClick={handleReset}
            className="text-[10px] px-2 py-0.5 border border-red-300 text-red-600 rounded hover:bg-red-50 ml-auto"
            type="button"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}
