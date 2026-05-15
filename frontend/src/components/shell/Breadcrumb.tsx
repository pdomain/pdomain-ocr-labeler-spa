// Breadcrumb.tsx — Right-panel header path chips.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 14.
//
// Renders a chain like `Project › Block 2 › Para 3 › Line 7 › Word 1` from the
// current `selection-store` path. Each chip is a real `<button>`:
//   - The deepest chip (data-active=true) is `text-ink-1`.
//   - Ancestor chips (data-active=false) are `text-ink-3` and clickable —
//     clicking them re-selects at that level, dropping deeper levels.
//   - The "Project" root chip clears the selection.
//
// Each non-root chip has a small layer-color glyph (B/P/L/W) keyed to its
// layer token (`text-layer-block`/`-para`/`-line`/`-word`).

import { useSyncExternalStore } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  selectionStore,
  selectBlock,
  selectPara,
  selectLine,
  clearSelection,
  type SelectionPath,
  type SelectionLevel,
} from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

// ─── Layer color lookups (static Tailwind classes — no interpolation) ────────

const LAYER_GLYPH_CLASS: Record<"block" | "para" | "line" | "word", string> = {
  block: "text-layer-block",
  para: "text-layer-para",
  line: "text-layer-line",
  word: "text-layer-word",
};

const LAYER_GLYPH: Record<"block" | "para" | "line" | "word", string> = {
  block: "B",
  para: "P",
  line: "L",
  word: "W",
};

// ─── Subscriber bridge ───────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => cb());
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── Chip ────────────────────────────────────────────────────────────────────

interface ChipProps {
  testid: string;
  label: string;
  layer?: "block" | "para" | "line" | "word";
  active: boolean;
  onClick: () => void;
}

function Chip({ testid, label, layer, active, onClick }: ChipProps) {
  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : "false"}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium select-none transition-colors",
        active ? "text-ink-1 cursor-default" : "text-ink-3 hover:text-ink-1 hover:bg-bg-raised",
      )}
    >
      {layer ? (
        <span aria-hidden="true" className={cn("font-bold text-[10px]", LAYER_GLYPH_CLASS[layer])}>
          {LAYER_GLYPH[layer]}
        </span>
      ) : null}
      <span>{label}</span>
    </button>
  );
}

// ─── Separator ───────────────────────────────────────────────────────────────

function Sep() {
  return <ChevronRight aria-hidden="true" className="h-3 w-3 text-ink-3 flex-shrink-0" />;
}

// ─── Label resolution ────────────────────────────────────────────────────────

function paraLabel(paraId: number | null | undefined): string {
  if (paraId === null || paraId === undefined) return "Unsorted";
  return `Para ${paraId + 1}`;
}

function lineLabel(lineId: number | undefined): string {
  if (lineId === undefined) return "";
  return `Line ${lineId + 1}`;
}

function wordLabel(wordId: [number, number] | undefined): string {
  if (!wordId) return "";
  return `Word ${wordId[1] + 1}`;
}

function blockLabel(blockId: string | undefined): string {
  if (!blockId) return "";
  // PagePayload has no block layer yet — use the synthetic id as-is.
  // Future: resolve to "Block N" when block_index lands.
  return `Block ${blockId}`;
}

// ─── Breadcrumb ──────────────────────────────────────────────────────────────

export interface BreadcrumbProps {
  /** Current page payload (used for label resolution; not required for routing). */
  page?: PagePayload;
}

export function Breadcrumb({ page }: BreadcrumbProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );
  const { level, path } = state;
  const resolved = resolveAncestors(path, page);

  return (
    <div
      data-testid="breadcrumb"
      className="flex items-center gap-1 min-w-0 overflow-hidden whitespace-nowrap"
    >
      <Chip
        testid="breadcrumb-chip-root"
        label="Project"
        active={level === "none"}
        onClick={() => clearSelection()}
      />
      {renderChips(level, resolved)}
    </div>
  );
}

/**
 * Backfill the ancestor levels of `path` from `page` so the chain renders as
 * `Project › Para N › Line N › Word N` even when the selection action only
 * set the leaf level. E.g. `selectWord(0, 1)` produces
 * `{lineId:0, wordId:[0,1]}`; this helper adds `paraId` by looking up the
 * line's `paragraph_index`.
 */
function resolveAncestors(path: SelectionPath, page?: PagePayload): SelectionPath {
  if (!page) return path;
  const result: SelectionPath = { ...path };
  // If wordId present but lineId missing, derive from wordId tuple.
  if (result.wordId !== undefined && result.lineId === undefined) {
    result.lineId = result.wordId[0];
  }
  // If lineId present but paraId missing, derive from the LineMatch.
  if (result.lineId !== undefined && result.paraId === undefined) {
    const lm = (page.line_matches ?? []).find((m) => m.line_index === result.lineId);
    if (lm) result.paraId = lm.paragraph_index;
  }
  return result;
}

function renderChips(level: SelectionLevel, path: SelectionPath) {
  const nodes: React.ReactNode[] = [];

  if (path.blockId !== undefined) {
    nodes.push(<Sep key="sep-block" />);
    nodes.push(
      <Chip
        key="block"
        testid="breadcrumb-chip-block"
        label={blockLabel(path.blockId)}
        layer="block"
        active={level === "block"}
        onClick={() => selectBlock(path.blockId!)}
      />,
    );
  }
  if (path.paraId !== undefined) {
    nodes.push(<Sep key="sep-para" />);
    nodes.push(
      <Chip
        key="para"
        testid="breadcrumb-chip-para"
        label={paraLabel(path.paraId)}
        layer="para"
        active={level === "para"}
        onClick={() => selectPara(path.paraId!)}
      />,
    );
  }
  if (path.lineId !== undefined) {
    nodes.push(<Sep key="sep-line" />);
    nodes.push(
      <Chip
        key="line"
        testid="breadcrumb-chip-line"
        label={lineLabel(path.lineId)}
        layer="line"
        active={level === "line"}
        onClick={() => selectLine(path.lineId!)}
      />,
    );
  }
  if (path.wordId !== undefined) {
    nodes.push(<Sep key="sep-word" />);
    nodes.push(
      <Chip
        key="word"
        testid="breadcrumb-chip-word"
        label={wordLabel(path.wordId)}
        layer="word"
        active={level === "word"}
        // The deepest chip is non-navigational; clicking it is a no-op.
        onClick={() => {
          /* no-op at deepest level */
        }}
      />,
    );
  }
  return nodes;
}
