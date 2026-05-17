// WordActionRows.tsx — Merge/Split/Delete/Crop rows for the word-edit dialog (#211)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      docs/architecture/07-word-edit-dialog.md §4.3 (split), §4.2 (merge), §4.4 (crop)
//
// All mutations fire synchronous POSTs and call onRefetch on success.
// The dialog stays open after merge/split/delete (legacy behaviour).
//
// driver-contract testids:
//   dialog-merge-prev-button   — Merge with previous word
//   dialog-merge-next-button   — Merge with next word
//   dialog-split-h-button      — Split horizontally (at click-marker x-fraction)
//   dialog-split-v-button      — Split vertically
//   dialog-delete-word-button  — Delete word
//   dialog-crop-above-button   — Crop above
//   dialog-crop-below-button   — Crop below
//   dialog-crop-left-button    — Crop left
//   dialog-crop-right-button   — Crop right
//   dialog-crop-padding-input  — Padding slider

import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WordActionCallbacks {
  /** Called with "prev" or "next" */
  onMerge?: ((direction: "prev" | "next") => Promise<void>) | undefined;
  /** Called with split fraction (0–1) and axis ("h" | "v") */
  onSplit?: ((fraction: number, axis: "h" | "v") => Promise<void>) | undefined;
  /** Called on word delete */
  onDelete?: (() => Promise<void>) | undefined;
  /** Called with padding pixels and direction */
  onCrop?:
    | ((direction: "above" | "below" | "left" | "right", padding: number) => Promise<void>)
    | undefined;
}

interface WordActionRowsProps extends WordActionCallbacks {
  /** Whether the previous word is available for merge. */
  hasPrev: boolean;
  /** Whether the next word is available for merge. */
  hasNext: boolean;
  /** Click-marker x-fraction (0–1) used for split operations. */
  splitFraction?: number;
}

// ---------------------------------------------------------------------------
// Small helper: a compact action button
// ---------------------------------------------------------------------------

function ActionBtn({
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
          ? "border-border-1 bg-bg-raised text-ink-4 cursor-default"
          : danger
            ? "border-status-mismatch bg-bg-surface text-status-mismatch hover:bg-bg-raised"
            : "border-border-2 bg-bg-surface text-ink-2 hover:bg-bg-raised",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// RowLabel
// ---------------------------------------------------------------------------

function RowLabel({ label }: { label: string }) {
  return <span className="text-xs text-ink-3 w-14 shrink-0 font-medium">{label}</span>;
}

// ---------------------------------------------------------------------------
// WordActionRows
// ---------------------------------------------------------------------------

export function WordActionRows({
  hasPrev,
  hasNext,
  splitFraction = 0.5,
  onMerge,
  onSplit,
  onDelete,
  onCrop,
}: WordActionRowsProps) {
  const [cropPadding, setCropPadding] = useState<number>(2);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(key: string, fn?: () => Promise<void>) {
    if (!fn || busy) return;
    setBusy(key);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-1.5 w-full pt-1 border-t border-border-1">
      {/* Merge row */}
      <div className="flex items-center gap-1.5">
        <RowLabel label="Merge" />
        <ActionBtn
          testId="dialog-merge-prev-button"
          label="← Prev"
          disabled={!hasPrev || busy !== null}
          onClick={() => {
            void run("merge-prev", () => onMerge?.("prev") ?? Promise.resolve());
          }}
        />
        <ActionBtn
          testId="dialog-merge-next-button"
          label="Next →"
          disabled={!hasNext || busy !== null}
          onClick={() => {
            void run("merge-next", () => onMerge?.("next") ?? Promise.resolve());
          }}
        />
      </div>

      {/* Split row */}
      <div className="flex items-center gap-1.5">
        <RowLabel label="Split" />
        <ActionBtn
          testId="dialog-split-h-button"
          label="H"
          disabled={busy !== null}
          onClick={() => {
            void run("split-h", () => onSplit?.(splitFraction, "h") ?? Promise.resolve());
          }}
        />
        <ActionBtn
          testId="dialog-split-v-button"
          label="V"
          disabled={busy !== null}
          onClick={() => {
            void run("split-v", () => onSplit?.(splitFraction, "v") ?? Promise.resolve());
          }}
        />
        <span className="text-xs text-ink-4 ml-1">at {Math.round(splitFraction * 100)}%</span>
      </div>

      {/* Delete row */}
      <div className="flex items-center gap-1.5">
        <RowLabel label="Delete" />
        <ActionBtn
          testId="dialog-delete-word-button"
          label="Delete"
          danger
          disabled={busy !== null}
          onClick={() => {
            void run("delete", () => onDelete?.() ?? Promise.resolve());
          }}
        />
      </div>

      {/* Crop row */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <RowLabel label="Crop" />
        <ActionBtn
          testId="dialog-crop-above-button"
          label="↑ Above"
          disabled={busy !== null}
          onClick={() =>
            void run("crop-above", () => onCrop?.("above", cropPadding) ?? Promise.resolve())
          }
        />
        <ActionBtn
          testId="dialog-crop-below-button"
          label="↓ Below"
          disabled={busy !== null}
          onClick={() =>
            void run("crop-below", () => onCrop?.("below", cropPadding) ?? Promise.resolve())
          }
        />
        <ActionBtn
          testId="dialog-crop-left-button"
          label="← Left"
          disabled={busy !== null}
          onClick={() => {
            void run("crop-left", () => onCrop?.("left", cropPadding) ?? Promise.resolve());
          }}
        />
        <ActionBtn
          testId="dialog-crop-right-button"
          label="Right →"
          disabled={busy !== null}
          onClick={() =>
            void run("crop-right", () => onCrop?.("right", cropPadding) ?? Promise.resolve())
          }
        />
        <label className="flex items-center gap-1 text-xs text-ink-3">
          pad
          <input
            data-testid="dialog-crop-padding-input"
            type="range"
            min={0}
            max={20}
            value={cropPadding}
            onChange={(e) => {
              setCropPadding(Number(e.target.value));
            }}
            className="w-16"
          />
          {cropPadding}px
        </label>
      </div>
    </div>
  );
}

export type { WordActionRowsProps };
