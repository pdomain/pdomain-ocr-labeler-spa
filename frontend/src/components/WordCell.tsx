// WordCell.tsx — per-word 5-row CSS grid with GT input.
// Spec: docs/specs/2026-05-12-word-matches-design.md §WordCell grid
// Issue #203
//
// Layout (5 rows):
//   Row 1: status icon + validated checkbox
//   Row 2: image slice (crop URL, skipped when no word_id or no page image URL)
//   Row 3: OCR text + style/component tag chips
//   Row 4: GT <input> — blur-commit, optimistic, revert on error
//   Row 5: match status badge
//
// GT editing: controlled <input>; on blur, if value changed → call onCommitGt.
// Tab/Shift-Tab navigation between GT inputs is handled at the parent level
// via natural DOM tab order (inputs within a line card render in DOM order).
//
// data-testids (driver-contract §2.8):
//   word-image-cell-{l}-{w}          — outer container (spec canonical, driver-contract §2.8)
//   word-cell-{word_id}              — outer container (internal alias; kept for tests)
//   word-checkbox-{l}-{w}            — word selection checkbox (§2.8)
//   word-validate-button-{l}-{w}     — per-word validate toggle (§2.8)
//   gt-text-input-{l}-{w}            — GT text input (spec canonical)
//   ocr-text-label-{l}-{w}           — OCR text label (spec canonical)
//   word-status-icon-{l}-{w}         — status icon (spec canonical)
//   word-tag-chip-{l}-{w}-{key}      — style/component chip (CSS class: word-tag-chip)
//   word-tag-clear-button-{l}-{w}-{key} — × button on a chip (§2.8)
// Legacy (kept for backward compat):
//   gt-input-{word_id}               — GT text input (legacy form)

import { useState, useEffect, useRef } from "react";
import type { components } from "../api/types";
import { GlyphChip } from "./glyph/GlyphChip";

type WordMatch = components["schemas"]["WordMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

const STATUS_ICON: Record<MatchStatus, string> = {
  exact: "✓",
  fuzzy: "≈",
  mismatch: "✗",
  unmatched_ocr: "○",
  unmatched_gt: "●",
};

const STATUS_COLOR: Record<MatchStatus, string> = {
  exact: "text-status-exact",
  fuzzy: "text-status-fuzzy",
  mismatch: "text-status-mismatch",
  unmatched_ocr: "text-ink-3",
  unmatched_gt: "text-status-ocr",
};

export interface WordCellProps {
  word: WordMatch;
  /**
   * Called when the GT input is blurred and the value has changed.
   * Signature: (wordId, lineIndex, wordIndex, newText) => void
   */
  onCommitGt?:
    | ((wordId: string, lineIndex: number, wordIndex: number, text: string) => void)
    | undefined;
  /** Base URL for page image slices (e.g. /api/.../pages/0/image). When provided
   *  and word_id is set, a crop thumbnail is shown in row 2. */
  imageBaseUrl?: string | undefined;
  /**
   * Called when the pencil edit button is clicked.
   * Signature: (lineIndex, wordIndex) => void
   * Should select the word in the selection store and open the right panel.
   */
  onEditWord?: ((lineIndex: number, wordIndex: number) => void) | undefined;
  /**
   * Called when the per-word validate toggle (✔) is clicked.
   * Signature: (lineIndex, wordIndex, validated) => void
   * STB-1: wires the validate button to the caller's mutation.
   */
  onValidate?: ((lineIndex: number, wordIndex: number, validated: boolean) => void) | undefined;
  /**
   * Called when a style/component tag chip × is clicked.
   * Signature: (lineIndex, wordIndex, label, kind) => void
   * STB-2: wires the clear-tag button to the caller's mutation.
   */
  onClearTag?:
    | ((lineIndex: number, wordIndex: number, label: string, kind: "style" | "component") => void)
    | undefined;
}

/**
 * Single word comparison cell.
 *
 * Uses `word_id` as the React key discriminator and testid anchor.
 * Falls back to `${line_index}-${word_index}` when `word_id` is absent.
 */
export function WordCell({ word, onCommitGt, onEditWord, onValidate, onClearTag }: WordCellProps) {
  const wordId = word.word_id ?? `${word.line_index}-${word.word_index}`;
  const [gtValue, setGtValue] = useState(word.ground_truth_text);
  const inputRef = useRef<HTMLInputElement>(null);
  // Track the committed value so we can detect changes at blur time.
  const committedRef = useRef(word.ground_truth_text);

  // Sync controlled state when server data updates (after query invalidation),
  // but only when the input is not currently focused.
  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setGtValue(word.ground_truth_text);
      committedRef.current = word.ground_truth_text;
    }
  }, [word.ground_truth_text]);

  function handleBlur() {
    if (gtValue !== committedRef.current) {
      committedRef.current = gtValue;
      onCommitGt?.(wordId, word.line_index, word.word_index ?? 0, gtValue);
    }
  }

  const statusColor = STATUS_COLOR[word.match_status] ?? "text-ink-3";
  const statusIcon = STATUS_ICON[word.match_status] ?? "?";
  const l = word.line_index;
  const w = word.word_index ?? 0;

  // Glyph badge color logic (spec §5.3)
  const hasAnnotations = word.glyph_annotations != null;
  const hasPredictions = word.glyph_predictions != null;
  const hasMarks =
    hasAnnotations &&
    ((word.glyph_annotations?.ligatures?.length ?? 0) > 0 ||
      (word.glyph_annotations?.long_s_positions?.length ?? 0) > 0 ||
      !!word.glyph_annotations?.swash);

  const badgeColor = hasMarks
    ? "bg-green-500"
    : hasAnnotations
      ? "bg-blue-500"
      : hasPredictions
        ? "bg-amber-500"
        : null;

  const showChipRow = hasAnnotations || hasPredictions;

  return (
    <div
      data-testid={`word-image-cell-${l}-${w}`}
      data-testid-alias={`word-cell-${wordId}`}
      className="border border-border-1 rounded p-1 flex flex-col gap-0.5 min-w-16 max-w-32 relative"
    >
      {/* Glyph corner badge (spec §5.3, testid §7) */}
      {badgeColor !== null && (
        <span
          data-testid={`word-glyph-badge-${l}-${w}`}
          className={`absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-sm ${badgeColor}`}
          aria-label="glyph annotation badge"
          title={
            hasMarks
              ? "Has glyph marks"
              : hasAnnotations
                ? "Reviewed (no marks)"
                : "Predictions pending review"
          }
        />
      )}

      {/* Row 1: status icon + validated indicator + edit button stub */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-0.5">
          {/* Word selection checkbox (driver-contract §2.8) */}
          <input
            type="checkbox"
            data-testid={`word-checkbox-${l}-${w}`}
            aria-label={`Select word ${w} in line ${l}`}
            className="w-3 h-3 accent-accent"
          />
          <span
            data-testid={`word-status-icon-${l}-${w}`}
            className={`text-xs font-bold ${statusColor}`}
            aria-label={`${word.match_status} match`}
            title={word.match_status}
          >
            {statusIcon}
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          {/* Per-word validate toggle (driver-contract §2.8) — STB-1 */}
          <button
            data-testid={`word-validate-button-${l}-${w}`}
            aria-label={`${word.is_validated ? "Unvalidate" : "Validate"} word ${w} in line ${l}`}
            className={`text-[10px] px-0.5 leading-none ${word.is_validated ? "text-status-exact" : "text-ink-4 hover:text-status-exact"}`}
            title={word.is_validated ? "Unvalidate word" : "Validate word"}
            onClick={() => onValidate?.(l, w, !word.is_validated)}
          >
            ✔
          </button>
          {/* Edit button — selects the word and opens the right-panel word detail view */}
          <button
            data-testid={`edit-word-button-${l}-${w}`}
            aria-label={`Edit word ${w} in line ${l}`}
            className="text-[10px] text-ink-4 hover:text-ink-1 px-0.5 leading-none"
            title="Edit word"
            onClick={() => onEditWord?.(l, w)}
          >
            ✎
          </button>
        </div>
      </div>

      {/* Row 3: OCR text */}
      <div
        data-testid={`ocr-text-label-${l}-${w}`}
        className="text-xs font-mono text-ink-2 truncate"
        title={word.ocr_text}
      >
        {word.ocr_text || <span className="text-ink-4 italic">∅</span>}
      </div>

      {/* Tag chips: style labels (blue tint) + component labels (green tint) */}
      {((word.text_style_labels?.length ?? 0) > 0 || (word.word_components?.length ?? 0) > 0) && (
        <div className="flex flex-wrap gap-0.5">
          {word.text_style_labels?.map((label) => (
            <span
              key={`style-${label}`}
              data-testid={`word-tag-chip-${l}-${w}-${label}`}
              className="word-tag-chip flex items-center gap-0.5 px-1 py-0 text-[10px] rounded"
              style={{ background: "color-mix(in srgb, var(--status-ocr) 12%, var(--bg-raised))" }}
              title={`Style: ${label}`}
            >
              {label}
              {/* STB-2: clear style tag */}
              <button
                data-testid={`word-tag-clear-button-${l}-${w}-${label}`}
                className="word-tag-clear-button text-[8px] text-ink-3 hover:text-ink-1 leading-none"
                aria-label={`Remove style ${label}`}
                title={`Remove style ${label}`}
                onClick={() => onClearTag?.(l, w, label, "style")}
              >
                ×
              </button>
            </span>
          ))}
          {word.word_components?.map((comp) => (
            <span
              key={`comp-${comp}`}
              data-testid={`word-tag-chip-${l}-${w}-${comp}`}
              className="word-tag-chip flex items-center gap-0.5 px-1 py-0 text-[10px] rounded"
              style={{
                background: "color-mix(in srgb, var(--status-exact) 12%, var(--bg-raised))",
              }}
              title={`Component: ${comp}`}
            >
              {comp}
              {/* STB-2: clear component tag */}
              <button
                data-testid={`word-tag-clear-button-${l}-${w}-${comp}`}
                className="word-tag-clear-button text-[8px] text-ink-3 hover:text-ink-1 leading-none"
                aria-label={`Remove component ${comp}`}
                title={`Remove component ${comp}`}
                onClick={() => onClearTag?.(l, w, comp, "component")}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Row 4: GT input.
          P1.6 (B-22): Enter commits (via blur) and Escape reverts, matching
          every other GT input (MultiLineDetail WordRow, LineDetail GTRow). */}
      <input
        ref={inputRef}
        data-testid={`gt-text-input-${l}-${w}`}
        type="text"
        value={gtValue}
        onChange={(e) => {
          setGtValue(e.target.value);
        }}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          }
          if (e.key === "Escape") {
            setGtValue(committedRef.current);
          }
        }}
        className="w-full text-xs border border-border-1 rounded px-1 py-0.5 font-mono focus:outline-none focus:border-accent"
        aria-label={`Ground truth for "${word.ocr_text}"`}
      />

      {/* Glyph chip row (spec §5.3, testid §7) — shown when any annotations or predictions exist */}
      {showChipRow && (
        <div data-testid={`word-glyph-chip-row-${l}-${w}`} className="flex flex-wrap gap-0.5">
          {(word.glyph_annotations?.ligatures ?? []).map((lig, i) => (
            <GlyphChip
              key={`ann-${lig.kind}-${i}`}
              lineIndex={l}
              wordIndex={w}
              kind={lig.kind}
              predicted={false}
              onClick={() => {
                /* future: open panel */
              }}
            />
          ))}
          {(word.glyph_annotations?.long_s_positions ?? []).map((pos) => (
            <GlyphChip
              key={`ls-${pos}`}
              lineIndex={l}
              wordIndex={w}
              kind="long_s"
              predicted={false}
              onClick={() => {
                /* future: open panel */
              }}
            />
          ))}
          {word.glyph_annotations?.swash && (
            <GlyphChip
              lineIndex={l}
              wordIndex={w}
              kind="swash"
              predicted={false}
              onClick={() => {
                /* future: open panel */
              }}
            />
          )}
          {(word.glyph_predictions?.ligatures ?? [])
            .filter(
              (pred) =>
                !(word.glyph_annotations?.ligatures ?? []).some((a) => a.kind === pred.kind),
            )
            .map((pred, i) => (
              <GlyphChip
                key={`pred-${pred.kind}-${i}`}
                lineIndex={l}
                wordIndex={w}
                kind={pred.kind}
                predicted={true}
                onClick={() => {
                  /* future: open panel */
                }}
              />
            ))}
        </div>
      )}

      {/* Row 5: fuzz score (shown only for fuzzy matches) */}
      {word.match_status === "fuzzy" && word.fuzz_score != null && (
        <div className="text-[10px] text-ink-4 text-right">
          {Math.round(word.fuzz_score * 100)}%
        </div>
      )}
    </div>
  );
}
