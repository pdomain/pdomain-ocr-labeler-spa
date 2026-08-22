import { TriStateChip, type TriStateValue } from "@pdomain/pdomain-ui/primitives";

export interface ChipPaletteItem {
  key: string;
  label: string;
}

interface ChipPaletteProps {
  items: ChipPaletteItem[];
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TriStateValue) => void;
}

export function ChipPalette({
  items,
  activeKeys,
  "data-testid-prefix": prefix,
  onChange,
}: ChipPaletteProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <TriStateChip
          key={item.key}
          value={activeKeys.has(item.key) ? "on" : "off"}
          data-testid={`${prefix}-${item.key.replace(/ /g, "-")}`}
          onChange={(next) => {
            onChange(item.key, next === "mixed" ? "off" : next);
          }}
        >
          {item.label}
        </TriStateChip>
      ))}
    </div>
  );
}
