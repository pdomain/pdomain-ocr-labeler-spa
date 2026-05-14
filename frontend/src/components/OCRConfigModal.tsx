// OCRConfigModal.tsx — OCR configuration modal with text-normalization and auto-rotation sections.
// Spec: docs/specs/2026-05-12-text-normalization-design.md §Toggle UI
// Spec: docs/specs/2026-05-12-auto-rotation-design.md §OCR config additions
// Issues #261, #264
//
// Sections:
//   - Text normalization: normalize-gt-matching-checkbox, normalize-plaintext-checkbox,
//     normalize-profile-select (greyed out in v1, only "ascii" available)
//   - Auto-rotation: auto-rotate-checkbox, auto-rotate-method-select
//     (disabled when auto_rotate_available=false)
//   - When pd_book_tools.text.normalize unavailable: shows disabled message
//
// Testids: ocr-config-modal, normalize-gt-matching-checkbox, normalize-plaintext-checkbox,
//          normalize-profile-select, auto-rotate-checkbox, auto-rotate-method-select

import { useQuery } from "@tanstack/react-query";

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

async function postAutoRotateConfig(settings: {
  auto_rotate_on_load: boolean;
  auto_rotate_method: AutoRotateMethod;
}): Promise<void> {
  await fetch("/api/ocr-config/auto-rotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export interface NormalizeSettings {
  normalize_for_gt_matching: boolean;
  normalize_plaintext_tabs: boolean;
  normalize_profile: string;
}

export interface AutoRotateSettings {
  auto_rotate_on_load: boolean;
  auto_rotate_method: AutoRotateMethod;
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
 * Issue #261 testid contract:
 *   - ``ocr-config-modal``
 *   - ``normalize-gt-matching-checkbox``
 *   - ``normalize-plaintext-checkbox``
 *   - ``normalize-profile-select``
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
    await postAutoRotateConfig({
      auto_rotate_on_load: e.target.checked,
      auto_rotate_method: autoRotateMethod,
    });
    void refetchOcrConfig();
  }

  async function handleAutoRotateMethodChange(e: React.ChangeEvent<HTMLSelectElement>) {
    await postAutoRotateConfig({
      auto_rotate_on_load: autoRotateOnLoad,
      auto_rotate_method: e.target.value as AutoRotateMethod,
    });
    void refetchOcrConfig();
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

  if (!open) return null;

  const unavailableTitle =
    "Requires pd-book-tools with text.normalize module. " +
    "Update pd-book-tools to enable these options.";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="OCR configuration"
      data-testid="ocr-config-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900 text-base">OCR Configuration</h2>
          <button
            type="button"
            aria-label="Close"
            className="text-gray-400 hover:text-gray-600 rounded p-1"
            onClick={onClose}
            data-testid="ocr-config-close-button"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-4 overflow-y-auto flex-1">
          {/* Text normalization section */}
          <section aria-labelledby="normalize-section-heading">
            <h3 id="normalize-section-heading" className="text-sm font-medium text-gray-700 mb-2">
              Text normalization
            </h3>

            {!normalizeAvailable && (
              <p
                className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 mb-3"
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
                  normalizeAvailable ? "text-gray-800" : "text-gray-400"
                }`}
                title={normalizeAvailable ? undefined : unavailableTitle}
              >
                <input
                  type="checkbox"
                  data-testid="normalize-gt-matching-checkbox"
                  checked={settings.normalize_for_gt_matching}
                  disabled={!normalizeAvailable}
                  onChange={handleGtMatchingChange}
                  className="accent-blue-600"
                />
                Normalize for GT matching (long-s, ligatures → ASCII)
              </label>

              {/* Plaintext tabs toggle */}
              <label
                className={`flex items-center gap-2 text-sm ${
                  normalizeAvailable ? "text-gray-800" : "text-gray-400"
                }`}
                title={normalizeAvailable ? undefined : unavailableTitle}
              >
                <input
                  type="checkbox"
                  data-testid="normalize-plaintext-checkbox"
                  checked={settings.normalize_plaintext_tabs}
                  disabled={!normalizeAvailable}
                  onChange={handlePlaintextChange}
                  className="accent-blue-600"
                />
                Normalize plaintext tab content
              </label>

              {/* Profile select — greyed out in v1 (only "ascii" available) */}
              <div
                className={`flex items-center gap-2 text-sm ${
                  normalizeAvailable ? "text-gray-800" : "text-gray-400"
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
                  className="border border-gray-200 rounded text-xs px-1 py-0.5 bg-gray-50 cursor-not-allowed"
                  aria-label="Normalization profile"
                >
                  <option value="ascii">ascii</option>
                </select>
                <span className="text-xs text-gray-400">(v1: ascii only)</span>
              </div>
            </div>
          </section>

          {/* Auto-rotation section */}
          <section aria-labelledby="auto-rotate-section-heading" className="mt-4">
            <h3 id="auto-rotate-section-heading" className="text-sm font-medium text-gray-700 mb-2">
              Auto-rotation
            </h3>

            {!autoRotateAvailable && (
              <p
                className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 mb-3"
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
                  autoRotateAvailable ? "text-gray-800" : "text-gray-400"
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
                  onChange={handleAutoRotateOnLoadChange}
                  className="accent-blue-600"
                />
                Auto-rotate pages on load
              </label>

              {/* Method select */}
              <div
                className={`flex items-center gap-2 text-sm ${
                  autoRotateAvailable ? "text-gray-800" : "text-gray-400"
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
                  className={`border border-gray-200 rounded text-xs px-1 py-0.5 ${
                    autoRotateAvailable && autoRotateOnLoad
                      ? "bg-white"
                      : "bg-gray-50 cursor-not-allowed"
                  }`}
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

        {/* Footer */}
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
        <div className="px-4 py-3 border-t border-gray-200 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded"
            data-testid="ocr-config-done-button"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

export default OCRConfigModal;
