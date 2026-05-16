// SourceFolderDialog.tsx — file-browser-style dialog for setting the projects source folder.
// Issue #294 (spec 22 §10 — real source-folder picker).
//
// driver-contract testids (docs/architecture/13-driver-contract.md §2.2):
//   source-folder-dialog              — dialog root
//   source-folder-current-path-label  — read-only display of the currently browsed path
//   source-folder-path-input          — text input for typing a path directly
//   source-folder-home-button         — resets current path to "~"
//   source-folder-up-button           — navigates up one directory level
//   source-folder-open-typed-button   — sets current path to whatever is in path-input
//   source-folder-use-current-button  — copies current-path-label into path-input
//   source-folder-apply-button        — POSTs current path and closes
//   source-folder-cancel-button       — closes without API call
//
// Directory listing: GET /api/fs/ls?path=<currentPath>
//   Each entry row testid: data-testid="fs-ls-entry-{name}"

import { useState, useEffect } from "react";

interface FsEntry {
  name: string;
  is_dir: boolean;
}

interface SourceFolderDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog should close (cancel or after successful apply). */
  onClose: () => void;
}

/** Compute the parent path of `p` using string manipulation (no filesystem call). */
function parentPath(p: string): string {
  // Expand leading "~" to a placeholder so split works uniformly.
  const expanded = p.startsWith("~") ? "/home/user" + p.slice(1) : p;
  const parts = expanded.split("/").filter(Boolean);
  if (parts.length > 1) {
    return "/" + parts.slice(0, -1).join("/");
  }
  return "/";
}

/**
 * File-browser-style modal dialog for setting the projects source root.
 *
 * Maintains two pieces of state:
 *   currentPath — the "browsed" path shown in the current-path-label.
 *   inputPath   — the text typed in the path-input.
 *
 * On apply, POSTs { path: currentPath } to POST /api/projects/source-root.
 * Directory listing is fetched from GET /api/fs/ls?path=<currentPath>.
 * Renders nothing when `open` is false.
 */
export function SourceFolderDialog({ open, onClose }: SourceFolderDialogProps) {
  const [currentPath, setCurrentPath] = useState<string>("~");
  const [inputPath, setInputPath] = useState<string>("~");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [listLoading, setListLoading] = useState(false);

  // Fetch directory listing whenever currentPath changes (and dialog is open).
  useEffect(() => {
    if (!open) return;
    setListLoading(true);
    const params = new URLSearchParams({ path: currentPath });
    fetch(`/api/fs/ls?${params.toString()}`)
      .then((r) => r.json())
      .then((data: { entries?: FsEntry[] }) => {
        setEntries(data.entries ?? []);
        setListLoading(false);
      })
      .catch(() => {
        setEntries([]);
        setListLoading(false);
      });
  }, [currentPath, open]);

  if (!open) return null;

  // --- navigation handlers (client-side only) ----------------------------------

  function handleHome() {
    setCurrentPath("~");
    setInputPath("~");
  }

  function handleUp() {
    const parent = parentPath(currentPath);
    setCurrentPath(parent);
    setInputPath(parent);
  }

  function handleOpenTyped() {
    setCurrentPath(inputPath);
  }

  function handleUseCurrent() {
    setInputPath(currentPath);
  }

  function handleEntryClick(name: string) {
    const sep = currentPath.endsWith("/") ? "" : "/";
    const next = currentPath + sep + name;
    setCurrentPath(next);
    setInputPath(next);
  }

  // --- apply / cancel ----------------------------------------------------------

  async function handleApply() {
    if (loading) return;
    setError(null);
    try {
      setLoading(true);
      const resp = await fetch("/api/projects/source-root", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: currentPath }),
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
        setLoading(false);
        setError(msg);
        return;
      }
      // Success — clear loading before onClose so state update lands while
      // the component is still mounted (onClose unmounts the dialog).
      setLoading(false);
      setCurrentPath("~");
      setInputPath("~");
      setError(null);
      onClose();
    } catch (e) {
      setLoading(false);
      setError(String(e));
    }
  }

  function handleCancel() {
    if (loading) return;
    setCurrentPath("~");
    setInputPath("~");
    setError(null);
    onClose();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      // Mod+Enter in path-input triggers apply (spec §8 — Apply source folder).
      e.preventDefault();
      void handleApply();
    } else if (e.key === "Enter") {
      // Enter in path-input triggers open-typed (spec §2.2 hotkey note).
      e.preventDefault();
      handleOpenTyped();
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
        className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">Set Source Folder</h2>

        {/* Current path display */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Current path
          </label>
          <div
            data-testid="source-folder-current-path-label"
            className="px-3 py-1.5 text-sm bg-gray-50 border border-gray-200 rounded font-mono break-all"
          >
            {currentPath}
          </div>
        </div>

        {/* Navigation buttons row */}
        <div className="flex gap-2">
          <button
            type="button"
            data-testid="source-folder-home-button"
            onClick={handleHome}
            disabled={loading}
            title="Go to home (~)"
            className="flex-1 px-2 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Home
          </button>
          <button
            type="button"
            data-testid="source-folder-up-button"
            onClick={handleUp}
            disabled={loading}
            title="Go up one directory"
            className="flex-1 px-2 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Up
          </button>
        </div>

        {/* Directory listing */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Subdirectories
          </label>
          <div className="border border-gray-200 rounded max-h-40 overflow-y-auto bg-gray-50">
            {listLoading ? (
              <div data-testid="fs-ls-loading" className="px-3 py-2 text-xs text-gray-400 italic">
                Loading…
              </div>
            ) : entries.length === 0 ? (
              <div className="px-3 py-2 text-xs text-gray-400 italic">No subdirectories</div>
            ) : (
              entries.map((e) => (
                <button
                  key={e.name}
                  type="button"
                  data-testid={`fs-ls-entry-${e.name}`}
                  onClick={() => handleEntryClick(e.name)}
                  disabled={loading}
                  className="w-full text-left px-3 py-1.5 text-sm font-mono hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50"
                >
                  {e.name}/
                </button>
              ))
            )}
          </div>
        </div>

        {/* Path input */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Type a path
          </label>
          <input
            type="text"
            data-testid="source-folder-path-input"
            aria-label="Source folder path"
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder="/path/to/projects"
            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            autoFocus
          />
        </div>

        {/* Open-typed / Use-current row */}
        <div className="flex gap-2">
          <button
            type="button"
            data-testid="source-folder-open-typed-button"
            onClick={handleOpenTyped}
            disabled={loading}
            title="Navigate to the typed path"
            className="flex-1 px-2 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Open Typed Path
          </button>
          <button
            type="button"
            data-testid="source-folder-use-current-button"
            onClick={handleUseCurrent}
            disabled={loading}
            title="Copy current path into input"
            className="flex-1 px-2 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Use Current
          </button>
        </div>

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Cancel / Apply */}
        <div className="flex justify-end gap-2 pt-1">
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
            data-testid="source-folder-apply-button"
            onClick={() => void handleApply()}
            disabled={loading}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Setting…" : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
