---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# GET /api/jobs returns runner Job fields, not OpenAPI Job shape

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — list/get/cancel JSON disagrees with declared OpenAPI Job
- **Affected version:** deep code review 2026-07-21 (`P1-JOBS-API`)
- **Read when:** building Jobs pill/drawer, consuming `GET /api/jobs`, or changing Job models / OpenAPI export.
- **Search terms:** GET /api/jobs, Job model, job_id, job_type, progress_current, OpenAPI Job, P1-JOBS-API, JobsPill.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`docs/plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md),
  [`src/pdomain_ocr_labeler_spa/api/jobs.py`](../../src/pdomain_ocr_labeler_spa/api/jobs.py),
  [`src/pdomain_ocr_labeler_spa/core/models.py`](../../src/pdomain_ocr_labeler_spa/core/models.py),
  [`src/pdomain_ocr_labeler_spa/core/jobs/runner.py`](../../src/pdomain_ocr_labeler_spa/core/jobs/runner.py)

## Summary

Routes under `/api/jobs` declare `response_model=Job` from `core.models.Job`
(`id`, `type`, nested `progress`, `updated_at`, …) but serialize with
`_runner_job_to_dict`, which dumps the **in-process runner** `Job`
(`job_id`, `job_type`, flat `progress_current` / `progress_total`, `message`,
timestamps). Generated OpenAPI / frontend types therefore do not match runtime
JSON. This is the **contract gate before Jobs pill** (Wave 5), analogous to
Wave 1.0 export-list shape mapping.

## Impact

- Any client that trusts OpenAPI `Job` (including a future JobsPill/Drawer)
  will read the wrong field names and miss progress structure.
- `response_model=Job` does not validate outgoing `JSONResponse` content, so
  the mismatch is silent at runtime and only surfaces when UI or typed clients
  consume the list.
- Blocks honest Jobs chrome (PGDP item 4) until the mapping is decided.

## Environment / versions

- Source: deep code review Wave 5; finding **P1-JOBS-API**.
- Related SSE shape issues (**P1-JOB-SSE**, **P1-JOB-TYPE**) are separate
  (Wave 3a) but share the same dual-Job-model root.
- SPA today uses per-job SSE + BusyOverlay, not the list endpoint for chrome.

## Evidence

1. **OpenAPI / public model** — `core.models.Job`:

   - `id: str`
   - `type: JobType`
   - `status: JobStatus`
   - `progress: JobProgress` (`current`, `total`, `current_page`, `message`)
   - `error_message`, `created_at`, `updated_at`

1. **Runner model** — `core.jobs.runner.Job`:

   - `job_id`, `job_type`, `status`, `project_id`, `payload`
   - `progress_current`, `progress_total`, `message`, `error_message`, `result`
   - `created_at`, `started_at`, `completed_at`

1. **API serialization** — `api/jobs.py`:

   ```python
   def _runner_job_to_dict(job: RunnerJob) -> dict[str, object]:
       return job.model_dump(mode="json")
   ```

   Used by `list_jobs`, `get_job`, and `cancel_job` while annotating
   `response_model=list[Job]` / `response_model=Job` with the **public** model.

1. **Plan text** — “Gate before Jobs pill Wave 5: map runner job dump → OpenAPI
   `Job` (`id`/`type`/`progress`) or change OpenAPI to match runner.”

## Root-cause hypotheses

1. **(Most likely) Two Job types never unified** — runner kept an internal
   record shape; public models mirrored pgdp-prep; handlers dump runner dicts
   without an adapter.
2. **JSONResponse bypasses response_model validation** — FastAPI does not coerce
   `JSONResponse(content=…)` through the declared Pydantic model, so the wrong
   shape shipped without test failure.
3. **SSE path evolved separately** — flat snapshot events (`current`/`total`)
   further diverged from nested OpenAPI progress; list endpoints followed the
   runner dump for convenience.

## Defects to fix

1. `GET /api/jobs` and `GET /api/jobs/{id}` emit runner field names, not OpenAPI
   `Job`.
2. Cancel response has the same dump mismatch despite `response_model=Job`.
3. No documented mapping (or OpenAPI change) from runner → public Job before UI
   work.
4. (Adjacent) FE job progress SSE expects nested shape — track under P1-JOB-SSE;
   fix list contract before Jobs pill either way.

## Next steps

1. **Contract step (like Wave 1.0):** write a short decision — either:
   - **A.** Adapter `_public_job(job) -> models.Job` with `id←job_id`,
     `type←job_type`, nested `progress`, etc., and return validated models; or
   - **B.** Change OpenAPI / `core.models.Job` to match runner dump and regenerate
     frontend types (`make openapi-export`).
2. Integration tests asserting list/get JSON keys match the chosen public shape.
3. Only then implement JobsPill/Drawer (PGDP item 4 / P2-JOBS-UI).
4. Coordinate with Wave 3a SSE unification so FE does not need three shapes.

## What is NOT broken

- Job submission (`202 {job_id}`), runner execution, and cooperative cancel
  control flow.
- In-memory job storage and SSE broker subscription mechanics.
- BusyOverlay progress via `useJobProgress` (broken for **shape** reasons under
  P1-JOB-SSE, not because list_jobs is missing).
- Export / save / OCR job handlers themselves.

## Resolution

Open. Must close as a Wave 5 **contract gate** before Jobs pill UI. Prefer one
documented mapping; do not half-ship the drawer against runner-only fields.
