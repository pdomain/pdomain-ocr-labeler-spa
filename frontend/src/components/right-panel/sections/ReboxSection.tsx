// ReboxSection.tsx — Rebox accordion section for the word detail editor.
// Spec: docs/plans/hifi-gaps-plan.md slice P3.b (Gap 35).
//
// Replaces the legacy WordRefineNudgeRows-based content with an inline
// Konva mini-canvas. The user drags the 8 handles (or click-drags in
// "draw" mode) to reposition a word boundary, then clicks Apply rebox
// to commit via the existing /rebox endpoint.
//
// The structural actions previously bundled in this section (merge /
// split / delete / crop) now live exclusively in the Structure section
// of WordDetail — keeping Rebox focused on bbox geometry alone.
//
// data-testids:
//   rebox-section            — outer wrapper
//   rebox-tool-snap          — Snap tool button
//   rebox-tool-draw          — Draw tool button
//   rebox-tool-pan           — Pan tool button
//   rebox-zoom-in            — Zoom-in button
//   rebox-zoom-out           — Zoom-out button
//   rebox-zoom-level         — Zoom level text ("1×")
//   rebox-bbox-summary       — Current bbox size ("80 × 30 px")
//   rebox-apply              — Apply rebox primary button
//   rebox-reset              — Reset to original bbox

import { useCallback, useEffect, useState } from "react";
import { Button } from "../../ui/button";
import { ReboxCanvas, type ReboxTool } from "./ReboxCanvas";
import { useReboxWord } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

export interface ReboxSectionProps {
  /** The currently-selected word. */
  word: WordMatch;
  /** Project id (route param). */
  projectId: string;
  /** Page index (0-based). */
  pageIndex: number;
  /** Optional cropped word image URL (forwarded to the canvas). */
  imageUrl?: string | undefined;
}

function bboxEqual(a: BBox, b: BBox): boolean {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}

function roundBbox(b: BBox): BBox {
  return {
    x: Math.round(b.x),
    y: Math.round(b.y),
    width: Math.max(1, Math.round(b.width)),
    height: Math.max(1, Math.round(b.height)),
  };
}

export function ReboxSection({ word, projectId, pageIndex, imageUrl }: ReboxSectionProps) {
  const reboxMutation = useReboxWord(projectId, pageIndex);

  const [tool, setTool] = useState<ReboxTool>("snap");
  const [zoom, setZoom] = useState<number>(1);
  const [draft, setDraft] = useState<BBox>(() => ({ ...word.bbox }));

  // Track an identity key so a new word reseeds the draft + zoom + tool.
  const wordKey = `${word.line_index}-${word.word_index ?? 0}`;
  useEffect(() => {
    setDraft({ ...word.bbox });
    setTool("snap");
    setZoom(1);
    // wordKey intentionally not in deps — we want the seed to fire only on
    // *identity* change, and wordKey carries the same info as the indices.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wordKey]);

  const dirty = !bboxEqual(roundBbox(draft), roundBbox(word.bbox));
  const summary = `${roundBbox(draft).width} × ${roundBbox(draft).height} px`;

  const handleApply = useCallback(() => {
    const final = roundBbox(draft);
    reboxMutation.mutate({
      lineIndex: word.line_index,
      wordIndex: word.word_index ?? 0,
      bbox: final,
    });
  }, [draft, reboxMutation, word.line_index, word.word_index]);

  const handleReset = useCallback(() => {
    setDraft({ ...word.bbox });
  }, [word.bbox]);

  const zoomIn = () => {
    setZoom((z) => Math.min(MAX_ZOOM, z + 1));
  };
  const zoomOut = () => {
    setZoom((z) => Math.max(MIN_ZOOM, z - 1));
  };

  return (
    <div
      data-testid="rebox-section"
      data-word-key={wordKey}
      className="flex flex-col gap-2 px-3 py-2"
    >
      {/* Tool-mode segmented control */}
      <div
        role="radiogroup"
        aria-label="Rebox tool"
        className="inline-flex rounded border border-border-2 bg-raised overflow-hidden self-start"
      >
        <ToolButton
          testId="rebox-tool-snap"
          label="Snap"
          active={tool === "snap"}
          onClick={() => {
            setTool("snap");
          }}
        />
        <ToolButton
          testId="rebox-tool-draw"
          label="Draw"
          active={tool === "draw"}
          onClick={() => {
            setTool("draw");
          }}
        />
        <ToolButton
          testId="rebox-tool-pan"
          label="Pan"
          active={tool === "pan"}
          onClick={() => {
            setTool("pan");
          }}
        />
      </div>

      {/* Konva mini-canvas */}
      <ReboxCanvas
        originalBbox={word.bbox}
        bbox={draft}
        onChange={setDraft}
        tool={tool}
        zoom={zoom}
        imageUrl={imageUrl}
      />

      {/* Zoom controls + bbox summary */}
      <div className="flex items-center justify-between gap-2 text-xs text-ink-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="rebox-zoom-out"
            aria-label="Zoom out"
            className="h-6 w-6 rounded border border-border-2 bg-raised text-ink-1 hover:bg-sunk disabled:opacity-40"
            onClick={zoomOut}
            disabled={zoom <= MIN_ZOOM}
          >
            −
          </button>
          <span data-testid="rebox-zoom-level" className="w-8 text-center font-mono">
            {zoom}×
          </span>
          <button
            type="button"
            data-testid="rebox-zoom-in"
            aria-label="Zoom in"
            className="h-6 w-6 rounded border border-border-2 bg-raised text-ink-1 hover:bg-sunk disabled:opacity-40"
            onClick={zoomIn}
            disabled={zoom >= MAX_ZOOM}
          >
            +
          </button>
        </div>
        <span data-testid="rebox-bbox-summary" className="font-mono text-ink-3">
          {summary}
        </span>
      </div>

      {/* Apply + Reset */}
      <div className="flex items-center gap-2">
        <Button
          data-testid="rebox-apply"
          size="sm"
          variant="primary"
          disabled={!dirty || reboxMutation.isPending}
          onClick={handleApply}
        >
          Apply rebox
        </Button>
        <button
          type="button"
          data-testid="rebox-reset"
          className="text-xs text-ink-3 underline hover:text-ink-1 disabled:opacity-40"
          onClick={handleReset}
          disabled={!dirty}
        >
          Reset
        </button>
      </div>
    </div>
  );
}

interface ToolButtonProps {
  testId: string;
  label: string;
  active: boolean;
  onClick: () => void;
}

function ToolButton({ testId, label, active, onClick }: ToolButtonProps) {
  return (
    <button
      type="button"
      data-testid={testId}
      role="radio"
      aria-pressed={active}
      aria-checked={active}
      className={[
        "px-2 h-6 text-[11px] transition-colors",
        active ? "bg-accent text-accent-ink" : "bg-raised text-ink-2 hover:bg-sunk",
      ].join(" ")}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
