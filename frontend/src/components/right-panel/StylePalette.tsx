// StylePalette.tsx — STYLE chip palette for whole-word styling (P2.d, Gaps 31, 53 style half).
//
// Renders a row of tristate Chip primitives for text styles:
//   bold, italic, small-caps, superscript, subscript, strikethrough, underline
//
// Each chip is in tri-state (off / on / mixed) reflecting the word's current styles.
// Clicking a chip calls onStyleChange with the style key and the next value.
//
// ChipPalette is extracted as a reusable building block for P2.e (ComponentPalette).
//
// data-testids:
//   style-palette          — outer container
//   style-chip-{styleKey}  — individual chip

import { Chip } from "../ui/Chip";
import type { TristateValue } from "../ui/Chip";

export interface StyleItem {
  key: string;
  label: string;
}

// Full list of supported style labels (spec §2 / WordMatch.text_style_labels)
export const STYLE_ITEMS: StyleItem[] = [
  { key: "bold", label: "B" },
  { key: "italic", label: "I" },
  { key: "small-caps", label: "Sc" },
  { key: "superscript", label: "Sup" },
  { key: "subscript", label: "Sub" },
  { key: "strikethrough", label: "Strike" },
  { key: "underline", label: "U" },
];

// ─── ChipPalette — reusable building block for P2.d + P2.e ──────────────────

export interface ChipPaletteItem {
  key: string;
  label: string;
}

export interface ChipPaletteProps {
  items: ChipPaletteItem[];
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TristateValue) => void;
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
        const value: TristateValue = activeKeys.has(item.key) ? "on" : "off";
        return (
          <Chip
            key={item.key}
            variant="tristate"
            value={value}
            data-testid={`${testIdPrefix}-${item.key}`}
            onChange={(next) => {
              onChange(item.key, next);
            }}
          >
            {item.label}
          </Chip>
        );
      })}
    </div>
  );
}

// ─── StylePalette ─────────────────────────────────────────────────────────────

export interface StylePaletteProps {
  /** Currently active style labels on the word. */
  activeStyles: string[];
  /** Called when a chip is toggled — style key + new tristate value. */
  onStyleChange: (styleKey: string, next: TristateValue) => void;
}

export function StylePalette({ activeStyles, onStyleChange }: StylePaletteProps) {
  const activeSet = new Set(activeStyles);

  return (
    <div data-testid="style-palette" className="flex flex-col gap-1.5 px-3 py-2">
      <div className="text-[9px] font-semibold tracking-wider uppercase text-ink-3">Style</div>
      <ChipPalette
        items={STYLE_ITEMS}
        activeKeys={activeSet}
        data-testid-prefix="style-chip"
        onChange={onStyleChange}
      />
    </div>
  );
}
