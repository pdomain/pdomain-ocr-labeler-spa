// UnicodePicker.tsx — Searchable glyph picker for the Char Fixer.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.
//
// Renders a searchable list of common glyphs grouped in Accordion
// sub-sections (em-dash, curly quotes, fractions, ligatures, etc.).
// Clicking a glyph invokes ``onInsert`` with the glyph character — the
// parent ``CharFixerSection`` routes the insertion to its
// last-focused char input.
//
// data-testids:
//   unicode-picker             — outer container
//   unicode-picker-search      — search input
//   unicode-glyph-{id}         — clickable glyph button

import { useState, useMemo } from "react";
import { Accordion } from "../ui/accordion";
import { Input } from "../ui/Input";

interface Glyph {
  id: string;
  char: string;
  name: string;
  aliases?: string[];
}

interface GlyphGroup {
  id: string;
  label: string;
  glyphs: Glyph[];
}

const GROUPS: GlyphGroup[] = [
  {
    id: "em-dash",
    label: "Em-dash & punctuation",
    glyphs: [
      { id: "em-dash", char: "—", name: "em-dash" },
      { id: "en-dash", char: "–", name: "en-dash" },
      { id: "hellip", char: "…", name: "ellipsis" },
      { id: "minus", char: "−", name: "minus sign" },
    ],
  },
  {
    id: "curly-quotes",
    label: "Curly quotes",
    glyphs: [
      { id: "ldquo", char: "“", name: "left double quote" },
      { id: "rdquo", char: "”", name: "right double quote" },
      { id: "lsquo", char: "‘", name: "left single quote" },
      { id: "rsquo", char: "’", name: "right single quote" },
    ],
  },
  {
    id: "fractions",
    label: "Fractions",
    glyphs: [
      { id: "frac12", char: "½", name: "one half" },
      { id: "frac14", char: "¼", name: "one quarter" },
      { id: "frac34", char: "¾", name: "three quarters" },
      { id: "frac13", char: "⅓", name: "one third" },
      { id: "frac23", char: "⅔", name: "two thirds" },
    ],
  },
  {
    id: "ligatures",
    label: "Ligatures",
    glyphs: [
      { id: "fi", char: "ﬁ", name: "ligature fi" },
      { id: "fl", char: "ﬂ", name: "ligature fl" },
      { id: "ae", char: "æ", name: "ligature ae" },
      { id: "oe", char: "œ", name: "ligature oe" },
    ],
  },
];

function matchesSearch(g: Glyph, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  if (g.id.toLowerCase().includes(q)) return true;
  if (g.name.toLowerCase().includes(q)) return true;
  if (g.aliases?.some((a) => a.toLowerCase().includes(q))) return true;
  return false;
}

export interface UnicodePickerProps {
  onInsert: (glyph: string) => void;
}

export function UnicodePicker({ onInsert }: UnicodePickerProps) {
  const [query, setQuery] = useState("");
  const [openGroups, setOpenGroups] = useState<string[]>([]);

  const filtered = useMemo(() => {
    return GROUPS.map((g) => ({
      ...g,
      glyphs: g.glyphs.filter((gl) => matchesSearch(gl, query)),
    })).filter((g) => g.glyphs.length > 0);
  }, [query]);

  // When the user types a search query, auto-expand all matching groups
  // so the filtered glyph buttons are immediately visible.
  const effectiveOpen = query ? filtered.map((g) => g.id) : openGroups;

  return (
    <div
      data-testid="unicode-picker"
      className="flex flex-col gap-2 rounded border border-border-2 bg-sunk p-2"
    >
      <Input
        data-testid="unicode-picker-search"
        size="sm"
        placeholder="Search glyphs…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <Accordion
        type="multiple"
        value={effectiveOpen}
        onValueChange={query ? undefined : setOpenGroups}
        className="flex flex-col gap-1"
      >
        {filtered.map((group) => (
          <Accordion.Item key={group.id} value={group.id}>
            <Accordion.Trigger>{group.label}</Accordion.Trigger>
            <Accordion.Content>
              <div className="grid grid-cols-6 gap-1 pt-1">
                {group.glyphs.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    data-testid={`unicode-glyph-${g.id}`}
                    title={g.name}
                    onClick={() => onInsert(g.char)}
                    className="h-8 rounded border border-border-2 bg-raised text-ink-1 text-sm font-mono hover:bg-accent/10 hover:border-accent"
                  >
                    {g.char}
                  </button>
                ))}
              </div>
            </Accordion.Content>
          </Accordion.Item>
        ))}
      </Accordion>
    </div>
  );
}
