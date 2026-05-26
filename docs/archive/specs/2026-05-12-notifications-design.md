# pdomain-ocr-labeler-spa: Notifications, Busy Overlays, and SSE Jobs

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#26

## TL;DR

Three feedback channels: sonner toasts (transient), busy overlay (full-page during mutations/jobs),
inline banners (sticky page errors). Toasts come from two sources: client-side `useMutation`
callbacks and server-side SSE `NotificationQueue`. Backend ring-buffer of 100 notifications;
`queue_once` deduplication per project. `<BusyOverlay />` derived reactively from
`useIsMutating` + `useActiveJob`. Cancel button for long jobs (SAVE_PROJECT, EXPORT).

## Context

The legacy mixes toast/overlay/banner through `ui.notify` + `_action_context` + `is_busy`
flags. The SPA cleanly separates the three channels. The SSE notification stream mirrors the
legacy `AppState.queue_notification` / `pop_notification` pattern. The driver agent reads
toasts from DOM testids rather than the SSE stream. Auto-save success toasts are filtered
client-side (SaveStatus indicator covers them); failures surface as warnings.

## Constraints

- **Single `<Toaster />` in App.tsx.** All toasts go through sonner's `toast.*` API.
- **Two complementary toast sources.** Client-side per-mutation + server-side SSE; no
  duplication of the same event across both.
- **Ring buffer cap at 100.** Matches legacy; drops are silent.
- **`queue_once` dedup resets on project change.** Prevents per-page-nav "OCR using stock
  weights" spam.
- **Driver agent reads toasts from DOM.** Sonner renders custom renderer with
  `data-testid="notification-{kind}-{id}"`. Every DOM toast must have been on the SSE
  stream (1:1 correspondence).
- **Cancel button for SAVE_PROJECT + EXPORT only.** RELOAD_OCR cancel is best-effort
  (DocTR doesn't yield); show button with warning text.

## Decision

### Three feedback channels

1. **Toast (sonner)** — transient feedback. `<Toaster richColors position="top-right" />`
   in `App.tsx`. Methods: `toast.success`, `toast.error`, `toast.warning`, `toast.info`,
   `toast.loading` (dismissed by success on job completion).

2. **Busy overlay** — `<BusyOverlay />` in `App.tsx`. Visible when `useIsMutating > 0` (for
   page/project mutation keys) OR `useActiveJob` returns a running job. Full-page
   `bg-black/30 backdrop-blur-sm z-40`. Centred spinner + optional message string. testid:
   `busy-overlay`. Separate `<ProjectLoadingOverlay />` at z-50 for project-load specifically.

3. **Inline banners** — shadcn `<Alert />` for persistent/sticky page errors: OCR failed,
   project not found, image drift (409).

### NotificationQueue (backend)

`core/notifications.py`. Ring buffer of 100. `NotificationKind`: `positive | negative |
warning | info`. `queue_once(key, kind, message)` deduplicates by key per project; resets on
project change. SSE endpoint: `GET /api/notifications/stream` delivers snapshot on connect
(last ~100) then live events. Event shape:
`{id, kind, message, created_at}`.

`NotificationKind` → sonner mapping: `positive→success`, `negative→error`,
`warning→warning`, `info→info`.

### useNotificationStream hook

Subscribes to `/api/notifications/stream` via EventSource. Dispatches `toast.<kind>(message)`
on each notification event. Auto-save success notifications filtered client-side.

### BusyOverlay logic

```ts
const isMutating = useIsMutating({ predicate: (m) =>
  ["page", "project"].includes(m.options.mutationKey?.[0] as string) }) > 0;
const activeJob = useActiveJob(["RELOAD_OCR_PAGE", "REFINE_BBOXES_PAGE", ...]);
const visible = isMutating || activeJob !== null;
```

Cancel button shown for `SAVE_PROJECT` and `EXPORT` active jobs. Posts to
`/api/projects/{id}/jobs/{job_id}/cancel`. For `RELOAD_OCR_PAGE`: cancel button present with
"best-effort" tooltip (DocTR doesn't yield).

## Contract / Acceptance

- `toast.success` fired on Save Page success; `toast.error` on failure (with description).
- SSE stream delivers notifications in queue order; snapshot on connect includes last 100.
- `queue_once("ocr-stock-weights", ...)` fires once per project, not per page navigation.
- Busy overlay visible during active mutation; hidden on completion or error.
- Cancel button fires POST to cancel endpoint; busy overlay hides on `cancelled` event.
- Driver agent can locate toasts via `data-testid="notification-{kind}-{id}"`.
- `ProjectLoadingOverlay` testid `project-loading-overlay` visible during project fetch.

## Trade-offs considered

**Merge toast sources vs separate.** Merging (one SSE source) would simplify the hook but
add round-trip latency for per-mutation toasts. Keeping client-side for mutations + server-side
for background/auto events gives instant feedback for user actions. Chosen: two complementary
sources.

**Ring buffer vs persistent notification log.** Persistent log adds storage and a UI panel.
Ring buffer of 100 matches legacy behaviour and requires no extra storage. Chosen: ring buffer.

**Auto-save success toast: show vs filter.** Showing every auto-save toast creates wall-of-
green spam. SaveStatus indicator in PageActions covers auto-save state. Chosen: filter
auto-save success client-side; always show failures.

**Cancel on RELOAD_OCR: show vs hide.** Hiding cancel for non-cancellable jobs is simpler but
surprises users who expect a cancel option on any long operation. Show with warning tooltip.

## Consequences

- Every toast that appears in the DOM must originate from the SSE stream (driver-contract
  rule). Mutations that toast client-side must also trigger a corresponding backend
  notification or the 1:1 guarantee breaks — use client-only toasts only for mutations that
  never fail silently on the server.
- Auto-save failure notifications must use `negative` kind so they are never filtered.
- The `NotificationQueue` is per-`AppState` (singleton per process); multiple browser tabs
  share the same stream, which is intentional.

## Open questions

None.

## References

- `specs/11-notifications.md` — legacy feature doc (full SSE shape, sequence diagrams)
- `specs/02-backend.md §11` — job runner + SSE events
- `specs/03-frontend.md §12` — toast component integration
- `specs/13-driver-contract.md §2.13` — driver-agent toast testid contract
- `core/notifications.py` — NotificationQueue implementation
