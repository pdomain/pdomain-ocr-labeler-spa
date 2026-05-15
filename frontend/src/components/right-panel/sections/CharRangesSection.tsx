// CharRangesSection.tsx — Char Ranges accordion section for word detail.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 19.
//
// UI:
//   - One clickable cell per char in word.ocr_text.
//   - Click cell #1 = range anchor (start). Click cell #2 = range end.
//     If second click is before the anchor, the order is swapped.
//   - When a range is pending, five tri-state Chip selectors (italic,
//     bold, sub, super, drop-cap) appear; click cycles off→on→mixed→off.
//   - "Add range" button is enabled when at least one style chip is "on";
//     it appends a row to the ranges list and POSTs each enabled style
//     via apply-style (scope="part") so the word picks up the label.
//   - Existing ranges are listed below as compact rows with a delete button.
//
// Backend caveat: the apply-style endpoint takes only ``scope: "whole"|"part"``
// — no positions. We store the (start, end) positions locally so the UI
// can render them; the backend only learns the style label.  When the
// backend grows positioned ranges, switch the POST to a new endpoint.
//
// data-testids:
//   char-ranges-section          — outer container
//   char-cell-{i}                — clickable per-character cell
//   char-ranges-pending          — start..end pending readout
//   char-ranges-chip-{style}     — tri-state chip per style
//   char-ranges-add-button       — Add range button
//   char-ranges-row-{i}          — existing range row
//   char-ranges-delete-{i}       — delete button per row

import { useState } from "react";
import { type TristateValue } from "../../ui/Chip";
import { Button } from "../../ui/button";
import { useApplyStyle } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";

// Static lookup maps — Tailwind purge cannot resolve interpolated classes.
const tristateWrapperClasses: Record<TristateValue, string> = {
  off: "bg-raised border-border-2 text-ink-2",
  on: "bg-accent/10 border-accent text-accent",
  mixed: "bg-raised border-border-2 text-ink-3",
};

const tristateCycle: Record<TristateValue, TristateValue> = {
  off: "on",
  on: "mixed",
  mixed: "off",
};

type WordMatch = components["schemas"]["WordMatch"];

// Style label keys (lowercase, used as both testid suffix and backend label).
const STYLE_KEYS = ["italic", "bold", "sub", "super", "drop-cap"] as const;
type StyleKey = (typeof STYLE_KEYS)[number];

interface CharRange {
  start: number;
  end: number;
  styles: Record<StyleKey, TristateValue>;
}

function emptyStyles(): Record<StyleKey, TristateValue> {
  return {
    italic: "off",
    bold: "off",
    sub: "off",
    super: "off",
    "drop-cap": "off",
  };
}

function styleLabel(s: StyleKey, v: TristateValue): string {
  if (v === "off") return "";
  return s;
}

function rangeLabel(r: CharRange): string {
  return STYLE_KEYS.filter((s) => r.styles[s] === "on")
    .map((s) => styleLabel(s, "on"))
    .filter(Boolean)
    .join(", ");
}

export interface CharRangesSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
}

export function CharRangesSection({ word, projectId, pageIndex }: CharRangesSectionProps) {
  const applyStyle = useApplyStyle(projectId, pageIndex);

  const text = word.ocr_text ?? "";
  const chars = Array.from(text);

  // Pending range state.
  const [anchor, setAnchor] = useState<number | null>(null);
  const [endPos, setEndPos] = useState<number | null>(null);
  const [styles, setStyles] = useState<Record<StyleKey, TristateValue>>(emptyStyles());

  // Persisted ranges (local-only for now — see file header).
  const [ranges, setRanges] = useState<CharRange[]>([]);

  const pendingStart = anchor !== null && endPos !== null ? Math.min(anchor, endPos) : null;
  const pendingEnd = anchor !== null && endPos !== null ? Math.max(anchor, endPos) : null;
  const hasPendingRange = pendingStart !== null && pendingEnd !== null;

  function handleCellClick(i: number) {
    if (anchor === null) {
      setAnchor(i);
      setEndPos(null);
      setStyles(emptyStyles());
      return;
    }
    if (endPos === null) {
      setEndPos(i);
      return;
    }
    // Both anchor + endPos set → restart with a new anchor.
    setAnchor(i);
    setEndPos(null);
    setStyles(emptyStyles());
  }

  function handleChipChange(key: StyleKey, next: TristateValue) {
    setStyles((prev) => ({ ...prev, [key]: next }));
  }

  function handleAdd() {
    if (pendingStart === null || pendingEnd === null) return;
    const row: CharRange = {
      start: pendingStart,
      end: pendingEnd,
      styles: { ...styles },
    };
    setRanges((prev) => [...prev, row]);

    // Persist each enabled style (best-effort — see file header for caveats).
    const lineIndex = word.line_index;
    const wordIndex = word.word_index ?? 0;
    for (const s of STYLE_KEYS) {
      if (row.styles[s] === "on") {
        applyStyle.mutate({ lineIndex, wordIndex, style: s, scope: "part" });
      }
    }

    // Reset pending state.
    setAnchor(null);
    setEndPos(null);
    setStyles(emptyStyles());
  }

  function handleDelete(index: number) {
    setRanges((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div data-testid="char-ranges-section" className="flex flex-col gap-2 py-1">
      {/* Char cells */}
      <div className="flex flex-wrap gap-1">
        {chars.map((ch, i) => {
          const isAnchor = anchor === i;
          const isInPending =
            hasPendingRange && pendingStart !== null && pendingEnd !== null
              ? i >= pendingStart && i <= pendingEnd
              : isAnchor;
          return (
            <button
              key={i}
              data-testid={`char-cell-${i}`}
              data-range-anchor={isAnchor ? "true" : undefined}
              onClick={() => handleCellClick(i)}
              className={[
                "min-w-[18px] h-6 px-1.5 rounded border text-[11px] font-mono",
                isInPending
                  ? "bg-accent/15 border-accent text-accent"
                  : "bg-sunk border-border-2 text-ink-1 hover:bg-raised",
              ].join(" ")}
            >
              {ch}
            </button>
          );
        })}
      </div>

      {/* Pending range + chips */}
      <div className="flex flex-col gap-1.5 rounded border border-border-2 bg-sunk p-2">
        <p
          data-testid="char-ranges-pending"
          className="text-[10px] text-ink-3 uppercase tracking-wide"
        >
          {anchor === null
            ? "Click a char to start a range"
            : `Range: ${pendingStart ?? anchor}..${pendingEnd ?? "_"}`}
        </p>
        <div className="flex flex-wrap gap-1">
          {STYLE_KEYS.map((s) => {
            const v = styles[s];
            return (
              <button
                key={s}
                type="button"
                data-testid={`char-ranges-chip-${s}`}
                data-tristate-value={v}
                onClick={() => handleChipChange(s, tristateCycle[v])}
                className={[
                  "inline-flex items-center h-6 px-2.5 rounded-[12px] border cursor-pointer select-none text-[10px] font-semibold transition-colors duration-100",
                  tristateWrapperClasses[v],
                ].join(" ")}
              >
                {s}
              </button>
            );
          })}
        </div>
        <div className="flex justify-end">
          <Button
            data-testid="char-ranges-add-button"
            variant="secondary"
            size="sm"
            disabled={!hasPendingRange || applyStyle.isPending}
            onClick={handleAdd}
          >
            Add range
          </Button>
        </div>
      </div>

      {/* Existing ranges */}
      {ranges.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-[10px] text-ink-3 uppercase tracking-wide">Ranges</p>
          {ranges.map((r, i) => (
            <div
              key={i}
              data-testid={`char-ranges-row-${i}`}
              className="flex items-center justify-between gap-2 rounded border border-border-2 bg-sunk px-2 py-1 text-[11px]"
            >
              <span className="font-mono text-ink-2">
                {r.start}..{r.end}
              </span>
              <span className="text-ink-1 flex-1 truncate">{rangeLabel(r) || "—"}</span>
              <Button
                data-testid={`char-ranges-delete-${i}`}
                variant="ghost"
                size="sm"
                onClick={() => handleDelete(i)}
              >
                ×
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
