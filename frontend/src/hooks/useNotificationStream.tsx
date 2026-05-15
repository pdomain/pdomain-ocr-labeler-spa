// useNotificationStream.tsx — subscribe to the backend SSE notification stream
// and dispatch sonner toasts per notification kind.
//
// Spec: docs/specs/2026-05-12-notifications-design.md §useNotificationStream hook
// Issue #231
//
// NotificationKind → toast mapping (Slice 26):
//   positive → toast.success (status-exact)
//   negative → toast.error (status-mismatch)
//   warning  → toast.warn (status-fuzzy)
//   info     → toast.info (status-ocr)
//
// Auto-save success notifications are filtered client-side: messages whose
// text starts with "auto-save: " and kind is "positive" are suppressed.
// The SaveStatus indicator in PageActions covers auto-save state.
//
// Each toast carries `data-testid="notification-{kind}-{id}"` for driver-agent
// access (spec §13-driver-contract §2.13). The driver uses selectors like
// `[data-testid^="notification-negative-"]` to find error toasts.

import { useEffect } from "react";
import { toast } from "../lib/toast";

/** Matches the backend Notification shape from core/notifications.py. */
interface NotificationEvent {
  id: string;
  kind: "positive" | "negative" | "warning" | "info";
  message: string;
  created_at: string;
}

const SSE_URL = "/api/notifications/stream";

/** Wrap message in a span with the driver-contract testid. */
function ToastMessage({ kind, id, message }: { kind: string; id: string; message: string }) {
  return <span data-testid={`notification-${kind}-${id}`}>{message}</span>;
}

/**
 * Open an EventSource against /api/notifications/stream and dispatch
 * sonner toasts for each notification event. Closes on unmount.
 *
 * Auto-save success notifications are filtered (messages starting with
 * "auto-save: " and kind "positive") — the SaveStatus badge covers them.
 */
export function useNotificationStream(): void {
  useEffect(() => {
    const es = new EventSource(SSE_URL);

    function handleNotification(e: MessageEvent) {
      let notif: NotificationEvent;
      try {
        notif = JSON.parse(e.data as string) as NotificationEvent;
      } catch {
        return;
      }

      // Filter auto-save success: client-side suppression per spec.
      if (notif.kind === "positive" && notif.message.startsWith("auto-save: ")) {
        return;
      }

      const msg = <ToastMessage kind={notif.kind} id={notif.id} message={notif.message} />;

      switch (notif.kind) {
        case "positive":
          toast.success(msg, { id: notif.id });
          break;
        case "negative":
          toast.error(msg, { id: notif.id });
          break;
        case "warning":
          toast.warn(msg, { id: notif.id });
          break;
        case "info":
          toast.info(msg, { id: notif.id });
          break;
      }
    }

    es.addEventListener("notification", handleNotification);

    return () => {
      es.removeEventListener("notification", handleNotification);
      es.close();
    };
  }, []); // stable — mount once, tear down on unmount
}
