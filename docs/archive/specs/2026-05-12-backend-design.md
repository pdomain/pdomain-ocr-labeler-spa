# pdomain-ocr-labeler-spa: FastAPI Backend

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#8

## TL;DR

The Python backend for `pdomain-ocr-labeler-spa`: a `build_app(settings)` FastAPI factory,
10 resource-organized routers, three adapter protocols (IStorage / IAuth / IOCREngine),
an in-process job runner with SSE progress, and a `lifespan` hook that discovers projects
and restores session on startup. All endpoints declared in `specs/02-backend.md` are the
canonical contract; the spec wins over the implementation if they diverge.

## Context

The backend replaces NiceGUI's server-rendered event model with a stateless FastAPI REST
surface that any HTTP client (SPA, driver agent, CLI) can consume. It mirrors the
`pdomain-prep-for-pgdp` architecture (`build_app` factory, `app.state` DI, `IStorage`
adapter) with three key differences:

1. **OCR adapter axis.** `IOCREngine` replaces pgdp-prep's processing pipeline. Only
   `local_doctr` is wired for v1; `modal` and `shared_container` are `NotImplementedYet`
   stubs.
2. **No database adapter.** Single-user filesystem persistence is sufficient; no ORM or
   migrations needed.
3. **In-process job runner** (no distributed queue). Long-running operations (OCR reload,
   refine-bboxes, save-project, export) run in `asyncio.create_task` within the server
   process; progress is broadcast via SSE.

The three-level state tree (`AppState → ProjectState → PageState`) lives in-process on
`app.state`, giving O(1) access without serialisation overhead for hot-path operations
(word validate, selection update).

## Constraints

- **`build_app` is pure.** Same `Settings` always produces the same wired dependency
  graph. No global singletons; every test wires its own `Settings`. Errors at wire time
  are `RuntimeError`, not lazy failures at request time.
- **URL stability for the driver contract.** Every route prefix and path parameter
  convention is frozen once shipped; renaming requires a coordinated update to
  `specs/13-driver-contract.md` and the driver agent. API routes use 0-based `page_index`;
  driver-facing SPA routes use 1-based `pageno/{n}`.
- **Adapter protocol isolation.** Route handlers never call `local_doctr` or filesystem
  paths directly; all I/O goes through `IStorage` / `IAuth` / `IOCREngine` so the seam
  for future backends (S3, JWT, Modal) is preserved.
- **One mutation per HTTP request.** No batching multiple state transitions in a single
  handler; each endpoint does one logical operation + one autosave side-effect.
- **Autosave is server-side.** After any mutation the handler writes through to disk
  (cached lane) without a client-side debounce timer.
- **`pdomain-book-tools` only.** No direct DocTR or OpenCV imports in the backend; all OCR
  and layout primitives come from `pd_book_tools`.

## Decision

### Module layout

```
src/pd_ocr_labeler_spa/
├── __init__.py          # version via importlib.metadata
├── __main__.py          # console script entry → uvicorn
├── bootstrap.py         # build_app(settings) factory
├── settings.py          # Settings (pydantic-settings, PDLABELER_ prefix)
├── api/                 # routers + middleware + dependencies
│   ├── dependencies.py  # get_app_state, get_storage, get_user Depends helpers
│   ├── middleware/      # RequestIdMiddleware, error_handler
│   ├── projects.py      # /api/projects/*
│   ├── pages.py         # /api/projects/{pid}/pages/*
│   ├── words.py         # /api/projects/{pid}/pages/{idx}/words/*
│   ├── lines.py         # /api/projects/{pid}/pages/{idx}/lines/*
│   ├── paragraphs.py    # /api/projects/{pid}/pages/{idx}/paragraphs/*
│   ├── refine.py        # /api/projects/{pid}/pages/{idx}/refine
│   ├── ocr_config.py    # /api/ocr-config
│   ├── export.py        # /api/projects/{pid}/export
│   ├── jobs.py          # /api/jobs/*
│   └── notifications.py # /api/notifications/stream (SSE)
├── adapters/            # IStorage / IAuth / IOCREngine implementations
├── core/                # AppState, ProjectState, PageState, models, persistence, jobs
└── static/              # built SPA (.gitignored)
```

### App factory (`bootstrap.py`)

`build_app(settings)` wires in order: logging → adapters → job runner → `AppState` →
`lifespan` → FastAPI → CORS → RequestIdMiddleware → error handlers → routers → static
mounts. The `lifespan` async context manager runs `app_state.startup()` (project
discovery + session restore) and `runner.run_forever()` as a background task on enter;
graceful shutdown on exit.

### Settings (`settings.py`)

Pydantic-settings with `PDLABELER_` prefix. Key fields: `host`, `port`, `log_format`,
`config_root`, `data_root`, `cache_root`, `storage_backend`, `auth_mode`, `ocr_engine`,
`source_projects_root`, `cli_project_dir`, `frontend_dev_url`, `mode`. Read once in
`__main__.main()` and passed to `build_app`; no post-construction mutation.

### Routers and URL conventions

10 routers, each in its own module, all prefixed `/api/`:

- `projects_router` at `/api/projects`
- `pages_router` at `/api/projects/{project_id}/pages`
- `words_router` at `/api/projects/{project_id}/pages/{page_index}/words`
- `lines_router`, `paragraphs_router`, `refine_router` — sibling to words
- `ocr_config_router` at `/api/ocr-config`
- `export_router` at `/api/projects/{project_id}/export`
- `jobs_router` at `/api/jobs`
- `notifications_router` at `/api/notifications`

`page_index` in API URLs is **0-based**. Driver-facing SPA URLs use 1-based
`/projects/{id}/pages/pageno/{n}`; unqualified `/projects/{id}/pages/{n}` redirects to
`pageno/{n}`. Legacy paths (`/project/`, `/project/.../page/`) get `301` redirects.

### Endpoint contract

Full list in `specs/02-backend.md §5`. Key design points:

- Long-running operations (`reload-ocr`, `refine-bboxes`, `save-all`, `export`) return
  `202 Accepted` with `{job_id}`; callers open `EventSource(/api/jobs/{id}/events)`.
- `GET /api/projects/{pid}/pages/{idx}` lazily ensures the page is loaded (cache → saved
  → OCR → fallback) on every call; no separate "load page" step for the SPA.
- `POST /api/projects/load` eagerly fetches the first `PagePayload` synchronously before
  returning, eliminating a waterfall round-trip.
- `DELETE /api/projects/{pid}` forgets the project from in-memory state without touching
  disk.

### Job runner and SSE

`core/jobs/runner.py` — in-process `asyncio`-based runner. Each long job runs in an
`asyncio.create_task`; the handler posts `JobProgress` events to a `JobEventBroker` (
per-job `asyncio.Queue`). `GET /api/jobs/{id}/events` streams SSE until the terminal
`complete` or `error` event. The broker discards the queue after the terminal event.

### Error handling

`api/middleware/error_handler.py` catches: `404 ProjectNotFound`, `404 PageNotFound`,
`409 ImageDrift`, `422 IncompatibleEnvelope`. All errors return
`{"detail": "<message>", "error_code": "<stable_code>"}`. Unhandled exceptions become
`500` with a request-id for log correlation.

## Contract / Acceptance

- `make test` (pytest) passes: unit tests for `build_app`, `AppState`, all route
  handlers, job runner SSE cycle.
- `GET /healthz` returns `200 {"status": "ok", "version": "..."}`.
- `make openapi-export` regenerates `frontend/src/api/types.ts` with no drift.
- Legacy-path redirects: `GET /project/foo` → `301` → `/projects/foo`.
- Job SSE: `POST /api/projects/{pid}/pages/{idx}/reload-ocr` → `202 {job_id}`;
  `EventSource` receives `progress` events followed by terminal `complete`.
- `lifespan` startup: if `session_state.json` exists and points to a valid project dir,
  `app_state.current_project_id` is set without an explicit `/api/projects/load` call.

## Trade-offs considered

**In-process job runner vs distributed queue (pgdp-prep pattern).** A distributed queue
(Redis, Celery) would survive server restarts and support multiple workers. The labeler
has no multi-user requirement and single-page operations complete in seconds; the
complexity is unjustified. In-process `asyncio` task chosen.

**Eager first-page fetch in `LoadProjectResponse` vs lazy.** Lazy would return faster
but cause a waterfall round-trip in the UI. Eager chosen: project load is infrequent;
paying the OCR cost upfront avoids a spinner on the immediately-displayed first page.

**0-based API page_index vs 1-based.** 0-based is natural for Python list indexing and
simplifies the `PageState` array access. The driver-facing URL is 1-based for
human-readability. Convention documented in `specs/13-driver-contract.md`.

**Route-per-resource vs route-per-feature.** Per-resource gives predictable REST
semantics and makes the OpenAPI schema navigable. Per-feature would require fewer files
for tightly-coupled actions (e.g., refine + OCR) but obscures the resource boundary.
Per-resource chosen.

## Consequences

- Any new long-running operation requires a new `JobType` enum value and a handler in
  `core/jobs/handlers.py`; no changes to the SSE infrastructure.
- The driver agent must not rely on job completion timing; it must poll
  `/api/jobs/{id}/events` until the terminal event.
- Adding a new adapter backend (S3, Modal) requires only a new implementation module
  in `adapters/`; `bootstrap.py` selects via `settings.storage_backend` /
  `settings.ocr_engine`.
- `frontend_dev_url` must be set at construction time via CLI arg, not mutated after
  `build_app` returns (fixed in this SPA; pgdp-prep allowed post-construction mutation).

## Open questions

None.

## References

- `specs/02-backend.md` — legacy feature-description doc with full endpoint list (§5)
- `specs/01-data-models.md` — all request/response Pydantic shapes
- `specs/13-driver-contract.md` — URL invariants and testid contract
- `specs/09-persistence.md` — on-disk lanes and `UserPageEnvelope` schema
- `../pdomain-prep-for-pgdp/src/pd_prep_for_pgdp/bootstrap.py` — reference `build_app`
  implementation
