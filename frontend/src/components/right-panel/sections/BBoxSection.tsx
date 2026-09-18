// BBoxSection.tsx — Bounding box editor for a selected word.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16 (original) + P3.a (gaps 33, 34).
//
// P3.a additions:
//   - Coordinate readout strip inside the section body (Gap 33).
//   - Coordinate hint exported via bboxUtils.bboxHint() for AccordionTrigger.
//   - Refine operations sub-row: Refine / Expand+Refine / Expand buttons.
//   - Nudge sub-row: step input (px) + L/R/T/B button group (Gap 34).
//
// P1-BBOX-UI (docs/issues/2026-07-21-bbox-refine-crop-misleading.md): the
// Refine / Expand+Refine / Crop buttons used to all call the plain rebox
// mutation (`commitBbox`) — no refine or crop ever ran. They now call the
// real `refine_bboxes` job (`POST .../refine`, `useRefineWordBbox`), scoped
// to this word, mapped onto the three modes the backend handler
// (`core/jobs/handlers/refine.py`) actually implements:
//   Refine         → mode: "refine"              (snap bbox to ink)
//   Expand+Refine  → mode: "expand_then_refine"   (expand, then snap to ink)
//   Expand         → mode: "expand_only"          (expand only, no snap)
// The backend has no image-crop operation at all — "Crop" never matched any
// real capability, so it is renamed to "Expand" (honest name for the third
// mode) rather than kept as a rebox pretending to crop. Gated by the
// `useRefineAvailable` capability probe: when unavailable, the three
// refine buttons are disabled and say so instead of failing on click.
// `refine_bboxes` is not in the backend's cancellable job set (BusyOverlay's
// CANCELLABLE / BEST_EFFORT_CANCEL policy sets), so no Cancel action is
// offered for these jobs.
//
// Review finding 3: the refine_bboxes job tracker (SSE subscription +
// terminal-status invalidation + toast) does NOT live in this component.
// This component's `Accordion.Content` unmounts whenever the "Bounding Box"
// item collapses (Radix removes closed content from the DOM), which would
// close the SSE connection and drop the terminal event mid-job. The tracker
// lives in `useBboxRefineTracking`, owned by ProjectPage (the only ancestor
// guaranteed to stay mounted for the whole session) and passed down as the
// `refineTracking` prop. This component only calls `refineTracking.start`
// once a refine POST returns 202, and reads `refineTracking.jobId` /
// `.wordKey` / `.outcome` back to compute its own busy state and to resync
// `draft` once a real (refined > 0) outcome for this word lands.
//
// All original testids preserved except `bbox-crop-button`, renamed to
// `bbox-expand-button` (see above). New testids (P3.a + P1-BBOX-UI):
//   bbox-nudge-step             — step px input
//   bbox-nudge-left             — nudge left button
//   bbox-nudge-right            — nudge right button
//   bbox-nudge-top              — nudge top/up button
//   bbox-nudge-bottom           — nudge bottom/down button
//   bbox-refine-button          — Refine button (mode: refine)
//   bbox-expand-refine-button   — Expand+Refine button (mode: expand_then_refine)
//   bbox-expand-button          — Expand button (mode: expand_only; was bbox-crop-button)
//   bbox-refine-unavailable     — shown when useRefineAvailable() reports unavailable

import { useState } from "react";
import { Input } from "@pdomain/pdomain-ui/primitives";
import { Button } from "@pdomain/pdomain-ui/primitives";
import { useReboxWord, useRefineWordBbox } from "../../../hooks/useWordMutations";
import { useRefineAvailable } from "../../../hooks/useRefineAvailable";
import type { UseBboxRefineTrackingResult } from "../../../hooks/useBboxRefineTracking";
import { toast } from "../../../lib/toast";
import type { components } from "../../../api/types";

type BBox = components["schemas"]["BBox"];
type WordMatch = components["schemas"]["WordMatch"];
type RefineMode = components["schemas"]["RefineScopeRequest"]["mode"];

/** `padding_px` sent with `mode: "refine"` / `"expand_then_refine"` — matches
 * the `RefineScopeRequest` schema default. `expand_then_refine`'s handler
 * ignores `padding_px` (`word.expand_then_refine_bbox` takes no padding
 * argument), but the field is required on the wire, so both modes share it. */
const REFINE_PADDING_PX = 2;

/** `padding_px` sent with `mode: "expand_only"` — preserves the 4px-per-side
 * expansion the old (fake) "Expand + Refine" button used to apply via rebox. */
const EXPAND_ONLY_PADDING_PX = 4;

export interface BBoxSectionProps {
  word: WordMatch;
  projectId: string;
  pageIndex: number;
  /** Hoisted refine_bboxes job tracker — see the module doc comment
   * (review finding 3) for why this lives in an ancestor rather than here. */
  refineTracking: UseBboxRefineTrackingResult;
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

export function BBoxSection({ word, projectId, pageIndex, refineTracking }: BBoxSectionProps) {
  const reboxMutation = useReboxWord(projectId, pageIndex);
  const refineMutation = useRefineWordBbox(projectId, pageIndex);

  // Local draft state — mirrors word.bbox, reset on word identity change.
  const [draft, setDraft] = useState<BBox>(() => ({ ...word.bbox }));
  const [nudgeStep, setNudgeStep] = useState(1);

  // Track word identity for potential future key-based reset.
  const wordKey = `${word.line_index}-${word.word_index ?? 0}`;

  // Keep a ref to the original bbox for Reset.
  const originalBbox = word.bbox;

  // P1-BBOX-UI: every other path that changes `draft` (nudge, blur-commit,
  // reset) already knows the new bbox locally and calls `setDraft` itself —
  // `draft` never needs to resync from the `word` prop for those. A refine
  // job is different: the server computes the new bbox, so `draft` only
  // ever knows the real value once the ancestor's `useBboxRefineTracking`
  // invalidates the page query and a fresh `word.bbox` arrives as a prop.
  // `pendingRefineSync` is armed below (from `refineTracking.outcome`) and
  // consumed the next time `word.bbox` actually changes — adjusting state
  // during render (not in an effect) the same way `useJobProgress` resets
  // `latest` on `jobId` change, so this doesn't cost an extra render or use
  // an effect to watch a prop. Gating on the flag (rather than resyncing on
  // every `word.bbox` change unconditionally) matters: an unconditional
  // resync would also fire after an ordinary nudge/reset's own
  // invalidation-triggered refetch, which could stomp a newer local edit
  // made while that round trip was still in flight.
  const [pendingRefineSync, setPendingRefineSync] = useState(false);
  const bboxSignature = `${String(word.bbox.x)},${String(word.bbox.y)},${String(word.bbox.width)},${String(word.bbox.height)}`;
  const [prevBboxSignature, setPrevBboxSignature] = useState(bboxSignature);
  if (bboxSignature !== prevBboxSignature) {
    setPrevBboxSignature(bboxSignature);
    if (pendingRefineSync) {
      setPendingRefineSync(false);
      setDraft({ ...word.bbox });
    }
  }

  // Review finding 2 (now sourced from the hoisted tracker's outcome
  // instead of a locally-owned job-completion callback): arm the resync
  // only once, per outcome token, for THIS word, and only when the job
  // actually refined something. `lastSeenOutcomeToken` is consumed the same
  // render-time-adjustment way as `pendingRefineSync` above.
  const [lastSeenOutcomeToken, setLastSeenOutcomeToken] = useState<number | null>(null);
  const outcome = refineTracking.outcome;
  if (outcome?.wordKey === wordKey && outcome.token !== lastSeenOutcomeToken) {
    setLastSeenOutcomeToken(outcome.token);
    if (outcome.refined > 0) {
      setPendingRefineSync(true);
    }
  }

  // P1-BBOX-UI: capability probe — the Refine / Expand+Refine / Expand
  // buttons are disabled (with an explanatory message) rather than failing
  // on click when the server has no refine engine wired.
  const refineProbe = useRefineAvailable();
  const refineAvailable = refineProbe.data?.available ?? false;
  const refineProbeLoading = refineProbe.isLoading;

  // Review finding 4: `refineTracking.jobId` is one shared value across
  // every word (the hoisted tracker has a single slot — see
  // useBboxRefineTracking.ts's module doc comment). Scoped so that a job
  // running for a DIFFERENT word only disables the refine-job-backed
  // buttons here (they share that one slot, so starting a second job would
  // orphan the first — see the same doc comment), not the manual
  // rebox/nudge/reset controls, which are independent per-word mutations
  // with nothing to do with the shared slot.
  const refineJobRunningHere = refineTracking.jobId !== null && refineTracking.wordKey === wordKey;
  const refineJobRunningElsewhere =
    refineTracking.jobId !== null &&
    refineTracking.wordKey !== null &&
    refineTracking.wordKey !== wordKey;

  /** Queue a `refine_bboxes` job scoped to this word. */
  function startRefine(mode: RefineMode, paddingPx: number, loadingMessage: string) {
    refineMutation.mutate(
      { lineIndex: word.line_index, wordIndex: word.word_index ?? 0, mode, paddingPx },
      {
        onSuccess: (data) => {
          refineTracking.start(data.job_id, wordKey);
          void import("sonner").then(({ toast: sonnerToast }) => {
            sonnerToast.loading(loadingMessage, { id: data.job_id });
          });
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Failed to start bbox refine");
        },
      },
    );
  }

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

  // review finding 4: scoped to this word's own job, so a different word's
  // in-flight refine no longer disables this word's manual controls.
  const busy = reboxMutation.isPending || refineMutation.isPending || refineJobRunningHere;

  // Refine-button-specific disabled reason: the probe still loading, the
  // engine unavailable, or (review finding 4) a different word's job
  // already holds the tracker's one slot. `busy` (above) separately covers
  // an in-flight rebox/refine mutation for THIS word and disables every
  // button in this section, refine or not.
  const refineDisabledTitle = refineProbeLoading
    ? "Checking refine availability…"
    : !refineAvailable
      ? "Refine is not available in this deployment."
      : refineJobRunningElsewhere
        ? "A refine is already running for another word — wait for it to finish."
        : null;

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
            disabled={busy}
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
            disabled={busy}
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
            disabled={busy}
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
            disabled={busy}
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

      {/* Refine / Expand+Refine / Expand action sub-row (Gap 33 / P1-BBOX-UI).
          Each button queues the real `refine_bboxes` job, scoped to this
          word — see the module doc comment for the mode mapping and why
          the old "Crop" button was renamed "Expand". */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Actions</p>
        <div className="flex flex-wrap gap-1.5">
          <Button
            data-testid="bbox-refine-button"
            variant="secondary"
            size="sm"
            disabled={busy || !refineAvailable || refineJobRunningElsewhere}
            title={refineDisabledTitle ?? "Snap bbox to ink boundary"}
            onClick={() => {
              startRefine("refine", REFINE_PADDING_PX, "Refining bbox…");
            }}
          >
            Refine
          </Button>
          <Button
            data-testid="bbox-expand-refine-button"
            variant="secondary"
            size="sm"
            disabled={busy || !refineAvailable || refineJobRunningElsewhere}
            title={refineDisabledTitle ?? "Expand bbox, then snap to ink boundary"}
            onClick={() => {
              startRefine("expand_then_refine", REFINE_PADDING_PX, "Expanding + refining bbox…");
            }}
          >
            Expand + Refine
          </Button>
          <Button
            data-testid="bbox-expand-button"
            variant="secondary"
            size="sm"
            disabled={busy || !refineAvailable || refineJobRunningElsewhere}
            title={
              refineDisabledTitle ??
              `Expand bbox by ${String(EXPAND_ONLY_PADDING_PX)}px on each side (no refine)`
            }
            onClick={() => {
              startRefine("expand_only", EXPAND_ONLY_PADDING_PX, "Expanding bbox…");
            }}
          >
            Expand
          </Button>
        </div>
        {refineDisabledTitle && (
          <p data-testid="bbox-refine-unavailable" className="text-[10px] text-ink-4 italic">
            {refineDisabledTitle}
          </p>
        )}
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
