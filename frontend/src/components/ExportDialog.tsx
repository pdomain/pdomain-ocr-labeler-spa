// ExportDialog.tsx — Export dialog for DocTR training data export (#227)
// Spec: docs/specs/2026-05-12-export-design.md
//
// Sections:
//   - Scope radio (current page | all validated pages)
//   - Style filter checkboxes (from GET .../export/styles; "All" toggle)
//   - Component filter dropdown
//   - Output mode flags (mutually exclusive)
//   - Run history (client-only, resets on close)
//   - Export button -> POST -> 202 -> useJobProgress SSE inline
//   - Cancel while running
//
// Chrome backed by pdomain-ui's Radix Dialog suite. Radix provides native focus trap +
// Escape handling. Backdrop click is blocked while a job is running via
// onInteractOutside.
//
// driver-contract testids:
//   export-dialog                  — DialogContent wrapper
//   export-scope-current           — scope radio: current page
//   export-scope-all               — scope radio: all validated pages
//   export-style-all-checkbox      — "All (no style filter)" checkbox
//   export-style-checkbox-{key}    — per-style checkbox
//   export-button                  — run export button
//   export-results                 — container for run history rows
//   export-close-button            — Close button

import { useEffect, useState } from "react";
import { useJobProgress } from "../hooks/useJobProgress";
import { useLabelVocabulary } from "../hooks/useLabelVocabulary";
import { fetchTrainerInstalled, launchTrainer } from "./ExportDialogUtils";
import type { components } from "../api/types";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@pdomain/pdomain-ui/primitives";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ExportScope = components["schemas"]["ExportScope"];

interface RunHistoryEntry {
  id: string;
  scope: ExportScope;
  styleFilters: string[];
  pagesExported: number;
  timestamp: string;
  // Stats breakdown from the terminal SSE event (Lane E3). Undefined for
  // older events that predate the breakdown. Explicit ``| undefined`` so the
  // tsconfig's exactOptionalPropertyTypes accepts a missing-stat assignment.
  wordsDetection?: number | undefined;
  wordsRecognition?: number | undefined;
  pagesSkippedNotValidated?: number | undefined;
}

interface ExportDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Project ID for building API URLs. */
  projectId: string;
  /** Current page index (0-based). Passed through to ExportRequest when scope=current. */
  currentPageIndex?: number;
  /** Called when Close is clicked. */
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// ExportDialog
// ---------------------------------------------------------------------------

export function ExportDialog({
  open,
  projectId,
  currentPageIndex = 0,
  onClose,
}: ExportDialogProps) {
  // --- Canonical word-component vocabulary from the backend ---
  const { wordComponents } = useLabelVocabulary();

  // --- Scope ---
  const [scope, setScope] = useState<ExportScope>("all_validated");

  // --- Style filters ---
  const [availableStyles, setAvailableStyles] = useState<string[]>([]);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);
  const [stylesLoading, setStylesLoading] = useState(false);

  // --- Component filter ---
  const [componentFilter, setComponentFilter] = useState<string>("");

  // --- Output mode (mutually exclusive flags) ---
  type OutputMode = "both" | "detection" | "recognition" | "classification";
  const [outputMode, setOutputMode] = useState<OutputMode>("both");

  // --- Job / progress ---
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const progress = useJobProgress(jobId);

  // --- Run history (client-only) ---
  const [history, setHistory] = useState<RunHistoryEntry[]>([]);

  // --- Trainer availability (polled once when the dialog opens) ---
  const [trainerInstalled, setTrainerInstalled] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetchTrainerInstalled()
      .then(setTrainerInstalled)
      .catch(() => setTrainerInstalled(false));
  }, [open]);

  // Fetch available styles when scope=all_validated and dialog is open
  useEffect(() => {
    if (!open || scope !== "all_validated") return;
    let cancelled = false;
    setStylesLoading(true);
    fetch(`/api/projects/${encodeURIComponent(projectId)}/export/styles`)
      .then((r) => r.json())
      .then((data: string[]) => {
        if (!cancelled) {
          setAvailableStyles(data);
          // Default: all styles selected (empty means "all")
          setSelectedStyles([]);
        }
      })
      .catch(() => {
        if (!cancelled) setAvailableStyles([]);
      })
      .finally(() => {
        if (!cancelled) setStylesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, scope, projectId]);

  // Watch job progress for terminal events
  useEffect(() => {
    if (!progress) return;
    if (progress.status === "complete") {
      setRunning(false);
      setHistory((prev) => [
        ...prev,
        {
          id: progress.job_id,
          scope,
          styleFilters: selectedStyles,
          pagesExported: progress.progress?.total ?? 0,
          timestamp: new Date().toLocaleTimeString(),
          wordsDetection: progress.words_exported_detection,
          wordsRecognition: progress.words_exported_recognition,
          pagesSkippedNotValidated: progress.pages_skipped_not_validated,
        },
      ]);
      setJobId(null);
    } else if (progress.status === "error") {
      setRunning(false);
      setError(progress.error_message ?? "Export failed");
      setJobId(null);
    }
  }, [progress, scope, selectedStyles]);

  // --- Style filter helpers ---
  const allStylesSelected = selectedStyles.length === 0;

  function toggleAllStyles() {
    setSelectedStyles([]);
  }

  function toggleStyle(style: string) {
    if (selectedStyles.includes(style)) {
      setSelectedStyles(selectedStyles.filter((s) => s !== style));
    } else {
      setSelectedStyles([...selectedStyles, style]);
    }
  }

  // --- Export ---
  async function handleExport() {
    setError(null);
    setRunning(true);

    const body = {
      scope,
      page_index: scope === "current" ? currentPageIndex : null,
      style_filters: selectedStyles,
      component_filter: componentFilter || null,
      include_classification: outputMode === "classification",
      detection_only: outputMode === "detection",
      recognition_only: outputMode === "recognition",
      normalize_recognition_labels: false,
    };

    try {
      const resp = await fetch(`/api/projects/${encodeURIComponent(projectId)}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const text = await resp.text();
        setError(`Export failed (${resp.status}): ${text}`);
        setRunning(false);
        return;
      }

      const data: { job_id: string } = await resp.json();
      setJobId(data.job_id);
    } catch (e) {
      setError(String(e));
      setRunning(false);
    }
  }

  async function handleCancel() {
    if (!jobId) return;
    await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" },
    );
    setRunning(false);
    setJobId(null);
  }

  // --- Derived UI strings ---
  const progressMsg =
    progress && running
      ? `Exporting page ${progress.progress?.current ?? 0} of ${progress.progress?.total ?? "?"}`
      : null;

  return (
    // NOTE: Escape is handled natively by Radix Dialog. Backdrop click is blocked
    // while running via onInteractOutside — no manual Esc handler or hand-rolled
    // backdrop div needed.
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      {/* DialogContent auto-composes DialogPortal + DialogOverlay (pdomain-ui convention).
          The .dialog-overlay CSS in primitives.css provides the backdrop. */}
      <DialogContent
        data-testid="export-dialog"
        className="rounded-lg border border-border-2 w-full max-w-lg mx-4 flex flex-col overflow-hidden max-h-[90vh] p-0 gap-0"
        onInteractOutside={(e) => {
          // Block backdrop dismissal while a job is running.
          if (running) e.preventDefault();
        }}
      >
        {/* Header */}
        <DialogHeader className="flex flex-row items-center justify-between px-4 py-3 border-b border-border-1 bg-bg-raised shrink-0">
          <DialogTitle className="text-sm font-semibold text-ink-1">
            Export Training Data
          </DialogTitle>
          <DialogClose
            onClick={onClose}
            disabled={running}
            aria-label="Close export dialog"
            className="px-2 py-1.5 text-lg text-ink-3 hover:text-ink-1 hover:bg-bg-raised rounded transition-colors disabled:opacity-40"
          >
            x
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
          {/* Scope */}
          <fieldset>
            <legend className="text-xs font-semibold text-ink-2 mb-1">Scope</legend>
            <div className="flex gap-4">
              <label className="flex items-center gap-1.5 text-sm text-ink-2 cursor-pointer">
                <input
                  type="radio"
                  data-testid="export-scope-all"
                  name="export-scope"
                  value="all_validated"
                  checked={scope === "all_validated"}
                  onChange={() => {
                    setScope("all_validated");
                  }}
                />
                All Validated Pages
              </label>
              <label className="flex items-center gap-1.5 text-sm text-ink-2 cursor-pointer">
                <input
                  type="radio"
                  data-testid="export-scope-current"
                  name="export-scope"
                  value="current"
                  checked={scope === "current"}
                  onChange={() => {
                    setScope("current");
                  }}
                />
                Current Page
              </label>
            </div>
          </fieldset>

          {/* Style filters */}
          {scope === "all_validated" && (
            <fieldset>
              <legend className="text-xs font-semibold text-ink-2 mb-1">
                Style Filter
                {stylesLoading && (
                  <span className="ml-2 text-xs text-ink-4 font-normal">Loading...</span>
                )}
              </legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <label className="flex items-center gap-1.5 text-sm text-ink-2 cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid="export-style-all-checkbox"
                    checked={allStylesSelected}
                    onChange={toggleAllStyles}
                  />
                  All (no filter)
                </label>
                {availableStyles.map((style) => (
                  <label
                    key={style}
                    className="flex items-center gap-1.5 text-sm text-ink-2 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      data-testid={`export-style-checkbox-${style}`}
                      checked={selectedStyles.includes(style)}
                      onChange={() => {
                        toggleStyle(style);
                      }}
                    />
                    {style}
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {/* Component filter */}
          <div>
            <label
              htmlFor="export-component-filter"
              className="text-xs font-semibold text-ink-2 mb-1 block"
            >
              Component Filter
            </label>
            <select
              id="export-component-filter"
              value={componentFilter}
              onChange={(e) => {
                setComponentFilter(e.target.value);
              }}
              className="text-sm border border-border-1 rounded px-2 py-1 bg-bg-sunk text-ink-2"
            >
              <option key="" value="">
                (none)
              </option>
              {wordComponents.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Output mode */}
          <fieldset>
            <legend className="text-xs font-semibold text-ink-2 mb-1">Output Mode</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {(
                [
                  ["both", "Detection + Recognition"],
                  ["detection", "Detection only"],
                  ["recognition", "Recognition only"],
                  ["classification", "Classification"],
                ] as const
              ).map(([mode, label]) => (
                <label
                  key={mode}
                  className="flex items-center gap-1.5 text-sm text-ink-2 cursor-pointer"
                >
                  <input
                    type="radio"
                    name="export-output-mode"
                    value={mode}
                    checked={outputMode === mode}
                    onChange={() => {
                      setOutputMode(mode);
                    }}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          {/* Error */}
          {error && (
            <div
              className="text-sm text-status-mismatch border border-status-mismatch/40 rounded px-3 py-2"
              style={{
                background: "color-mix(in srgb, var(--status-mismatch) 12%, var(--bg-surface))",
              }}
            >
              {error}
            </div>
          )}

          {/* Progress */}
          {progressMsg && (
            <div
              className="text-sm text-accent border border-accent/40 rounded px-3 py-2"
              style={{ background: "color-mix(in srgb, var(--status-ocr) 8%, var(--bg-surface))" }}
            >
              {progressMsg}
            </div>
          )}

          {/* Run history */}
          {history.length > 0 && (
            <div data-testid="export-results">
              <div className="text-xs font-semibold text-ink-2 mb-1">Run History</div>
              <div className="flex flex-col gap-1">
                {history.map((entry) => (
                  <div
                    key={entry.id}
                    className="text-xs text-ink-2 bg-bg-raised border border-border-1 rounded px-2 py-1"
                  >
                    <span className="font-medium">
                      {entry.scope === "current" ? "Current page" : "All validated"}
                    </span>
                    {entry.styleFilters.length > 0 && (
                      <span className="ml-2 text-ink-3">
                        styles: {entry.styleFilters.join(", ")}
                      </span>
                    )}
                    <span className="ml-2 text-ink-4">{entry.pagesExported} pages</span>
                    {entry.wordsDetection !== undefined && (
                      <span
                        className="ml-2 text-ink-4"
                        data-testid={`export-stats-detection-${entry.id}`}
                      >
                        det: {entry.wordsDetection} words
                      </span>
                    )}
                    {entry.wordsRecognition !== undefined && (
                      <span
                        className="ml-2 text-ink-4"
                        data-testid={`export-stats-recognition-${entry.id}`}
                      >
                        rec: {entry.wordsRecognition} words
                      </span>
                    )}
                    {entry.pagesSkippedNotValidated !== undefined &&
                      entry.pagesSkippedNotValidated > 0 && (
                        <span
                          className="ml-2 text-status-fuzzy"
                          data-testid={`export-stats-skipped-${entry.id}`}
                        >
                          {entry.pagesSkippedNotValidated} skipped (not validated)
                        </span>
                      )}
                    <span className="ml-2 text-ink-4">{entry.timestamp}</span>
                    {trainerInstalled && (
                      <button
                        data-testid="export-send-to-trainer"
                        className="ml-3 px-2 py-0.5 text-xs rounded border border-accent text-accent hover:bg-accent hover:text-accent-ink transition-colors"
                        onClick={() => {
                          void launchTrainer().then((result) => {
                            if (result?.kind === "opened" && result.url) {
                              window.open(result.url, "_blank", "noopener");
                            }
                          });
                        }}
                      >
                        Send to trainer
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <DialogFooter className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border-1 bg-bg-raised shrink-0">
          {running ? (
            <button
              onClick={() => {
                void handleCancel();
              }}
              className="px-3 py-1.5 text-sm rounded border border-status-fuzzy bg-bg-surface text-status-fuzzy hover:bg-bg-raised transition-colors"
            >
              Cancel
            </button>
          ) : (
            <button
              data-testid="export-button"
              onClick={() => {
                void handleExport();
              }}
              className="px-3 py-1.5 text-sm rounded bg-accent text-accent-ink hover:opacity-90 transition-opacity"
            >
              Export
            </button>
          )}
          <button
            data-testid="export-close-button"
            onClick={onClose}
            disabled={running}
            className="px-3 py-1.5 text-sm rounded border border-border-2 bg-bg-surface text-ink-2 hover:bg-bg-raised transition-colors disabled:opacity-40"
          >
            Close
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
