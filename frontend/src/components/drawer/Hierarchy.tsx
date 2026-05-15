// Hierarchy.tsx — Drawer Hierarchy tab: block/para/line/word tree view.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 12.
//
// Builds a tree from PagePayload.line_matches:
//   paragraph groups → lines → words
//
// Each node has a 6px layer-color square + text label.
// Click → updates selection-store.
// Keyboard: Up/Down navigate; Left/Right collapse/expand branch nodes.
//
// Note: the PagePayload has no explicit block layer; we render paragraphs as
// top-level tree nodes (with lines as children and words as leaf nodes).
// A future PagePayload expansion may add block_index to expose true blocks.

import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { selectionStore } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

// ─── Layer color squares (6px, matches CSS token names) ──────────────────────

const LAYER_DOT_CLASS: Record<"para" | "line" | "word", string> = {
  para: "bg-layer-para",
  line: "bg-layer-line",
  word: "bg-layer-word",
};

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

type TreeNode = ParaNode | LineNode | WordNode;

// ─── Build tree from PagePayload ─────────────────────────────────────────────

function buildTree(page: PagePayload): ParaNode[] {
  const paraMap = new Map<number, LineMatch[]>();
  const nullParaLines: LineMatch[] = [];

  for (const lm of page.line_matches ?? []) {
    if (lm.paragraph_index === null || lm.paragraph_index === undefined) {
      nullParaLines.push(lm);
    } else {
      const existing = paraMap.get(lm.paragraph_index) ?? [];
      existing.push(lm);
      paraMap.set(lm.paragraph_index, existing);
    }
  }

  const paras: ParaNode[] = [];

  // Sorted paragraph indices
  const sortedKeys = Array.from(paraMap.keys()).sort((a, b) => a - b);
  for (const paraIdx of sortedKeys) {
    const lines = paraMap.get(paraIdx)!;
    paras.push({
      kind: "para",
      paraIndex: paraIdx,
      label: `Para ${paraIdx + 1}`,
      children: buildLineNodes(lines),
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

function flattenTree(paras: ParaNode[], expanded: Set<string>): FlatNode[] {
  const result: FlatNode[] = [];

  for (const para of paras) {
    const paraId = `para-${para.paraIndex ?? "null"}`;
    const paraExpanded = expanded.has(paraId);
    result.push({ id: paraId, depth: 0, node: para, hasChildren: para.children.length > 0 });

    if (paraExpanded) {
      for (const line of para.children) {
        const lineId = `line-${line.lineIndex}`;
        const lineExpanded = expanded.has(lineId);
        result.push({ id: lineId, depth: 1, node: line, hasChildren: line.children.length > 0 });

        if (lineExpanded) {
          for (const word of line.children) {
            const wordId = `word-${word.lineIndex}-${word.wordIndex}`;
            result.push({ id: wordId, depth: 2, node: word, hasChildren: false });
          }
        }
      }
    }
  }

  return result;
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
  const layerKey = node.kind === "para" ? "para" : node.kind === "line" ? "line" : "word";

  let label = "";
  if (node.kind === "para") label = node.label;
  else if (node.kind === "line") label = node.text;
  else label = node.text;

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

      {/* Label */}
      <span className="truncate font-mono">{label}</span>
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
  const containerRef = useRef<HTMLDivElement>(null);

  const paras = page ? buildTree(page) : [];
  const flat = flattenTree(paras, expanded);

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
    // Update selection-store
    if (node.kind === "line") {
      selectionStore.setState((s) => ({
        ...s,
        selectedLines: [node.lineIndex],
        selectedParagraphs: [],
        selectedWords: [],
      }));
    } else if (node.kind === "word") {
      selectionStore.setState((s) => ({
        ...s,
        selectedWords: [[node.lineIndex, node.wordIndex]],
        selectedLines: [],
        selectedParagraphs: [],
      }));
    } else if (node.kind === "para" && node.paraIndex !== null) {
      selectionStore.setState((s) => ({
        ...s,
        selectedParagraphs: [node.paraIndex!],
        selectedLines: [],
        selectedWords: [],
      }));
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
    <div
      ref={containerRef}
      data-testid="hierarchy"
      role="tree"
      aria-label="Page structure hierarchy"
      className="flex flex-col h-full overflow-y-auto py-1"
      onKeyDown={handleKeyDown}
    >
      {paras.length === 0 ? (
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
  );
}
