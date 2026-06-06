// OCRConfigModal.tsx — OCR configuration modal with text-normalization and auto-rotation sections.
// Spec: docs/specs/2026-05-12-text-normalization-design.md §Toggle UI
// Spec: docs/specs/2026-05-12-auto-rotation-design.md §OCR config additions
// Issues #261, #264, #447
//
// Sections:
//   - Text normalization: normalize-gt-matching-checkbox, normalize-plaintext-checkbox,
//     normalize-profile-select (greyed out in v1, only "ascii" available)
//   - Auto-rotation: auto-rotate-checkbox, auto-rotate-method-select
//     (disabled when auto_rotate_available=false)
//   - When pdomain_book_tools.text.normalize unavailable: shows disabled message
//
// Chrome backed by pdomain-ui's Radix Dialog suite. Radix provides native focus trap +
// Escape handling — no manual Esc handler or hand-rolled backdrop needed.
//
// Testids: ocr-config-modal (DialogContent), normalize-gt-matching-checkbox,
//          normalize-plaintext-checkbox, normalize-profile-select,
//          auto-rotate-checkbox, auto-rotate-method-select,
//          ocr-config-close-button, ocr-config-done-button,
//          ocr-config-save-error (error banner when a POST fails)
//          OCR models (Lane C / Task C3 — real controls, no longer stubbed):
//            ocr-detection-model-select, ocr-recognition-model-select,
//            ocr-hf-revision-input, ocr-rescan-models-button, ocr-config-apply-button.
//          ocr-config-cancel-button — footer button that discards pending
//          (un-applied) changes and closes. Model picks commit via Apply;
//          auto-rotate commits via Done. Every close path clears pending state.

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@pdomain/pdomain-ui/primitives";

type AutoRotateMethod = "gt-best-match" | "layout" | "auto";

// Minimal in-line fetch wrappers to avoid adding openapi-ts-generated fetch
// before #276 completes the client setup.
async function fetchNormalizeAvailable(): Promise<boolean> {
  const resp = await fetch("/api/normalize/available");
  if (!resp.ok) return false;
  const data = await resp.json();
  return Boolean(data.available);
}

/** One detection/recognition model option from ``GET /api/ocr-config``. */
interface OcrModelOption {
  key: string;
  label: string;
  source: string;
  is_default: boolean;
}

interface OcrConfigSnapshot {
  auto_rotate_available: boolean;
  auto_rotate_on_load: boolean;
  auto_rotate_method: AutoRotateMethod;
  // C3: model-selection fields. Absent in some mocked responses → degrade to
  // empty option lists / "stock" defaults so the selects render without error.
  detection_options: OcrModelOption[];
  recognition_options: OcrModelOption[];
  selected_detection: string;
  selected_recognition: string;
  hf_pinned_revision: string | null;
}

async function fetchOcrConfig(): Promise<OcrConfigSnapshot | null> {
  const resp = await fetch("/api/ocr-config");
  if (!resp.ok) return null;
  const data = await resp.json();
  return {
    auto_rotate_available: Boolean(data.auto_rotate_available),
    auto_rotate_on_load: Boolean(data.auto_rotate_on_load ?? true),
    auto_rotate_method: (data.auto_rotate_method ?? "auto") as AutoRotateMethod,
    detection_options: Array.isArray(data.detection_options)
      ? (data.detection_options as OcrModelOption[])
      : [],
    recognition_options: Array.isArray(data.recognition_options)
      ? (data.recognition_options as OcrModelOption[])
      : [],
    selected_detection:
      typeof data.selected_detection === "string" ? data.selected_detection : "stock",
    selected_recognition:
      typeof data.selected_recognition === "string" ? data.selected_recognition : "stock",
    hf_pinned_revision:
      typeof data.hf_pinned_revision === "string" ? data.hf_pinned_revision : null,
  };
}

// C3: POST helpers for model selection + rescan. Both throw on !ok with the
// server-provided message so failures can be surfaced via the existing
// ocr-config-save-error banner.
async function postOcrModels(body: {
  detection_key: string;
  recognition_key: string;
  hf_pinned_revision: string | null;
}): Promise<void> {
  const resp = await fetch("/api/ocr-config/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `Server error ${resp.status.toString()}`);
  }
}

async function postOcrRescan(): Promise<void> {
  const resp = await fetch("/api/ocr-config/rescan", { method: "POST" });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `Server error ${resp.status.toString()}`);
  }
}

// Fix #447: check response.ok and throw with server text on failure.
async function postAutoRotateConfig(settings: {
  auto_rotate_on_load: boolean;
  auto_rotate_method: AutoRotateMethod;
}): Promise<void> {
  const resp = await fetch("/api/ocr-config/auto-rotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `Server error ${resp.status.toString()}`);
  }
}

export interface NormalizeSettings {
  normalize_for_gt_matching: boolean;
  normalize_plaintext_tabs: boolean;
  normalize_profile: string;
}

interface OCRConfigModalProps {
  open: boolean;
  /** Current normalize settings from AppConfig. */
  normalizeSettings?: NormalizeSettings;
  /** Called when the user changes normalize settings. */
  onNormalizeChange?: (settings: NormalizeSettings) => void;
  onClose: () => void;
}

/**
 * OCR configuration modal.
 *
 * Renders the "Text normalization" section.  Toggle states mirror
 * AppConfig fields (``normalize_for_gt_matching``, ``normalize_plaintext_tabs``,
 * ``normalize_profile``).  When ``pdomain_book_tools.text.normalize`` is absent,
 * the section is disabled with a tooltip message.
 *
 * Backed by pdomain-ui's Radix Dialog suite (native focus trap + Escape handling).
 *
 * Issue #261 testid contract:
 *   - ``ocr-config-modal``  (DialogContent)
 *   - ``normalize-gt-matching-checkbox``
 *   - ``normalize-plaintext-checkbox``
 *   - ``normalize-profile-select``
 *
 * Issue #447 testid contract:
 *   - ``ocr-config-save-error``  (error banner on POST failure)
 */
export function OCRConfigModal({
  open,
  normalizeSettings,
  onNormalizeChange,
  onClose,
}: OCRConfigModalProps) {
  const defaults: NormalizeSettings = {
    normalize_for_gt_matching: false,
    normalize_plaintext_tabs: false,
    normalize_profile: "ascii",
  };
  const settings = normalizeSettings ?? defaults;

  // Fix #447: track save errors from POST /api/ocr-config/auto-rotate.
  const [saveError, setSaveError] = useState<string | null>(null);

  // Probe pdomain_book_tools normalize availability.
  const { data: normalizeAvailable = false } = useQuery({
    queryKey: ["normalize-available"],
    queryFn: fetchNormalizeAvailable,
    staleTime: 60_000, // 1 minute — module presence doesn't change at runtime
    enabled: open,
  });

  // Fetch OCR config (auto-rotate settings + availability).
  const { data: ocrConfig, refetch: refetchOcrConfig } = useQuery({
    queryKey: ["ocr-config-auto-rotate"],
    queryFn: fetchOcrConfig,
    staleTime: 30_000,
    enabled: open,
  });
  const autoRotateAvailable = ocrConfig?.auto_rotate_available ?? false;

  // S6.3: Snapshot / pending state for auto-rotate settings.
  // Changes are captured into pendingAutoRotate (not POSTed immediately);
  // POST fires only on Done. Cancel discards and closes.
  const [pendingAutoRotate, setPendingAutoRotate] = useState<{
    auto_rotate_on_load: boolean;
    auto_rotate_method: AutoRotateMethod;
  } | null>(null);

  // Capture snapshot when modal opens (open: false → true).
  const prevOpenRef = useRef(open);
  useEffect(() => {
    if (open && !prevOpenRef.current && ocrConfig) {
      setPendingAutoRotate({
        auto_rotate_on_load: ocrConfig.auto_rotate_on_load,
        auto_rotate_method: ocrConfig.auto_rotate_method,
      });
    }
    if (!open) {
      setPendingAutoRotate(null);
      setSaveError(null);
      // Discard un-applied model selections on every close path (Cancel,
      // Done, Close, Escape) so a reopen reflects the server snapshot, not a
      // stale pending pick the user never committed via Apply.
      setPendingDetection(null);
      setPendingRecognition(null);
      setPendingRevision(null);
    }
    prevOpenRef.current = open;
  }, [open, ocrConfig]);

  // Also capture snapshot once ocrConfig loads (if modal is already open
  // before the query resolves).
  const ocrConfigLoadedRef = useRef(false);
  useEffect(() => {
    if (open && ocrConfig && !ocrConfigLoadedRef.current) {
      ocrConfigLoadedRef.current = true;
      setPendingAutoRotate((prev) =>
        prev === null
          ? {
              auto_rotate_on_load: ocrConfig.auto_rotate_on_load,
              auto_rotate_method: ocrConfig.auto_rotate_method,
            }
          : prev,
      );
    }
    if (!open) {
      ocrConfigLoadedRef.current = false;
    }
  }, [open, ocrConfig]);

  // Effective auto-rotate values (pending takes precedence over server snapshot).
  const autoRotateOnLoad =
    pendingAutoRotate?.auto_rotate_on_load ?? ocrConfig?.auto_rotate_on_load ?? true;
  const autoRotateMethod: AutoRotateMethod =
    pendingAutoRotate?.auto_rotate_method ?? ocrConfig?.auto_rotate_method ?? "auto";

  // C3: model-selection state. Pending values are local so the user can pick a
  // model + revision and commit with Apply. They re-sync to the server snapshot
  // whenever the config query resolves/refetches.
  const detectionOptions = ocrConfig?.detection_options ?? [];
  const recognitionOptions = ocrConfig?.recognition_options ?? [];
  const [pendingDetection, setPendingDetection] = useState<string | null>(null);
  const [pendingRecognition, setPendingRecognition] = useState<string | null>(null);
  const [pendingRevision, setPendingRevision] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [rescanning, setRescanning] = useState(false);

  const detectionValue = pendingDetection ?? ocrConfig?.selected_detection ?? "stock";
  const recognitionValue = pendingRecognition ?? ocrConfig?.selected_recognition ?? "stock";
  const revisionValue = pendingRevision ?? ocrConfig?.hf_pinned_revision ?? "";

  async function handleApplyModels() {
    setSaveError(null);
    setApplying(true);
    try {
      await postOcrModels({
        detection_key: detectionValue,
        recognition_key: recognitionValue,
        hf_pinned_revision: revisionValue.trim() === "" ? null : revisionValue.trim(),
      });
      setPendingDetection(null);
      setPendingRecognition(null);
      setPendingRevision(null);
      void refetchOcrConfig();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to apply model selection.");
    } finally {
      setApplying(false);
    }
  }

  async function handleRescanModels() {
    setSaveError(null);
    setRescanning(true);
    try {
      await postOcrRescan();
      setPendingDetection(null);
      setPendingRecognition(null);
      setPendingRevision(null);
      void refetchOcrConfig();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to rescan models.");
    } finally {
      setRescanning(false);
    }
  }

  // S6.3: onChange handlers update pending state only (no immediate POST).
  function handleAutoRotateOnLoadChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSaveError(null);
    setPendingAutoRotate((prev) => ({
      auto_rotate_on_load: e.target.checked,
      auto_rotate_method: prev?.auto_rotate_method ?? autoRotateMethod,
    }));
  }

  function handleAutoRotateMethodChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSaveError(null);
    setPendingAutoRotate((prev) => ({
      auto_rotate_on_load: prev?.auto_rotate_on_load ?? autoRotateOnLoad,
      auto_rotate_method: e.target.value as AutoRotateMethod,
    }));
  }

  // S6.3: Cancel — discard pending state and close (no POST).
  function handleCancel() {
    setPendingAutoRotate(null);
    setSaveError(null);
    onClose();
  }

  // Determine whether auto-rotate settings changed from server snapshot.
  const autoRotateDirty =
    pendingAutoRotate !== null &&
    (pendingAutoRotate.auto_rotate_on_load !== (ocrConfig?.auto_rotate_on_load ?? true) ||
      pendingAutoRotate.auto_rotate_method !== (ocrConfig?.auto_rotate_method ?? "auto"));

  // S6.3: Done — POST pending auto-rotate if dirty, then close.
  function handleDone() {
    if (!autoRotateDirty || !pendingAutoRotate) {
      onClose();
      return;
    }
    setSaveError(null);
    postAutoRotateConfig(pendingAutoRotate)
      .then(() => {
        void refetchOcrConfig();
        onClose();
      })
      .catch((err: unknown) => {
        setSaveError(err instanceof Error ? err.message : "Failed to save auto-rotate settings.");
      });
  }

  function handleGtMatchingChange(e: React.ChangeEvent<HTMLInputElement>) {
    onNormalizeChange?.({
      ...settings,
      normalize_for_gt_matching: e.target.checked,
    });
  }

  function handlePlaintextChange(e: React.ChangeEvent<HTMLInputElement>) {
    onNormalizeChange?.({
      ...settings,
      normalize_plaintext_tabs: e.target.checked,
    });
  }

  function handleProfileChange(e: React.ChangeEvent<HTMLSelectElement>) {
    onNormalizeChange?.({
      ...settings,
      normalize_profile: e.target.value,
    });
  }

  const unavailableTitle =
    "Requires pdomain-book-tools with text.normalize module. " +
    "Update pdomain-book-tools to enable these options.";

  return (
    // NOTE: Escape is handled natively by Radix Dialog — no manual Esc handler needed.
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      {/* DialogContent auto-composes DialogPortal + DialogOverlay (pdomain-ui convention).
          The .dialog-overlay CSS in primitives.css provides the backdrop. */}
      <DialogContent
        data-testid="ocr-config-modal"
        className="rounded-lg border border-border-2 max-w-lg w-full mx-4 max-h-[80vh] flex flex-col p-0 gap-0"
      >
        {/* Header */}
        <DialogHeader className="flex flex-row items-center justify-between px-4 py-3 border-b border-border-1">
          <DialogTitle className="font-semibold text-ink-1 text-base">
            OCR Configuration
          </DialogTitle>
          <DialogClose
            aria-label="Close"
            className="text-ink-4 hover:text-ink-2 rounded p-1"
            data-testid="ocr-config-close-button"
          >
            ×
          </DialogClose>
        </DialogHeader>

        {/* Body */}
        <div className="px-4 py-4 overflow-y-auto flex-1">
          {/* Fix #447: save-error banner — shown when POST /api/ocr-config/auto-rotate fails. */}
          {saveError !== null && (
            <p
              role="alert"
              data-testid="ocr-config-save-error"
              className="text-xs rounded px-2 py-1 mb-3"
              style={{
                color: "var(--status-bad)",
                background: "color-mix(in srgb, var(--status-bad) 8%, var(--bg-surface))",
              }}
            >
              Failed to save: {saveError}
            </p>
          )}

          {/* Text normalization section */}
          <section aria-labelledby="normalize-section-heading">
            <h3 id="normalize-section-heading" className="text-sm font-medium text-ink-2 mb-2">
              Text normalization
            </h3>

            {!normalizeAvailable && (
              <p
                className="text-xs rounded px-2 py-1 mb-3"
                style={{
                  color: "var(--status-fuzzy)",
                  background: "color-mix(in srgb, var(--status-fuzzy) 8%, var(--bg-surface))",
                }}
                data-testid="normalize-unavailable-message"
              >
                Requires pdomain-book-tools with text.normalize module. Update pdomain-book-tools to
                enable these options.
              </p>
            )}

            <div className="space-y-2">
              {/* GT matching toggle */}
              <label
                className={`flex items-center gap-2 text-sm ${
                  normalizeAvailable ? "text-ink-1" : "text-ink-4"
                }`}
                title={normalizeAvailable ? undefined : unavailableTitle}
              >
                <input
                  type="checkbox"
                  data-testid="normalize-gt-matching-checkbox"
                  checked={settings.normalize_for_gt_matching}
                  disabled={!normalizeAvailable}
                  onChange={handleGtMatchingChange}
                  className="accent-accent"
                />
                Normalize for GT matching (long-s, ligatures → ASCII)
              </label>

              {/* Plaintext tabs toggle */}
              <label
                className={`flex items-center gap-2 text-sm ${
                  normalizeAvailable ? "text-ink-1" : "text-ink-4"
                }`}
                title={normalizeAvailable ? undefined : unavailableTitle}
              >
                <input
                  type="checkbox"
                  data-testid="normalize-plaintext-checkbox"
                  checked={settings.normalize_plaintext_tabs}
                  disabled={!normalizeAvailable}
                  onChange={handlePlaintextChange}
                  className="accent-accent"
                />
                Normalize plaintext tab content
              </label>

              {/* Profile select — greyed out in v1 (only "ascii" available) */}
              <div
                className={`flex items-center gap-2 text-sm ${
                  normalizeAvailable ? "text-ink-1" : "text-ink-4"
                }`}
                title={
                  normalizeAvailable ? "Only 'ascii' profile available in v1" : unavailableTitle
                }
              >
                <label htmlFor="normalize-profile-select" className="shrink-0">
                  Profile:
                </label>
                <select
                  id="normalize-profile-select"
                  data-testid="normalize-profile-select"
                  value={settings.normalize_profile}
                  disabled={true}
                  onChange={handleProfileChange}
                  className="border border-border-1 rounded text-xs px-1 py-0.5 bg-bg-sunk cursor-not-allowed"
                  aria-label="Normalization profile"
                >
                  <option value="ascii">ascii</option>
                </select>
                <span className="text-xs text-ink-4">(v1: ascii only)</span>
              </div>
            </div>
          </section>

          {/* Auto-rotation section */}
          <section aria-labelledby="auto-rotate-section-heading" className="mt-4">
            <h3 id="auto-rotate-section-heading" className="text-sm font-medium text-ink-2 mb-2">
              Auto-rotation
            </h3>

            {!autoRotateAvailable && (
              <p
                className="text-xs rounded px-2 py-1 mb-3"
                style={{
                  color: "var(--status-fuzzy)",
                  background: "color-mix(in srgb, var(--status-fuzzy) 8%, var(--bg-surface))",
                }}
                data-testid="auto-rotate-unavailable-message"
              >
                Requires pdomain-book-tools with rotation module. Update pdomain-book-tools to
                enable auto-rotation.
              </p>
            )}

            <div className="space-y-2">
              {/* Auto-rotate on load toggle */}
              <label
                className={`flex items-center gap-2 text-sm ${
                  autoRotateAvailable ? "text-ink-1" : "text-ink-4"
                }`}
                title={
                  autoRotateAvailable
                    ? undefined
                    : "Requires pdomain-book-tools rotation module to enable auto-rotation."
                }
              >
                <input
                  type="checkbox"
                  data-testid="auto-rotate-checkbox"
                  checked={autoRotateOnLoad}
                  disabled={!autoRotateAvailable}
                  onChange={handleAutoRotateOnLoadChange}
                  className="accent-accent"
                />
                Auto-rotate pages on load
              </label>

              {/* Method select */}
              <div
                className={`flex items-center gap-2 text-sm ${
                  autoRotateAvailable ? "text-ink-1" : "text-ink-4"
                }`}
              >
                <label htmlFor="auto-rotate-method-select" className="shrink-0">
                  Method:
                </label>
                <select
                  id="auto-rotate-method-select"
                  data-testid="auto-rotate-method-select"
                  value={autoRotateMethod}
                  disabled={!autoRotateAvailable || !autoRotateOnLoad}
                  onChange={handleAutoRotateMethodChange}
                  className="border border-border-1 rounded text-xs px-1 py-0.5 bg-bg-sunk"
                  aria-label="Auto-rotation method"
                >
                  <option value="auto">auto</option>
                  <option value="gt-best-match">gt-best-match</option>
                  <option value="layout">layout</option>
                </select>
              </div>
            </div>
          </section>

          {/* OCR model selection section — Lane C / Task C3.
              Real detection/recognition selects + HF revision input + Apply /
              Rescan, bound to GET /api/ocr-config, POST /api/ocr-config/models,
              POST /api/ocr-config/rescan. (Was a display:none stub.) */}
          <section aria-labelledby="ocr-models-section-heading" className="mt-4">
            <h3 id="ocr-models-section-heading" className="text-sm font-medium text-ink-2 mb-2">
              OCR models
            </h3>

            <div className="space-y-2">
              {/* Detection model select */}
              <div className="flex items-center gap-2 text-sm text-ink-1">
                <label htmlFor="ocr-detection-model-select" className="shrink-0 w-28">
                  Detection:
                </label>
                <select
                  id="ocr-detection-model-select"
                  data-testid="ocr-detection-model-select"
                  value={detectionValue}
                  onChange={(e) => {
                    setPendingDetection(e.target.value);
                  }}
                  className="border border-border-1 rounded text-xs px-1 py-0.5 bg-bg-sunk flex-1"
                  aria-label="Detection model"
                >
                  {detectionOptions.length === 0 ? (
                    <option value={detectionValue}>{detectionValue}</option>
                  ) : (
                    detectionOptions.map((opt) => (
                      <option key={opt.key} value={opt.key}>
                        {opt.label}
                      </option>
                    ))
                  )}
                </select>
              </div>

              {/* Recognition model select */}
              <div className="flex items-center gap-2 text-sm text-ink-1">
                <label htmlFor="ocr-recognition-model-select" className="shrink-0 w-28">
                  Recognition:
                </label>
                <select
                  id="ocr-recognition-model-select"
                  data-testid="ocr-recognition-model-select"
                  value={recognitionValue}
                  onChange={(e) => {
                    setPendingRecognition(e.target.value);
                  }}
                  className="border border-border-1 rounded text-xs px-1 py-0.5 bg-bg-sunk flex-1"
                  aria-label="Recognition model"
                >
                  {recognitionOptions.length === 0 ? (
                    <option value={recognitionValue}>{recognitionValue}</option>
                  ) : (
                    recognitionOptions.map((opt) => (
                      <option key={opt.key} value={opt.key}>
                        {opt.label}
                      </option>
                    ))
                  )}
                </select>
              </div>

              {/* HF pinned-revision input */}
              <div className="flex items-center gap-2 text-sm text-ink-1">
                <label htmlFor="ocr-hf-revision-input" className="shrink-0 w-28">
                  HF revision:
                </label>
                <input
                  id="ocr-hf-revision-input"
                  data-testid="ocr-hf-revision-input"
                  type="text"
                  value={revisionValue}
                  placeholder="(latest)"
                  onChange={(e) => {
                    setPendingRevision(e.target.value);
                  }}
                  className="border border-border-1 rounded text-xs px-1 py-0.5 bg-bg-sunk flex-1"
                  aria-label="Hugging Face pinned revision"
                />
              </div>

              {/* Apply + Rescan */}
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  data-testid="ocr-config-apply-button"
                  disabled={applying}
                  onClick={() => {
                    void handleApplyModels();
                  }}
                  className="px-3 py-1 text-xs rounded border border-border-2 bg-bg-raised text-accent hover:border-accent disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Apply OCR model selection"
                >
                  Apply
                </button>
                <button
                  type="button"
                  data-testid="ocr-rescan-models-button"
                  disabled={rescanning}
                  onClick={() => {
                    void handleRescanModels();
                  }}
                  className="px-3 py-1 text-xs rounded border border-border-2 bg-bg-raised text-ink-2 hover:text-ink-1 disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Rescan available OCR models"
                >
                  Rescan
                </button>
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <DialogFooter className="px-4 py-3 border-t border-border-1 flex items-center justify-end gap-2">
          {/* S6.3: Cancel — discards pending changes and closes without POSTing */}
          <button
            type="button"
            onClick={handleCancel}
            className="px-4 py-1.5 text-sm border border-border-2 bg-bg-raised hover:opacity-80 rounded text-ink-2"
            data-testid="ocr-config-cancel-button"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDone}
            className="px-4 py-1.5 text-sm bg-accent text-accent-ink hover:opacity-80 rounded"
            data-testid="ocr-config-done-button"
          >
            Done
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
