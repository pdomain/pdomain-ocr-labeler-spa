// StylePalette.tsx — STYLE chip palette for whole-word styling (P2.d, Gaps 31, 53 style half).
//
// Renders a row of tristate Chip primitives for text styles.
//
// Q-B2-STYLE-LABELS option (b): the style list is sourced from the backend via
// useLabelVocabulary so it can never drift from book-tools' canonical
// ALLOWED_TEXT_STYLE_LABELS. superscript / subscript are COMPONENTS (not styles)
// and no longer appear here — they surface in ComponentPalette.
//
// Each chip is in tri-state (off / on / mixed) reflecting the word's current styles.
// Clicking a chip calls onStyleChange with the canonical style key and the next value.
//
// ChipPalette is extracted as a reusable building block for P2.e (ComponentPalette).
//
// data-testids:
//   style-palette          — outer container
//   style-chip-{styleKey}  — individual chip (key = canonical style string, spaces → -)

import { TriStateChip } from "@pdomain/pdomain-ui/primitives";
import type { TriStateValue } from "@pdomain/pdomain-ui/primitives";
import { useLabelVocabulary, FALLBACK_STYLES } from "../../hooks/useLabelVocabulary";

export interface StyleItem {
  key: string;
  label: string;
}

// Display-name map: canonical style key → short label shown on chip.
// Keys must exactly match ALLOWED_TEXT_STYLE_LABELS from book-tools.
const STYLE_DISPLAY_NAMES: Record<string, string> = {
  "all caps": "AC",
  blackletter: "Bl",
  bold: "B",
  handwritten: "Hw",
  italics: "I",
  monospace: "Mono",
  regular: "Reg",
  "small caps": "Sc",
  strikethrough: "Strike",
  underline: "U",
};

// STYLE_ITEMS — canonical fallback list for use by sibling components that need
// a static reference before the query resolves (e.g. CharRangesSection).
// Sourced from FALLBACK_STYLES (mirrors book-tools ALLOWED_TEXT_STYLE_LABELS).
export const STYLE_ITEMS: StyleItem[] = FALLBACK_STYLES.map((key) => ({
  key,
  label: STYLE_DISPLAY_NAMES[key] ?? key,
}));

function styleDisplayLabel(canonical: string): string {
  return STYLE_DISPLAY_NAMES[canonical] ?? canonical;
}

// ─── ChipPalette — reusable building block for P2.d + P2.e ──────────────────

export interface ChipPaletteItem {
  key: string;
  label: string;
}

export interface ChipPaletteProps {
  items: ChipPaletteItem[];
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TriStateValue) => void;
}

export function ChipPalette({
  items,
  activeKeys,
  "data-testid-prefix": testIdPrefix,
  onChange,
}: ChipPaletteProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => {
        const value: TriStateValue = activeKeys.has(item.key) ? "on" : "off";
        return (
          <TriStateChip
            key={item.key}
            value={value}
            data-testid={`${testIdPrefix}-${item.key.replace(/ /g, "-")}`}
            onChange={(next) => {
              // P1.4 (B-41): Chip's tristate cycle is off→on→mixed→off, but
              // ChipPalette renders a BINARY state (activeKeys.has → on/off;
              // "mixed" is never displayed). Consumers skip "mixed", so
              // without this mapping the off-toggle is unreachable — an
              // active chip could never be cleared.
              onChange(item.key, next === "mixed" ? "off" : next);
            }}
          >
            {item.label}
          </TriStateChip>
        );
      })}
    </div>
  );
}

// ─── StylePalette ─────────────────────────────────────────────────────────────

export interface StylePaletteProps {
  /** Currently active style labels on the word. */
  activeStyles: string[];
  /** Called when a chip is toggled — canonical style key + new tristate value. */
  onStyleChange: (styleKey: string, next: TriStateValue) => void;
}

export function StylePalette({ activeStyles, onStyleChange }: StylePaletteProps) {
  const { textStyleLabels } = useLabelVocabulary();
  const activeSet = new Set(activeStyles);

  const items: ChipPaletteItem[] = textStyleLabels.map((key) => ({
    key,
    label: styleDisplayLabel(key),
  }));

  return (
    <div data-testid="style-palette" className="flex flex-col gap-1.5 px-3 py-2">
      <div className="text-[9px] font-semibold tracking-wider uppercase text-ink-3">Style</div>
      <ChipPalette
        items={items}
        activeKeys={activeSet}
        data-testid-prefix="style-chip"
        onChange={onStyleChange}
      />
    </div>
  );
}
