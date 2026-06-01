# Behavior unit spec - Jobs and notifications

- **Unit type:** shared runtime service
- **Address:** `useJobProgress`, `BusyOverlay`, notification stream/toasts
- **UI definition:** none - implementation and tests define current behavior.
- **Parent unit(s):** page actions, drawer bulk actions, export dialog
- **Child unit(s):** JobRunner, notification queue, SSE endpoints
- **Shared unit:** yes
- **Implementation:** `frontend/src/hooks/useJobProgress.ts`,
  `useNotificationStream.ts`, `frontend/src/components/BusyOverlay.tsx`,
  backend jobs/notifications routers
- **Backend / collaborators touched:** `/api/jobs/*`, notification SSE,
  job-backed save/reload/refine/rotate/export handlers

## Behavior records

### B-JOBS-001 - Job progress subscribes, updates, invalidates, and cancels

- **Flow(s):** F-JOB-SSE-01
- **Composed by:** B-ACTIONS-010
- **Trigger:** Frontend receives a job id from a job-backed action.
- **Preconditions:** Job id is valid or recently created.
- **Observable output:** Progress, message, terminal success/error, and optional
  busy overlay update until terminal state.
- **Backend / side-effects:** EventSource or polling reads job state; terminal
  success invalidates affected queries; cancel posts job cancel endpoint.
- **Bad-state / error:** SSE disconnect or terminal error leaves page data
  intact and reports recoverably.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-JOBS-002 - Notification stream replays and maps live events to toasts

- **Flow(s):** F-NOTIFICATIONS-01
- **Composed by:** B-ACTIONS-011
- **Trigger:** App shell mounts or backend emits notification event.
- **Preconditions:** Notification stream hook active.
- **Observable output:** Replayed and live notifications become visible toasts;
  dismiss removes the targeted notification; auto-save success can be filtered.
- **Backend / side-effects:** Notification queue stores bounded history and SSE
  streams new events.
- **Bad-state / error:** Stream failure must not crash app shell; important
  failures remain visible.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-JOBS-003 - Busy overlay blocks duplicate mutation while keeping cancel visible

- **Flow(s):** F-JOB-SSE-01
- **Composed by:** B-JOBS-001
- **Trigger:** A page-level job enters running state.
- **Preconditions:** Project page mounted.
- **Observable output:** Busy overlay/progress state disables duplicate actions
  and exposes cancel where supported.
- **Backend / side-effects:** Cancel delegates to job cancel route; no document
  mutation occurs from overlay render.
- **Bad-state / error:** Unsupported cancel remains hidden/disabled instead of
  posting an invalid route.
- **Tier(s):** A
- **Regression:** no
- **Test:** -
