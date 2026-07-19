---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 11 — Notifications, Busy Overlays, and SSE Jobs

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#26

How user-visible feedback flows from server actions to the UI.

> Cross-refs:
> Legacy notification queue —
> `pd-ocr-labeler/pd_ocr_labeler/state/app_state.py:queue_notification`,
> `views/main_view.py:_flush_queued_notifications`
> Job runner — [`02-backend.md`](02-backend.md) §11
> Toast component — [`03-frontend.md`](03-frontend.md) §12

---

## 1. Three feedback channels

| Channel | What it shows | Driver |
|---|---|---|
| Toast (sonner) | Transient: "Saved", "OCR complete", "Validate failed" | server-pushed via SSE OR client-side from `useMutation.onSuccess/onError` |
| Busy overlay | Full-page modal blur during long actions | `useIsMutating` OR active `Job` |
| Sticky banner | Persistent: "OCR failed for this page", "Project not found" | rendered inline in the page that produces it |

The legacy mixes all three through `ui.notify` + `_action_context` +
`is_busy` flags. The SPA cleanly separates them.

---

## 2. Toasts (sonner)

One `<Toaster richColors position="top-right" />` mounted in
`App.tsx`. All toasts go through `sonner`'s `toast.*` API:

```ts
toast.success("Saved");
toast.error("Save failed", { description: err.message });
toast.warning("Some pages failed to save", { action: {label: "Details", onClick: ...} });
toast.info("OCR using cached weights");
toast.loading("Saving project…", { id: jobId });   // dismissed by toast.success on completion
```

### 2.1 Two sources of toasts

**Client-side (per-mutation):**
```tsx
useMutation({
  mutationFn,
  onError: (e) => toast.error("Apply style failed", { description: e.message }),
  onSuccess: () => toast.success("Style applied"),
});
```

**Server-side (per-notification SSE event):**
The backend pushes notifications onto an in-memory `NotificationQueue`,
exposed via SSE at `/api/notifications/stream`. The SPA's
`useNotificationStream()` hook reads each event and calls the
matching `toast.<kind>(message)`.

The two channels are **complementary**, not duplicated. Client-side
covers per-mutation feedback; server-side covers system events that
don't tie to a specific user action (auto-save success/failure,
notifications during job execution, OCR-config selection-reason
announcements, etc.).

### 2.2 NotificationKind mapping

Backend `NotificationKind` → sonner method:

| Kind | Method | Color |
|---|---|---|
| `positive` | `toast.success` | green |
| `negative` | `toast.error` | red |
| `warning` | `toast.warning` | amber |
| `info` | `toast.info` | blue |

### 2.3 SSE shape

`GET /api/notifications/stream`:

```
event: notification
data: {"id":"abc","kind":"positive","message":"Auto-saved","created_at":"..."}

event: notification
data: {"id":"def","kind":"warning","message":"Cache write failed: <reason>"}
```

The backend keeps a ring buffer of the last ~100 notifications so a
late subscriber sees recent events. Each subscriber gets the snapshot
on connect, then live events.

Implementation: `src/pdomain_ocr_labeler_spa/core/notifications.py` — port
of legacy `AppState.queue_notification` / `pop_notification`, plus the
SSE wrapper.

### 2.4 Driver-agent path

The driver agent (Playwright) doesn't open the SSE stream — it reads
notifications from the DOM. Sonner renders each toast with
`data-testid="notification-{kind}-{id}"` (custom toast renderer; see
[`13-driver-contract.md`](13-driver-contract.md) §2.13).

The driver-agent contract guarantees the `{kind, message, id}` triple
is present. Spec author rule: every toast that lands in the DOM must
also have been on the SSE stream (1:1 correspondence).

---

## 3. Busy overlay

`<BusyOverlay />` in `App.tsx`:

```tsx
const isMutating = useIsMutating({ predicate: (m) =>
  ["page", "project"].includes(m.options.mutationKey?.[0] as string)
}) > 0;
const activeJob = useActiveJob(["RELOAD_OCR_PAGE", "REFINE_BBOXES_PAGE", ...]);
const visible = isMutating || activeJob !== null;
```

When visible: full-page semi-transparent dark overlay
(`bg-black/30 backdrop-blur-sm z-40`) with a centred spinner and
optional message ("Refining page bboxes — line 12 of 23…").

testid: `busy-overlay`.

The legacy uses a similar overlay (`project_view.py:78`) but couples it
to a per-action context manager. The SPA computes it reactively from
mutation + job state, no manual flag.

The SPA retains the outer overlay as a local composition boundary and renders
`OperationStatusPanel` from `@pdomain/pdomain-ui/status` inside it. It does not
use the shared `BlockingOperationOverlay` because that component portals to
`document.body`. The local wrapper keeps `busy-overlay` inside the image pane,
as required by the driver contract and the containment test. It also retains
the labeler's job-to-message mapping and cancel rules.

Evidence:

- Code: `frontend/src/components/BusyOverlay.tsx`
- Tests: `frontend/src/components/BusyOverlay.test.tsx` and
  `frontend/src/pages/ProjectPage.test.tsx`
- Commit: `c238965`
- Verified: 2026-07-19 against current code and tests

### 3.1 Project-loading overlay

A separate `<ProjectLoadingOverlay />` for project-load specifically:
fires on `useProject(...).isLoading`. Higher z-index (z-50) than the
busy overlay.

testid: `project-loading-overlay`.

### 3.2 Cancel button

For long jobs (`SAVE_PROJECT`, `EXPORT`), the busy overlay shows a
Cancel button that calls `runner.cancel(jobId)`. Best-effort: handlers
check the cancellation token periodically.

---

## 4. Inline banners

For persistent / sticky messages tied to a specific page or project:

- "OCR failed for this page. Click Reload OCR to retry." — in the
  content area when `pageRecord.ocr_failed === true`.
- "Project not found at /abs/path." — in the project chrome when
  routing to a project_id that doesn't resolve.
- "Image on disk has changed. Reload page to continue." — at the top
  of the matches view after a `409 image_drift` save.

Implementation: per-page React components rendering shadcn `<Alert />`.
Not toasts.

---

## 5. Sequence diagrams

### 5.1 Reload OCR

```
SPA              Backend                            Job runner
 │                  │                                 │
 │ POST .../reload-ocr (use_edited_image=false)       │
 │─────────────────▶│                                 │
 │                  │ submit(RELOAD_OCR_PAGE, payload)│
 │                  │────────────────────────────────▶│
 │ 202 {job_id}     │                                 │
 │◀─────────────────│                                 │
 │                                                    │ (running)
 │ EventSource(/api/jobs/{job_id}/events)             │
 │───────────────────────────────────────────────────▶│
 │ event:progress  {current:0,total:1,msg:"Loading…"} │
 │◀───────────────────────────────────────────────────│
 │ event:progress  {current:0,total:1,msg:"OCR…"}     │
 │◀───────────────────────────────────────────────────│
 │ event:complete  {result:{...}}                     │
 │◀───────────────────────────────────────────────────│
 │ EventSource closes                                 │
 │ refetch ["page",pid,idx]                           │
 │ toast.success("OCR complete")                      │
```

The busy overlay is up the whole time (driven by `useActiveJob`).

### 5.2 Auto-save after a word edit

```
SPA              Backend
 │ POST .../words/.../style {...}
 │─────────────────▶│
 │                  │ PageState.update_word_attributes(...)
 │                  │ _auto_save_to_cache(...)   ← writes envelope, emits notification
 │ 200 WordMatch    │
 │◀─────────────────│
 │ patch cache, render
 │
 │ (separately, on the SSE notifications stream:)
 │ event:notification {kind:"positive", message:"Auto-saved", ...}
 │ toast.success("Auto-saved")        ← optional; could be filtered out
```

For auto-save success, the SPA may filter the toast (it's noisy).
Auto-save **failures** are surfaced as warning toasts.

---

## 6. Notification de-duplication

For repeated identical messages (e.g. "OCR using stock weights" on
every page navigation), the legacy uses `_safe_notify_once(key, ...)`
to dedupe. The SPA backend implements the same semantics:

```python
class NotificationQueue:
    def queue_once(self, key: str, kind: NotificationKind, message: str) -> None:
        if key in self._seen_keys:
            return
        self._seen_keys.add(key)
        self.queue(kind, message)
```

Reset on project change. Same dedupe behaviour.

---

## 7. Tests

- Backend: `tests/unit/test_notification_queue.py` — queue order, ring
  buffer eviction, `queue_once` dedupe.
- Backend: `tests/integration/test_notification_sse.py` — connect to
  the SSE endpoint, queue 5 notifications, assert the right events
  arrive in order.
- Frontend: `useNotificationStream.test.tsx` — given a stub
  EventSource that emits 3 notifications, the right toast.* methods
  are called.
- Frontend: `BusyOverlay.test.tsx` — visible when `useIsMutating > 0`.
- E2E: `test_busy_overlay.py` — trigger a Save Project, see overlay
  appear, see cancel button work.

---

## 8. Open issues

- **Auto-save toast spam.** Every word edit triggers an auto-save. If
  we toast each, the corner is a wall of green. Spec author bet:
  filter `Auto-save` success notifications client-side (the SaveStatus
  indicator covers them); keep failures.
- **Long history.** A multi-hour session accumulates ~hundreds of
  notifications in the ring buffer. The buffer caps at 100 (matches
  legacy queue behaviour). Drops are silent.
- **Cancel button visibility.** Cancel on `RELOAD_OCR_PAGE` doesn't
  meaningfully cancel — DocTR doesn't yield. Show but warn it's
  best-effort. For `SAVE_PROJECT` and `EXPORT`, cancel does work.
