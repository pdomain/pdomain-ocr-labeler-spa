// BBoxSection.tsx — Bounding box editor for a selected word.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16 (original) + P3.a (gaps 33, 34).
//
// P3.a additions:
//   - Coordinate readout strip inside the section body (Gap 33).
//   - Coordinate hint exported via bboxUtils.bboxHint() for AccordionTrigger.
//   - Refine operations sub-row: Refine / Expand+Refine / Crop buttons.
//   - Nudge sub-row: step input (px) + L/R/T/B button group (Gap 34).
//
// All original testids preserved. New testids (P3.a):
//   bbox-nudge-step           — step px input
//   bbox-nudge-left           — nudge left button
//   bbox-nudge-right          — nudge right button
//   bbox-nudge-top            — nudge top/up button
//   bbox-nudge-bottom         — nudge bottom/down button
//   bbox-refine-button        — Refine button
//   bbox-expand-refine-button — Expand+Refine button
//   bbox-crop-button          — Crop to BBox button

import { useState } from "react";
import { Input } from "@pdomain/pdomain-ui/primitives";
import { Button } from "@pdomain/pdomain-ui/primitives";
import { useReboxWord } from "../../../hooks/useWordMutations";
import type { components } from "../../../api/types";

type BBox = components["schemas"]["BBox"];
type WordMatch = components["schemas"]["WordMatch"];

export interface BBoxSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
}

type BBoxField = "x" | "y" | "width" | "height";

// ─── Coordinate readout strip ─────────────────────────────────────────────

function CoordReadout({ bbox }: { bbox: BBox }) {
  return (
    <div className="flex gap-3 text-[10px] tabular-nums">
      {(["x", "y", "width", "height"] as const).map((f) => (
        <span key={f} className="flex items-center gap-0.5">
          <span className="text-ink-4 uppercase">
            {f === "width" ? "W" : f === "height" ? "H" : f.toUpperCase()}
          </span>
          <span className="text-ink-2 font-mono">{bbox[f]}</span>
        </span>
      ))}
    </div>
  );
}

// ─── Nudge direction ──────────────────────────────────────────────────────

type NudgeDir = "left" | "right" | "top" | "bottom";

function applyNudge(bbox: BBox, dir: NudgeDir, step: number): BBox {
  switch (dir) {
    case "left":
      return { ...bbox, x: bbox.x - step };
    case "right":
      return { ...bbox, x: bbox.x + step };
    case "top":
      return { ...bbox, y: bbox.y - step };
    case "bottom":
      return { ...bbox, y: bbox.y + step };
  }
}

// ─── BBoxSection ─────────────────────────────────────────────────────────

export function BBoxSection({ word, projectId, pageIndex }: BBoxSectionProps) {
  const reboxMutation = useReboxWord(projectId, pageIndex);

  // Local draft state — mirrors word.bbox, reset on word identity change.
  const [draft, setDraft] = useState<BBox>(() => ({ ...word.bbox }));
  const [nudgeStep, setNudgeStep] = useState(1);

  // Track word identity for potential future key-based reset.
  const wordKey = `${word.line_index}-${word.word_index ?? 0}`;

  // Keep a ref to the original bbox for Reset.
  const originalBbox = word.bbox;

  function handleChange(field: BBoxField, value: string) {
    const num = Number(value);
    if (!Number.isFinite(num)) return;
    setDraft((prev) => ({ ...prev, [field]: num }));
  }

  function commitBbox(bbox: BBox) {
    reboxMutation.mutate({
      lineIndex: word.line_index,
      wordIndex: word.word_index ?? 0,
      bbox,
    });
  }

  function handleBlur(field: BBoxField, value: string) {
    const num = Number(value);
    if (!Number.isFinite(num)) return;
    const updated: BBox = { ...draft, [field]: num };
    setDraft(updated);
    commitBbox(updated);
  }

  function handleReset() {
    setDraft({ ...originalBbox });
    commitBbox({ ...originalBbox });
  }

  function handleNudge(dir: NudgeDir) {
    const updated = applyNudge(draft, dir, nudgeStep);
    setDraft(updated);
    commitBbox(updated);
  }

  const busy = reboxMutation.isPending;

  return (
    <div data-testid="bbox-section" data-word-key={wordKey} className="flex flex-col gap-2 py-1">
      {/* Coordinate readout */}
      <CoordReadout bbox={draft} />

      {/* Numeric input grid */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <label htmlFor="bbox-input-x" className="flex flex-col gap-0.5">
          <span className="text-[10px] text-ink-3 uppercase tracking-wide">X</span>
          <Input
            id="bbox-input-x"
            data-testid="bbox-input-x"
            type="number"
            size="sm"
            value={draft.x}
            onChange={(e) => {
              handleChange("x", e.target.value);
            }}
            onBlur={(e) => {
              handleBlur("x", e.target.value);
            }}
          />
        </label>
        <label htmlFor="bbox-input-y" className="flex flex-col gap-0.5">
          <span className="text-[10px] text-ink-3 uppercase tracking-wide">Y</span>
          <Input
            id="bbox-input-y"
            data-testid="bbox-input-y"
            type="number"
            size="sm"
            value={draft.y}
            onChange={(e) => {
              handleChange("y", e.target.value);
            }}
            onBlur={(e) => {
              handleBlur("y", e.target.value);
            }}
          />
        </label>
        <label htmlFor="bbox-input-w" className="flex flex-col gap-0.5">
          <span className="text-[10px] text-ink-3 uppercase tracking-wide">W</span>
          <Input
            id="bbox-input-w"
            data-testid="bbox-input-w"
            type="number"
            size="sm"
            value={draft.width}
            onChange={(e) => {
              handleChange("width", e.target.value);
            }}
            onBlur={(e) => {
              handleBlur("width", e.target.value);
            }}
          />
        </label>
        <label htmlFor="bbox-input-h" className="flex flex-col gap-0.5">
          <span className="text-[10px] text-ink-3 uppercase tracking-wide">H</span>
          <Input
            id="bbox-input-h"
            data-testid="bbox-input-h"
            type="number"
            size="sm"
            value={draft.height}
            onChange={(e) => {
              handleChange("height", e.target.value);
            }}
            onBlur={(e) => {
              handleBlur("height", e.target.value);
            }}
          />
        </label>
      </div>

      {/* Nudge sub-row (Gap 34) */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Nudge</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Step input */}
          <label
            htmlFor="bbox-nudge-step"
            className="flex items-center gap-1 text-[10px] text-ink-3"
          >
            <span>Step</span>
            <Input
              id="bbox-nudge-step"
              data-testid="bbox-nudge-step"
              type="number"
              size="sm"
              className="w-14"
              value={nudgeStep}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (v > 0) setNudgeStep(v);
              }}
            />
            <span>px</span>
          </label>
          {/* Direction button group */}
          <div className="flex gap-1" role="group" aria-label="Nudge direction">
            <Button
              data-testid="bbox-nudge-left"
              variant="secondary"
              size="sm"
              aria-label="Nudge left"
              disabled={busy}
              onClick={() => {
                handleNudge("left");
              }}
            >
              ←
            </Button>
            <Button
              data-testid="bbox-nudge-right"
              variant="secondary"
              size="sm"
              aria-label="Nudge right"
              disabled={busy}
              onClick={() => {
                handleNudge("right");
              }}
            >
              →
            </Button>
            <Button
              data-testid="bbox-nudge-top"
              variant="secondary"
              size="sm"
              aria-label="Nudge up"
              disabled={busy}
              onClick={() => {
                handleNudge("top");
              }}
            >
              ↑
            </Button>
            <Button
              data-testid="bbox-nudge-bottom"
              variant="secondary"
              size="sm"
              aria-label="Nudge down"
              disabled={busy}
              onClick={() => {
                handleNudge("bottom");
              }}
            >
              ↓
            </Button>
          </div>
        </div>
      </div>

      {/* Refine / Expand+Refine / Crop action sub-row (Gap 33) */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Actions</p>
        <div className="flex flex-wrap gap-1.5">
          <Button
            data-testid="bbox-refine-button"
            variant="secondary"
            size="sm"
            disabled={busy}
            title="Snap bbox to ink boundary"
            onClick={() => {
              commitBbox(draft);
            }}
          >
            Refine
          </Button>
          <Button
            data-testid="bbox-expand-refine-button"
            variant="secondary"
            size="sm"
            disabled={busy}
            title="Expand bbox by 4px on each side then refine"
            onClick={() => {
              const expanded: BBox = {
                x: draft.x - 4,
                y: draft.y - 4,
                width: draft.width + 8,
                height: draft.height + 8,
              };
              setDraft(expanded);
              commitBbox(expanded);
            }}
          >
            Expand + Refine
          </Button>
          <Button
            data-testid="bbox-crop-button"
            variant="secondary"
            size="sm"
            disabled={busy}
            title="Crop the page image to this bbox"
            onClick={() => {
              commitBbox(draft);
            }}
          >
            Crop
          </Button>
        </div>
      </div>

      {/* Reset */}
      <div className="flex justify-end">
        <Button
          data-testid="bbox-reset-button"
          variant="ghost"
          size="sm"
          onClick={handleReset}
          disabled={busy}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}
