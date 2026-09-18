---
Status: active
Owner: maintainers
Created: 2026-09-18
Last verified: 2026-09-18
Kind: issue
Level: I1
---

# pdomain-ui's JobRow/JobsDrawer status contract can't represent a cancelled job honestly

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Medium — blocks PGDP-alignment item 4 (jobs pill/drawer); no
  data loss, but the only fix inside this repo is to misrepresent job state.
- **Affected version:** `@pdomain/pdomain-ui@0.12.1` (installed;
  `pdomain-ui` commit `073846e`), consumed by
  `pdomain-ocr-labeler-spa` frontend.
- **Read when:** picking up PGDP-alignment item 4 (jobs pill/drawer), or
  deciding whether to consume `JobsPill`/`JobsDrawer`/`JobRow` for any
  persistent job-status surface in this app.
- **Search terms:** JobsPill, JobsDrawer, JobRow, JobStatus, AppShellJobsProps,
  UtilityDock jobs surface, cancelled job status, pause resume dead button,
  P1-CANCEL.
- **Relates to:**
  [`../plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md)
  (item 4), [`../context/intent-map.md`](../context/intent-map.md) (Needs
  owner decision).

## Summary

`pdomain-ui`'s job-list components (`JobRow`, consumed by both `JobsDrawer`
and the `AppShell` → `UtilityDock` → `JobsPanelBody` path) type their per-job
`status` as a fixed six-member union —
`'queued' | 'running' | 'paused' | 'succeeded' | 'done' | 'failed'` — with no
member for a user-cancelled job. This app's backend `JobStatus` has five
members — `queued | running | complete | error | cancelled` — and already
treats `cancelled` as materially different from `error`: the shared
`useJobCompletionInvalidation` hook exposes a dedicated `onCancelled`
callback, separate from `onError`, specifically because a cooperative cancel
(P1-CANCEL) is a user-initiated stop, not a failure. There is no honest way
to compile a cancelled job into `JobRow`'s six-value union: every option
(`'failed'`, `'succeeded'`/`'done'`, `'paused'`) misrepresents either the
cause or the outcome. Separately, `JobRow` unconditionally renders a
Pause/Resume hover button for every non-done job with no prop to hide it,
and this backend's job model has no pause/resume capability at all — wiring
nothing behind it ships a dead control; wiring a fake one invents a
capability that doesn't exist.

## Impact

- PGDP-alignment item 4 (jobs pill/drawer) cannot consume `JobsDrawer` /
  `JobsPanelBody` / `JobRow` for the per-job list without either lying about
  a cancelled job's outcome or shipping a button that silently does nothing.
- `JobsPill` itself (the header trigger/badge) is **not** affected — its
  `ActiveJob` prop type (`id`, `title`, `phase`, `pct`, `project`) has no
  `status` field at all, and the component only reads `activeJobs.length`.
  It is usable on its own.
- No user-facing regression today: nothing in this app currently renders
  `JobRow`/`JobsDrawer`/`JobsPanelBody`. This report blocks new work, not
  shipped behavior.

## Environment / versions

```
@pdomain/pdomain-ui: 0.12.1 (frontend/package.json; installed via the
  pdomain-index-npm registry, matches pdomain-ui commit 073846e "chore:
  release v0.12.1")
pdomain-ocr-labeler-spa: frontend/src/hooks/useJobProgress.ts,
  frontend/src/hooks/useJobCompletionInvalidation.ts,
  frontend/src/components/BusyOverlay.tsx,
  src/pdomain_ocr_labeler_spa/core/models.py (Job, JobStatus)
```

## Evidence — comparison

### 1. Backend `JobStatus` has five members; `cancelled` is a first-class, product-distinguished terminal state

`src/pdomain_ocr_labeler_spa/core/models.py`:

```python
class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"
```

`frontend/src/hooks/useJobCompletionInvalidation.ts` gives `cancelled` its
own callback, explicitly distinct from `error`:

```ts
/**
 * Optional callback fired once on the `"cancelled"` transition — the
 * cooperative-cancel terminal state (P1-CANCEL), distinct from both
 * `"complete"` and `"error"`. ...
 */
onCancelled?: (jobId: string, event: JobProgressEvent) => void;
```

and the effect body branches on `"cancelled"` separately from `"error"`
(lines 122–131). `frontend/src/hooks/useCancelJob.ts` and
`frontend/src/components/BusyOverlay.tsx`'s `CANCELLABLE`/`BEST_EFFORT_CANCEL`
policy sets show cancel is a live, reachable, first-class control — not a
theoretical edge case — for `save_project`, `export`, `auto_rotate_all`,
`propose_page_kinds`, `propose_regions`, and (best-effort) `reload_ocr`.

### 2. `pdomain-ui`'s `JobStatus` has no member for it

`pdomain-ui/src/shell/JobRow.tsx`:

```ts
export type JobStatus = 'queued' | 'running' | 'paused' | 'succeeded' | 'done' | 'failed';
```

`isDone`/`isPaused`/`isFailed` are the only three status predicates the
component branches on; anything that isn't `'done'`/`'succeeded'` and isn't
`'paused'` and isn't `'failed'` renders as the default running/queued
treatment (pulsing dot, `{pct}%` badge). There is no fourth predicate and no
escape hatch — `job.status` must be one of the six literal strings to
type-check at all.

### 3. No honest mapping exists

| Backend `cancelled` mapped to → | What `JobRow` shows | Why it's wrong |
|---|---|---|
| `'failed'` | Red dot, "Failed" text, `job-row-status-failed` testid, Delete button | Blames a user-initiated stop as a system failure — the opposite of what `onCancelled` vs. `onError` exists to distinguish |
| `'succeeded'` / `'done'` | Green tint, "Open" button, no progress bar | Claims the job finished normally when it did not |
| `'paused'` | Dashed progress bar, "Resume" hover label | Claims the job is resumable; nothing in this backend can resume a cancelled job — cancel is terminal |
| `'queued'` / `'running'` | Pulsing dot, live `{pct}%`, forever | Claims the job is still active; would show a permanently "running" job that will never finish |

### 4. A second, independent gap: the Pause/Resume button has no capability flag

`pdomain-ui/src/shell/JobRow.tsx`'s hover strip:

```tsx
{hovered && !done ? (
  <div ...>
    <button onClick={() => onOpen?.(job.id)}>Open project ...</button>
    <button onClick={() => onPauseResume?.(job.id)}>
      {paused ? <Play .../> : <Pause .../>} {paused ? 'Resume' : 'Pause'}
    </button>
    {job.cancelable ? <button onClick={() => onCancel?.(job.id)}>Discard</button> : null}
  </div>
) : null}
```

Only the Discard button is gated by a job-level flag (`cancelable`). Pause/
Resume renders unconditionally for every non-done job. This backend's job
model (`core/jobs/runner.py`) has queued → running → one of three terminals,
plus cooperative cancel; there is no pause/resume concept anywhere. Leaving
`onPauseResume` unwired means the button is present, hoverable, and clickable,
and does nothing when clicked — a dead affordance, not a missing feature the
user can discover is missing.

### 5. Precedent already set inside this app: don't stretch a coarser enum over a state it can't hold honestly

`frontend/src/components/BusyOverlay.tsx` already faces the same shape of
problem with a different pdomain-ui component —
`@pdomain/pdomain-ui/status`'s `OperationStatusPanel`, whose `state` prop is
`'idle' | 'queued' | 'running' | 'success' | 'warning' | 'error'` (also no
`cancelled`). `BusyOverlay` never passes anything but `state="running"`; it
relies on the overlay unmounting once the job leaves the active set, and
lets the existing toast system narrate `complete`/`error`/`cancelled`
outcomes. That precedent — don't force a terminal state through a component
whose enum can't hold it; let another surface (already shipped, not touched
by this report) carry the nuance instead — informed this report's
recommendation below.

## Gaps to close (upstream, in `pdomain-ui`)

1. **(Primary)** Add a `cancelled` member to `JobRow`'s `JobStatus` union
   (and, if `JobsDrawer`'s `running`/`done` split needs it,
   `JobsDrawer.buildSummary`), with its own accent color and label —
   mirroring the five-state `JobStatusPip`
   (`pdomain-ui/docs/architecture/job-status-pip.md`) already shipped
   elsewhere in the same package, rather than inventing a new vocabulary.
2. Gate the Pause/Resume hover button behind a job-level capability flag
   (e.g. `pausable: boolean`, alongside the existing `cancelable: boolean`)
   so a consumer whose backend has no pause/resume can omit it instead of
   shipping a dead control.

## Recommended next steps

1. File the two gaps above against `pdomain-ui` (owner: pdomain-ui
   maintainers) and reference this report.
2. Once `pdomain-ui` ships a `cancelled` status and a pause/resume
   capability flag, revisit PGDP-alignment item 4: `JobsPill` (header
   trigger/badge, already contract-compatible) plus `AppShell`'s `jobs` prop
   → `UtilityDock` → `JobsPanelBody` is the integration path (no need for
   the standalone `JobsDrawer` — `AppShell` already docks a jobs surface).
3. Until then, do not render `JobRow`/`JobsDrawer`/`JobsPanelBody` for any
   job that can reach `cancelled` in this app (i.e. any job type in
   `BusyOverlay`'s `CANCELLABLE` or `BEST_EFFORT_CANCEL` sets — which is
   most of them).

## What is NOT broken

- `useJobProgress`, `useCancelJob`, `useJobCompletionInvalidation`,
  `BusyOverlay`, and the toast-based completion narration are all shipped,
  correct, and untouched by this report — they don't route job status
  through `pdomain-ui`'s coarse enums at all.
- `JobsPill`'s own contract (`ActiveJob`) is fine as-is; it has no `status`
  field and only reads `activeJobs.length`. It can be adopted independently
  as a header running-count indicator without waiting on this gap.
- `GET /api/jobs`, `GET /api/jobs/{id}`, and the SSE stream
  (`GET /api/jobs/{id}/events`) are all correctly shaped and race-free as of
  the 2026-09-18 broker fix (`docs/context/decisions.md`, "Fixed: a job that
  finished fast hung its event stream forever"). This report is scoped to
  the frontend job-list *rendering* contract only.

## Resolution

*Open.* Blocked on an upstream `pdomain-ui` decision (add `cancelled` to
`JobRow`'s `JobStatus`; add a pause/resume capability flag). Tracked in
[`../context/intent-map.md`](../context/intent-map.md) "Needs owner
decision".
