---
kind: architecture
status: built
owner: maintainers
created: 2026-05-31
last_verified: 2026-11-13
---

# Runtime Flows

These are the current local data/control paths. [Module ownership](module-map.md) supplies navigation.

## Startup and serving

The console script builds FastAPI through `bootstrap.py::build_app`. The factory wires app services,
active-project/page state, middleware, routers, blob/image-cache routes and the reserved-path SPA fallback.
The bundled SPA reads `/env.js`; unknown client routes receive the shell without masking reserved API routes.

## Project and page loading

The root screen selects an existing source-root project. The labeler does not implement the older shared
managed-library picker/copy-import proposal. Project navigation reads current memory/store state; a genuine
cold miss returns a load job identifier. The image pane follows SSE stage/error updates while the shell stays
interactive. Warm stored pages create no load job. Predictor preparation and OCR share one stage.
See [page loading/history](29-page-loading-and-history.md).

## Editing and persistence

The workbench uses the actual line/word-index GT route in `api/words.py`, then invalidates page queries.
Page mutations serialize current content and sidecars into the project event/blob store under the per-page
lock. An unsuccessful store write is an explicit failure. Selection remains session-only state. Explicit Save
uses generation guards and dirty-page tracking; Reload reads the current saved head.

## Jobs and notifications

Action callers track queued/running/terminal lifecycle through the public Job payload plus `event`
discriminator. Job kind is `type`, not the event name. Callers refresh affected queries after completion and
post cancellation through `/api/jobs/{job_id}/cancel`. Server notifications and direct client toasts are
separate channels; a client toast need not have an SSE counterpart.

## Export

Export resolves saved pages/styles store-first and writes DocTR training artifacts, image crops, recognition
labels and the manifest. It is not an XHTML pipeline. Complete text and typography review gate correction
bundles separately; an active edited page is not automatically a reviewed sample. Current layout, saved export
history and CLI options are documented in [export](10-export.md). Training and source ingestion stay in their
existing owning repositories.

## Evidence

- Code: `bootstrap.py`, `api/pages.py`, `api/words.py`, `core/page_state.py`, `core/persistence/page_store.py`,
  `core/jobs/handlers/export.py`; frontend `ProjectPage.tsx`, `usePage.ts`, `useJobProgress.ts`.
- Tests: `tests/integration/test_load_page_job.py`, `test_save_page_route_roundtrip.py`,
  `test_export_list_and_cli_store.py`, and `tests/unit/api/test_typography_corrections.py`.
- Verified: 2026-11-13 by source and test inspection. This does not claim a fresh complete browser exercise.
