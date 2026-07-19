---
kind: architecture
status: built
owner: maintainers
created: 2026-05-31
last_verified: 2026-07-13
---

# Module Map

> **Status**: Active
> **Last updated**: 2026-05-31

Source-level structure and ownership. For goals, non-goals, and tech stack see
[`00-overview.md`](00-overview.md).

---

## Backend package: `src/pdomain_ocr_labeler_spa/`

### Top-level modules

| Module | Role |
|--------|------|
| `bootstrap.py` | FastAPI app factory `build_app(settings)` — wires logging → adapters → AppState → carriers → lifespan → middleware → routers → mounts |
| `settings.py` | `Settings(BaseSettings)`, env prefix `PDLABELER_`, all runtime config |
| `__main__.py` | CLI entry point (`pdomain-ocr-labeler-ui [project_dir] [options]`), uvicorn launcher |

### `api/` — FastAPI routers

One file per domain area:

| File | Endpoints |
|------|-----------|
| `projects.py` | project discovery, load, create |
| `pages.py` | page fetch, navigation |
| `words.py` | word GT text edits, validate, batch-validate |
| `lines_paragraphs.py` | line/paragraph mutations |
| `jobs.py` | job status, SSE event stream |
| `export.py` | DocTR export, manifest listing |
| `refine.py` | bbox refinement |
| `ocr_config.py` | OCR config read/write |
| `notifications.py` | SSE notification stream |
| `fs.py` | filesystem browsing (source root selection) |
| `healthz.py` | `GET /healthz` liveness probe |
| `env_js.py` | `GET /env.js` runtime config injection |
| `session_state.py` | last-opened project persistence |
| `normalize.py` | text normalization endpoint |
| `static_mounts.py` | `/image-cache` StaticFiles + SPA catch-all |
| `middleware/` | `RequestIdMiddleware`, error handler |

### `core/` — domain logic

| Module | Role |
|--------|------|
| `models.py` | All Pydantic request/response models |
| `app_state.py` | `AppState` frozen dataclass; injected via `Depends` |
| `project_state.py` | `ProjectState` — per-project in-memory state |
| `page_state.py` | `PageState` — per-page in-memory state, mutation methods |
| `active_project.py` | `ActiveProjectCarrier` FastAPI dependency |
| `ocr_config_state.py` | `OCRConfigCarrier` FastAPI dependency |
| `source_root_state.py` | `SourceRootCarrier` FastAPI dependency |
| `ocr/` | `predictor.py` (DocTR call site), `weights_resolver.py` |
| `jobs/` | `runner.py` (async `JobRunner`), `events.py` (SSE), `handlers/` (one file per job type: reload-OCR, refine, export, …) |
| `persistence/` | JSON/YAML disk I/O, atomic-rename save, `UserPageEnvelope` v2.1 read/write |
| `glyph/` | `bulk_mark.py`, `predictions.py` (M11 glyph annotation logic) |

### `adapters/` — pluggable protocols

| Module | Protocol | Production impl | Stubs |
|--------|----------|-----------------|-------|
| `auth/` | `IAuth` | `NoneAuth` | — |
| `ocr/` | `IOCREngine` | `LocalDoctrOCR` | `ModalOCR`, `SharedContainerOCR` (`NotImplementedYet`) |
| `storage/` | `IStorage` | `FilesystemStorage` | `S3Storage` (`NotImplementedYet`) |

---

## Frontend source root: `frontend/src/`

### `pages/`

| File | Route |
|------|-------|
| `RootPage.tsx` | `/` — project browser |
| `ProjectPage.tsx` | `/projects/:projectId/pages/pageno/:pageNo` — main labeling surface |
| `PerfTestPage.tsx` | `/perf-test` — developer perf harness |

### `components/`

Major groups:

| Folder / file | What it renders |
|---------------|-----------------|
| `PageImageCanvas/` | Host for Konva canvas + `BBoxOverlay`; image + bbox rendering |
| `LineCard.tsx` | Single line row in the worklist |
| `WordCell.tsx` | Single word chip inside a `LineCard` |
| `WordDetail.tsx` | Right-panel word detail view |
| `LineDetail.tsx` | Right-panel line detail view |
| `BlockDetail.tsx` | Right-panel block detail view |
| `dialogs/` | `WordEditDialog`, `ExportDialog`, `OCRConfigDialog`, others |
| `shell/` | `AppShell` wrapper, top toolbar, navigation |
| `right-panel/` | Panel host + section components |
| `drawer/` | Worklist, Hierarchy, Bulk-action drawer panels |
| `ui/` | Radix/shadcn primitive wrappers |

### `api/`

| File | Role |
|------|------|
| `ApiClient.ts` | Typed HTTP client wrapping `fetch`; all backend calls go here |
| `types.ts` | **Generated** from `make openapi-export` — 6,130 lines; never hand-edit |

### `stores/` — Zustand stores

| Store | Owns |
|-------|------|
| `dialog` | Which dialog is open and its payload |
| `rail` | Left-rail tab selection |
| `selection` | Currently selected word/line/block |
| `worklist` | Match-filter state (filter buttons above the worklist) |
| `ui-prefs` | Font scale, layer visibility, panel split positions |
| `viewport` | Canvas zoom / scroll position |

### `hooks/` — React Query hooks

| Hook | Server interaction |
|------|--------------------|
| `useProject` | `GET /api/projects/{id}` |
| `usePage` | `GET /api/projects/{id}/pages/{idx}` |
| `usePageMutations` | Save page, reload OCR, refine bboxes |
| `useLineMutations` | Line GT edits |
| `useWordMutations` | Word GT text, validate, bbox |
| `useJobProgress` | `GET /api/jobs/{id}` polling + SSE |
| `useNotificationStream` | `GET /api/notifications` SSE |
| `useGlobalHotkeys` | `react-hotkeys-hook` registration |
| `useRefineAvailable` | Feature-flag check for refine |
| `useLayerColors` | Palette/picker state bridge |

### `lib/`

| File | Role |
|------|------|
| `routes.ts` | Typed route builders (keeps URL shape in one place) |
| utilities | Misc helpers |

---

## Entry points

| Entry point | Module | Notes |
|-------------|--------|-------|
| `pdomain-ocr-labeler-ui` (console script) | `__main__:main` | CLI launch; parses args, calls uvicorn |
| `pdomain-ocr-labeler-spa-export` | `core.jobs.handlers.export_cli:main` | Headless export CLI |
| `build_app(settings)` | `bootstrap:build_app` | FastAPI factory for uvicorn + tests |

---

## Sibling dependencies

### Python

| Package | Min version | Used for |
|---------|-------------|----------|
| `pdomain-book-tools` | `>=0.14.1` | OCR page models, glyph annotations (`pdomain_book_tools.ocr.page`) |
| `pdomain-ops` | `>=0.11.2` | Suite bootstrap/routes, device preferences, shared paths, page records and aggregates, local persistence, provenance, and export schemas |

### npm

| Package | Version | Used for |
|---------|---------|----------|
| `@pdomain/pdomain-ui` | `^0.11.0` | `PageImageCanvas`, `AppShell`, `WordList`, shared primitives, status panels, and icons |

Evidence:

- Code: `pyproject.toml` and `frontend/package.json`
- Lockfiles: `uv.lock` and `frontend/pnpm-lock.yaml`
- Verified: 2026-07-19 against the current manifests and lockfiles

---

## Generated and build artefacts

| Path | How produced | Notes |
|------|-------------|-------|
| `frontend/src/api/types.ts` | `make openapi-export` | Never hand-edit; CI gates on no drift |
| `frontend/openapi.json` | `make openapi-export` | OpenAPI schema checked into repo |
| `frontend/dist/` | `make frontend-build` | Copied to `src/pdomain_ocr_labeler_spa/static/` |
| `src/pdomain_ocr_labeler_spa/static/` | `make frontend-build` | Bundled into wheel as package resources |
| `dist/*.whl` | `uv build --wheel` | Includes bundled SPA; `build_hooks/spa_check.py` refuses if `static/` is empty |
