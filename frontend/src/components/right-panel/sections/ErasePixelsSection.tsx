// ErasePixelsSection.tsx — P3.c hi-fi rebuild (Gap 36).
// Spec: docs/plans/hifi-gaps-plan.md Slice P3.c.
//
// On open we run the existing `/api/refine/available` probe (via
// `useRefineAvailable`).  If the engine is not available we show a single
// muted "Not available for this word" message.  Otherwise we render the
// full erase UI:
//
//   1. EraseCanvas (Konva) — tool switcher, brush-size slider, draw overlay.
//   2. Ops list — scrollable, per-op remove button, empty-state hint.
//   3. Commit footer — Apply erases (primary) + Clear all (link button).
//
// The component is self-contained — it owns the local list of `EraseOp`s
// and the active tool / brush size.  When the user clicks Apply, we pass
// the ops list to the `onApply` callback (parent owns the mutation wiring).
//
// data-testids:
//   erase-pixels-section       — outer wrapper (legacy contract, retained)
//   erase-not-available        — fallback when probe returns available:false
//   erase-canvas               — Konva stage root (from EraseCanvas)
//   erase-tool-{brush|lasso|rect}
//   erase-brush-size
//   erase-ops-list             — scrollable ops list container
//   erase-op-{N}-remove        — remove button per op
//   erase-apply                — primary commit button
//   erase-clear                — clear-all link button

import { useState } from "react";
import { Button } from "../../ui/button";
import { useRefineAvailable } from "../../../hooks/useRefineAvailable";
import { EraseCanvas, describeOp, type EraseOp, type EraseTool } from "./EraseCanvas";

export interface ErasePixelsSectionProps {
  /**
   * Test/storybook override.  When provided, we skip the `useRefineAvailable`
   * probe and use this value directly.  When undefined, we consult the probe.
   */
  backendAvailable?: boolean;
  /** Called when Apply is clicked.  Receives the ops list. */
  onApply?: (ops: EraseOp[]) => Promise<void> | void;
  /** URL of the word image slice (forwarded to EraseCanvas). */
  imageUrl?: string;
}

const DEFAULT_BRUSH = 8;

export function ErasePixelsSection({
  backendAvailable,
  onApply,
  imageUrl,
}: ErasePixelsSectionProps) {
  // Probe — only consulted when no explicit override was passed.  We always
  // call the hook (rules of hooks) but ignore its value when `backendAvailable`
  // is set.
  const probe = useRefineAvailable();
  const probeAvailable = probe.data?.available ?? false;
  const probeLoading = probe.isLoading;
  const available = backendAvailable ?? probeAvailable;
  // We show the loading state only when the caller didn't pre-decide and the
  // probe hasn't resolved yet.
  const showLoading = backendAvailable === undefined && probeLoading;

  const [tool, setTool] = useState<EraseTool>("brush");
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH);
  const [ops, setOps] = useState<EraseOp[]>([]);
  const [busy, setBusy] = useState(false);

  function handleOpCommit(op: EraseOp) {
    setOps((prev) => [...prev, op]);
  }

  function handleRemoveOp(index: number) {
    setOps((prev) => prev.filter((_, i) => i !== index));
  }

  function handleClear() {
    setOps([]);
  }

  async function handleApply() {
    if (!onApply || ops.length === 0) return;
    setBusy(true);
    try {
      await onApply(ops);
      // Clear after successful apply so the user can start a fresh batch.
      setOps([]);
    } finally {
      setBusy(false);
    }
  }

  // ─── Render: probe loading ───────────────────────────────────────────────

  if (showLoading) {
    return (
      <div data-testid="erase-pixels-section" className="flex flex-col gap-2 py-1">
        <p className="text-[11px] text-ink-3 italic">Checking erase availability…</p>
      </div>
    );
  }

  // ─── Render: not available ───────────────────────────────────────────────

  if (!available) {
    return (
      <div data-testid="erase-pixels-section" className="flex flex-col gap-2 py-1">
        <p data-testid="erase-not-available" className="text-[11px] text-ink-3 italic">
          Not available for this word.
        </p>
      </div>
    );
  }

  // ─── Render: full erase UI ───────────────────────────────────────────────

  return (
    <div data-testid="erase-pixels-section" className="flex flex-col gap-3 py-1">
      <EraseCanvas
        imageUrl={imageUrl}
        tool={tool}
        onToolChange={setTool}
        brushSize={brushSize}
        onBrushSizeChange={setBrushSize}
        ops={ops}
        onOpCommit={handleOpCommit}
      />

      {/* Ops list */}
      <div
        data-testid="erase-ops-list"
        className="flex flex-col gap-1 max-h-32 overflow-y-auto rounded border border-border-2 bg-sunk p-1"
      >
        {ops.length === 0 ? (
          <p className="text-[11px] text-ink-3 italic p-1">Draw to mark pixels for erasing</p>
        ) : (
          ops.map((op, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-2 px-1 py-0.5 rounded hover:bg-raised"
            >
              <span className="text-[11px] text-ink-2 truncate">{describeOp(op, i)}</span>
              <button
                data-testid={`erase-op-${i}-remove`}
                onClick={() => handleRemoveOp(i)}
                aria-label={`Remove op ${i + 1}`}
                className="text-ink-3 hover:text-status-mismatch text-sm px-1"
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      {/* Commit footer */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-border-2">
        <button
          data-testid="erase-clear"
          onClick={handleClear}
          disabled={ops.length === 0}
          className="text-[11px] text-ink-3 hover:text-ink-1 underline disabled:opacity-40 disabled:no-underline"
        >
          Clear all
        </button>
        <Button
          data-testid="erase-apply"
          variant="primary"
          size="sm"
          onClick={() => void handleApply()}
          disabled={ops.length === 0 || busy}
        >
          {busy ? "Applying…" : "Apply erases"}
        </Button>
      </div>
    </div>
  );
}
