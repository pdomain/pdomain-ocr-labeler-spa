// OcrGtCompareRow.tsx — OCR/GT compare row + Ω chars inline trigger (P2.c, Gap 30).
//
// Two-column row:
//   Left:  OCR text in a code-style well (monospace, read-only)
//   Right: GT text in an <Input> with:
//     - copy-OCR-to-GT button (one-click to fill GT from OCR)
//     - an Ω chars button that opens UnicodePicker inline (collapsible)
//
// The GT input calls onCommitGt when blurred with a changed value.
// The UnicodePicker inserts at the current cursor position.
//
// data-testids:
//   ocr-gt-compare              — outer container
//   ocr-gt-ocr-well             — OCR text read-only well
//   ocr-gt-copy-btn             — copy OCR→GT button
//   ocr-gt-input                — GT text input
//   ocr-gt-omega-btn            — Ω chars toggle button
//   ocr-gt-unicode-picker       — inline UnicodePicker wrapper (when open)

import { useState, useRef } from "react";
import { Input } from "../ui/Input";
import { UnicodePicker } from "./UnicodePicker";

export interface OcrGtCompareRowProps {
  ocrText: string;
  gtText: string;
  onCommitGt: (text: string) => void;
  /**
   * S2.1: Called when the user presses Tab (dir="next") or Shift+Tab
   * (dir="prev") while focused on the GT input. The current GT value is
   * committed before this callback fires. When omitted, Tab falls through
   * to default browser behavior.
   */
  onTab?: ((dir: "next" | "prev") => void) | undefined;
}

export function OcrGtCompareRow({ ocrText, gtText, onCommitGt, onTab }: OcrGtCompareRowProps) {
  const [localGt, setLocalGt] = useState(gtText);
  const [pickerOpen, setPickerOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync when word changes
  if (localGt !== gtText && document.activeElement !== inputRef.current) {
    setLocalGt(gtText);
  }

  /** Persist the current GT value if it has changed. */
  function commitGt() {
    if (localGt !== gtText) {
      onCommitGt(localGt);
    }
  }

  function handleBlur() {
    commitGt();
  }

  function handleGtKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Tab" && onTab) {
      e.preventDefault();
      commitGt();
      onTab(e.shiftKey ? "prev" : "next");
    }
  }

  function handleCopyOcr() {
    setLocalGt(ocrText);
    if (ocrText !== gtText) {
      onCommitGt(ocrText);
    }
    inputRef.current?.focus();
  }

  function handleInsertGlyph(glyph: string) {
    const el = inputRef.current;
    if (!el) {
      setLocalGt((prev) => prev + glyph);
      return;
    }
    const start = el.selectionStart ?? localGt.length;
    const end = el.selectionEnd ?? localGt.length;
    const next = localGt.slice(0, start) + glyph + localGt.slice(end);
    setLocalGt(next);
    // Restore cursor after glyph insertion
    requestAnimationFrame(() => {
      el.setSelectionRange(start + glyph.length, start + glyph.length);
    });
  }

  return (
    <div data-testid="ocr-gt-compare" className="flex flex-col gap-1.5 px-3 py-2">
      {/* Two-column compare row */}
      <div className="flex gap-2">
        {/* Left: OCR text well (read-only) */}
        <div className="flex-1 min-w-0">
          <div className="text-[9px] font-semibold tracking-wider uppercase text-ink-3 mb-0.5">
            OCR
          </div>
          <div
            data-testid="ocr-gt-ocr-well"
            className="h-8 px-2 flex items-center rounded border border-border-2 bg-bg-sunk font-mono text-[11px] text-ink-2 overflow-hidden truncate select-all"
          >
            {ocrText || <span className="text-ink-4 italic">∅</span>}
          </div>
        </div>

        {/* Right: GT input with copy + Ω buttons */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-semibold tracking-wider uppercase text-ink-3">GT</span>
            <div className="flex gap-0.5">
              <button
                type="button"
                data-testid="ocr-gt-copy-btn"
                title="Copy OCR text to GT"
                onClick={handleCopyOcr}
                className="h-4 px-1.5 text-[9px] rounded border border-border-2 text-ink-3 hover:text-ink-1 hover:border-accent transition-colors"
              >
                ← OCR
              </button>
              <button
                type="button"
                data-testid="ocr-gt-omega-btn"
                title="Insert special character"
                aria-pressed={pickerOpen}
                onClick={() => {
                  setPickerOpen((o) => !o);
                }}
                className={[
                  "h-4 px-1.5 text-[9px] rounded border transition-colors font-mono",
                  pickerOpen
                    ? "bg-accent text-accent-ink border-accent"
                    : "border-border-2 text-ink-3 hover:text-ink-1 hover:border-accent",
                ].join(" ")}
              >
                Ω
              </button>
            </div>
          </div>
          <Input
            ref={inputRef}
            data-testid="ocr-gt-input"
            size="sm"
            value={localGt}
            onChange={(e) => {
              setLocalGt(e.target.value);
            }}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              handleGtKeyDown(e);
              if (e.key === "Enter") {
                e.preventDefault();
                inputRef.current?.blur();
              }
            }}
            className="font-mono"
          />
        </div>
      </div>

      {/* Inline UnicodePicker — collapsible */}
      {pickerOpen && (
        <div data-testid="ocr-gt-unicode-picker">
          <UnicodePicker onInsert={handleInsertGlyph} />
        </div>
      )}
    </div>
  );
}
