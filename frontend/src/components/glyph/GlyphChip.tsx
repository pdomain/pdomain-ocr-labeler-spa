// GlyphChip.tsx — tiny pill rendered inline under WordCell GT input.
// Spec: specs/20-glyph-annotations.md §5.2
// Issue #269
//
// data-testids (spec §7):
//   word-glyph-chip-{line}-{word}-{kind}          — confirmed chip
//   word-glyph-chip-{line}-{word}-predicted-{kind} — predicted-only chip

export interface GlyphChipProps {
  lineIndex: number;
  wordIndex: number;
  /** Ligature kind ("ct", "st", "fi", "long_s", "swash", …) */
  kind: string;
  /** True when this is a prediction that has not been confirmed */
  predicted: boolean;
  onClick: () => void;
}

/**
 * Single glyph annotation chip pill.
 *
 * - Confirmed (predicted=false): solid pill, normal opacity
 * - Predicted-only (predicted=true): hollow/muted pill with opacity-60
 */
export function GlyphChip({ lineIndex, wordIndex, kind, predicted, onClick }: GlyphChipProps) {
  const testid = predicted
    ? `word-glyph-chip-${lineIndex}-${wordIndex}-predicted-${kind}`
    : `word-glyph-chip-${lineIndex}-${wordIndex}-${kind}`;

  const label = kind === "long_s" ? "ſ" : kind.toUpperCase();

  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={[
        "inline-flex items-center px-1 py-0 text-[9px] font-mono rounded border leading-tight",
        "cursor-pointer select-none",
        predicted
          ? "opacity-60 border-dashed border-ink-4 text-ink-3 bg-transparent"
          : "border-accent text-accent bg-accent/10",
      ].join(" ")}
      title={predicted ? `Predicted ${kind} (click to review)` : `${kind} annotation`}
      aria-label={predicted ? `Predicted ${kind}` : kind}
      type="button"
    >
      {label}
      {predicted && <span className="ml-0.5 text-[8px]">?</span>}
    </button>
  );
}
