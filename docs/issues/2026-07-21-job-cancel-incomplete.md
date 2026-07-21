---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Cooperative job cancel is incomplete outside export

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — Cancel marks the job cancelled but long page loops keep
  running
- **Affected version:** verified 2026-07-21 (Wave 3b code review)
- **Read when:** implementing or testing job cancel, BusyOverlay cancel,
  auto_rotate_all, or OCR-heavy job handlers.
- **Search terms:** P1-CANCEL, request_cancel, JobStatus.CANCELLED,
  auto_rotate_all, cooperative cancel, handle_export cancel.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  `src/pdomain_ocr_labeler_spa/core/jobs/runner.py`,
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/auto_rotate_all.py`,
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py`

## Summary

`JobRunner.request_cancel` marks a job `CANCELLED` and emits SSE, but handlers
must poll that status themselves. The export handler checks `JobStatus.CANCELLED`
each page and aborts (including partial output cleanup). `handle_auto_rotate_all`
iterates every page with OCR/rotate work and never inspects cancel status, so a
user “Cancel” leaves status cancelled while work continues until the loop
finishes. Other OCR-heavy handlers similarly lack per-iteration cancel checks.

Finding ID: **P1-CANCEL** (Wave 3b).

## Impact

- BusyOverlay / API cancel can report cancelled while CPU, disk rotation, and
  re-OCR still run for remaining pages.
- Auto-rotate-all on large projects cannot be stopped mid-batch after cancel.
- UI and job list disagree with actual handler progress (trust / ops issue).
- Partial rotations may still apply after the user believes the job stopped.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Verified by static read of job runner + handlers, 2026-07-21
- Job types: `export` (honors cancel), `auto_rotate_all` (does not),
  `reload_ocr` / `rotate_page` (single-shot / no page-loop cancel poll)
- Source plan:
  `docs/plans/2026-07-21-deep-code-review-continuation.md` (P1-CANCEL)

## Evidence

1. **Runner cancel is cooperative only** — status write + emit; task is not
   aborted:

```150:180:src/pdomain_ocr_labeler_spa/core/jobs/runner.py
    async def request_cancel(self, job_id: str) -> Job | None:
        """Cooperatively cancel a queued or running job.
        ...
        The running task is NOT forcibly stopped — handlers must periodically
        check their cancellation token.
        """
        ...
        cancelled = job.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "completed_at": datetime.now(UTC),
            }
        )
        self._jobs[job_id] = cancelled
        await self._emit(cancelled)
        return cancelled
```

1. **Export honors cancel each page:**

```677:684:src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py
        # Cooperative cancel check.
        current_job = runner._jobs.get(job.job_id)
        if current_job and current_job.status == JobStatus.CANCELLED:
            # rmtree partial output for all subfolders.
            project_export_root = data_root / _DOCTR_EXPORT_DIRNAME / project_id
            if project_export_root.exists():
                shutil.rmtree(project_export_root, ignore_errors=True)
            return
```

1. **`auto_rotate_all` page loop has no cancel check.** The body is
   `for page_idx in range(page_count):` with load → detect → rotate → re-OCR →
   progress update. There is no `JobStatus.CANCELLED` (or equivalent) read in
   `handlers/auto_rotate_all.py`. Grep of that file for cancel/CANCELLED is
   empty.

1. **Handlers package cancel usage is export-only.** Under
   `core/jobs/handlers/`, `status == JobStatus.CANCELLED` appears only in
   `export.py`. `reload_ocr.py` comments mention cancel/timeout interaction for
   the OCR thread, not a cooperative status poll for multi-page work.

1. **Plan disposition.** Deep-review plan lists P1-CANCEL under Wave 3b:
   “cooperative cancel mainly honored by export, not OCR/`auto_rotate_all`
   page loop.”

## Root-cause hypotheses

1. **(Most likely) Export was the first multi-page job with cancel UX;**
   auto_rotate_all shipped later without copying the per-iteration check
   pattern.
2. **Single-page OCR jobs** made cancel seem low-value; multi-page auto-rotate
   inherited the same non-checking style by default.

## Defects to fix

1. **`handle_auto_rotate_all` never checks `JobStatus.CANCELLED` in its page
   loop** — primary.
2. **Asymmetry:** `request_cancel` always succeeds for running jobs, but only
   export aborts work early.
3. **Optional follow-on:** add cheap cancel polls to other long-running /
   OCR-heavy handlers where a loop or multi-step await exists.

## Next steps

1. At the top of each `auto_rotate_all` page iteration (before OCR/rotate),
   read `runner._jobs[job.job_id]` (or a small helper) and return early on
   `CANCELLED` — mirror export.
2. Decide cleanup policy on cancel (leave already-rotated pages; do not claim
   full success notification).
3. Add a unit/integration test: start auto_rotate_all with a slow detect stub,
   `request_cancel`, assert remaining pages are not processed.
4. Audit `reload_ocr` / `rotate_page` / `refine` for multi-step waits; add
   checks only where cost is justified.

## What is NOT broken

- `request_cancel` API and CANCELLED status/SSE emission.
- Export cooperative cancel + partial output rmtree.
- Terminal-job idempotency of `request_cancel`.
- Auto-rotate-all functional path when cancel is not requested (rotate + re-OCR
  - metadata).

## Resolution

Open. Filed from deep code review Wave 3b (**P1-CANCEL**). No fix landed in
this documentation pass.
