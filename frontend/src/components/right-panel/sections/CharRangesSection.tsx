// CharRangesSection.tsx — Char Ranges accordion section for word detail.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 19.
// P4.a (Gap 38): per-char glyph editor rows, overlap markers, STYLE/COMPONENT kind switcher.
// FO-2: switched from apply-style (scope:"part") to useSetCharRanges which
//        carries full (start, end, styles[]) position data to the backend.
//
// UI:
//   - One clickable cell per char in word.ocr_text.
//   - Click cell #1 = range anchor (start). Click cell #2 = range end.
//     If second click is before the anchor, the order is swapped.
//   - When a range is pending, STYLE chip selectors appear in the pending panel.
//   - "Add range" button (pending panel) appends a row from the pending selection.
//   - Existing ranges are shown as rich editor cards with:
//     - Glyph preview card (serif character display)
//     - Editable start/end position inputs
//     - STYLE / COMPONENT kind switcher (segmented control per card)
//     - Style or component chip palette based on active kind
//     - Overlap warning badge when ranges intersect
//     - Delete x button
//   - "+ Add range" button at bottom appends a blank range.
//
// data-testids (Slice 19 originals):
//   char-ranges-section          -- outer container
//   char-cell-{i}                -- clickable per-character cell
//   char-ranges-pending          -- start..end pending readout
//   char-ranges-chip-{style}     -- tri-state chip per style (pending panel)
//   char-ranges-add-button       -- Add range button (pending panel)
//   char-ranges-row-{i}          -- existing range card (compat alias)
//   char-ranges-delete-{i}       -- delete button per card (compat alias)
//
// data-testids (P4.a additions):
//   char-range-{N}               -- rich editor card per range
//   char-range-{N}-glyph         -- glyph preview card
//   char-range-{N}-delete        -- delete button
//   char-range-{N}-overlap-warning -- overlap badge (only when overlapping)
//   char-range-{N}-kind-style    -- STYLE kind segmented button
//   char-range-{N}-kind-component -- COMPONENT kind segmented button
//   char-range-add               -- bottom "+ Add range" button

import { useState, useEffect } from "react";
import { TriStateChip, type TriStateValue } from "@pdomain/pdomain-ui/primitives";
import { Button } from "../../ui/button";
import { useSetCharRanges } from "../../../hooks/useWordMutations";
import { ChipPalette, STYLE_ITEMS } from "../StylePalette";
import { COMPONENT_ITEMS } from "../ComponentPalette";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

// Style label keys used in the pending panel (tristate mode).
// Q-B2: use canonical book-tools label strings so the pending-panel styles
// round-trip correctly through the char-ranges sidecar and display as expected.
// Previous non-canonical keys: "italic", "sub", "super", "drop-cap".
const PENDING_STYLE_KEYS = ["italics", "bold", "subscript", "superscript", "drop cap"] as const;
type PendingStyleKey = (typeof PENDING_STYLE_KEYS)[number];

type RangeKind = "style" | "component";

interface CharRange {
  start: number;
  end: number;
  // Legacy tristate styles from the pending panel (kept for compat).
  styles: Record<PendingStyleKey, TriStateValue>;
  // P4.a: per-range kind + chip state.
  kind: RangeKind;
  activeStyles: Set<string>;
  activeComponents: Set<string>;
}

function emptyStyles(): Record<PendingStyleKey, TriStateValue> {
  return {
    italics: "off",
    bold: "off",
    subscript: "off",
    superscript: "off",
    "drop cap": "off",
  };
}

/** Human-readable label for a range (used in compat row). */
function rangeDisplayLabel(r: CharRange): string {
  const legacyOn = PENDING_STYLE_KEYS.filter((s) => r.styles[s] === "on");
  const styleOn = Array.from(r.activeStyles);
  const compOn = Array.from(r.activeComponents);
  return Array.from(new Set([...legacyOn, ...styleOn, ...compOn])).join(", ");
}

/** Derive the styles[] array to POST from a CharRange state.
 *  F-037: include activeComponents in the payload so component labels persist.
 */
function toApiStyles(r: CharRange): string[] {
  const legacyOn = PENDING_STYLE_KEYS.filter((s) => r.styles[s] === "on");
  const styleOn = Array.from(r.activeStyles);
  const compOn = Array.from(r.activeComponents);
  return Array.from(new Set([...legacyOn, ...styleOn, ...compOn]));
}

type ApiCharRange = components["schemas"]["CharRange-Output"];

/** Convert an API CharRange (from word.char_ranges) back to local CharRange state. */
function fromApiCharRange(r: ApiCharRange): CharRange {
  const styleSet = new Set(r.styles ?? []);
  const componentKeys = new Set(COMPONENT_ITEMS.map((item) => item.key));
  const activeStyles = new Set(r.styles?.filter((s) => !componentKeys.has(s)) ?? []);
  const activeComponents = new Set(r.styles?.filter((s) => componentKeys.has(s)) ?? []);
  const kind: RangeKind = activeComponents.size > 0 ? "component" : "style";
  const styles = Object.fromEntries(
    PENDING_STYLE_KEYS.map((k) => [k, styleSet.has(k) ? "on" : "off"]),
  ) as Record<PendingStyleKey, TriStateValue>;
  return { start: r.start, end: r.end, kind, styles, activeStyles, activeComponents };
}

/** Returns true if ranges A and B overlap (inclusive endpoints). */
function rangesOverlap(a: CharRange, b: CharRange): boolean {
  return a.start <= b.end && b.start <= a.end;
}

/** Returns a Set of indices that overlap with at least one other range. */
function computeOverlappingIndices(ranges: CharRange[]): Set<number> {
  const result = new Set<number>();
  for (let i = 0; i < ranges.length; i++) {
    for (let j = i + 1; j < ranges.length; j++) {
      // i and j are loop-bound — always within ranges.length — non-null safe.
      if (rangesOverlap(ranges[i]!, ranges[j]!)) {
        result.add(i);
        result.add(j);
      }
    }
  }
  return result;
}

// ---- Sub-components ---------------------------------------------------------

/** Small glyph card showing the characters covered by a range (P4.a). */
function GlyphCard({
  text,
  start,
  end,
  testId,
}: {
  text: string;
  start: number;
  end: number;
  testId: string;
}) {
  const chars = Array.from(text);
  const rangeChars = chars.slice(start, end + 1).join("");
  return (
    <div
      data-testid={testId}
      className="flex items-center justify-center min-w-[32px] h-8 px-1.5 rounded border border-border-2 bg-raised font-serif text-[13px] text-ink-1 select-none"
      title={`chars ${start}..${end}`}
    >
      {rangeChars || "?"}
    </div>
  );
}

/** Segmented STYLE | COMPONENT kind switcher (P4.a). */
function KindSwitcher({
  kind,
  onChange,
  rangeIndex,
}: {
  kind: RangeKind;
  onChange: (k: RangeKind) => void;
  rangeIndex: number;
}) {
  return (
    <div className="flex rounded border border-border-2 overflow-hidden text-[9px] font-bold tracking-wider uppercase">
      <button
        data-testid={`char-range-${rangeIndex}-kind-style`}
        onClick={() => {
          onChange("style");
        }}
        className={[
          "px-2 py-0.5 transition-colors",
          kind === "style" ? "bg-accent text-white" : "bg-raised text-ink-3 hover:bg-bg-raised",
        ].join(" ")}
      >
        Style
      </button>
      <button
        data-testid={`char-range-${rangeIndex}-kind-component`}
        onClick={() => {
          onChange("component");
        }}
        className={[
          "px-2 py-0.5 transition-colors border-l border-border-2",
          kind === "component" ? "bg-accent text-white" : "bg-raised text-ink-3 hover:bg-bg-raised",
        ].join(" ")}
      >
        Comp
      </button>
    </div>
  );
}

/** Editable character-offset input (P4.a). */
function PosInput({
  label,
  value,
  max,
  testId,
  onChange,
}: {
  label: string;
  value: number;
  max: number;
  testId?: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-[10px] text-ink-3">
      <span className="uppercase tracking-wide">{label}</span>
      <input
        type="number"
        min={0}
        max={max}
        data-testid={testId}
        value={value}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10);
          if (!isNaN(n)) onChange(Math.max(0, Math.min(max, n)));
        }}
        className="w-10 h-5 px-1 rounded border border-border-2 bg-sunk text-[10px] text-ink-1 text-center"
      />
    </label>
  );
}

// ---- Main component ---------------------------------------------------------

export interface CharRangesSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
}

export function CharRangesSection({ word, projectId, pageIndex }: CharRangesSectionProps) {
  const setCharRanges = useSetCharRanges(projectId, pageIndex);

  const text = word.ocr_text ?? "";
  const chars = Array.from(text);
  const maxIdx = Math.max(0, chars.length - 1);

  // Pending range state.
  const [anchor, setAnchor] = useState<number | null>(null);
  const [endPos, setEndPos] = useState<number | null>(null);
  const [pendingStyles, setPendingStyles] =
    useState<Record<PendingStyleKey, TriStateValue>>(emptyStyles);

  // Persisted range cards — initialise from word.char_ranges if present.
  const [ranges, setRanges] = useState<CharRange[]>(() =>
    (word.char_ranges ?? []).map(fromApiCharRange),
  );

  // Sync ranges when navigating to a different word.
  useEffect(() => {
    setRanges((word.char_ranges ?? []).map(fromApiCharRange));
  }, [word.char_ranges]);

  const pendingStart = anchor !== null && endPos !== null ? Math.min(anchor, endPos) : null;
  const pendingEnd = anchor !== null && endPos !== null ? Math.max(anchor, endPos) : null;
  const hasPendingRange = pendingStart !== null && pendingEnd !== null;

  const overlappingIndices = computeOverlappingIndices(ranges);

  // Persist full range list to backend.
  function persistRanges(nextRanges: CharRange[]) {
    const lineIndex = word.line_index;
    const wordIndex = word.word_index ?? 0;
    setCharRanges.mutate({
      lineIndex,
      wordIndex,
      ranges: nextRanges.map((r) => ({
        start: r.start,
        end: r.end,
        styles: toApiStyles(r),
      })),
    });
  }

  // ---- Pending panel handlers -----------------------------------------------

  function handleCellClick(i: number) {
    if (anchor === null) {
      setAnchor(i);
      setEndPos(null);
      setPendingStyles(emptyStyles);
      return;
    }
    if (endPos === null) {
      setEndPos(i);
      return;
    }
    // Both set -- restart.
    setAnchor(i);
    setEndPos(null);
    setPendingStyles(emptyStyles);
  }

  function handlePendingChipChange(key: PendingStyleKey, next: TriStateValue) {
    setPendingStyles((prev) => ({ ...prev, [key]: next }));
  }

  function handleAdd() {
    if (pendingStart === null || pendingEnd === null) return;
    const row: CharRange = {
      start: pendingStart,
      end: pendingEnd,
      styles: { ...pendingStyles },
      kind: "style",
      activeStyles: new Set(PENDING_STYLE_KEYS.filter((s) => pendingStyles[s] === "on")),
      activeComponents: new Set(),
    };
    const nextRanges = [...ranges, row];
    setRanges(nextRanges);
    persistRanges(nextRanges);

    setAnchor(null);
    setEndPos(null);
    setPendingStyles(emptyStyles);
  }

  // ---- Range card handlers (P4.a) -------------------------------------------

  function handleDelete(index: number) {
    const nextRanges = ranges.filter((_, i) => i !== index);
    setRanges(nextRanges);
    persistRanges(nextRanges);
  }

  // F-037: existing-range edits (kind, position, style/component chips) must
  // persist to the backend immediately — they previously only updated local state.
  // Using plain functions (not useCallback) because they depend on `persistRanges`
  // which is itself re-created on each render; memoisation would be a no-op.

  function handleKindChange(index: number, kind: RangeKind) {
    const next = ranges.map((r, i) => (i === index ? { ...r, kind } : r));
    setRanges(next);
    persistRanges(next);
  }

  function handleRangeStartChange(index: number, value: number) {
    const next = ranges.map((r, i) => (i === index ? { ...r, start: Math.min(value, r.end) } : r));
    setRanges(next);
    persistRanges(next);
  }

  function handleRangeEndChange(index: number, value: number) {
    const next = ranges.map((r, i) => (i === index ? { ...r, end: Math.max(value, r.start) } : r));
    setRanges(next);
    persistRanges(next);
  }

  function handleStyleChipChange(index: number, key: string, next: TriStateValue) {
    const updated = ranges.map((r, i) => {
      if (i !== index) return r;
      const activeStyles = new Set(r.activeStyles);
      if (next === "on" || next === "mixed") activeStyles.add(key);
      else activeStyles.delete(key);
      return { ...r, activeStyles };
    });
    setRanges(updated);
    persistRanges(updated);
  }

  function handleComponentChipChange(index: number, key: string, next: TriStateValue) {
    const updated = ranges.map((r, i) => {
      if (i !== index) return r;
      const activeComponents = new Set(r.activeComponents);
      if (next === "on" || next === "mixed") activeComponents.add(key);
      else activeComponents.delete(key);
      return { ...r, activeComponents };
    });
    setRanges(updated);
    persistRanges(updated);
  }

  function handleAddBlankRange() {
    const newRange: CharRange = {
      start: 0,
      end: maxIdx,
      styles: emptyStyles(),
      kind: "style",
      activeStyles: new Set(),
      activeComponents: new Set(),
    };
    const nextRanges = [...ranges, newRange];
    setRanges(nextRanges);
    persistRanges(nextRanges);
  }

  // ---- Render ---------------------------------------------------------------

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
              onClick={() => {
                handleCellClick(i);
              }}
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

      {/* Pending panel */}
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
          {PENDING_STYLE_KEYS.map((s) => (
            <TriStateChip
              key={s}
              value={pendingStyles[s]}
              data-testid={`char-ranges-chip-${s}`}
              onChange={(next) => {
                handlePendingChipChange(s, next);
              }}
            >
              {s}
            </TriStateChip>
          ))}
        </div>
        <div className="flex justify-end">
          <Button
            data-testid="char-ranges-add-button"
            variant="secondary"
            size="sm"
            disabled={!hasPendingRange || setCharRanges.isPending}
            onClick={handleAdd}
          >
            Add range
          </Button>
        </div>
      </div>

      {/* Rich editor cards (P4.a) */}
      {ranges.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] text-ink-3 uppercase tracking-wide">Ranges</p>
          {ranges.map((r, i) => {
            const isOverlapping = overlappingIndices.has(i);
            const label = rangeDisplayLabel(r);

            return (
              <div
                key={i}
                data-testid={`char-range-${i}`}
                className={[
                  "flex flex-col gap-2 rounded border bg-sunk p-2 text-[11px]",
                  isOverlapping ? "border-status-fuzzy" : "border-border-2",
                ].join(" ")}
              >
                {/* Row 1: glyph + positions + kind + actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  <GlyphCard
                    text={text}
                    start={r.start}
                    end={r.end}
                    testId={`char-range-${i}-glyph`}
                  />

                  <PosInput
                    label="S"
                    value={r.start}
                    max={maxIdx}
                    testId={`char-range-${i}-start`}
                    onChange={(v) => {
                      handleRangeStartChange(i, v);
                    }}
                  />
                  <PosInput
                    label="E"
                    value={r.end}
                    max={maxIdx}
                    testId={`char-range-${i}-end`}
                    onChange={(v) => {
                      handleRangeEndChange(i, v);
                    }}
                  />

                  <KindSwitcher
                    kind={r.kind}
                    onChange={(k) => {
                      handleKindChange(i, k);
                    }}
                    rangeIndex={i}
                  />

                  <div className="ml-auto flex items-center gap-1">
                    {isOverlapping && (
                      <span
                        data-testid={`char-range-${i}-overlap-warning`}
                        className="text-[9px] font-semibold text-status-fuzzy uppercase tracking-wide border border-status-fuzzy rounded px-1 py-0.5"
                      >
                        overlap
                      </span>
                    )}
                    <Button
                      data-testid={`char-range-${i}-delete`}
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        handleDelete(i);
                      }}
                    >
                      x
                    </Button>
                  </div>
                </div>

                {/* Row 2: chip palette */}
                {r.kind === "style" ? (
                  <ChipPalette
                    items={STYLE_ITEMS}
                    activeKeys={r.activeStyles}
                    data-testid-prefix={`char-range-${i}-style-chip`}
                    onChange={(key, next) => {
                      handleStyleChipChange(i, key, next);
                    }}
                  />
                ) : (
                  <ChipPalette
                    items={COMPONENT_ITEMS}
                    activeKeys={r.activeComponents}
                    data-testid-prefix={`char-range-${i}-component-chip`}
                    onChange={(key, next) => {
                      handleComponentChipChange(i, key, next);
                    }}
                  />
                )}

                {/* Row 3: tag summary */}
                {label && (
                  <p className="text-[10px] text-ink-3 truncate">
                    <span className="font-mono text-ink-2">
                      {r.start}..{r.end}
                    </span>
                    {" -- "}
                    {label}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Slice-19 compat: hidden range rows + delete buttons with legacy testids. */}
      {ranges.map((r, i) => (
        <div
          key={`compat-row-${i}`}
          data-testid={`char-ranges-row-${i}`}
          className="sr-only"
          aria-hidden="true"
        >
          {r.start}..{r.end} {rangeDisplayLabel(r)}
          <button
            data-testid={`char-ranges-delete-${i}`}
            onClick={() => {
              handleDelete(i);
            }}
            aria-hidden="true"
            tabIndex={-1}
          >
            x
          </button>
        </div>
      ))}

      {/* P4.a: bottom "+ Add range" button */}
      <Button
        data-testid="char-range-add"
        variant="outline"
        size="sm"
        className="w-full text-[10px]"
        onClick={handleAddBlankRange}
      >
        + Add range
      </Button>
    </div>
  );
}
