// WordRefineNudgeRows.tsx — Refine row + Nudge accumulator + Apply/Reset row (#212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      specs/07-word-edit-dialog.md §3.6 (refine), §3.7 (nudge), §3.8 (apply/reset)
//
// Refine buttons fire immediately (onRefine / onExpandRefine).
// Nudge is accumulated locally; Apply emits onApply(pendingNudge, refineAfter).
// Reset clears pending nudge and erase rects.
//
// driver-contract testids:
//   dialog-refine-button          — Refine
//   dialog-expand-refine-button   — Expand + Refine
//   dialog-nudge-left-minus       — move left edge inward
//   dialog-nudge-left-plus        — expand left
//   dialog-nudge-right-minus      — shrink right
//   dialog-nudge-right-plus       — expand right
//   dialog-nudge-top-minus        — shrink top
//   dialog-nudge-top-plus         — expand top
//   dialog-nudge-bottom-minus     — shrink bottom
//   dialog-nudge-bottom-plus      — expand bottom
//   dialog-nudge-display          — live delta summary "L:0 R:0 T:0 B:0"
//   dialog-reset-button           — Reset pending nudge
//   dialog-apply-button           — Apply (no refine)
//   dialog-apply-refine-button    — Apply + Refine

import { useState, useImperativeHandle, forwardRef } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PendingNudge {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface WordRefineNudgeRowsHandle {
  /** Accumulate a nudge step (positive or negative pixels). */
  addNudge(edge: "left" | "right" | "top" | "bottom", delta: number): void;
  /** Reset pending nudge to zero. */
  resetNudge(): void;
  /** Return current pending nudge (for Apply&Close). */
  getPendingNudge(): PendingNudge;
}

interface WordRefineNudgeRowsProps {
  /** Step size per nudge click (px). Default: 5 per spec §3.7. */
  stepPx?: number;
  /** Called when Refine is clicked. */
  onRefine?: () => Promise<void>;
  /** Called when Expand+Refine is clicked. */
  onExpandRefine?: () => Promise<void>;
  /**
   * Called when Apply or Apply+Refine is clicked.
   * The component passes the accumulated nudge and whether refine is requested.
   */
  onApply?: (nudge: PendingNudge, refineAfter: boolean) => Promise<void>;
  /** Called when Reset is clicked (clears nudge locally; parent may clear erase rects). */
  onReset?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SmallBtn({
  testId,
  label,
  onClick,
  disabled = false,
  danger = false,
}: {
  testId: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className={[
        "px-2 py-1 text-xs rounded border transition-colors",
        disabled
          ? "border-gray-200 bg-gray-50 text-gray-300 cursor-default"
          : danger
            ? "border-red-300 bg-white text-red-600 hover:bg-red-50"
            : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function RowLabel({ label }: { label: string }) {
  return <span className="text-xs text-gray-500 w-14 shrink-0 font-medium">{label}</span>;
}

// ---------------------------------------------------------------------------
// WordRefineNudgeRows
// ---------------------------------------------------------------------------

export const WordRefineNudgeRows = forwardRef<WordRefineNudgeRowsHandle, WordRefineNudgeRowsProps>(
  function WordRefineNudgeRows({ stepPx = 5, onRefine, onExpandRefine, onApply, onReset }, ref) {
    const zero: PendingNudge = { left: 0, right: 0, top: 0, bottom: 0 };
    const [pending, setPending] = useState<PendingNudge>(zero);
    const [busy, setBusy] = useState<string | null>(null);

    const hasPending =
      pending.left !== 0 || pending.right !== 0 || pending.top !== 0 || pending.bottom !== 0;

    // Expose imperative API for keyboard-driven nudge
    useImperativeHandle(ref, () => ({
      addNudge(edge, delta) {
        setPending((prev) => ({ ...prev, [edge]: prev[edge] + delta }));
      },
      resetNudge() {
        setPending(zero);
      },
      getPendingNudge() {
        return pending;
      },
    }));

    function addNudge(edge: keyof PendingNudge, delta: number) {
      setPending((prev) => ({ ...prev, [edge]: prev[edge] + delta }));
    }

    function handleReset() {
      setPending(zero);
      onReset?.();
    }

    async function run(key: string, fn: () => Promise<void>) {
      if (busy) return;
      setBusy(key);
      try {
        await fn();
      } finally {
        setBusy(null);
      }
    }

    async function handleApply(refineAfter: boolean) {
      await run(`apply-${refineAfter ? "refine" : "plain"}`, async () => {
        await onApply?.(pending, refineAfter);
        setPending(zero);
      });
    }

    const step = stepPx;

    return (
      <div className="flex flex-col gap-1.5 w-full pt-1">
        {/* Refine row */}
        <div className="flex items-center gap-1.5">
          <RowLabel label="Refine" />
          <SmallBtn
            testId="dialog-refine-button"
            label="Refine"
            disabled={busy !== null}
            onClick={() => run("refine", () => onRefine?.() ?? Promise.resolve())}
          />
          <SmallBtn
            testId="dialog-expand-refine-button"
            label="Expand+Refine"
            disabled={busy !== null}
            onClick={() => run("expand-refine", () => onExpandRefine?.() ?? Promise.resolve())}
          />
        </div>

        {/* Nudge grid */}
        <div className="flex items-start gap-1.5">
          <RowLabel label="Nudge" />
          <div className="flex flex-col gap-1">
            {/* Top edge */}
            <div className="flex gap-1 justify-center">
              <SmallBtn
                testId="dialog-nudge-top-minus"
                label="T−"
                onClick={() => addNudge("top", -step)}
              />
              <SmallBtn
                testId="dialog-nudge-top-plus"
                label="T+"
                onClick={() => addNudge("top", step)}
              />
            </div>
            {/* Middle row: left + right edges */}
            <div className="flex gap-1">
              <SmallBtn
                testId="dialog-nudge-left-minus"
                label="L−"
                onClick={() => addNudge("left", -step)}
              />
              <SmallBtn
                testId="dialog-nudge-left-plus"
                label="L+"
                onClick={() => addNudge("left", step)}
              />
              <span className="px-1 text-xs text-gray-300 self-center">·</span>
              <SmallBtn
                testId="dialog-nudge-right-minus"
                label="R−"
                onClick={() => addNudge("right", -step)}
              />
              <SmallBtn
                testId="dialog-nudge-right-plus"
                label="R+"
                onClick={() => addNudge("right", step)}
              />
            </div>
            {/* Bottom edge */}
            <div className="flex gap-1 justify-center">
              <SmallBtn
                testId="dialog-nudge-bottom-minus"
                label="B−"
                onClick={() => addNudge("bottom", -step)}
              />
              <SmallBtn
                testId="dialog-nudge-bottom-plus"
                label="B+"
                onClick={() => addNudge("bottom", step)}
              />
            </div>
            {/* Delta display */}
            <div
              data-testid="dialog-nudge-display"
              className="text-xs text-gray-500 text-center font-mono"
            >
              L:{pending.left} R:{pending.right} T:{pending.top} B:{pending.bottom}
            </div>
          </div>
        </div>

        {/* Apply / Reset row */}
        <div className="flex items-center gap-1.5">
          <RowLabel label="" />
          <SmallBtn
            testId="dialog-reset-button"
            label="Reset"
            disabled={!hasPending || busy !== null}
            onClick={handleReset}
          />
          <SmallBtn
            testId="dialog-apply-button"
            label="Apply"
            disabled={!hasPending || busy !== null}
            onClick={() => handleApply(false)}
          />
          <SmallBtn
            testId="dialog-apply-refine-button"
            label="Apply+Refine"
            disabled={!hasPending || busy !== null}
            onClick={() => handleApply(true)}
          />
        </div>
      </div>
    );
  },
);
