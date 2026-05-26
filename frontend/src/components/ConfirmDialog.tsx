// ConfirmDialog.tsx — destructive-action confirmation dialog, backed by pd-ui AlertDialog.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Destructive keys confirm
// Issue #236
//
// Replaces the hand-rolled modal with @concavetrillion/pd-ui's AlertDialog suite
// (Radix-based). This gives us a native focus trap and Escape handling built in,
// addressing the aria-modal-without-focus-trap concern from issue #445.
//
// Public API is unchanged — callers do not need modification.
//
// data-testids:
//   confirm-dialog         — AlertDialogContent (the dialog panel)
//   confirm-dialog-confirm — confirm button (AlertDialogAction)
//   confirm-dialog-cancel  — cancel button (AlertDialogCancel)

import { useRef } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@concavetrillion/pd-ui/primitives";

interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Message shown to the user, e.g. "This will discard unsaved changes." */
  message: string;
  /** Optional title (defaults to "Confirm"). */
  title?: string | undefined;
  /** Label for the confirm button (defaults to "Confirm"). */
  confirmLabel?: string | undefined;
  /** Label for the cancel button (defaults to "Cancel"). */
  cancelLabel?: string | undefined;
  /** Fired when the user clicks Confirm. */
  onConfirm: () => void;
  /** Fired when the user clicks Cancel, presses Escape, or clicks the overlay. */
  onCancel: () => void;
}

/**
 * Modal confirm dialog for destructive actions, backed by pd-ui's Radix-based
 * AlertDialog suite. Provides a native focus trap and Escape key handling.
 *
 * Both AlertDialogAction and AlertDialogCancel close the dialog (triggering
 * onOpenChange(false)). We use a ref to distinguish: if the user clicked
 * Confirm, we fire onConfirm and suppress the onCancel that onOpenChange
 * would otherwise emit. All other close paths (Cancel button, Escape key,
 * overlay click) fire onCancel.
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
  // Track whether the confirm button was just clicked, so onOpenChange can
  // distinguish a confirm-close from a cancel/escape/overlay-close.
  const confirmedRef = useRef(false);

  return (
    <AlertDialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          if (confirmedRef.current) {
            confirmedRef.current = false;
            // onConfirm was already called in the button's onClick handler.
          } else {
            onCancel();
          }
        }
      }}
    >
      {/* AlertDialogContent already composes AlertDialogPortal + AlertDialogOverlay
          internally (pd-ui convention). The overlay uses class "dialog-overlay" and
          the content uses class "dialog" — we supplement with Tailwind to match the
          labeler's visual style since those CSS classes have no definition in the
          local primitives.css. */}
      <AlertDialogContent
        data-testid="confirm-dialog"
        className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 max-w-sm w-full mx-4 bg-bg-surface rounded-lg border border-border-2 p-5 space-y-4 shadow-lg focus:outline-none"
      >
        <AlertDialogHeader className="space-y-1">
          <AlertDialogTitle className="text-base font-semibold">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-sm text-ink-2">{message}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="flex justify-end gap-2">
          <AlertDialogCancel
            data-testid="confirm-dialog-cancel"
            className="px-3 py-1.5 text-sm rounded border border-border-2 bg-bg-surface hover:bg-bg-raised"
          >
            {cancelLabel}
          </AlertDialogCancel>
          <AlertDialogAction
            data-testid="confirm-dialog-confirm"
            onClick={() => {
              confirmedRef.current = true;
              onConfirm();
            }}
            className="px-3 py-1.5 text-sm rounded bg-status-mismatch text-accent-ink hover:opacity-90 transition-opacity"
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
