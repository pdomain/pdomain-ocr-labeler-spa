// CharFixerSection.tsx — Per-character GT editor for a word.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.
//
// Renders a per-char grid:
//   - Original OCR char shown as a small label.
//   - Editable Input whose initial value is the GT char.
//   - Cells where OCR ≠ GT get a ``data-mismatch`` attribute and a
//     ``--status-mismatch`` left edge stripe.
//
// Edits are debounced (500ms after last keystroke) and saved by
// POSTing the reconstructed GT string to the word-GT endpoint.  An
// "Open Unicode picker" button reveals the UnicodePicker; selecting a
// glyph inserts it at the last-focused char input (replacing its value).
//
// data-testids:
//   char-fixer-section                  — outer container
//   char-fixer-cell-{i}                 — per-char wrapper
//   char-fixer-orig-{i}                 — original (OCR) char label
//   char-fixer-input-{i}                — editable input
//   char-fixer-open-picker-button       — toggle Unicode picker

import { useState, useRef, useEffect, useMemo } from "react";
import { Button } from "../../ui/button";
import { Input } from "../../ui/Input";
import { UnicodePicker } from "../UnicodePicker";
import { useUpdateWordGroundTruth } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

const DEBOUNCE_MS = 500;

export interface CharFixerSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
}

export function CharFixerSection({ word, projectId, pageIndex }: CharFixerSectionProps) {
  const updateGt = useUpdateWordGroundTruth(projectId, pageIndex);

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

  // Reset draft when the underlying word changes (server-side update).
  useEffect(() => {
    if (lastWordKey.current !== wordKey) {
      setDraft(initialDraft);
      lastWordKey.current = wordKey;
    }
  }, [wordKey, initialDraft]);

  // Refs to each input cell, for the unicode picker to insert into.
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);
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

  return (
    <div data-testid="char-fixer-section" className="flex flex-col gap-2 py-1">
      {/* Per-char grid */}
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
                onChange={(e) => handleChange(i, e.target.value)}
                onFocus={() => handleFocus(i)}
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
          onClick={() => setPickerOpen((v) => !v)}
        >
          {pickerOpen ? "Close Unicode picker" : "Open Unicode picker"}
        </Button>
      </div>

      {pickerOpen && <UnicodePicker onInsert={handleInsertGlyph} />}
    </div>
  );
}
