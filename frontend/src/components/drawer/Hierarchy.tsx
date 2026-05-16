// Hierarchy.tsx — Drawer Hierarchy tab: block/para/line/word tree view.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 12, P5.c.
//
// P5.c (Gaps 21, 22): each tree node shows a kind chip + mono ID stamp.
// Filter pills above the tree (Block / Para / Line / Word) show only that
// kind. A node-count badge shows total visible nodes.
//
// Builds a tree from PagePayload.line_matches:
//   blocks (when block_index is present) → paragraphs → lines → words
//   paragraphs (fallback when no block_index) → lines → words
//
// Each node has a 6px layer-color square + text label.
// Click → updates selection-store.
// Keyboard: Up/Down navigate; Left/Right collapse/expand branch nodes.
//
// FO-7 / CU-4.3: when any LineMatch carries a numeric block_index, block nodes
// are rendered as the top level of the tree. When no LineMatch carries a
// block_index (pre-FO-7 payload), paragraphs remain the top level (backward
// compatible).

import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { selectBlock, selectLine, selectPara, selectWord } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

// ─── Layer color squares (6px, matches CSS token names) ──────────────────────

const LAYER_DOT_CLASS: Record<"block" | "para" | "line" | "word", string> = {
  block: "bg-layer-block",
  para: "bg-layer-para",
  line: "bg-layer-line",
  word: "bg-layer-word",
};

// ─── Kind chip (P5.c) ─────────────────────────────────────────────────────────

const KIND_CHIP_CLASS: Record<"block" | "para" | "line" | "word", string> = {
  block: "bg-layer-block/20 text-layer-block border-layer-block/40",
  para: "bg-layer-para/20 text-layer-para border-layer-para/40",
  line: "bg-layer-line/20 text-layer-line border-layer-line/40",
  word: "bg-layer-word/20 text-layer-word border-layer-word/40",
};

const KIND_LABELS: Record<"block" | "para" | "line" | "word", string> = {
  block: "B",
  para: "¶",
  line: "L",
  word: "W",
};

function KindChip({ kind }: { kind: "block" | "para" | "line" | "word" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-1 py-0 rounded border text-[9px] font-mono font-semibold flex-shrink-0",
        KIND_CHIP_CLASS[kind],
      )}
    >
      {KIND_LABELS[kind]}
    </span>
  );
}

// ─── Tree data model ──────────────────────────────────────────────────────────

interface WordNode {
  kind: "word";
  lineIndex: number;
  wordIndex: number;
  text: string;
}

interface LineNode {
  kind: "line";
  lineIndex: number;
  text: string;
  children: WordNode[];
}

interface ParaNode {
  kind: "para";
  paraIndex: number | null;
  label: string;
  children: LineNode[];
}

/** FO-7 / CU-4.3: top-level block node, rendered when block_index is present. */
interface BlockNode {
  kind: "block";
  blockIndex: number;
  label: string;
  children: ParaNode[];
}

type TreeNode = BlockNode | ParaNode | LineNode | WordNode;

// ─── Build tree from PagePayload ─────────────────────────────────────────────

/**
 * True when at least one LineMatch carries a numeric block_index.
 * Used to decide whether to render the block layer.
 */
function hasBlockLayer(page: PagePayload): boolean {
  return (page.line_matches ?? []).some((lm) => typeof lm.block_index === "number");
}

/** Build para nodes from a flat list of LineMatches (para → line → word). */
function buildParaNodes(lines: LineMatch[]): ParaNode[] {
  const paraMap = new Map<number, LineMatch[]>();
  const nullParaLines: LineMatch[] = [];

  for (const lm of lines) {
    if (lm.paragraph_index === null || lm.paragraph_index === undefined) {
      nullParaLines.push(lm);
    } else {
      const existing = paraMap.get(lm.paragraph_index) ?? [];
      existing.push(lm);
      paraMap.set(lm.paragraph_index, existing);
    }
  }

  const paras: ParaNode[] = [];
  const sortedKeys = Array.from(paraMap.keys()).sort((a, b) => a - b);
  for (const paraIdx of sortedKeys) {
    const paraLines = paraMap.get(paraIdx)!;
    paras.push({
      kind: "para",
      paraIndex: paraIdx,
      label: `Para ${paraIdx + 1}`,
      children: buildLineNodes(paraLines),
    });
  }
  if (nullParaLines.length > 0) {
    paras.push({
      kind: "para",
      paraIndex: null,
      label: "Unsorted",
      children: buildLineNodes(nullParaLines),
    });
  }
  return paras;
}

/**
 * Build the top-level block tree (FO-7 / CU-4.3).
 *
 * Groups LineMatches by their block_index, then builds para → line → word
 * subtrees within each block. Lines with a null block_index are placed in
 * a synthetic "Unsorted" block at the end.
 */
function buildBlockTree(page: PagePayload): BlockNode[] {
  const blockMap = new Map<number, LineMatch[]>();
  const nullBlockLines: LineMatch[] = [];

  for (const lm of page.line_matches ?? []) {
    if (typeof lm.block_index === "number") {
      const existing = blockMap.get(lm.block_index) ?? [];
      existing.push(lm);
      blockMap.set(lm.block_index, existing);
    } else {
      nullBlockLines.push(lm);
    }
  }

  const blocks: BlockNode[] = [];
  const sortedKeys = Array.from(blockMap.keys()).sort((a, b) => a - b);
  for (const blockIdx of sortedKeys) {
    const blockLines = blockMap.get(blockIdx)!;
    blocks.push({
      kind: "block",
      blockIndex: blockIdx,
      label: `Block ${blockIdx + 1}`,
      children: buildParaNodes(blockLines),
    });
  }
  if (nullBlockLines.length > 0) {
    // Synthesize a block index beyond the last real one for unsorted lines.
    const syntheticIdx = sortedKeys.length > 0 ? sortedKeys[sortedKeys.length - 1] + 1 : 0;
    blocks.push({
      kind: "block",
      blockIndex: syntheticIdx,
      label: "Unsorted",
      children: buildParaNodes(nullBlockLines),
    });
  }
  return blocks;
}

/** Build the para-rooted tree (legacy / no-block-layer path). */
function buildTree(page: PagePayload): ParaNode[] {
  return buildParaNodes(page.line_matches ?? []);
}

function buildLineNodes(lines: LineMatch[]): LineNode[] {
  return lines
    .slice()
    .sort((a, b) => a.line_index - b.line_index)
    .map((lm) => ({
      kind: "line" as const,
      lineIndex: lm.line_index,
      text: lm.ocr_line_text || `Line ${lm.line_index + 1}`,
      children: buildWordNodes(lm.word_matches, lm.line_index),
    }));
}

function buildWordNodes(words: WordMatch[], lineIndex: number): WordNode[] {
  return words
    .slice()
    .sort((a, b) => (a.word_index ?? 0) - (b.word_index ?? 0))
    .map((wm) => ({
      kind: "word" as const,
      lineIndex,
      wordIndex: wm.word_index ?? 0,
      text: wm.ocr_text || "·",
    }));
}

// ─── Flat navigation index ────────────────────────────────────────────────────

interface FlatNode {
  id: string;
  depth: number;
  node: TreeNode;
  hasChildren: boolean;
}

function flattenParas(paras: ParaNode[], expanded: Set<string>, baseDepth: number): FlatNode[] {
  const result: FlatNode[] = [];
  for (const para of paras) {
    const paraId = `para-${para.paraIndex ?? "null"}`;
    const paraExpanded = expanded.has(paraId);
    result.push({
      id: paraId,
      depth: baseDepth,
      node: para,
      hasChildren: para.children.length > 0,
    });

    if (paraExpanded) {
      for (const line of para.children) {
        const lineId = `line-${line.lineIndex}`;
        const lineExpanded = expanded.has(lineId);
        result.push({
          id: lineId,
          depth: baseDepth + 1,
          node: line,
          hasChildren: line.children.length > 0,
        });

        if (lineExpanded) {
          for (const word of line.children) {
            const wordId = `word-${word.lineIndex}-${word.wordIndex}`;
            result.push({ id: wordId, depth: baseDepth + 2, node: word, hasChildren: false });
          }
        }
      }
    }
  }
  return result;
}

/** Flatten a block-rooted tree (block → para → line → word). */
function flattenBlocks(blocks: BlockNode[], expanded: Set<string>): FlatNode[] {
  const result: FlatNode[] = [];
  for (const block of blocks) {
    const blockId = `block-${block.blockIndex}`;
    const blockExpanded = expanded.has(blockId);
    result.push({ id: blockId, depth: 0, node: block, hasChildren: block.children.length > 0 });

    if (blockExpanded) {
      result.push(...flattenParas(block.children, expanded, 1));
    }
  }
  return result;
}

/** Flatten a para-rooted tree (legacy / no-block-layer path). */
function flattenTree(paras: ParaNode[], expanded: Set<string>): FlatNode[] {
  return flattenParas(paras, expanded, 0);
}

// ─── Kind filter (P5.c) ───────────────────────────────────────────────────────

type KindFilter = "all" | "block" | "para" | "line" | "word";

interface KindFilterPillProps {
  label: string;
  kind: KindFilter;
  active: boolean;
  onClick: () => void;
  testid: string;
}

function KindFilterPill({ label, kind, active, onClick, testid }: KindFilterPillProps) {
  const colorClass =
    kind === "all"
      ? active
        ? "bg-accent text-accent-ink border-accent"
        : "bg-bg-raised text-ink-2 border-border-2"
      : active
        ? cn(
            "border",
            kind === "block"
              ? "bg-layer-block/30 text-layer-block border-layer-block/60"
              : kind === "para"
                ? "bg-layer-para/30 text-layer-para border-layer-para/60"
                : kind === "line"
                  ? "bg-layer-line/30 text-layer-line border-layer-line/60"
                  : "bg-layer-word/30 text-layer-word border-layer-word/60",
          )
        : "bg-bg-raised text-ink-2 border-border-2";

  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : undefined}
      onClick={onClick}
      className={cn(
        "text-[10px] px-1.5 py-0.5 rounded-full border transition-colors select-none",
        colorClass,
        !active && "hover:border-accent hover:text-ink-1",
      )}
    >
      {label}
    </button>
  );
}

function filterByKind(flat: FlatNode[], kind: KindFilter): FlatNode[] {
  if (kind === "all") return flat;
  return flat.filter((fn) => fn.node.kind === kind);
}

// ─── Node row ─────────────────────────────────────────────────────────────────

interface NodeRowProps {
  flatNode: FlatNode;
  isSelected: boolean;
  isExpanded: boolean;
  onSelect: (id: string, node: TreeNode) => void;
  onToggle: (id: string) => void;
}

function NodeRow({ flatNode, isSelected, isExpanded, onSelect, onToggle }: NodeRowProps) {
  const { id, depth, node, hasChildren } = flatNode;
  const layerKey: "block" | "para" | "line" | "word" =
    node.kind === "block"
      ? "block"
      : node.kind === "para"
        ? "para"
        : node.kind === "line"
          ? "line"
          : "word";

  let label = "";
  let monoId = "";
  if (node.kind === "block") {
    label = node.label;
    monoId = `B-${node.blockIndex + 1}`;
  } else if (node.kind === "para") {
    label = node.label;
    monoId = node.paraIndex !== null ? `P-${node.paraIndex + 1}` : "P-?";
  } else if (node.kind === "line") {
    label = node.text;
    monoId = `L-${node.lineIndex + 1}`;
  } else {
    label = node.text;
    monoId = `W-${String(node.wordIndex + 1).padStart(3, "0")}`;
  }

  return (
    <div
      data-testid={`hierarchy-node-${id}`}
      data-selected={isSelected ? "true" : undefined}
      data-kind={node.kind}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
      className={cn(
        "flex items-center gap-1.5 py-0.5 pr-2 cursor-pointer select-none text-[11px]",
        isSelected
          ? "bg-bg-raised text-ink-1"
          : "text-ink-2 hover:bg-bg-raised/60 hover:text-ink-1",
      )}
      role="treeitem"
      aria-expanded={hasChildren ? isExpanded : undefined}
      aria-selected={isSelected}
      tabIndex={0}
      onClick={() => onSelect(id, node)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(id, node);
        }
        if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && hasChildren) {
          e.preventDefault();
          onToggle(id);
        }
      }}
    >
      {/* Expand chevron placeholder — keeps alignment */}
      <span className="w-3 text-ink-3 text-[9px] flex-shrink-0">
        {hasChildren ? (isExpanded ? "▾" : "▸") : ""}
      </span>

      {/* Layer color square */}
      <span
        data-testid={`hierarchy-color-${id}`}
        className={cn("w-[6px] h-[6px] rounded-sm flex-shrink-0", LAYER_DOT_CLASS[layerKey])}
      />

      {/* Kind chip (P5.c) */}
      <KindChip kind={layerKey} />

      {/* Mono ID stamp (P5.c) */}
      <span className="font-mono text-[10px] text-ink-3 flex-shrink-0">{monoId}</span>

      {/* Label */}
      <span className="truncate">{label}</span>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export interface HierarchyProps {
  page?: PagePayload | null;
}

export function Hierarchy({ page }: HierarchyProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const containerRef = useRef<HTMLDivElement>(null);

  // FO-7 / CU-4.3: use block tree when block_index is populated, else fall
  // back to para-rooted tree for backward compatibility.
  const useBlocks = page ? hasBlockLayer(page) : false;
  const flatAll = page
    ? useBlocks
      ? flattenBlocks(buildBlockTree(page), expanded)
      : flattenTree(buildTree(page), expanded)
    : [];
  const flat = filterByKind(flatAll, kindFilter);

  // Total visible node count (P5.c)
  const nodeCount = flat.length;

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleSelect = useCallback((id: string, node: TreeNode) => {
    setSelectedId(id);
    // Update selection-store using canonical helpers so level+path are set atomically.
    if (node.kind === "block") {
      selectBlock(String(node.blockIndex));
    } else if (node.kind === "line") {
      selectLine(node.lineIndex);
    } else if (node.kind === "word") {
      selectWord(node.lineIndex, node.wordIndex);
    } else if (node.kind === "para" && node.paraIndex !== null) {
      selectPara(node.paraIndex);
    }
  }, []);

  // Keyboard navigation — Up/Down through flat visible list.
  // Left/Right (collapse/expand) are handled per-node in NodeRow.onKeyDown.
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const idx = flat.findIndex((n) => n.id === selectedId);
    if (e.key === "ArrowDown") {
      const next = flat[idx + 1];
      if (next) handleSelect(next.id, next.node);
    } else if (e.key === "ArrowUp") {
      const prev = flat[idx - 1];
      if (prev) handleSelect(prev.id, prev.node);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Filter pills + node count (P5.c) */}
      <div
        data-testid="hierarchy-filter-row"
        className="flex items-center gap-1 px-2 py-1.5 border-b border-border-1 flex-shrink-0 flex-wrap"
      >
        <KindFilterPill
          testid="hierarchy-filter-all"
          label="All"
          kind="all"
          active={kindFilter === "all"}
          onClick={() => setKindFilter("all")}
        />
        {useBlocks && (
          <KindFilterPill
            testid="hierarchy-filter-block"
            label="B Block"
            kind="block"
            active={kindFilter === "block"}
            onClick={() => setKindFilter("block")}
          />
        )}
        <KindFilterPill
          testid="hierarchy-filter-para"
          label="¶ Para"
          kind="para"
          active={kindFilter === "para"}
          onClick={() => setKindFilter("para")}
        />
        <KindFilterPill
          testid="hierarchy-filter-line"
          label="Line"
          kind="line"
          active={kindFilter === "line"}
          onClick={() => setKindFilter("line")}
        />
        <KindFilterPill
          testid="hierarchy-filter-word"
          label="Word"
          kind="word"
          active={kindFilter === "word"}
          onClick={() => setKindFilter("word")}
        />
        <span
          data-testid="hierarchy-node-count"
          className="ml-auto text-[10px] font-mono text-ink-3 tabular-nums flex-shrink-0"
        >
          {nodeCount}
        </span>
      </div>

      {/* Tree */}
      <div
        ref={containerRef}
        data-testid="hierarchy"
        role="tree"
        aria-label="Page structure hierarchy"
        className="flex-1 overflow-y-auto py-1"
        onKeyDown={handleKeyDown}
      >
        {flatAll.length === 0 ? (
          <div className="text-ink-3 text-[11px] p-3 text-center">No page data</div>
        ) : (
          flat.map((fn) => (
            <NodeRow
              key={fn.id}
              flatNode={fn}
              isSelected={selectedId === fn.id}
              isExpanded={expanded.has(fn.id)}
              onSelect={handleSelect}
              onToggle={toggleExpand}
            />
          ))
        )}
      </div>
    </div>
  );
}
