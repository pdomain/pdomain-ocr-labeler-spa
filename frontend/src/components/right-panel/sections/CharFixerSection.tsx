// CharFixerSection.tsx — Per-character GT editor for a word.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.
// P4.b (Gap 39): per-char bbox visualisation + drag-handle canvas + selected-
//                range coordinate detail strip + Apply commit button.
//
// Renders (top to bottom):
//   1. CharFixerCanvas — Konva mini-canvas with one coloured rectangle per
//      char range. Each rectangle is clickable to select it; the selected
//      range gets 8 drag handles (corners + midpoints) for direct bbox
//      manipulation. The set of ranges is synthesised from the word's
//      OCR text — one range per character — so the canvas works even
//      when the server has not yet emitted CharRange metadata for this
//      word. (CharRange.bbox is purely client-side state for now; the
//      server schema is start/end/styles only.)
//   2. Selected-range detail strip showing the range's character text and
//      four editable x1/y1/x2/y2 numeric inputs (image-pixel coords).
//   3. Apply button — disabled until at least one bbox has been modified.
//      (Wiring to a real persistence endpoint lives in a later slice; the
//      current iteration just resets local "dirty" tracking on Apply.)
//   4. Existing per-char GT input grid (Slice 20).
//   5. Unicode picker toggle (Slice 20).
//
// Edits to the GT input grid are debounced (500ms) and saved by POSTing the
// reconstructed GT string to the word-GT endpoint (Slice 20). Bbox edits are
// purely local in P4.b — the Apply button is a placeholder for the future
// CharRange-with-bbox persistence call.
//
// data-testids (Slice 20):
//   char-fixer-section                  — outer container
//   char-fixer-cell-{i}                 — per-char wrapper
//   char-fixer-orig-{i}                 — original (OCR) char label
//   char-fixer-input-{i}                — editable input
//   char-fixer-open-picker-button       — toggle Unicode picker
//
// data-testids (P4.b additions):
//   charfixer-canvas                    — Konva canvas (from CharFixerCanvas)
//   charfixer-range-{N}                 — per-range bbox rectangle
//   charfixer-range-{N}-handle-{pos}    — drag handles on the selected range
//   charfixer-detail-strip              — selected-range detail container
//   charfixer-detail-text               — selected range's character text
//   charfixer-detail-x1                 — editable x1 input
//   charfixer-detail-y1                 — editable y1 input
//   charfixer-detail-x2                 — editable x2 input
//   charfixer-detail-y2                 — editable y2 input
//   charfixer-apply                     — Apply button (disabled until dirty)

import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Button } from "../../ui/button";
import { Input } from "../../ui/Input";
import { UnicodePicker } from "../UnicodePicker";
import { useUpdateWordGroundTruth, useSetCharBboxes } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";
import { CharFixerCanvas, initialCharBboxes, type CharRangeBBox } from "./CharFixerCanvas";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];

const DEBOUNCE_MS = 500;

export interface CharFixerSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
  /** Optional cropped-word image URL forwarded to CharFixerCanvas. */
  imageUrl?: string;
}

/**
 * Build the initial per-char range set from a word's OCR text — one range
 * per character. The set is *stable* across re-renders for a given word
 * (the wordKey effect resets state when the underlying word changes).
 */
function buildInitialCharBboxes(word: WordMatch): CharRangeBBox[] {
  const chars = Array.from(word.ocr_text ?? "");
  if (chars.length === 0) return [];
  const ranges = chars.map((_, i) => ({ start: i, end: i }));
  return initialCharBboxes(word.bbox, ranges, chars.length);
}

/** Tiny numeric input bound to one coordinate of the selected range's bbox. */
function CoordInput({
  label,
  value,
  testId,
  onChange,
}: {
  label: string;
  value: number;
  testId: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-[10px] text-ink-3">
      <span className="uppercase tracking-wide">{label}</span>
      <input
        type="number"
        data-testid={testId}
        value={Math.round(value)}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10);
          if (!isNaN(n)) onChange(n);
        }}
        className="w-14 h-5 px-1 rounded border border-border-2 bg-sunk text-[10px] text-ink-1 text-center"
      />
    </label>
  );
}

export function CharFixerSection({ word, projectId, pageIndex, imageUrl }: CharFixerSectionProps) {
  const updateGt = useUpdateWordGroundTruth(projectId, pageIndex);
  const charBboxesMutation = useSetCharBboxes(projectId, pageIndex);

  const ocrChars = useMemo(() => Array.from(word.ocr_text ?? ""), [word.ocr_text]);
  const gtChars = useMemo(() => Array.from(word.ground_truth_text ?? ""), [word.ground_truth_text]);

  // The number of editable cells is the max of OCR and GT lengths so a
  // longer GT is fully editable and a longer OCR shows all the originals.
  const cellCount = Math.max(ocrChars.length, gtChars.length);

  const initialDraft = useMemo(() => {
    const arr: string[] = [];
    for (let i = 0; i < cellCount; i += 1) arr.push(gtChars[i] ?? "");
    return arr;
  }, [cellCount, gtChars]);

  const [draft, setDraft] = useState<string[]>(initialDraft);
  const wordKey = `${word.line_index}-${word.word_index ?? 0}-${word.ground_truth_text}`;
  const lastWordKey = useRef(wordKey);

  // ---- P4.b: bbox state -----------------------------------------------------

  const initialBboxes = useMemo(() => buildInitialCharBboxes(word), [word]);
  const [charBboxes, setCharBboxes] = useState<CharRangeBBox[]>(initialBboxes);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(
    initialBboxes.length > 0 ? 0 : null,
  );
  const [dirty, setDirty] = useState(false);

  // Reset draft + bbox state when the underlying word changes.
  useEffect(() => {
    if (lastWordKey.current !== wordKey) {
      setDraft(initialDraft);
      setCharBboxes(initialBboxes);
      setSelectedIndex(initialBboxes.length > 0 ? 0 : null);
      setDirty(false);
      lastWordKey.current = wordKey;
    }
  }, [wordKey, initialDraft, initialBboxes]);

  // Refs to each input cell, for the unicode picker to insert into.
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const lastFocusedIndex = useRef<number | null>(null);

  // Debounce timer for save.
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function scheduleSave(next: string[]) {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      const text = next.join("");
      updateGt.mutate({
        lineIndex: word.line_index,
        wordIndex: word.word_index ?? 0,
        text,
      });
    }, DEBOUNCE_MS);
  }

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  function handleChange(i: number, value: string) {
    setDraft((prev) => {
      const next = [...prev];
      next[i] = value;
      scheduleSave(next);
      return next;
    });
  }

  function handleFocus(i: number) {
    lastFocusedIndex.current = i;
  }

  const [pickerOpen, setPickerOpen] = useState(false);

  function handleInsertGlyph(glyph: string) {
    const i = lastFocusedIndex.current;
    if (i === null) return;
    setDraft((prev) => {
      const next = [...prev];
      next[i] = glyph;
      scheduleSave(next);
      return next;
    });
    // Return focus to the cell after insertion.
    requestAnimationFrame(() => {
      inputRefs.current[i]?.focus();
    });
  }

  // ---- P4.b: bbox handlers --------------------------------------------------

  const handleSelect = useCallback((index: number) => {
    setSelectedIndex(index);
  }, []);

  const handleBboxChange = useCallback((index: number, next: BBox) => {
    setCharBboxes((prev) => {
      if (index < 0 || index >= prev.length) return prev;
      const copy = [...prev];
      // index < prev.length checked above — non-null safe.
      copy[index] = { ...copy[index]!, bbox: next };
      return copy;
    });
    setDirty(true);
  }, []);

  const handleCoordChange = useCallback(
    (axis: "x1" | "y1" | "x2" | "y2", value: number) => {
      if (selectedIndex === null) return;
      setCharBboxes((prev) => {
        if (selectedIndex < 0 || selectedIndex >= prev.length) return prev;
        // selectedIndex < prev.length checked above — non-null safe.
        const cur = prev[selectedIndex]!;
        const b = cur.bbox;
        let x1 = b.x;
        let y1 = b.y;
        let x2 = b.x + b.width;
        let y2 = b.y + b.height;
        if (axis === "x1") x1 = value;
        else if (axis === "y1") y1 = value;
        else if (axis === "x2") x2 = value;
        else if (axis === "y2") y2 = value;
        // Normalise so width/height stay positive.
        const nx = Math.min(x1, x2);
        const ny = Math.min(y1, y2);
        const nw = Math.max(1, Math.abs(x2 - x1));
        const nh = Math.max(1, Math.abs(y2 - y1));
        const copy = [...prev];
        copy[selectedIndex] = { ...cur, bbox: { x: nx, y: ny, width: nw, height: nh } };
        return copy;
      });
      setDirty(true);
    },
    [selectedIndex],
  );

  function handleApply() {
    // POST the current per-char bboxes to the backend so they survive
    // page reloads (stored in word_attributes sidecar via char-bboxes endpoint).
    charBboxesMutation.mutate({
      lineIndex: word.line_index,
      wordIndex: word.word_index ?? 0,
      charBboxes: charBboxes.map((r) => r.bbox),
    });
    setDirty(false);
  }

  const selected =
    selectedIndex !== null && selectedIndex < charBboxes.length ? charBboxes[selectedIndex] : null;
  const selectedText = selected
    ? ocrChars.slice(selected.start, selected.end + 1).join("") || "∅"
    : "";

  return (
    <div data-testid="char-fixer-section" className="flex flex-col gap-2 py-1">
      {/* P4.b: per-char bbox canvas */}
      {charBboxes.length > 0 && (
        <CharFixerCanvas
          wordBbox={word.bbox}
          charBboxes={charBboxes}
          imageUrl={imageUrl}
          selectedIndex={selectedIndex}
          onSelect={handleSelect}
          onChange={handleBboxChange}
        />
      )}

      {/* P4.b: selected-range detail strip */}
      {selected && (
        <div
          data-testid="charfixer-detail-strip"
          className="flex flex-wrap items-center gap-2 rounded border border-border-2 bg-sunk px-2 py-1.5"
        >
          <span
            data-testid="charfixer-detail-text"
            className="font-mono text-[12px] text-ink-1 px-1"
            title={`chars ${selected.start}..${selected.end}`}
          >
            {selectedText}
          </span>
          <CoordInput
            label="x1"
            value={selected.bbox.x}
            testId="charfixer-detail-x1"
            onChange={(v) => {
              handleCoordChange("x1", v);
            }}
          />
          <CoordInput
            label="y1"
            value={selected.bbox.y}
            testId="charfixer-detail-y1"
            onChange={(v) => {
              handleCoordChange("y1", v);
            }}
          />
          <CoordInput
            label="x2"
            value={selected.bbox.x + selected.bbox.width}
            testId="charfixer-detail-x2"
            onChange={(v) => {
              handleCoordChange("x2", v);
            }}
          />
          <CoordInput
            label="y2"
            value={selected.bbox.y + selected.bbox.height}
            testId="charfixer-detail-y2"
            onChange={(v) => {
              handleCoordChange("y2", v);
            }}
          />
          <Button
            data-testid="charfixer-apply"
            variant="secondary"
            size="sm"
            disabled={!dirty}
            onClick={handleApply}
            className="ml-auto"
          >
            Apply
          </Button>
        </div>
      )}

      {/* Per-char GT input grid (Slice 20) */}
      <div className="grid grid-cols-6 gap-1.5">
        {Array.from({ length: cellCount }).map((_, i) => {
          const orig = ocrChars[i] ?? "";
          const gtChar = gtChars[i] ?? "";
          const draftChar = draft[i] ?? "";
          const isMismatch = orig !== gtChar;
          return (
            <div
              key={i}
              data-testid={`char-fixer-cell-${i}`}
              data-mismatch={isMismatch ? "true" : undefined}
              className={[
                "flex flex-col items-center gap-0.5 rounded border bg-sunk px-1 py-1",
                isMismatch
                  ? "border-l-2 border-l-status-mismatch border-border-2"
                  : "border-border-2",
              ].join(" ")}
            >
              <span
                data-testid={`char-fixer-orig-${i}`}
                className="text-[10px] text-ink-3 font-mono leading-none"
                title={`OCR char ${i}`}
              >
                {orig || "∅"}
              </span>
              <Input
                ref={(el) => {
                  inputRefs.current[i] = el;
                }}
                data-testid={`char-fixer-input-${i}`}
                size="sm"
                className="text-center px-0.5 h-6"
                value={draftChar}
                onChange={(e) => {
                  handleChange(i, e.target.value);
                }}
                onFocus={() => {
                  handleFocus(i);
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Unicode picker toggle */}
      <div className="flex justify-end">
        <Button
          data-testid="char-fixer-open-picker-button"
          variant="secondary"
          size="sm"
          onClick={() => {
            setPickerOpen((v) => !v);
          }}
        >
          {pickerOpen ? "Close Unicode picker" : "Open Unicode picker"}
        </Button>
      </div>

      {pickerOpen && <UnicodePicker onInsert={handleInsertGlyph} />}
    </div>
  );
}
