# Runtime Flows

> **Status**: Active
> **Last updated**: 2026-05-31

Major data and control flows through the system. For module ownership see
[`module-map.md`](module-map.md); for endpoint shapes see
[`02-backend.md`](02-backend.md).

---

## Flow 1: App startup

```
pd-ocr-labeler-ui
  └─ __main__.py:main()
       ├─ parse CLI args
       ├─ build Settings (from env + args)
       └─ uvicorn.run("bootstrap:build_app", factory=True)
            └─ bootstrap.build_app(settings)
                 ├─ adapters: FilesystemStorage, NoneAuth, LocalDoctrOCR
                 ├─ AppState(settings, storage, auth, ocr_engine)  ← frozen dataclass
                 ├─ carriers: ActiveProjectCarrier, OCRConfigCarrier, SourceRootCarrier
                 ├─ lifespan:
                 │    ├─ write port to .pdlabeler-port
                 │    └─ pdomain-ops register_self()
                 ├─ middleware: RequestIdMiddleware, error handler
                 ├─ routers: all api/ routers mounted under /api/
                 └─ mounts: /image-cache (StaticFiles), / catch-all (SPA fallback)
```

uvicorn serves on `PDLABELER_HOST:PDLABELER_PORT` (default `127.0.0.1`, next free from 8080).

---

## Flow 2: Frontend startup

```
Browser → GET /
  └─ FastAPI catch-all → static/index.html
       └─ Vite bundle parses; React 19 mounts to #root
            └─ App.tsx
                 ├─ React Router (v7)
                 ├─ TanStack Query QueryClient
                 ├─ Zustand stores (dialog, rail, selection, worklist, ui-prefs, viewport)
                 └─ AppShell (pdomain-ui) — theme, font-scale, suite-siblings context
                      └─ Router matches / → RootPage
                           └─ GET /api/session-state
                                └─ last project found?
                                     ├─ yes → POST /api/projects/load
                                     │         └─ navigate to /projects/{id}/pages/pageno/1
                                     └─ no  → show project browser
```

---

## Flow 3: Page load and display

```
URL: /projects/:projectId/pages/pageno/:pageNo
  └─ ProjectPage mounts
       ├─ useProject(projectId) → GET /api/projects/{id}
       │    └─ project metadata cached in QueryClient
       │
       └─ usePage(projectId, idx0) → GET /api/projects/{id}/pages/{idx}
            └─ PagePayload:
                 ├─ page_record (metadata)
                 ├─ encoded_dims
                 └─ lines[]: LineMatch[]
                      └─ each LineMatch: WordMatch[] (OCR text, GT text, bbox, confidence, match status)

Rendering:
  ├─ Canvas: PageImageCanvas
  │    ├─ page bitmap from image URL
  │    └─ BBoxOverlay (Konva): word/line/block bboxes on selection layer
  │
  └─ Worklist: WordMatchView
       ├─ virtualises LineMatch[] (@tanstack/react-virtual)
       ├─ filtered by matchFilterStore
       └─ click bbox → selectionStore → RightPanel (WordDetail / LineDetail / BlockDetail)
```

---

## Flow 4: Word mutation (edit → save)

```
User edits GT text in word row or WordEditDialog
  └─ useWordMutations.mutate()
       └─ POST /api/projects/{id}/pages/{idx}/words/{wIdx}/text  { text: "..." }
            └─ backend: page_state.set_word_gt_text(...)
                 └─ returns updated PagePayload
                      └─ TanStack Query onSuccess:
                           └─ queryClient.invalidateQueries(['page', projectId, idx0])
                                └─ refetch → canvas + worklist re-render
```

GT changes are held in-memory on the server until explicit Save Page
(`POST .../save`), which flushes to the `UserPageEnvelope` v2.1 JSON sidecar.

---

## Flow 5: Async job (Reload OCR example)

```
User triggers "Reload OCR"
  └─ POST /api/projects/{id}/pages/{idx}/reload-ocr
       └─ backend:
            ├─ Job(id, type=RELOAD_OCR, status=PENDING) created
            ├─ coroutine started in JobRunner
            └─ 202 Accepted  { job_id: "..." }

Frontend:
  └─ useJobProgress(job_id)
       ├─ polls GET /api/jobs/{job_id}
       └─ opens SSE EventSource: GET /api/jobs/{job_id}/events

Job coroutine:
  PENDING → RUNNING → (progress events) → COMPLETE

useJobCompletionInvalidation:
  └─ on COMPLETE → queryClient.invalidateQueries(['page', ...])
       └─ page data refetches with new OCR results
```

Same shape applies to Refine Bboxes and Export (see Flows 6 and below).

---

## Flow 6: Export

```
User opens ExportDialog, selects scope + style filters
  └─ POST /api/projects/{id}/export
       └─ backend creates EXPORT job (same JobRunner as Flow 5)
            └─ job handler:
                 ├─ generates XHTML export file on disk
                 └─ writes ExportManifest

Frontend polls job → COMPLETE
  └─ GET /api/projects/{id}/exports → manifest list with file paths
```

---

## Flow 7: Frontend dev mode (Vite proxy)

```
Backend starts on port N
  └─ writes N to .pdlabeler-port

vite.config.ts reads .pdlabeler-port (fallback: 8080)
  └─ Vite dev server on :5173
       ├─ serves SPA via HMR
       └─ proxies /api/* and /image-cache/* → http://localhost:N

Browser at :5173
  └─ API calls → Vite proxy → FastAPI backend
```

Run with `make dev` (uvicorn --reload) in terminal 1 and `make frontend-dev` (Vite) in terminal 2.
