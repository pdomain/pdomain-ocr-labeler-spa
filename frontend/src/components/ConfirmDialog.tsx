// ConfirmDialog.tsx — lightweight confirm dialog for destructive hotkey actions.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Destructive keys confirm
// Issue #236
//
// Used by global hotkeys (Mod+L Load Page, Mod+G Rematch GT) and any other
// action that needs "Are you sure?" before executing.
//
// data-testids:
//   confirm-dialog         — outer overlay
//   confirm-dialog-confirm — confirm button
//   confirm-dialog-cancel  — cancel button

interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Message shown to the user, e.g. "This will discard unsaved changes." */
  message: string;
  /** Optional title (defaults to "Confirm"). */
  title?: string;
  /** Label for the confirm button (defaults to "Confirm"). */
  confirmLabel?: string;
  /** Label for the cancel button (defaults to "Cancel"). */
  cancelLabel?: string;
  /** Fired when the user clicks Confirm. */
  onConfirm: () => void;
  /** Fired when the user clicks Cancel or the overlay backdrop. */
  onCancel: () => void;
}

/**
 * Simple modal confirm dialog for destructive actions.
 *
 * Renders nothing when `open` is false.
 */
export function ConfirmDialog({
  open,
  message,
  title = "Confirm",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label={title}
      data-testid="confirm-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="bg-white rounded-lg shadow-xl max-w-sm w-full mx-4 p-5 space-y-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-gray-700">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            data-testid="confirm-dialog-cancel"
            onClick={onCancel}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50"
          >
            {cancelLabel}
          </button>
          <button
            data-testid="confirm-dialog-confirm"
            onClick={onConfirm}
            className="px-3 py-1.5 text-sm rounded bg-red-600 text-white hover:bg-red-700"
            autoFocus
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
