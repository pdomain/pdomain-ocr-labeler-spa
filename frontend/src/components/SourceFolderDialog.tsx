// SourceFolderDialog.tsx — dialog for setting the projects source folder.
// Issue #294 (spec 22 §10 — real source-folder picker).
//
// Replaces the `display:none` stub block in HeaderBar.tsx. Calls
// POST /api/projects/source-root on confirm.
//
// driver-contract testids (docs/architecture/13-driver-contract.md):
//   source-folder-dialog          — outer wrapper (the dialog root)
//   source-folder-input           — text input for the folder path
//   source-folder-confirm-button  — confirm / apply button
//   source-folder-cancel-button   — cancel button

import { useState } from "react";

interface SourceFolderDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog should close (cancel or after successful confirm). */
  onClose: () => void;
}

/**
 * Simple modal dialog for setting the projects source root.
 *
 * On confirm, calls POST /api/projects/source-root with the typed path.
 * Shows a loading state while the request is in flight.
 * Renders nothing when `open` is false.
 */
export function SourceFolderDialog({ open, onClose }: SourceFolderDialogProps) {
  const [path, setPath] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleConfirm() {
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      const resp = await fetch("/api/projects/source-root", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        let msg = `Request failed (${resp.status})`;
        try {
          const body = JSON.parse(text) as { message?: string };
          if (body.message) msg = body.message;
        } catch {
          if (text) msg = text;
        }
        setError(msg);
        setLoading(false);
        return;
      }
      // Success — close the dialog and reset state.
      setPath("");
      setError(null);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    if (loading) return;
    setPath("");
    setError(null);
    onClose();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleConfirm();
    } else if (e.key === "Escape") {
      handleCancel();
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Set source folder"
      data-testid="source-folder-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) handleCancel();
      }}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-sm w-full mx-4 p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">Set Source Folder</h2>
        <p className="text-sm text-gray-600">
          Enter the absolute path to the folder containing your projects.
        </p>

        <input
          type="text"
          data-testid="source-folder-input"
          aria-label="Source folder path"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="/path/to/projects"
          className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          autoFocus
        />

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            data-testid="source-folder-cancel-button"
            onClick={handleCancel}
            disabled={loading}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="source-folder-confirm-button"
            onClick={() => void handleConfirm()}
            disabled={loading || path.trim() === ""}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Setting…" : "Set Folder"}
          </button>
        </div>
      </div>
    </div>
  );
}
