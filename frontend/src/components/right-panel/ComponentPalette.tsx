// ComponentPalette.tsx — COMPONENT chip palette for word component tags (P2.e, Gaps 31, 53 component half).
//
// Renders a row of tristate Chip primitives for component tags.
//
// Q-B2-STYLE-LABELS option (b): the component list is sourced from the backend via
// useLabelVocabulary so it can never drift from book-tools' canonical
// ALLOWED_COMPONENTS. superscript and subscript now appear here (they are
// components, not text styles).
//
// Reuses the ChipPalette building block from P2.d (StylePalette.tsx).
// Wires to useWordMutations.applyComponent.
//
// data-testids:
//   component-palette             — outer container
//   component-chip-{componentKey} — individual chip (key = canonical component string, spaces → -)

import { ChipPalette, type ChipPaletteItem } from "./ChipPalette";
import type { TriStateValue } from "@pdomain/pdomain-ui/primitives";
import { useLabelVocabulary } from "../../hooks/useLabelVocabulary";

// Display-name map: canonical component key → short label shown on chip.
// Keys must exactly match ALLOWED_COMPONENTS from book-tools.
const COMPONENT_DISPLAY_NAMES: Record<string, string> = {
  "drop cap": "Drop Cap",
  "drop cap unrecovered": "Drop Cap?",
  "footnote marker": "Fn Mark",
  subscript: "Sub",
  superscript: "Sup",
};

function componentDisplayLabel(canonical: string): string {
  return COMPONENT_DISPLAY_NAMES[canonical] ?? canonical;
}

// COMPONENT_ITEMS — canonical fallback list for use by sibling components that need
// a static reference for local palette rendering.
// Sourced from FALLBACK_COMPONENTS (mirrors book-tools ALLOWED_COMPONENTS).
export interface ComponentPaletteProps {
  /** Currently active component tags on the word. */
  activeComponents: string[];
  /** Called when a chip is toggled — canonical component key + new tristate value. */
  onComponentChange: (componentKey: string, next: TriStateValue) => void;
}

export function ComponentPalette({ activeComponents, onComponentChange }: ComponentPaletteProps) {
  const { wordComponents } = useLabelVocabulary();
  const activeSet = new Set(activeComponents);

  const items: ChipPaletteItem[] = wordComponents.map((key) => ({
    key,
    label: componentDisplayLabel(key),
  }));

  return (
    <div data-testid="component-palette" className="flex flex-col gap-1.5 px-3 py-2">
      <div className="text-[9px] font-semibold tracking-wider uppercase text-ink-3">Component</div>
      <ChipPalette
        items={items}
        activeKeys={activeSet}
        data-testid-prefix="component-chip"
        onChange={onComponentChange}
      />
    </div>
  );
}
