---
kind: architecture
status: built
owner: maintainers
created: 2026-05-14
last_verified: 2026-07-13
---

# 23 — Backend page payload + mutation endpoints

> **Status**: Active (shipped — all spec-23-* child issues closed 2026-05-15).
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#291
> **Depends on**: M3 OCR loader (shipped); `core/page_state.ensure_page_model`
> dispatcher (shipped); `persist_page_to_file` (shipped #284).
> **Last updated**: 2026-05-14

Replaces the 501 stubs in `api/pages.py`, `api/words.py`,
`api/lines_paragraphs.py` with real handlers. The frontend cannot
operate until these return real data; the retired parity audit identified this
as one of the two P0 backend-side gaps.

---

## 1. Goal

Every endpoint listed in `docs/architecture/02-backend.md` §5.3-§5.7
returns real data backed by `ProjectState` + the three-lane
persistence model + autosave.

---

## 2. Non-goals

- New endpoints. Every URL stays exactly as routed today; only the
  handler bodies change.
- New domain models. `PagePayload`, `Selection`, `LineMatch`,
  `WordMatch`, `EncodedDims`, `PageRecord` all already exist.
- Refining bbox refinement (M7 spec covered separately) — only the
  202-style endpoint that enqueues a refine job.

---

## 3. `GET /api/projects/{id}/pages/{idx}` — payload assembler

**Today.** `api/pages.py:174-178` returns `_not_implemented(...)`.

**Target.**

```py
@router.get("/{page_index}", response_model=PagePayload)
def get_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> PagePayload:
    project = _require_project(project_id, project_state)
    _validate_page_index(page_index, project)

    page = ensure_page_model(project, page_index)   # labeled → cached → OCR precedence
    pstate = project_state.page_states.get(page_index, PageState.empty())

    return PagePayload(
        project_id=project_id,
        page_index=page_index,
        page_record=page.record,
        line_matches=page.line_matches,
        selection=pstate.selection,
        encoded_dims=page.encoded_dims,
        line_filter=pstate.line_filter,
        image_url=_build_image_url(project_id, page_index, page.encoded_dims),
        generation=pstate.generation,
        page_text_ocr=_render_plaintext(page, source="ocr", settings=settings),
        page_text_gt=_render_plaintext(page, source="gt", settings=settings),
    )
```

`_build_image_url` produces a relative URL like
`/api/projects/{id}/pages/{idx}/image?w={display_width}` that the
existing image-cache route serves; the frontend uses it directly in
`useImage(url)`.

`_render_plaintext` calls into `core/text_normalization.py` (shipped
in issue #260) — joins words per line with newlines, applies
normalize-tabs when `AppConfig.normalize_plaintext_tabs=true`.

**Errors.** 404 on project not found / page out of range (already
implemented via `_check_project_and_page`); 500 envelope on
internal errors per spec 02 §error-handler.

**Concurrency.** `ensure_page_model` is already lock-guarded
(`PredictorCache` + per-page `asyncio.Lock`). No new locking needed.

---

## 4. `POST /api/projects/{id}/pages/{idx}/save`

**Today.** 501 stub.

**Target.** Call `persist_page_to_file(project, page_index, page_state)`
(shipped #284), receive the saved envelope path, return:

```py
return SavePageResponse(project_id=…, page_index=…, saved=True)
```

If `body.generation != pstate.generation`: return 409 `{error:
"generation_mismatch", current_generation: …}` so the frontend can
re-fetch.

On `OSError` during write: return 500 envelope (`save_failed`).

---

## 5. `POST /api/projects/{id}/pages/{idx}/load`

**Today.** 501 stub.

**Target.** Re-read the labeled lane (`<project>_NNN.json`); if not
present, fall through to cached; if neither, run OCR. This is just
`ensure_page_model(project, page_index, force_reload=True)` with the
existing dispatcher. Replaces `ProjectState.page_states[idx]` (so
in-memory edits are discarded — explicit user intent per legacy
"Load Page" button). Returns `PagePayload` (same as GET).

---

## 6. `POST /api/projects/{id}/pages/{idx}/reload-ocr` (202 job)

**Today.** Submits a `reload_ocr` job whose handler `await asyncio.sleep(0)`.

**Target.** Job handler `core/jobs/handlers/reload_ocr.py` (new — mirrors
`handlers/rotate.py` pattern):

```py
async def handle_reload_ocr(runner: JobRunner, job: Job) -> None:
    ctx = runner.context
    project_state: ProjectState = ctx["project_state"]
    settings: Settings = ctx["settings"]
    page_index = job.payload["page_index"]

    await runner.update_progress(job, fraction=0.0, message="Loading OCR model")
    project = project_state.active_project
    loader = LocalDoctrPageLoader(settings=settings, predictor_cache=ctx["predictor_cache"])

    await runner.update_progress(job, fraction=0.1, message="Running OCR")
    page = await asyncio.to_thread(loader.run_ocr, project, page_index, force=job.payload.get("force", False))

    await runner.update_progress(job, fraction=0.9, message="Persisting cached envelope")
    project_state.set_page(page_index, page)

    await runner.update_progress(job, fraction=1.0, message="Done")
```

Notifications side-effects (start / progress / done / failed) go
through `core/notifications.NotificationQueue` per spec 11.

Wired in `_HANDLERS` dict in `runner.py:279`.

---

## 7. `POST /api/projects/{id}/pages/{idx}/rematch-gt`

**Today.** 501 stub.

**Target.** Re-run `core/ground_truth_matcher.rematch_page` (a thin
wrapper over `pdomain_book_tools.matching` calls already used during
initial OCR). Replaces `page.line_matches` with freshly-matched
results; per-word GT edits are discarded (legacy semantics documented in
`pd-ocr-labeler/docs/usage/how-to-label-a-page.md` §10).

Body is empty (`RematchGtRequest` is intentionally empty).

Returns `PagePayload` post-rematch.

Confirmation prompt is the frontend's responsibility (`ConfirmDialog`
in spec 22) — the endpoint is unconditional.

---

## 8. `POST /api/projects/{id}/pages/{idx}/save-all` (202 job)

**Today.** Submits a `save_project` job whose handler is `sleep(0)`.

**Target.** Job handler iterates over every page in `ProjectState.page_states`
that has `generation > last_saved_generation` and calls
`persist_page_to_file` on each. Reports progress per page; emits
`save_project_done` notification with `failures: list[SaveFailure]`
on completion.

---

## 9. Word / line / paragraph mutation endpoints

19 endpoints today return an empty `PagePayload` without mutating
state. Each needs:

1. Resolve target word / line / paragraph from URL path params.
2. Validate request body (already done via Pydantic).
3. Call the mutation method on `Page` / `Line` / `Word` (from
   `pdomain_book_tools.ocr`) — most are already implemented in
   pdomain-book-tools (`Word.set_ground_truth_text`, `Line.merge_words`,
   `Page.split_line`, `Word.apply_style`, `Word.set_validated`, etc.).
4. Bump `ProjectState.page_states[idx].generation`.
5. Trigger autosave (write cached envelope to disk via
   `core/persistence/cached_envelope.py`).
6. Return refreshed `PagePayload` (round-trip through §3).

Endpoint catalog (each is ~30 LOC handler):

**Word (`api/words.py`).**

| URL | pdomain-book-tools call |
|---|---|
| `.../words/{l}/{w}/gt` | `word.set_ground_truth_text(text)` |
| `.../words/{l}/{w}/style` | `word.apply_style(style_id, scope)` |
| `.../words/{l}/{w}/component` | `word.set_component(component_id)` |
| `.../words/{l}/{w}/validated` | `word.set_validated(bool)` |
| `.../words/validate-batch` | iterate over `body.targets` |
| `.../words/add` | `page.add_word(bbox, text, line_index=None)` |
| `.../words/{l}/{w}/rebox` | `word.rebox(bbox)` |
| `.../words/{l}/{w}/nudge` | `word.nudge(left, top, right, bottom)` |
| `.../words/{l}/{w}/split` | `word.split(orientation, marker_position)` |
| `.../words/merge` | `page.merge_words(targets)` |
| `.../words/erase-pixels` | `page.erase_pixels(bbox, fill_value=255)` |

**Line / paragraph (`api/lines_paragraphs.py`).**

| URL | Call |
|---|---|
| `.../lines/{l}/copy-gt-to-ocr` | `line.copy_gt_to_ocr()` |
| `.../lines/{l}/copy-ocr-to-gt` | `line.copy_ocr_to_gt()` |
| `.../lines/{l}/validate` | `line.set_validated(bool)` |
| `.../lines/{l}/delete` | `page.delete_line(l)` |
| `.../lines/merge` | `page.merge_lines(targets)` |
| `.../lines/split-after-word` | `line.split_after_word(w)` |
| `.../lines/split-by-words` | `page.split_line_by_words(targets)` |
| `.../lines/refine-batch` | enqueue refine job |
| `.../paragraphs/{p}/copy-*` | symmetric |
| `.../paragraphs/{p}/validate` | symmetric |
| `.../paragraphs/{p}/delete` | symmetric |
| `.../paragraphs/merge` | `page.merge_paragraphs(targets)` |
| `.../paragraphs/{p}/split-after-line` | `paragraph.split_after_line(l)` |

The handlers themselves are mechanical; the heavy lifting is in
`pdomain_book_tools` (already exists). Any missing methods in
pdomain-book-tools become tracking issues against that repo's agent.

---

## 10. Selection endpoint

`POST /api/projects/{id}/pages/{idx}/selection` — body
`{mode: "replace"|"remove"|"toggle", selection: Selection}`. Currently
stubbed; needs:

```py
def update_selection(...):
    pstate = project_state.page_states[page_index]
    pstate.selection = _apply_selection(pstate.selection, body.mode, body.selection)
    pstate.generation += 1
    return _page_payload(project_id, page_index)
```

`_apply_selection` is set-union / set-difference / symmetric-difference
on the index tuples (lives in `core/selection.py`, new ~40 LOC).
This is what `PageImageCanvas.onBoxSelect` POSTs to in `select` mode
after drag.

---

## 11. Refine endpoint (M7 — out of scope here)

`POST /api/projects/{id}/pages/{idx}/refine` already has a real
job handler per `api/refine.py:83`. **Verify** during this spec's
acceptance that it works end-to-end; M7 spec covers the actual refine
algorithm in `pdomain_book_tools`.

---

## 12. Autosave + cached lane

After every mutation in §9-§10, the handler must:

1. Increment `pstate.generation`.
2. Write the cached-lane envelope via `core/persistence/cached_envelope.py`
   (`_envelope.json` filename suffix per memory-note
   `cached_envelope_filename_diverges_from_legacy`).
3. **Not** write the labeled-lane envelope — that's explicit Save.

Cached-lane write is best-effort: on `OSError`, log a warning and
continue. The page-state in memory is the source of truth; the
cache is a perf optimization.

---

## 13. Atomicity / locking

Per-page lock: `ProjectState.page_locks[idx]: asyncio.Lock`. Every
mutation handler acquires the lock for the duration of the call.
This serializes concurrent edits on the same page from the same SPA
client (rare but possible with React 19 transitions) and prevents
torn cached-envelope writes.

---

## 14. Wire-shape stability

Every endpoint in this spec keeps its current URL and request body
exactly. The only response-shape change: handlers that previously
returned empty `PagePayload(project_id, page_index)` now return a
populated payload via `_page_payload` (defined in §3). The TS types
in `frontend/src/api/types.ts` need no regeneration unless backend
Pydantic models change.

### Current PageRecord convergence boundary

Page lifecycle fields now use `pdomain_ops.pages.PageRecord`. The local
`core.models` module re-exports that shared type and `RotationSource`, so code
and tests still use both import paths even though they resolve to the shared
model. Labeler-only view state is stored in the namespaced
`extensions["labeler"]` payload defined by `core/labeler_extension.py`.

Convergence is therefore partial at the import and adaptation boundary, not a
claim that every Labeler path is suite-neutral. Persistence and validation
paths import `PageRecord` directly from `pdomain_ops`; rotation coverage and
older Labeler modules still import the local compatibility facade. Keep the
facade until those callers migrate, and do not move Labeler-only fields into
the shared lifecycle schema.

The [shared PageRecord decision](../decisions/2026-07-13-shared-page-record-boundary.md)
defines field ownership and the compatibility-facade policy. The
[intent map](../context/intent-map.md) tracks removal of the remaining indirect
imports as active convergence work.

---

## 15. Tests

**Unit (pytest).**

- `tests/unit/api/test_pages_get.py` — given a fixture project,
  `GET .../pages/0` returns a `PagePayload` with `page_record` set,
  `line_matches` non-empty, `image_url` matching the expected route.
- `tests/unit/api/test_words_mutate.py` — for each mutation endpoint,
  POST a body, assert returned payload reflects the change, assert
  `generation` incremented, assert cached-envelope file written.
- `tests/unit/api/test_save_load.py` — full round-trip: mutate,
  save, restart `AppState`, load, assert mutations persist.

**Integration.**

- `tests/integration/test_reload_ocr_job.py` — submit reload-OCR,
  await job completion via SSE, assert progress events emitted in
  order.
- `tests/integration/test_concurrent_mutations.py` — two concurrent
  GT edits on different words; assert both apply, single cached
  envelope written.

---

## 16. Migration plan — five issues

1. **spec-23-A** — `GET .../pages/{idx}` real payload + `_render_plaintext`.
   Acceptance: SPA frontend can fetch a page and render the image URL.
2. **spec-23-B** — `reload_ocr` + `save_project` job handlers (real).
   Acceptance: page reload + project save complete; SSE notifications fire.
3. **spec-23-C** — Word mutation handlers (`api/words.py`).
   Acceptance: GT edit, validate, style/component, rebox, erase all
   round-trip through pdomain-book-tools.
4. **spec-23-D** — Line / paragraph mutation handlers
   (`api/lines_paragraphs.py`).
5. **spec-23-E** — Selection endpoint + `core/selection.py` set ops.

A → B can run in parallel. C/D/E can run in parallel after A lands
(they depend on `_page_payload` from A).

---

## 17. Refs

- Historical parity audit: retained in Git history.
- Existing helpers: `core/page_state.py`, `core/persistence/cached_envelope.py`,
  `core/persistence/ground_truth.py`, `core/jobs/runner.py`.
- Spec 02 (backend): [`02-backend.md`](02-backend.md) §5
- Spec 09 (persistence): [`09-persistence.md`](09-persistence.md)
- Spec 11 (notifications): [`11-notifications.md`](11-notifications.md)
- pdomain-book-tools: `Word`, `Line`, `Page` mutation methods (delegated).
