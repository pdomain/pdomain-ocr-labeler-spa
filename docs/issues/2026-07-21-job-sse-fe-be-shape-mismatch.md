---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Job SSE: frontend nested shape vs backend flat emit; wrong BusyOverlay job type

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — job progress, cancel policy, and completion handling can fail silently at the FE↔BE SSE boundary
- **Affected version:** workspace tree as of 2026-07-21
- **Read when:** changing job runner SSE, `useJobProgress`, BusyOverlay, or any 202-accepted background job UX.
- **Search terms:** useJobProgress, JobProgressEvent, SSE, snapshot, cancelled, reload_ocr_page, BusyOverlay,
  P1-JOB-SSE, P1-JOB-TYPE, Wave 3a.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  `frontend/src/hooks/useJobProgress.ts`,
  `src/pdomain_ocr_labeler_spa/core/jobs/runner.py`,
  `src/pdomain_ocr_labeler_spa/api/jobs.py`

## Summary

The SPA job-progress path assumes an **OpenAPI-nested** SSE payload
(`{ job_id, status, progress: { current, total, … }, error_message }`), while
the in-process runner and `/api/jobs/{id}/events` stream emit a **flat** shape
(`{ type, status, current, total, message, error }`). The first SSE frame is
often `event: snapshot`, which `useJobProgress` does not listen for; `cancelled`
is also unhandled. Separately, `ProjectPage` synthesizes every active job as
`type: "reload_ocr_page"`, so BusyOverlay cancel policy is wrong for save,
export, and other job types.

This issue covers **P1-JOB-SSE**, **P1-JOB-TYPE**, and the related
snapshot/cancelled gaps. Fix work is **Wave 3a** tasks **3a.1–3a.4** in the
deep-review continuation plan.

## Impact

- Progress overlays may never update (`progress.current` undefined on flat
  payloads; first frame ignored if only `snapshot`).
- Terminal handling can miss cancel streams (`event: cancelled` not registered).
- `error_message` vs `error` naming mismatch breaks error text in completion /
  toast paths that read the nested FE field.
- BusyOverlay always treats the tracked job as `reload_ocr_page` → incorrect
  cancel button / “best-effort” policy for export, save_project, refine, rotate,
  etc.
- Unit tests currently feed **nested** fixtures only, so the contract gap is
  invisible to the local FE test suite.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Plan: `docs/plans/2026-07-21-deep-code-review-continuation.md` — Wave 3a
- Finding IDs: `P1-JOB-SSE`, `P1-JOB-TYPE`
- Surfaces: `JobRunner._emit`, `GET /api/jobs/{job_id}/events`,
  `useJobProgress`, `ProjectPage` BusyOverlay synthesis, `BusyOverlay`
- Verified by static inspection of runner, jobs API, and FE hooks (2026-07-21)

## Evidence

### 1. Backend emits flat events (`runner.py`)

```213:226:src/pdomain_ocr_labeler_spa/core/jobs/runner.py
    async def _emit(self, job: Job) -> None:
        terminal = {JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.CANCELLED}
        ev_type = job.status.value if job.status in terminal else "progress"
        event = {
            "type": ev_type,
            "status": job.status.value,
            "current": job.progress_current,
            "total": job.progress_total,
            "message": job.message,
            "error": job.error_message,
        }
        if job.result:
            event.update(job.result)
        await self._broker.publish(job.job_id, event)
```

Flat fields: `type`, `status`, `current`, `total`, `message`, `error`. No
`job_id`, no nested `progress`, no `error_message`.

### 2. First frame is often `event: snapshot` (`jobs.py`)

```108:120:src/pdomain_ocr_labeler_spa/api/jobs.py
    async def stream():
        snapshot = _job_snapshot(job)
        ev_name = snapshot["type"] if snapshot["type"] in ("complete", "error", "cancelled") else "snapshot"
        yield _sse_line(ev_name, snapshot)

        if job.status in _TERMINAL:
            return

        async for event in broker.subscribe(job_id):
            ev_type = event.get("type", "progress")
            yield _sse_line(ev_type, event)
            if ev_type in ("complete", "error", "cancelled"):
                return
```

`_job_snapshot` uses the same flat dict shape as `_emit` (`current` / `total` /
`error`, not nested OpenAPI `JobProgress`).

### 3. FE expects nested shape and only listens for progress/complete/error

```20:30:frontend/src/hooks/useJobProgress.ts
export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  progress: JobProgress;
  error_message?: string | null;
  // Export stats breakdown (Lane E3) — present on the terminal event of an
  // export job. Flat top-level fields, matching the backend SSE wire format.
  words_exported_detection?: number;
  words_exported_recognition?: number;
  pages_skipped_not_validated?: number;
}
```

```73:79:frontend/src/hooks/useJobProgress.ts
    // "progress" covers running updates; "complete"/"error" are the terminal
    // SSE event types the backend sends (event: complete / event: error).
    // Without these, jobProgress.status never reaches "complete" and any
    // downstream invalidateQueries call is never triggered.
    es.addEventListener("progress", handleProgress);
    es.addEventListener("complete", handleProgress);
    es.addEventListener("error", handleProgress);
```

No `snapshot` or `cancelled` listeners. Comment documents nested OpenAPI-style
payload; export stats note already acknowledges some flat terminal fields, but
progress counters are still nested.

`useJobProgress.test.tsx` fixtures use nested
`{ job_id, status, progress: { current, total, message }, error_message }` —
not the flat runner payload.

### 4. ProjectPage hard-codes job type (`P1-JOB-TYPE`)

```513:532:frontend/src/pages/ProjectPage.tsx
  // Pseudo-Job object for BusyOverlay. BusyOverlay accepts the full
  // `components.schemas.Job` shape but only branches on `type` / `status`;
  // we synthesize the minimal shape from the SSE progress event. The
  // `id` / `project_id` / `created_at` / `updated_at` fields are required
  // by the type but not consumed by the overlay — placeholder values keep
  // tsc happy without inventing data.
  const nowIso = new Date(0).toISOString();
  const activeJob: components["schemas"]["Job"] | null =
    jobProgress && jobProgress.status !== "complete" && jobProgress.status !== "error"
      ? {
          id: jobProgress.job_id,
          project_id: projectId ?? null,
          type: "reload_ocr_page" as components["schemas"]["JobType"],
          status: jobProgress.status,
          progress: jobProgress.progress,
          error_message: jobProgress.error_message ?? null,
          created_at: nowIso,
          updated_at: nowIso,
        }
      : null;
```

`BusyOverlay` treats `reload_ocr_page` as best-effort cancel
(`BEST_EFFORT_CANCEL`); other job types get different cancel UX. Synthesis
forces the OCR reload policy for every tracked job.

## Root-cause hypotheses

1. **(Most likely) Two contracts evolved separately.** OpenAPI `Job` /
   `JobProgress` shaped the FE hook and tests; the runner broker used a compact
   flat dict for SSE and never remapped at the API boundary. Snapshot naming
   followed “first frame = current snapshot” without a matching FE listener.
2. **BusyOverlay synthesis was a minimal placeholder.** `ProjectPage` only
   needed a typed `Job` for the overlay during OCR reload work and hard-coded
   the dominant type instead of threading `job_type` from 202 responses.
3. **Less likely: intentional dual format with missing adapter.** Export stats
   comments on the FE type hint awareness of flat terminal fields, but no
   normalize step was added for counters / ids / error keys.

## Defects to fix

Ordered as Wave **3a.1–3a.4**:

1. **3a.1 — Unify wire format** — Either emit nested OpenAPI-shaped events from
   the jobs API (or runner), **or** adapt flat backend events inside
   `useJobProgress` to `{ job_id, status, progress: { current, total, message },
   error_message }`. Pick one source of truth; document it.
2. **3a.2 — Listen for `snapshot` and `cancelled`** — Register SSE event types
   the backend already yields; treat snapshot like progress; treat cancelled as
   terminal (close EventSource; clear busy state).
3. **3a.3 — Pass real `job_type` into BusyOverlay synthesis** — From 202
   responses (and/or job list/get), stop hard-coding `type: "reload_ocr_page"`
   in `ProjectPage` (and any other synthesizers).
4. **3a.4 — Unit tests with flat backend fixtures** — Cover flat
   `{ type, status, current, total, message, error }` plus `event: snapshot` /
   `event: cancelled`, not only nested mocks.

## Next steps

1. Decide normalize-at-API vs adapt-in-hook (3a.1); prefer the smaller blast
   radius if OpenAPI `Job` consumers expect nested shapes for REST but SSE is
   flat today.
2. Implement snapshot + cancelled listeners and terminal set updates (3a.2).
3. Thread `job_type` from mutation 202 payloads into active-job state (3a.3).
4. Replace or supplement nested-only tests with flat fixtures (3a.4); smoke
   OCR reload, export, and save-project overlays manually or via e2e if present.
5. Wave 3a can run **parallel** with Wave 1 export work per the continuation
   plan (no store-serialization coupling).

## What is NOT broken

- Job enqueue + handler execution (OCR reload, export, save, refine, rotate,
  etc.) on the backend.
- Cooperative cancel **API** (`POST /api/jobs/{id}/cancel`) and runner
  `CANCELLED` emit (FE may not observe it until 3a.2).
- `GET /api/jobs` / `GET /api/jobs/{id}` list/detail paths (separate residual
  `P1-JOBS-API` shape vs OpenAPI `Job` — not this issue’s primary fix, but
  related contract debt).
- Export dialog / other callers that already hold a job id and only need
  completion if they happen to work with partial events — still should be
  fixed under the unified contract.
- Non-job synchronous mutations and TanStack page mutations that do not use SSE.

## Resolution

Open. Implementation tasks: Wave **3a.1–3a.4** in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
(§ Wave 3a — Job SSE contract). Findings: **P1-JOB-SSE**, **P1-JOB-TYPE**.
