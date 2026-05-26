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
//   - When pd_book_tools.text.normalize unavailable: shows disabled message
//
// Chrome backed by pd-ui's Radix Dialog suite. Radix provides native focus trap +
// Escape handling — no manual Esc handler or hand-rolled backdrop needed.
//
// Testids: ocr-config-modal (DialogContent), normalize-gt-matching-checkbox,
//          normalize-plaintext-checkbox, normalize-profile-select,
//          auto-rotate-checkbox, auto-rotate-method-select,
//          ocr-config-close-button, ocr-config-done-button,
//          ocr-config-save-error (error banner when POST /api/ocr-config/auto-rotate fails)
//          (stub: ocr-detection-model-select, ocr-recognition-model-select,
//           ocr-hf-revision-input, ocr-rescan-models-button,
//           ocr-config-cancel-button, ocr-config-apply-button)

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@concavetrillion/pd-ui/primitives";

type AutoRotateMethod = "gt-best-match" | "layout" | "auto";

// Minimal in-line fetch wrappers to avoid adding openapi-ts-generated fetch
// before #276 completes the client setup.
async function fetchNormalizeAvailable(): Promise<boolean> {
  const resp = await fetch("/api/normalize/available");
  if (!resp.ok) return false;
  const data = await resp.json();
  return Boolean(data.available);
}

async function fetchOcrConfig(): Promise<{
  auto_rotate_available: boolean;
  auto_rotate_on_load: boolean;
  auto_rotate_method: AutoRotateMethod;
} | null> {
  const resp = await fetch("/api/ocr-config");
  if (!resp.ok) return null;
  const data = await resp.json();
  return {
    auto_rotate_available: Boolean(data.auto_rotate_available),
    auto_rotate_on_load: Boolean(data.auto_rotate_on_load ?? true),
    auto_rotate_method: (data.auto_rotate_method ?? "auto") as AutoRotateMethod,
  };
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
 * ``normalize_profile``).  When ``pd_book_tools.text.normalize`` is absent,
 * the section is disabled with a tooltip message.
 *
 * Backed by pd-ui's Radix Dialog suite (native focus trap + Escape handling).
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

  // Probe pd_book_tools normalize availability.
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
  const autoRotateOnLoad = ocrConfig?.auto_rotate_on_load ?? true;
  const autoRotateMethod: AutoRotateMethod = ocrConfig?.auto_rotate_method ?? "auto";

  async function handleAutoRotateOnLoadChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSaveError(null);
    try {
      await postAutoRotateConfig({
        auto_rotate_on_load: e.target.checked,
        auto_rotate_method: autoRotateMethod,
      });
      void refetchOcrConfig();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save auto-rotate settings.");
    }
  }

  async function handleAutoRotateMethodChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSaveError(null);
    try {
      await postAutoRotateConfig({
        auto_rotate_on_load: autoRotateOnLoad,
        auto_rotate_method: e.target.value as AutoRotateMethod,
      });
      void refetchOcrConfig();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save auto-rotate settings.");
    }
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
    "Requires pd-book-tools with text.normalize module. " +
    "Update pd-book-tools to enable these options.";

  return (
    // NOTE: Escape is handled natively by Radix Dialog — no manual Esc handler needed.
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      {/* DialogContent auto-composes DialogPortal + DialogOverlay (pd-ui convention).
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
                Requires pd-book-tools with text.normalize module. Update pd-book-tools to enable
                these options.
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
                Requires pd-book-tools with rotation module. Update pd-book-tools to enable
                auto-rotation.
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
                    : "Requires pd-book-tools rotation module to enable auto-rotation."
                }
              >
                <input
                  type="checkbox"
                  data-testid="auto-rotate-checkbox"
                  checked={autoRotateOnLoad}
                  disabled={!autoRotateAvailable}
                  onChange={(e) => {
                    void handleAutoRotateOnLoadChange(e);
                  }}
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
                  onChange={(e) => {
                    void handleAutoRotateMethodChange(e);
                  }}
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
        </div>

        {/* Stub elements for driver-contract §2.3 — model selection not yet implemented */}
        <div style={{ display: "none" }}>
          <select
            data-testid="ocr-detection-model-select"
            data-testid-stub="true"
            aria-label="Detection model (stub)"
          />
          <select
            data-testid="ocr-recognition-model-select"
            data-testid-stub="true"
            aria-label="Recognition model (stub)"
          />
          <input
            data-testid="ocr-hf-revision-input"
            data-testid-stub="true"
            aria-label="HF revision (stub)"
          />
          <button
            data-testid="ocr-rescan-models-button"
            data-testid-stub="true"
            aria-label="Rescan models (stub)"
          >
            Rescan
          </button>
          <button
            data-testid="ocr-config-cancel-button"
            data-testid-stub="true"
            aria-label="Cancel (stub)"
          >
            Cancel
          </button>
          <button
            data-testid="ocr-config-apply-button"
            data-testid-stub="true"
            aria-label="Apply (stub)"
          >
            Apply
          </button>
        </div>

        {/* Footer */}
        <DialogFooter className="px-4 py-3 border-t border-border-1 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-bg-raised hover:opacity-80 rounded"
            data-testid="ocr-config-done-button"
          >
            Done
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
