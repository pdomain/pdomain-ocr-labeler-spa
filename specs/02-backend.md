# 02 — Backend (FastAPI)

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#8

The Python side of `pd-ocr-labeler-spa`. Ships as a single wheel; the
`pd-ocr-labeler-spa-ui` console script boots a `uvicorn` server that
serves both the API and the bundled SPA.

This spec is the source of truth for **every endpoint contract**. If
the implementation diverges, the spec is wrong — fix the spec first.

---

## 1. Module layout

```
src/pd_ocr_labeler_spa/
├── __init__.py             # version probe via importlib.metadata
├── __main__.py             # console-script entry → uvicorn
├── bootstrap.py            # build_app(settings)
├── settings.py             # pydantic-settings (PDLABELER_* env)
├── api/
│   ├── __init__.py
│   ├── healthz.py          # GET /healthz
│   ├── env_js.py           # GET /env.js
│   ├── dependencies.py     # get_storage / get_app_state / get_user
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── error_handler.py
│   │   └── request_id.py
│   ├── projects.py         # /api/projects/*
│   ├── pages.py            # /api/projects/{pid}/pages/*
│   ├── words.py            # /api/projects/{pid}/pages/{idx}/words/*
│   ├── lines.py            # /api/projects/{pid}/pages/{idx}/lines/*
│   ├── paragraphs.py       # /api/projects/{pid}/pages/{idx}/paragraphs/*
│   ├── refine.py           # /api/projects/{pid}/pages/{idx}/refine
│   ├── ocr_config.py       # /api/ocr-config
│   ├── export.py           # /api/projects/{pid}/export
│   ├── jobs.py             # /api/jobs/*
│   └── notifications.py    # /api/notifications/stream (SSE)
├── adapters/
│   ├── __init__.py
│   ├── storage/{base,filesystem,__init__}.py
│   ├── auth/{base,none_,__init__}.py
│   └── ocr/{base,local_doctr,modal,shared_container,__init__}.py
├── core/
│   ├── __init__.py
│   ├── models.py           # domain models (see 01-data-models.md)
│   ├── app_state.py        # AppState
│   ├── project_state.py    # ProjectState
│   ├── page_state.py       # PageState (the heavy-lifting class)
│   ├── line_match.py       # build LineMatch + WordMatch from a Page
│   ├── selection.py        # selection state mgmt
│   ├── notifications.py    # NotificationQueue (in-memory)
│   ├── jobs/{events,runner,handlers,__init__}.py
│   ├── persistence/
│   │   ├── user_page_envelope.py
│   │   ├── project_envelope.py
│   │   ├── ground_truth.py
│   │   ├── session_state.py
│   │   ├── image_cache.py
│   │   └── paths.py        # OS-aware roots
│   ├── ocr/
│   │   ├── predictor.py    # _get_or_create_predictor + cache
│   │   ├── provenance.py
│   │   └── model_selection.py
│   ├── pgdp_normalize.py   # PGDPResults wrapper
│   └── logging_config.py
└── static/                 # populated by `make frontend-build` (.gitignored)
```

Where this differs from pgdp-prep:

- No `dispatcher/`, no `core/queue/single_executor.py`. Single in-process
  job runner with an in-memory Job dict.
- Full `IOCREngine` adapter axis (D-018): `local_doctr | modal | shared_container`.
  Only `local_doctr` is wired in v1; the other two are `NotImplementedYet`
  Protocol stubs. Same shape as pgdp-prep, smaller v1 surface.
- No `database/` adapter axis. We don't need a DB.

---

## 2. App factory

`src/pd_ocr_labeler_spa/bootstrap.py` exports `build_app(settings: Settings | None = None) -> FastAPI`.

Order:

1. `configure_logging(settings.log_format)`.
2. Build adapters: `IStorage`, `IAuth`, `IOCREngine`.
3. Build `JobEventBroker` + `JobRunner`.
4. Build `AppState(settings, storage, auth, ocr_engine, broker, runner)`.
5. Define `lifespan` async ctx mgr that:
   - `await app_state.startup()` — discovers projects, restores session.
   - `task = asyncio.create_task(runner.run_forever())`
   - on shutdown: `await runner.stop()`, await task, `await app_state.shutdown()`.
6. `FastAPI(title="pd-ocr-labeler-spa", lifespan=lifespan)`.
7. Add `CORSMiddleware(allow_origins=["*"], ...)` (same shape as pgdp-prep).
8. Add `RequestIdMiddleware` last (becomes outermost).
9. Stash adapters + state on `app.state`.
10. Install error handlers + every router.
11. Install `/healthz` (BEFORE the SPA mount).
12. If `mode != "api_only"`, install `/env.js`, `/image-cache` static
    mount via the `IStorage` adapter ([D-019](17-decisions.md)), and SPA fallback.

The factory is pure — same `Settings` always produces the same wired
graph. Errors (e.g. unreadable data root) are loud `RuntimeError` at
wire time, not at request time.

---

## 3. Settings

`src/pd_ocr_labeler_spa/settings.py`. Pydantic-settings, env prefix
`PDLABELER_`.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDLABELER_")

    host: str = "127.0.0.1"
    port: int = 8080
    log_format: Literal["plain", "json"] = "plain"
    request_id_header: str = "X-Request-ID"

    config_root: Path = ...      # OS default; see 01-data-models §5
    data_root: Path = ...
    cache_root: Path = ...

    storage_backend: Literal["filesystem", "s3"] = "filesystem"   # s3 = NotImplementedYet (D-019)
    auth_mode: Literal["none"] = "none"
    ocr_engine: Literal["local_doctr", "modal", "shared_container"] = "local_doctr"  # modal/shared_container = NotImplementedYet (D-018)

    # Project discovery
    source_projects_root: Path | None = None
    cli_project_dir: Path | None = None        # set by --project-dir

    # Frontend dev
    frontend_dev_url: str | None = None        # e.g. http://localhost:5173

    # Job runner
    poll_interval_seconds: float = 0.5

    # OCR
    hf_repo: str = "CT2534/pd-ocr-models"
    no_prefetch: bool = False

    mode: Literal["normal", "api_only"] = "normal"   # api_only skips SPA mount
```

`Settings` is read **once** in `__main__.main()` and passed into
`build_app(settings)`. The `frontend_dev_url` flag is set via the
`--frontend-dev` CLI arg (override after construction is forbidden;
the SPA fixes the pgdp-prep
`__main__.py:44` mutation smell — close that gap).

---

## 4. Routers

Three top-level namespaces: `/api/...`, `/healthz`, `/env.js`. Static
asset mounts: `/image-cache/{key:path}` (read-only StaticFiles), `/`
(SPA).

URL invariant: every domain route is prefixed `/api/`. The driver-
visible SPA paths follow the **plural pgdp-prep convention** with
disambiguating sub-routes (D-030):

- `/projects/{id}` (canonical project root)
- `/projects/{id}/pages/index/{idx0}` (0-based, programmatic)
- `/projects/{id}/pages/pageno/{n}` (1-based, human-friendly)
- `/projects/{id}/pages/{n}` (unqualified) → `301 → pages/pageno/{n}`

Legacy paths (`/project/{id}`, `/project/{id}/page/{n}`) get
`301 Moved Permanently` redirects (Q-A4 may flip to 308 — pending).
See [`13-driver-contract.md`](13-driver-contract.md).

Routers are organised by resource, not by feature:

| Router | Prefix | File |
|---|---|---|
| `projects_router` | `/api/projects` | `api/projects.py` |
| `pages_router` | `/api/projects/{project_id}/pages` | `api/pages.py` |
| `words_router` | `/api/projects/{project_id}/pages/{page_index}/words` | `api/words.py` |
| `lines_router` | `/api/projects/{project_id}/pages/{page_index}/lines` | `api/lines.py` |
| `paragraphs_router` | `/api/projects/{project_id}/pages/{page_index}/paragraphs` | `api/paragraphs.py` |
| `refine_router` | `/api/projects/{project_id}/pages/{page_index}/refine` | `api/refine.py` |
| `ocr_config_router` | `/api/ocr-config` | `api/ocr_config.py` |
| `export_router` | `/api/projects/{project_id}/export` | `api/export.py` |
| `jobs_router` | `/api/jobs` | `api/jobs.py` |
| `notifications_router` | `/api/notifications` | `api/notifications.py` |

`page_index` in the URL is **0-based** to match the SPA's internal
representation. The driver-facing URL bar still uses 1-based
`/project/{id}/page/{n}` because that's a **SPA** route.

---

## 5. Endpoint contract (canonical list)

> Every endpoint declares request/response Pydantic models that map to
> the wire shapes in [`01-data-models.md`](01-data-models.md).

### 5.1 Health

- `GET /healthz` → `{"status": "ok", "version": "..."}`. Uptime probe.
- `GET /env.js` → `text/javascript`. Emits
  `window.__ENV__ = {API_BASE: "", API_TOKEN: null}`.

### 5.2 Projects

- `GET /api/projects` → `ListProjectsResponse`.
  Reads `Settings.source_projects_root`, scans for project dirs,
  returns sorted list with the currently selected one (last loaded or
  CLI-provided).
- `POST /api/projects/discover` → `ListProjectsResponse`.
  Force re-scan.
- `POST /api/projects/load` → `LoadProjectResponse`.
  Body: `LoadProjectRequest`. Resolves the path, loads project,
  optionally seeds the first page (synchronously OCRs if no cache). Saves
  session state. Sets `app_state.current_project_id`.
- `POST /api/projects/source-root` → `SetSourceProjectsRootResponse`.
  Body: `SetSourceProjectsRootRequest`. Persists to YAML config + re-scans.
- `GET /api/projects/{project_id}` → `Project`.
  Returns the loaded `Project` model.
- `DELETE /api/projects/{project_id}` → `204`.
  Closes (forgets) the project state in memory; doesn't touch disk.

### 5.3 Pages

- `GET /api/projects/{project_id}/pages/{page_index}?line_filter=unvalidated`
  → `PagePayload`.
  Lazily ensures the page is loaded (cache > saved > OCR), returns the
  full payload (record + line matches + image URL + overlay URLs +
  `has_edited_image`).
- `POST /api/projects/{project_id}/pages/{page_index}/save`
  → `SavePageResponse`.
  Body: `SavePageRequest`. Writes envelope + copies image; flips source
  badge to `filesystem`.
- `POST /api/projects/{project_id}/save-all`
  → `SaveProjectResponse`.
  Saves every loaded page. Long-running — wraps in a job (`SAVE_PROJECT`).
- `POST /api/projects/{project_id}/pages/{page_index}/load`
  → `PagePayload`.
  Re-loads from disk, discarding in-memory edits.
- `POST /api/projects/{project_id}/pages/{page_index}/reload-ocr`
  → `202` `JobResponse{job_id}`.
  Body: `ReloadOCRRequest`. Long-running; SSE for progress.
- `POST /api/projects/{project_id}/pages/{page_index}/rematch-gt`
  → `PagePayload`.
  Synchronous. Wipes per-word GT, re-runs page-wide alignment.
- `POST /api/projects/{project_id}/pages/{page_index}/erase-pixels`
  → `PagePayload`.
  Body: `ErasePixelsRequest`. In-memory image mutation. **Doesn't**
  touch the on-disk source image — the edited image is only used for
  Reload OCR (Edited).
- `GET /api/projects/{project_id}/pages/{page_index}/edited-image`
  → `200 image/png` (or `404` if not edited).
  Returns the in-memory edited bytes for verification.

### 5.4 Words

- `POST /.../words/{line_index}/{word_index}/ground-truth`
  → `WordMatch`. Body: `UpdateWordGroundTruthRequest`.
- `POST /.../words/{line_index}/{word_index}/style`
  → `WordMatch`. Body: `ApplyStyleRequest`.
- `POST /.../words/{line_index}/{word_index}/component`
  → `WordMatch`. Body: `ApplyComponentRequest`.
- `POST /.../words/{line_index}/{word_index}/validate`
  → `WordMatch`. Body: `ToggleValidatedRequest`.
- `POST /.../words/validate-batch`
  → `PagePayload`. Body: `ValidateBatchRequest`. Single batched
  mutation, single autosave (legacy `set_words_validated` shape).
- `POST /.../words/add`
  → `PagePayload`. Body: `AddWordRequest`.
- `POST /.../words/{line_index}/{word_index}/rebox`
  → `WordMatch`. Body: `ReboxWordRequest`.
- `POST /.../words/{line_index}/{word_index}/nudge`
  → `WordMatch`. Body: `NudgeBboxRequest`.
- `POST /.../words/{line_index}/{word_index}/split`
  → `PagePayload`. Body: `SplitWordRequest`.
- `POST /.../words/{line_index}/{word_index}/merge`
  → `PagePayload`. Body: `MergeWordsRequest`.
- `POST /.../words/{line_index}/{word_index}/erase-pixels`
  → `WordMatch`. Body: `ErasePixelsRequest`. Word-scoped erase
  (operates on the page-level image, scoped to bbox).
- `DELETE /.../words/{line_index}/{word_index}` → `PagePayload`. Single-word delete.
- `POST /.../words/delete-batch` → `PagePayload`. Body: `DeleteScopeRequest` with `scope="word"`.
- `POST /.../words/style-batch`
  → `SavePageResponse`. Body: `{ style: str, scope: "whole" | "part", word_keys: list[WordKey] }`.
  Set the style tag for all specified words in one shot. Used by the toolbar Apply Style
  button ([`06-toolbar-actions.md`](06-toolbar-actions.md) §3).
- `POST /.../words/component-batch`
  → `SavePageResponse`. Body: `{ component: str, enabled: bool, word_keys: list[WordKey] }`.
  Set or clear a component tag for all specified words in one shot. Used by the toolbar
  Apply Component and Clear Component buttons ([`06-toolbar-actions.md`](06-toolbar-actions.md) §3).
- `POST /.../words/{line_index}/{word_index}/crop`
  → `WordMatch`. Body: `{ side: "above" | "below" | "left" | "right", marker_x: int, marker_y: int }`.
  Clip the word's bbox at the click marker coordinate. Used by the Crop row in the word
  edit dialog ([`07-word-edit-dialog.md`](07-word-edit-dialog.md) §3.5 / §4.4).
- `POST /.../words/{line_index}/{word_index}/refine-bbox`
  → `WordMatch`. Body: `{}` (no body). Re-run bbox refinement for a single word using
  the current OCR model. Dialog re-renders with the updated bbox preview
  ([`07-word-edit-dialog.md`](07-word-edit-dialog.md) §3.6).
- `POST /.../words/{line_index}/{word_index}/expand-and-refine-bbox`
  → `WordMatch`. Body: `{ margin_px: int }`. Expand the word's bbox by `margin_px` then
  refine. Paired with the Expand + Refine button in the word edit dialog
  ([`07-word-edit-dialog.md`](07-word-edit-dialog.md) §3.6).

`PagePayload` is returned for any operation that may have changed
counts/positions of other words (split, merge, add, batch-validate,
delete). Single-word style/validate/nudge/crop/refine return just the updated
`WordMatch` so the SPA can apply a targeted reconciliation.

### 5.5 Lines

- `POST /.../lines/{line_index}/copy-gt` → `PagePayload`. Body: `CopyLineGtRequest`.
- `POST /.../lines/copy-gt-batch`
  → `SavePageResponse`. Body: `{ line_indices: list[int], direction: "gt_to_ocr" | "ocr_to_gt" }`.
  Copy ground truth from OCR (or vice-versa) for a set of lines in one shot. The toolbar
  sends `line_indices` = all matched line indices on the page for the page-scope GT↔OCR
  actions, or the indices for the selected paragraph for paragraph-scope
  ([`06-toolbar-actions.md`](06-toolbar-actions.md) §2).
- `POST /.../lines/{line_index}/validate` → `PagePayload`. Body: `ToggleValidatedRequest`.
- `POST /.../lines/{line_index}/split-after-word`
  → `PagePayload`. Body: `SplitLineAfterWordRequest`.
- `POST /.../lines/{line_index}/split-with-selected-words`
  → `PagePayload`. Body: `SplitLineWithSelectedWordsRequest`.
- `POST /.../lines/merge` → `PagePayload`. Body: `MergeScopeRequest{scope: "line"}`.
- `POST /.../lines/delete-batch` → `PagePayload`. Body: `DeleteScopeRequest{scope: "line"}`.

### 5.6 Paragraphs

- `POST /.../paragraphs/merge` → `PagePayload`. Body: `MergeScopeRequest{scope: "paragraph"}`.
- `POST /.../paragraphs/{paragraph_index}/split-after-line`
  → `PagePayload`. Body: `SplitParagraphAfterLineRequest`.
- `POST /.../paragraphs/group-selected-words`
  → `PagePayload`. Body: `GroupSelectedWordsIntoNewParagraphRequest`.
- `POST /.../paragraphs/delete-batch` → `PagePayload`. Body: `DeleteScopeRequest{scope: "paragraph"}`.

### 5.7 Refine bboxes

- `POST /.../refine` → `202 JobResponse` for page-scope, `PagePayload`
  for selection-scope. Body: `RefineScopeRequest`.
  - `scope="page"` always queues a job (SSE).
  - `scope="paragraph|line|word"` runs synchronously.

### 5.8 OCR config

- `GET /api/ocr-config` → `GetOCRConfigResponse`.
- `POST /api/ocr-config/models` → `GetOCRConfigResponse`. Body: `SetOCRModelsRequest`.
- `POST /api/ocr-config/rescan` → `GetOCRConfigResponse`.

### 5.9 Export

- `POST /api/projects/{project_id}/export` → `202 ExportResponse{job_id}`.
- `GET /api/projects/{project_id}/exports` → list of past exports
  (best-effort, read from disk).

### 5.10 Jobs

- `GET /api/jobs` → `list[Job]` (in-memory only).
- `GET /api/jobs/{job_id}` → `Job`.
- `GET /api/jobs/{job_id}/events` → `text/event-stream`. SSE: first
  frame = current snapshot; subsequent = broker events; ends on
  terminal state. (Verbatim port from pgdp-prep
  `api/gpu/jobs.py:132-176`.)
- `POST /api/jobs/{job_id}/cancel` → `Job`. Cooperative cancel; only
  valid for `queued` / `running`.

### 5.11 Notifications

- `GET /api/notifications/stream` → `text/event-stream`. SSE for the
  global notification queue. Replaces the legacy 50ms-poller pattern;
  the SPA pulls from this stream and feeds `sonner` toasts.
- `POST /api/notifications/{id}/dismiss` → `204`. Server forgets the
  notification (for test purposes only).

---

## 6. Dependencies (FastAPI `Depends`)

`api/dependencies.py`:

```python
def get_settings(request: Request) -> Settings:
    return request.app.state.settings

def get_storage(request: Request) -> IStorage:
    return request.app.state.storage

def get_auth(request: Request) -> IAuth:
    return request.app.state.auth

def get_ocr_engine(request: Request) -> IOCREngine:
    return request.app.state.ocr_engine

def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state

def get_job_runner(request: Request) -> JobRunner:
    return request.app.state.job_runner

def get_job_events(request: Request) -> JobEventBroker:
    return request.app.state.job_events

async def get_user(request: Request) -> UserContext:
    auth: IAuth = request.app.state.auth
    creds = await HTTPBearer(auto_error=False)(request)
    try:
        return await auth.verify(creds)
    except AuthError as e:
        raise HTTPException(401, str(e))
```

Routes consume:

```python
@router.get("/{project_id}/pages/{page_index}", response_model=PagePayload)
async def get_page(
    project_id: str,
    page_index: int,
    line_filter: LineFilter = LineFilter.UNVALIDATED,
    user: UserContext = Depends(get_user),
    state: AppState = Depends(get_app_state),
) -> PagePayload:
    ...
```

`get_user` is consumed by every route; `auth.none_` returns the same
anonymous `UserContext("local", "Local User")` for every call
([D-005](17-decisions.md)).

---

## 7. Adapter Protocols

### `IStorage`

`adapters/storage/base.py`. Same shape as pgdp-prep
`adapters/storage/base.py:17-37`:

```python
class IStorage(Protocol):
    async def get_bytes(self, key: str) -> bytes: ...
    async def put_bytes(self, key: str, data: bytes) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> None: ...
    async def list_keys(self, prefix: str) -> list[str]: ...
    def presign_put(self, key: str, *, expires_in: int = 600) -> str: ...
```

`filesystem` impl wraps `anyio.Path` with the path-traversal guard
(verbatim port from pgdp-prep). `presign_put` returns
`f"/cdn/{key}"` — but `pd-ocr-labeler-spa` doesn't expose a CDN PUT
endpoint (the SPA never uploads files). The method is implemented but
unused. Keep the seam.

### `IAuth`

`adapters/auth/base.py`:

```python
class IAuth(Protocol):
    async def verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext: ...

class UserContext(BaseModel):
    user_id: str
    display_name: str
```

`none_.py` returns `UserContext("local", "Local User")` for any input.

### `IOCREngine`

`adapters/ocr/base.py`:

```python
class IOCREngine(Protocol):
    async def ocr_page(
        self,
        image: numpy.ndarray,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]: ...
```

`local_doctr.py` wraps
`pd_book_tools.ocr.document.Document.from_image_ocr_via_doctr` and a
predictor cache (`_get_or_create_predictor`).

`modal.py` and `shared_container.py` are scaffolded **stubs** that
raise `NotImplementedYet("modal OCR adapter not yet wired")` from
their `ocr_page` method. The Protocol is real; the wiring isn't.
This satisfies D-018 without doing premature work — when off-machine
OCR is needed, only the impl bodies need filling in.

---

## 8. Error handling

`api/middleware/error_handler.py`. Verbatim port of pgdp-prep with one
addition: `BoundingBox.is_geometry_normalization_error` → `422
geometry_error`.

Handler chain:

1. `StarletteHTTPException` → original status, `error="http_<n>"`.
2. `RequestValidationError` → `400 validation_error`, `details = exc.errors()`.
3. `BoundingBoxGeometryError` (custom exception in `core/exceptions.py`)
   → `422 geometry_error`.
4. `Exception` (catch-all) → `500 internal_error`, `details=` last 3
   traceback lines, log via `logger.exception(...)`.

The SPA's `client.ts` parses `{error, message, details}` uniformly.

---

## 9. RequestId + structured logging

Verbatim port from pgdp-prep:

- `api/middleware/request_id.py` — ASGI middleware reading/echoing
  `X-Request-ID`, minting `uuid4().hex` if absent, stamping a
  `ContextVar`.
- `core/logging_config.py` — JSON / plain formatter selectable via
  `Settings.log_format`. `RequestIdFilter` injects the contextvar.
  Idempotent: removes previous handlers tagged
  `_pdlabeler_managed = True` so `--reload` doesn't double-log.

Per-route audit log (closes pgdp-prep gap):

- `request_start` info log on entry (path, method, request_id).
- `request_end` info log on exit (status, duration_ms).

---

## 10. SPA / static serving

`bootstrap._mount_static_frontend(app, settings)`:

- Skipped when `settings.frontend_dev_url` is set.
- Resolves `pd_ocr_labeler_spa/static/` via `importlib.resources.files()`.
- Defines a manual catch-all `/{full_path:path}` that:
  - 404s for reserved prefixes (`/api/`, `/healthz`, `/env.js`,
    `/docs`, `/redoc`, `/openapi.json`, `/image-cache/`) so backend
    bugs aren't masked by the SPA shell;
  - Serves a real file under `static/<path>` if it exists (with a
    traversal guard via `resolve()`-then-`relative_to`);
  - Falls back to `static/index.html` with `Cache-Control: no-store`
    so the dev-loop reload doesn't pick up a stale shell (B-62).
- The catch-all is registered LAST so it doesn't shadow real routes.

(We deliberately do NOT use `StaticFiles(directory=path, html=True)`:
it has no reserved-prefix carve-out, no `Cache-Control: no-store` on
`index.html`, and its missing-dir behaviour is a `RuntimeError` at
mount time rather than a graceful 404 with a "run `make
frontend-build`" hint.)

Image cache: served via `IStorage` adapter (D-019) at
`/image-cache/{key:path}`. The filesystem adapter reads from
`<cache_root>/page-images/`; the S3 adapter is `NotImplementedYet`.
Read-only over HTTP — the server is the only writer. Path renamed
from legacy `/_word_image_cache/` to `/image-cache/` (cleaner, no
leading underscore). The driver agent doesn't reference this path;
only the SPA does.

---

## 11. Job runner

In-process. Simpler than pgdp-prep because we don't need batch jobs
or persistence across restarts.

- `core/jobs/events.py`: `JobEventBroker` — async fan-out keyed by
  `job_id`. Same shape as pgdp-prep `core/job_events.py:27-67`.
- `core/jobs/runner.py`: `JobRunner` —
  - Has an in-memory `dict[str, Job]`.
  - `submit(job_type, payload, project_id)` returns a job_id and
    enqueues onto an `asyncio.Queue`.
  - `run_forever()` consumes from the queue, dispatches to a handler
    via `_HANDLERS: dict[JobType, Handler]`, calls `_emit(updated)`
    after every progress update.
  - `cancel(job_id)` flips a `CancellationToken`; handlers check it
    every iteration.
- `core/jobs/handlers.py`:
  - `refine_bboxes_page` (one Page → many Word.bbox.refine calls)
  - `expand_refine_bboxes_page`
  - `reload_ocr_page`
  - `export` (DocTRExportOperations driver)
  - `save_project` (iter pages)
  - `refine_bboxes_project` (iter pages → refine each)

No SQLite. No batch dispatcher. No per-owner enumeration. The job
table is in-memory and lost on server restart — but the on-disk state
(envelopes + cache) is the durable record, not the job runner.

---

## 12. CORS / middleware

CORS: `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`.
Same as pgdp-prep. Acceptable because the SPA serves from the same
origin in production; wide setting unblocks Vite-dev (5173 → 8080).

Middleware order (Starlette applies outermost first):

1. `RequestIdMiddleware` (added last → outermost)
2. `CORSMiddleware`

No additional middleware in v1.

---

## 13. Background discovery + restoration

In `app_state.startup()`:

1. Read YAML config; resolve `source_projects_root`.
2. Scan for project subdirectories.
3. Read `session_state.json`. If `last_project_path` exists and is a
   project, eagerly load it + restore `last_page_index`. Same restore
   contract as legacy (`app.py:_try_restore_session:437`).
4. If `Settings.cli_project_dir` is set, override the restore — load
   the CLI dir.

Discovery runs in `await app_state.startup()` so the very first
`GET /api/projects` is fast. Page-loading is still lazy.

---

## 14. Testing seam

`tests/conftest.py`:

- `settings` fixture: filesystem storage, `auth_mode=none`, hermetic
  tmpdir for config/data/cache, no `frontend_dev_url`.
- `client` fixture: `TestClient(build_app(settings))` as ctx mgr.
- `gpu_available` boolean for OCR-conditional tests.
- A frozen labeled-project fixture under `tests/fixtures/projects/`
  copied into the tmpdir so OCR isn't required for most tests.

Same shape as pgdp-prep `tests/conftest.py:44-63`. No mocking at the
adapter layer; we wire real (but hermetic) adapters.

---

## 15. Endpoints NOT covered here

Anything user-facing that doesn't have an endpoint above is a missing
feature in the spec. Add it in the per-component spec, not in your
implementation, then come back here to sync.
