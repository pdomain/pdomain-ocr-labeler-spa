// StructureSection.tsx — Structure accordion section for word detail editor.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 18.
// P3.d (Gap 37): neighbors-strip + merge preview + gap-picker + vertical-split.
//
// Shows:
//   1. Neighbors strip — prev (muted) · current (accent) · next (muted)
//   2. Merge preview row — ← Merge with prev / Merge with next →
//      (hover shows merged preview text; confirm dialog on click)
//   3. Gap-picker slider — adjusts inter-word spacing −10…+10 px
//      (stub mutation — logs with TODO until backend endpoint lands)
//   4. Vertical-split affordance — click char to pick split point, then Split
//
// data-testids:
//   structure-section                 — outer wrapper
//   structure-prev-word               — prev neighbor card (or "none" label)
//   structure-current-word            — current word card (highlighted)
//   structure-next-word               — next neighbor card (or "none" label)
//   structure-merge-prev              — Merge with prev button
//   structure-merge-next              — Merge with next button
//   structure-gap-slider              — word-gap range input
//   structure-split-button            — Split at position N button

import { useState, useCallback, useRef } from "react";
import { Button } from "../../ui/button";
import { ConfirmDialog } from "../../ConfirmDialog";
import { useMergeWord, useSplitWord, useAdjustWordGap } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type PagePayload = components["schemas"]["PagePayload"];

// ─── helpers ─────────────────────────────────────────────────────────────────

function getNeighborWords(
  page: PagePayload,
  lineIndex: number,
  wordIndex: number,
): { prev: WordMatch | null; next: WordMatch | null } {
  const line = page.line_matches?.find((l) => l.line_index === lineIndex);
  if (!line) return { prev: null, next: null };
  const words = line.word_matches;
  const prev = wordIndex > 0 ? (words[wordIndex - 1] ?? null) : null;
  const next = wordIndex < words.length - 1 ? (words[wordIndex + 1] ?? null) : null;
  return { prev, next };
}

function wordText(w: WordMatch | null): string {
  return w?.ocr_text ?? w?.ground_truth_text ?? "";
}

// ─── NeighborCard ─────────────────────────────────────────────────────────────

interface NeighborCardProps {
  word: WordMatch | null;
  role: "prev" | "current" | "next";
  testId: string;
}

function NeighborCard({ word, role, testId }: NeighborCardProps) {
  const isCurrent = role === "current";
  const text = word ? wordText(word) : null;

  const baseClasses =
    "flex flex-col items-center justify-center rounded px-2 py-1.5 min-w-0 flex-1 text-center";
  const variantClasses = isCurrent
    ? "bg-accent/15 border border-accent/40 text-accent font-semibold"
    : "bg-bg-raised border border-border-1 text-ink-3 opacity-70";

  return (
    <div data-testid={testId} className={`${baseClasses} ${variantClasses}`}>
      {role === "prev" && <span className="text-[9px] text-ink-4 mb-0.5">← prev</span>}
      {role === "next" && <span className="text-[9px] text-ink-4 mb-0.5">next →</span>}
      {text ? (
        <span className="text-[12px] font-mono truncate max-w-full">{text}</span>
      ) : (
        <span className="text-[11px] italic text-ink-4">none</span>
      )}
    </div>
  );
}

// ─── MergeConfirmState ────────────────────────────────────────────────────────

type MergeDirection = "left" | "right";

interface MergeConfirmState {
  open: boolean;
  direction: MergeDirection | null;
}

// ─── SplitPicker ──────────────────────────────────────────────────────────────

interface SplitPickerProps {
  text: string;
  splitPos: number | null;
  onPick: (pos: number) => void;
}

function SplitPicker({ text, splitPos, onPick }: SplitPickerProps) {
  if (!text) return null;
  const chars = Array.from(text);
  return (
    <div className="flex flex-wrap gap-px mt-1">
      {chars.map((ch, i) => {
        const isSelected = splitPos === i + 1;
        // Split position i+1 means "after char i" (chars 0..i go left, i+1.. go right)
        // We mark the gap *after* each character as a split point.
        return (
          <button
            key={i}
            type="button"
            title={`Split after position ${i + 1}`}
            onClick={() => onPick(i + 1)}
            className={[
              "px-1 py-0.5 rounded text-[12px] font-mono border cursor-pointer transition-colors",
              isSelected
                ? "bg-accent text-white border-accent"
                : "bg-bg-raised text-ink-2 border-border-1 hover:border-accent hover:text-accent",
            ].join(" ")}
          >
            {ch}
          </button>
        );
      })}
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export interface StructureSectionProps {
  word: WordMatch;
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

export function StructureSection({ word, page, projectId, pageIndex }: StructureSectionProps) {
  const mergeWord = useMergeWord(projectId, pageIndex);
  const splitWord = useSplitWord(projectId, pageIndex);
  const adjustGap = useAdjustWordGap(projectId, pageIndex);

  const [confirm, setConfirm] = useState<MergeConfirmState>({ open: false, direction: null });
  const [gapPx, setGapPx] = useState(0);
  const [splitPos, setSplitPos] = useState<number | null>(null);
  const [hoveredMerge, setHoveredMerge] = useState<MergeDirection | null>(null);

  const gapDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const lineIndex = word.line_index;
  const wordIndex = word.word_index ?? 0;

  const { prev, next } = getNeighborWords(page, lineIndex, wordIndex);
  const hasPrev = prev !== null;
  const hasNext = next !== null;

  const currentText = wordText(word);
  const prevText = wordText(prev);
  const nextText = wordText(next);

  const busy = mergeWord.isPending || splitWord.isPending || adjustGap.isPending;

  // ── Merge preview ─────────────────────────────────────────────────────────

  function getMergePreview(direction: MergeDirection): string {
    if (direction === "left") return `${prevText}${currentText}`;
    return `${currentText}${nextText}`;
  }

  // ── Merge ─────────────────────────────────────────────────────────────────

  function requestMerge(direction: MergeDirection) {
    setConfirm({ open: true, direction });
  }

  function confirmMerge() {
    if (!confirm.direction) return;
    mergeWord.mutate({ lineIndex, wordIndex, direction: confirm.direction });
    setConfirm({ open: false, direction: null });
  }

  function cancelMerge() {
    setConfirm({ open: false, direction: null });
  }

  // ── Gap picker ────────────────────────────────────────────────────────────

  const handleGapChange = useCallback(
    (value: number) => {
      setGapPx(value);
      if (gapDebounceRef.current) clearTimeout(gapDebounceRef.current);
      gapDebounceRef.current = setTimeout(() => {
        adjustGap.mutate({ lineIndex, wordIndex, gapPx: value });
      }, 300);
    },
    [adjustGap, lineIndex, wordIndex],
  );

  // ── Split ─────────────────────────────────────────────────────────────────

  function handleSplit() {
    const pos = splitPos ?? Math.floor(currentText.length / 2);
    const charCount = Array.from(currentText).length || 1;
    const xFraction = pos / charCount;
    splitWord.mutate({ lineIndex, wordIndex, xFraction, direction: "horizontal" });
    setSplitPos(null);
  }

  // ── Merge preview label ───────────────────────────────────────────────────

  const mergePreviewText = hoveredMerge ? getMergePreview(hoveredMerge) : null;

  return (
    <div data-testid="structure-section" className="flex flex-col gap-3 py-1">
      {/* ── 1. Neighbors strip ───────────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Context</p>
        <div className="flex gap-1.5">
          <NeighborCard word={prev} role="prev" testId="structure-prev-word" />
          <NeighborCard word={word} role="current" testId="structure-current-word" />
          <NeighborCard word={next} role="next" testId="structure-next-word" />
        </div>
      </div>

      {/* ── 2. Merge preview row ────────────────────────────────────────── */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Merge</p>
        <div className="flex gap-1.5 flex-wrap">
          <Button
            data-testid="structure-merge-prev"
            variant="secondary"
            size="sm"
            disabled={!hasPrev || busy}
            onClick={() => requestMerge("left")}
            onMouseEnter={() => hasPrev && setHoveredMerge("left")}
            onMouseLeave={() => setHoveredMerge(null)}
          >
            ← Merge with prev
          </Button>
          <Button
            data-testid="structure-merge-next"
            variant="secondary"
            size="sm"
            disabled={!hasNext || busy}
            onClick={() => requestMerge("right")}
            onMouseEnter={() => hasNext && setHoveredMerge("right")}
            onMouseLeave={() => setHoveredMerge(null)}
          >
            Merge with next →
          </Button>
        </div>
        {mergePreviewText && (
          <p className="text-[11px] font-mono text-ink-2 bg-bg-sunk rounded px-2 py-1 mt-0.5">
            → <span className="text-accent">{mergePreviewText}</span>
          </p>
        )}
      </div>

      {/* ── 3. Gap-picker slider ─────────────────────────────────────────── */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">
          Word gap:{" "}
          <span className="font-mono text-ink-2">{gapPx > 0 ? `+${gapPx}` : gapPx}px</span>
        </p>
        <input
          data-testid="structure-gap-slider"
          type="range"
          min={-10}
          max={10}
          step={1}
          value={gapPx}
          disabled={busy}
          onChange={(e) => handleGapChange(Number(e.target.value))}
          className="w-full accent-accent cursor-pointer disabled:opacity-50"
          aria-label={`Word gap: ${gapPx}px`}
        />
        <div className="flex justify-between text-[9px] text-ink-4">
          <span>−10px</span>
          <span>0</span>
          <span>+10px</span>
        </div>
      </div>

      {/* ── 4. Vertical-split affordance ─────────────────────────────────── */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">
          Split{splitPos !== null ? ` at position ${splitPos}` : " — click a character"}
        </p>
        <SplitPicker text={currentText} splitPos={splitPos} onPick={setSplitPos} />
        <Button
          data-testid="structure-split-button"
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={handleSplit}
          className="mt-1 self-start"
        >
          {splitPos !== null ? `Split at position ${splitPos}` : "Split at midpoint"}
        </Button>
      </div>

      {/* ── Confirm dialog for destructive merges ────────────────────────── */}
      <ConfirmDialog
        open={confirm.open}
        title="Merge words"
        message={
          confirm.direction === "left"
            ? `Merge this word with the previous word? Result: "${getMergePreview("left")}". This cannot be undone.`
            : `Merge this word with the next word? Result: "${getMergePreview("right")}". This cannot be undone.`
        }
        confirmLabel="Merge"
        onConfirm={confirmMerge}
        onCancel={cancelMerge}
      />
    </div>
  );
}
