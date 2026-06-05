// RightPanel.tsx — 320px right-side context panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 14, Slice 21 (line), Slice 22 (block/para).
//
// Header: <Breadcrumb /> + collapse button.
// Body  : routes on `selection-store.level`:
//           "none"  → "Select a block/para/line/word…" placeholder.
//           "word"  → caller-provided `wordSlot` (e.g. WordMatchView for
//                     Slice 14; WordDetail in Slice 16). When no slot is
//                     supplied, falls back to a "Word: …" placeholder.
//           "line"  → <LineDetail> (Slice 21).
//           "block" → <BlockDetail> (Slice 22).
//           "para"  → thin para view reusing BlockDetail items (Slice 22).
//
// Slice 14 deliberately does NOT mount WordMatchView itself — the consumer
// (ProjectPage) provides word content via `wordSlot` so the panel stays free
// of API/data coupling.

import { useSyncExternalStore } from "react";
import { PanelRightClose } from "@/icons/local-shims";
import { cn } from "@/lib/utils";
import { Breadcrumb } from "./Breadcrumb";
import { selectionStore, type SelectionLevel } from "../../stores/selection-store";
import { LineDetail } from "../right-panel/LineDetail";
import { BlockDetail } from "../right-panel/BlockDetail";
import { ParagraphDetail } from "../right-panel/ParagraphDetail";
import { MultiWordDetail } from "../right-panel/MultiWordDetail";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

// ─── Subscriber bridge ───────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── Placeholder body per level ──────────────────────────────────────────────

const LEVEL_PLACEHOLDER: Record<SelectionLevel, string> = {
  none: "Select a block, paragraph, line, or word to inspect it here.",
  block: "Block detail — coming soon.",
  para: "Paragraph detail — coming soon.",
  line: "Line detail — coming soon.",
  word: "Word detail — coming soon.",
};

// ─── Component ───────────────────────────────────────────────────────────────

export interface RightPanelProps {
  /** Current page (used by Breadcrumb for label resolution and detail panels). */
  page?: PagePayload | undefined;
  /** Project id — forwarded to detail panels for mutations. */
  projectId?: string | undefined;
  /** Page index — forwarded to detail panels for mutations. */
  pageIndex?: number | undefined;
  /** Rendered when `selection-store.level === "word"`. */
  wordSlot?: React.ReactNode;
  /** Invoked when the collapse button is clicked. */
  onCollapse?: (() => void) | undefined;
}

export function RightPanel({ page, projectId, pageIndex, wordSlot, onCollapse }: RightPanelProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );
  const { level } = state;

  return (
    <div
      data-testid="right-panel"
      className="flex flex-col h-full w-full bg-bg-surface border-l border-border-1"
    >
      {/* Header: Breadcrumb + collapse */}
      <div
        data-testid="right-panel-header"
        className="flex items-center justify-between gap-2 h-10 px-3 border-b border-border-1"
      >
        <Breadcrumb page={page} />
        <button
          type="button"
          data-testid="right-panel-collapse"
          onClick={() => onCollapse?.()}
          title="Collapse right panel"
          className={cn(
            "inline-flex items-center justify-center w-6 h-6 rounded text-ink-3",
            "hover:text-ink-1 hover:bg-bg-raised transition-colors",
          )}
        >
          <PanelRightClose className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {/* Body */}
      <div
        data-testid="right-panel-body"
        data-level={level}
        className="flex-1 min-h-0 overflow-auto text-sm text-ink-2"
      >
        {state.selectedWords.length > 1 &&
        page &&
        projectId !== undefined &&
        pageIndex !== undefined ? (
          <MultiWordDetail
            page={page}
            projectId={projectId}
            pageIndex={pageIndex}
            selectedWords={state.selectedWords}
          />
        ) : level === "word" && wordSlot ? (
          <div className="p-3">{wordSlot}</div>
        ) : level === "line" && page && projectId !== undefined && pageIndex !== undefined ? (
          <LineDetail page={page} projectId={projectId} pageIndex={pageIndex} />
        ) : level === "block" && page && projectId !== undefined && pageIndex !== undefined ? (
          <BlockDetail page={page} projectId={projectId} pageIndex={pageIndex} level="block" />
        ) : level === "para" && page && projectId !== undefined && pageIndex !== undefined ? (
          <div className="flex flex-col">
            {/* D1: paragraph-scope actions panel above the items overview. */}
            <ParagraphDetail page={page} projectId={projectId} pageIndex={pageIndex} />
            <BlockDetail page={page} projectId={projectId} pageIndex={pageIndex} level="para" />
          </div>
        ) : (
          <div className="p-3">
            <Placeholder level={level} />
          </div>
        )}
      </div>
    </div>
  );
}

function Placeholder({ level }: { level: SelectionLevel }) {
  return (
    <div
      data-testid="right-panel-placeholder"
      data-level={level}
      className="flex h-full items-center justify-center text-center text-ink-3"
    >
      <p className="max-w-[28ch]">{LEVEL_PLACEHOLDER[level]}</p>
    </div>
  );
}
