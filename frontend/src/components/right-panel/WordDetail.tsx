// WordDetail.tsx — Word detail editor (right panel, level="word").
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16 (scaffold),
//       17 (Rebox/Erase), 18 (Structure).
//
// Renders an Accordion with 6 items:
//   1. Bounding Box  — wired (BBoxSection)
//   2. Rebox         — wired (ReboxSection, tag="accent")   [Slice 17]
//   3. Erase Pixels  — wired (ErasePixelsSection, tag="mismatch") [Slice 17]
//   4. Structure     — wired (StructureSection)              [Slice 18]
//   5. Char Ranges   — wired (CharRangesSection)              [Slice 19]
//   6. Char Fixer    — wired (CharFixerSection)                [Slice 20]
//
// The component receives the selected word via the selection-store path and
// the page payload from the parent (ProjectPage / RightPanel).
//
// data-testids:
//   word-detail             — outer container
//   word-detail-accordion   — accordion root

import { useSyncExternalStore } from "react";
import { Accordion } from "../ui/accordion";
import { BBoxSection } from "./sections/BBoxSection";
import { ReboxSection } from "./sections/ReboxSection";
import { ErasePixelsSection } from "./sections/ErasePixelsSection";
import { StructureSection } from "./sections/StructureSection";
import { CharRangesSection } from "./sections/CharRangesSection";
import { CharFixerSection } from "./sections/CharFixerSection";
import { WordHeader } from "./WordHeader";
import { selectionStore, walkSibling } from "../../stores/selection-store";
import { useRefineAvailable } from "../../hooks/useRefineAvailable";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

// ─── store subscription ───────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => cb());
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── helpers ──────────────────────────────────────────────────────────────

function resolveWord(
  page: PagePayload,
  lineId: number,
  wordId: [number, number],
): WordMatch | null {
  const line = page.line_matches?.find((l) => l.line_index === lineId);
  if (!line) return null;
  const [, wi] = wordId;
  return line.word_matches[wi] ?? null;
}

// ─── WordDetail ───────────────────────────────────────────────────────────

export interface WordDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

export function WordDetail({ page, projectId, pageIndex }: WordDetailProps) {
  const { data: refineProbe } = useRefineAvailable();
  const refineAvailable = refineProbe?.available ?? false;

  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );

  const { level, path } = state;

  if (level !== "word" || !path.wordId) {
    return (
      <div data-testid="word-detail" className="p-3 text-ink-3 text-sm">
        No word selected.
      </div>
    );
  }

  const lineIdx = path.lineId ?? path.wordId[0];
  const word = resolveWord(page, lineIdx, path.wordId);

  if (!word) {
    return (
      <div data-testid="word-detail" className="p-3 text-ink-3 text-sm">
        Word not found in page data.
      </div>
    );
  }

  // Slice 19: derive hasNext from the line length instead of hardcoding true.
  const currentLine = page.line_matches?.find((l) => l.line_index === lineIdx);
  const lineLength = currentLine?.word_matches.length ?? 0;
  const wordIdx = word.word_index ?? 0;
  const hasNextWord = wordIdx < lineLength - 1;

  return (
    <div data-testid="word-detail" className="flex flex-col gap-1">
      {/* P2.a: Word identity header with status pip + pager */}
      <WordHeader
        word={word}
        hasPrev={wordIdx > 0}
        hasNext={hasNextWord}
        onPrev={() => walkSibling("prev", page)}
        onNext={() => walkSibling("next", page)}
      />

      <Accordion
        data-testid="word-detail-accordion"
        type="multiple"
        className="flex flex-col gap-1"
      >
        {/* 1 — Bounding Box */}
        <Accordion.Item value="bbox">
          <Accordion.Trigger>Bounding Box</Accordion.Trigger>
          <Accordion.Content>
            <BBoxSection word={word} projectId={projectId} pageIndex={pageIndex} />
          </Accordion.Content>
        </Accordion.Item>

        {/* 2 — Rebox (Slice 17) */}
        <Accordion.Item value="rebox" tag="accent">
          <Accordion.Trigger>Rebox</Accordion.Trigger>
          <Accordion.Content>
            <ReboxSection hasPrev={wordIdx > 0} hasNext={hasNextWord} />
          </Accordion.Content>
        </Accordion.Item>

        {/* 3 — Erase Pixels (Slice 17) */}
        <Accordion.Item value="erase" tag="mismatch">
          <Accordion.Trigger>Erase Pixels</Accordion.Trigger>
          <Accordion.Content>
            <ErasePixelsSection backendAvailable={refineAvailable} />
          </Accordion.Content>
        </Accordion.Item>

        {/* 4 — Structure (Slice 18) */}
        <Accordion.Item value="structure">
          <Accordion.Trigger>Structure</Accordion.Trigger>
          <Accordion.Content>
            <StructureSection word={word} page={page} projectId={projectId} pageIndex={pageIndex} />
          </Accordion.Content>
        </Accordion.Item>

        {/* 5 — Char Ranges (Slice 19) */}
        <Accordion.Item value="char-ranges">
          <Accordion.Trigger>Char Ranges</Accordion.Trigger>
          <Accordion.Content>
            <CharRangesSection word={word} projectId={projectId} pageIndex={pageIndex} />
          </Accordion.Content>
        </Accordion.Item>

        {/* 6 — Char Fixer (Slice 20) */}
        <Accordion.Item value="char-fixer">
          <Accordion.Trigger>Char Fixer</Accordion.Trigger>
          <Accordion.Content>
            <CharFixerSection word={word} projectId={projectId} pageIndex={pageIndex} />
          </Accordion.Content>
        </Accordion.Item>
      </Accordion>
    </div>
  );
}
