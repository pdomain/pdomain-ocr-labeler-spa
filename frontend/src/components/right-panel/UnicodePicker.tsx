// UnicodePicker.tsx — Redesigned glyph picker for the OCR/GT compare row (P4.c, Gap 40).
// Spec: docs/plans/hifi-gaps-plan.md P4.c
//
// Three zones stacked vertically:
//   1. Sets row   — horizontal scrollable pill tabs (Latin / Greek / Punctuation / Symbols /
//                   Math / Currency / Other). Clicking filters the code-point grid.
//   2. Card grid  — code-point cards: large serif glyph + U+XXXX label. Click inserts.
//   3. Slash input — text input that accepts \emdash, \alpha, U+2019, etc.
//
// The ``onInsert`` prop is unchanged from the original Slice 20 interface so
// OcrGtCompareRow (P2.c) continues to work without modification.
//
// data-testids:
//   unicode-picker                             — outer container
//   unicode-set-{latin|greek|punctuation|symbols|math|currency|other}
//                                              — set pill buttons
//   unicode-char-{U+XXXX}                      — code-point card button
//   unicode-slash-input                        — slash-command text input

import { useState, useMemo, useRef } from "react";

// ---------------------------------------------------------------------------
// Character set definitions
// ---------------------------------------------------------------------------

interface CharEntry {
  char: string;
  cp: string; // "U+XXXX"
}

type SetId = "latin" | "greek" | "punctuation" | "symbols" | "math" | "currency" | "other";

interface CharSet {
  id: SetId;
  label: string;
  chars: CharEntry[];
}

function toCP(codePoint: number): string {
  return `U+${codePoint.toString(16).toUpperCase().padStart(4, "0")}`;
}

function entry(char: string): CharEntry {
  return { char, cp: toCP(char.codePointAt(0) ?? 0) };
}

const CHAR_SETS: CharSet[] = [
  {
    id: "latin",
    label: "Latin",
    chars: [
      // Extended Latin (common accented/ligature chars in scanned books)
      entry("À"),
      entry("Á"),
      entry("Â"),
      entry("Ã"),
      entry("Ä"),
      entry("Å"),
      entry("Æ"),
      entry("Ç"),
      entry("È"),
      entry("É"),
      entry("Ê"),
      entry("Ë"),
      entry("Ì"),
      entry("Í"),
      entry("Î"),
      entry("Ï"),
      entry("Ð"),
      entry("Ñ"),
      entry("Ò"),
      entry("Ó"),
      entry("Ô"),
      entry("Õ"),
      entry("Ö"),
      entry("Ø"),
      entry("Ù"),
      entry("Ú"),
      entry("Û"),
      entry("Ü"),
      entry("Ý"),
      entry("Þ"),
      entry("ß"),
      entry("à"),
      entry("á"),
      entry("â"),
      entry("ã"),
      entry("ä"),
      entry("å"),
      entry("æ"),
      entry("ç"),
      entry("è"),
      entry("é"),
      entry("ê"),
      entry("ë"),
      entry("ì"),
      entry("í"),
      entry("î"),
      entry("ï"),
      entry("ð"),
      entry("ñ"),
      entry("ò"),
      entry("ó"),
      entry("ô"),
      entry("õ"),
      entry("ö"),
      entry("ø"),
      entry("ù"),
      entry("ú"),
      entry("û"),
      entry("ü"),
      entry("ý"),
      entry("þ"),
      entry("ÿ"),
      // Ligatures
      entry("ﬁ"),
      entry("ﬂ"),
      entry("œ"),
      entry("Œ"),
    ],
  },
  {
    id: "greek",
    label: "Greek",
    chars: [
      entry("α"),
      entry("β"),
      entry("γ"),
      entry("δ"),
      entry("ε"),
      entry("ζ"),
      entry("η"),
      entry("θ"),
      entry("ι"),
      entry("κ"),
      entry("λ"),
      entry("μ"),
      entry("ν"),
      entry("ξ"),
      entry("ο"),
      entry("π"),
      entry("ρ"),
      entry("σ"),
      entry("τ"),
      entry("υ"),
      entry("φ"),
      entry("χ"),
      entry("ψ"),
      entry("ω"),
      entry("Α"),
      entry("Β"),
      entry("Γ"),
      entry("Δ"),
      entry("Ε"),
      entry("Ζ"),
      entry("Η"),
      entry("Θ"),
      entry("Ι"),
      entry("Κ"),
      entry("Λ"),
      entry("Μ"),
      entry("Ν"),
      entry("Ξ"),
      entry("Ο"),
      entry("Π"),
      entry("Ρ"),
      entry("Σ"),
      entry("Τ"),
      entry("Υ"),
      entry("Φ"),
      entry("Χ"),
      entry("Ψ"),
      entry("Ω"),
    ],
  },
  {
    id: "punctuation",
    label: "Punctuation",
    chars: [
      entry("—"),
      entry("–"),
      entry("…"),
      entry("·"),
      entry("“"),
      entry("”"),
      entry("‘"),
      entry("’"),
      entry("«"),
      entry("»"),
      entry("‹"),
      entry("›"),
      entry("¡"),
      entry("¿"),
      entry("‽"),
      entry("‒"),
      entry("−"),
      entry("¶"),
      entry("§"),
      entry("*"),
      entry("†"),
      entry("‡"),
    ],
  },
  {
    id: "symbols",
    label: "Symbols",
    chars: [
      entry("©"),
      entry("®"),
      entry("™"),
      entry("°"),
      entry("′"),
      entry("″"),
      entry("№"),
      entry("℃"),
      entry("℉"),
      entry("‰"),
      entry("‱"),
      entry("←"),
      entry("→"),
      entry("↑"),
      entry("↓"),
      entry("↔"),
      entry("↕"),
      entry("★"),
      entry("☆"),
      entry("♦"),
      entry("♠"),
      entry("♣"),
      entry("♥"),
      entry("✓"),
      entry("✗"),
      entry("✕"),
    ],
  },
  {
    id: "math",
    label: "Math",
    chars: [
      entry("±"),
      entry("×"),
      entry("÷"),
      entry("="),
      entry("≠"),
      entry("≤"),
      entry("≥"),
      entry("≈"),
      entry("≡"),
      entry("∝"),
      entry("∞"),
      entry("∑"),
      entry("∏"),
      entry("∂"),
      entry("∫"),
      entry("√"),
      entry("∈"),
      entry("∉"),
      entry("∅"),
      entry("∧"),
      entry("∨"),
      entry("¬"),
      entry("½"),
      entry("¼"),
      entry("¾"),
      entry("⅓"),
      entry("⅔"),
    ],
  },
  {
    id: "currency",
    label: "Currency",
    chars: [
      entry("€"),
      entry("£"),
      entry("¥"),
      entry("¢"),
      entry("₹"),
      entry("₽"),
      entry("₩"),
      entry("₿"),
      entry("$"),
      entry("¤"),
    ],
  },
  {
    id: "other",
    label: "…",
    chars: [
      // Miscellaneous often needed in book OCR
      entry("ª"),
      entry("º"),
      entry("µ"),
      entry("×"),
      entry("·"),
      entry("―"),
      entry("⁃"),
      entry("⁰"),
      entry("¹"),
      entry("²"),
      entry("³"),
      entry("⁴"),
      entry("⁵"),
      entry("⁶"),
      entry("⁷"),
      entry("⁸"),
      entry("⁹"),
      entry("₀"),
      entry("₁"),
      entry("₂"),
      entry("₃"),
      entry("₄"),
      entry("₅"),
      entry("₆"),
      entry("₇"),
      entry("₈"),
      entry("₉"),
    ],
  },
];

// ---------------------------------------------------------------------------
// Slash-command name map
// ---------------------------------------------------------------------------

/** Maps slash-command names (without leading \) and U+XXXX strings to a character. */
const SLASH_MAP: Record<string, string> = {
  // Dashes & punctuation
  emdash: "—",
  "em-dash": "—",
  endash: "–",
  "en-dash": "–",
  ellipsis: "…",
  hellip: "…",
  ldquo: "“",
  rdquo: "”",
  lsquo: "‘",
  rsquo: "’",
  laquo: "«",
  raquo: "»",
  lsaquo: "‹",
  rsaquo: "›",
  // Greek lowercase
  alpha: "α",
  beta: "β",
  gamma: "γ",
  delta: "δ",
  epsilon: "ε",
  zeta: "ζ",
  eta: "η",
  theta: "θ",
  iota: "ι",
  kappa: "κ",
  lambda: "λ",
  mu: "μ",
  nu: "ν",
  xi: "ξ",
  omicron: "ο",
  pi: "π",
  rho: "ρ",
  sigma: "σ",
  tau: "τ",
  upsilon: "υ",
  phi: "φ",
  chi: "χ",
  psi: "ψ",
  omega: "ω",
  // Greek uppercase
  Alpha: "Α",
  Beta: "Β",
  Gamma: "Γ",
  Delta: "Δ",
  Epsilon: "Ε",
  Theta: "Θ",
  Lambda: "Λ",
  Mu: "Μ",
  Pi: "Π",
  Sigma: "Σ",
  Phi: "Φ",
  Psi: "Ψ",
  Omega: "Ω",
  // Math / symbols
  pm: "±",
  plus: "+",
  minus: "−",
  times: "×",
  div: "÷",
  ne: "≠",
  neq: "≠",
  le: "≤",
  ge: "≥",
  approx: "≈",
  infty: "∞",
  infinity: "∞",
  sqrt: "√",
  sum: "∑",
  prod: "∏",
  // Currency
  euro: "€",
  pound: "£",
  yen: "¥",
  cent: "¢",
  // Misc
  copy: "©",
  reg: "®",
  trade: "™",
  deg: "°",
  para: "¶",
  sect: "§",
  dagger: "†",
  ddagger: "‡",
  frac12: "½",
  frac14: "¼",
  frac34: "¾",
  frac13: "⅓",
  frac23: "⅔",
};

/** Parse a slash command or U+XXXX string and return the resolved character, or null. */
function resolveSlashCommand(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  // U+XXXX form
  const uMatch = /^[Uu]\+([0-9A-Fa-f]{1,6})$/.exec(trimmed);
  if (uMatch) {
    // uMatch[1] is the capture group — always present when this branch is reached.
    const cp = parseInt(uMatch[1]!, 16);
    if (!isNaN(cp) && cp >= 0 && cp <= 0x10ffff) {
      return String.fromCodePoint(cp);
    }
    return null;
  }

  // \name or name
  const name = trimmed.startsWith("\\") ? trimmed.slice(1) : trimmed;
  return SLASH_MAP[name] ?? null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface UnicodePickerProps {
  onInsert: (glyph: string) => void;
}

export function UnicodePicker({ onInsert }: UnicodePickerProps) {
  const [activeSet, setActiveSet] = useState<SetId>("punctuation");
  const [slashValue, setSlashValue] = useState("");
  const slashRef = useRef<HTMLInputElement>(null);

  const currentChars = useMemo(
    () => CHAR_SETS.find((s) => s.id === activeSet)?.chars ?? [],
    [activeSet],
  );

  function handleSlashKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      const resolved = resolveSlashCommand(slashValue);
      if (resolved) {
        onInsert(resolved);
        setSlashValue("");
      }
    }
  }

  return (
    <div
      data-testid="unicode-picker"
      className="flex flex-col gap-1.5 rounded border border-border-2 bg-sunk p-2"
    >
      {/* Sets row — horizontal scrollable pills */}
      <div className="flex gap-1 overflow-x-auto pb-0.5 scrollbar-none">
        {CHAR_SETS.map((set) => (
          <button
            key={set.id}
            type="button"
            data-testid={`unicode-set-${set.id}`}
            onClick={() => {
              setActiveSet(set.id);
            }}
            className={[
              "shrink-0 h-6 px-2.5 rounded-full border text-[10px] font-semibold transition-colors whitespace-nowrap",
              activeSet === set.id
                ? "bg-accent/15 border-accent text-accent"
                : "bg-raised border-border-2 text-ink-3 hover:text-ink-1 hover:border-border-1",
            ].join(" ")}
          >
            {set.label}
          </button>
        ))}
      </div>

      {/* Code-point card grid */}
      <div
        className="grid gap-1 overflow-y-auto"
        style={{
          gridTemplateColumns: "repeat(auto-fill, minmax(44px, 1fr))",
          maxHeight: "160px",
        }}
      >
        {currentChars.map(({ char, cp }) => (
          <button
            key={cp}
            type="button"
            data-testid={`unicode-char-${cp}`}
            title={cp}
            onClick={() => {
              onInsert(char);
            }}
            className="flex flex-col items-center justify-center gap-0.5 h-12 rounded border border-border-2 bg-raised text-ink-1 hover:bg-accent/10 hover:border-accent transition-colors"
          >
            <span className="font-serif text-base leading-none">{char}</span>
            <span className="text-[8px] font-mono text-ink-4 leading-none">{cp}</span>
          </button>
        ))}
      </div>

      {/* Slash-command input */}
      <input
        ref={slashRef}
        type="text"
        data-testid="unicode-slash-input"
        placeholder="\emdash, \alpha, U+2019…"
        value={slashValue}
        onChange={(e) => {
          setSlashValue(e.target.value);
        }}
        onKeyDown={handleSlashKeyDown}
        className="h-7 w-full rounded border border-border-2 bg-raised px-2 text-[11px] font-mono text-ink-1 placeholder:text-ink-4 focus:outline-none focus:border-accent transition-colors"
      />
    </div>
  );
}
