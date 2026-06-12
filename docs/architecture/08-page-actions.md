# 08 — Page Actions

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#20

The horizontal row of buttons just below the project navigation
controls. Persistence + OCR + GT-rematch live here.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/page_actions.py`,
> `state/project_state.py`,
> `state/page_state.py:_auto_save_to_cache`,
> `operations/ocr/page_operations.py`
> Persistence — [`09-persistence.md`](09-persistence.md)
> Backend — [`02-backend.md`](02-backend.md) §5.3

---

## 1. Layout

```
[Reload OCR] [Reload OCR (Edited)] [Save Page] [Save Project] [Reload] [Undo] [Redo] [Rematch GT] [Rotate ↺] [Rotate ↻] [Export…]   page_001.png   [LABELED] [↻ 90 auto]
```

Buttons left-to-right, then a divider, then the page name + source
badge + rotation badge. The Rotate buttons (D-029) ship in M9.1 and
are present-but-hidden until then. All buttons disabled while:

- `useIsLoading(["page", pid, idx])` (page loading).
- `useIsMutating({mutationKey:["page", pid, idx]}) > 0`.
- An active job is targeting this page.

testids: see [`13-driver-contract.md`](13-driver-contract.md) §2.5.

---

## 2. Reload OCR

Triggers a fresh OCR run on the **original** source image (ignoring
any erase-pixels edits in memory).

`POST /api/projects/{id}/pages/{idx}/reload-ocr {use_edited_image: false}`.
Returns `202 Accepted` with a `Job` body. SPA opens
`useJobProgress(job.id)`, shows the busy overlay with the progress
message ("Loading detection model…", "Running OCR…", etc.).

On terminal `complete`:

- Invalidate `["page", pid, idx]`.
- Refetch produces a `PageRecord` with `page_source = "ocr"`.
- Toast `"OCR complete"`.

On `error`:

- Show the error message in a sticky negative toast.
- The page state stays as it was.

The OCR pipeline's error handling: if OCR fails entirely, the backend
constructs a *fallback* page (empty `Page` with one empty Block) and
sets `page_source = "fallback"`, `ocr_failed = true`. SPA renders this
with a banner: "OCR failed for this page. Use Reload OCR to retry."

---

## 3. Reload OCR (Edited)

Same shape as Reload OCR, but with `use_edited_image: true`. The
backend uses the in-memory edited image (after erase-pixels operations)
as the OCR input.

If no erase ops have been applied, this falls back to original-image
OCR. Backend tracks `page_state.has_edited_image: bool` and rejects
this call with `400 no_edited_image` when false. SPA disables the
button when `has_edited_image` is false (read from `PagePayload`).

---

## 4. Save Page

Synchronous. `POST /api/projects/{id}/pages/{idx}/save {saved_by:"Save Page"}`.

Backend:

1. `_resolve_save_directory` → `<data>/labeled-projects/<project_id>/`.
2. Copy the source image to `<save_dir>/<project_id>_<page:03d>.png`
   (only if not already there).
3. Build `UserPageEnvelope` with `provenance.source_lane="labeled"`,
   `saved_by="Save Page"`.
4. Write `<save_dir>/<project_id>_<page:03d>.json`.
5. Set `PageRecord.page_source = "filesystem"`.

Returns `SavePageResponse {page: PagePayload, saved_path: Path}`.

SPA:

- Optimistically flip the source badge to "LABELED" while the
  request is in flight.
- On error, revert + toast.
- Update the SaveStatus indicator timestamp.

Concurrency note: if another tab simultaneously saves the same page,
last-writer-wins by mtime. The image fingerprint (`source.image_fingerprint`)
is checked on the *next* save — if the source image changed under us,
return `409 image_drift`.

---

## 5. Save Project

Long-running. `POST /api/projects/{id}/save-all`. Returns `202`+`Job`.

Backend handler iterates `project_state.page_states.items()` (only the
pages the user has actually accessed) and saves each via the same
`Save Page` flow. Returns `SaveProjectResponse` once complete.

```python
class SaveProjectResponse(BaseModel):
    saved_count: int
    skipped_count: int
    failed_count: int
    total_count: int
    failures: list[SaveFailure] = []
```

A `failure` is logged but doesn't stop the loop — failed pages are
listed in the result.

SPA: shows the busy overlay with progress (`"Saved 3 of 12"`). On
completion: toast.success with the summary; on any failures, toast.warning
with a "View details" action that opens a modal listing them.

---

## 6. Reload (formerly "Load Page") + Undo/Redo

Synchronous. `POST /api/projects/{id}/pages/{idx}/load`.

Renamed "Reload" per `docs/specs/2026-06-12-event-store-undo.md` (U-7);
the `load-page-button` testid is unchanged. Every mutation auto-persists
to the event-store head and reads resolve the head blob, so there are
never "unsaved edits" to discard — the action is an honest refresh from
the store. The confirm copy says so: "This will refresh the page from
the latest stored version. Edits are saved automatically — use Undo to
step back through page history."

Returns full `PagePayload`. SPA invalidates the page query.

**Undo / Redo** (`undo-button` / `redo-button`, `Mod+Z` / `Mod+Shift+Z`):
per-page blob-version restore over the aggregate's provenance history.
`POST /api/projects/{id}/pages/{idx}/undo|redo` → 200 `PagePayload` or
409 at the bounds. Availability flags ride on `PagePayload.history`
(`undo_available` / `redo_available` / `cursor` / `depth`); depth is
bounded by `PDLABELER_UNDO_DEPTH` (default 50). Reload OCR and rotate
create a new page aggregate, so the history resets across that boundary
(the Reload-OCR confirm warns about it). Full design:
`docs/specs/2026-06-12-event-store-undo.md`.

---

## 7. Rematch GT

Synchronous. `POST /api/projects/{id}/pages/{idx}/rematch-gt`.

Backend:

1. Wipe per-word `ground_truth_text` overrides.
2. Re-run `Page.add_ground_truth(page_text_gt)` on the page.
3. Auto-save to cache.

Returns full `PagePayload`. SPA invalidates and refetches.

Confirmation: shadcn `<AlertDialog />` because it overwrites
per-word edits.

---

## 7.5. Rotate ↺ / Rotate ↻ (M9.1)

Manual rotation. POST `.../rotate {degrees: ±90}` returns `202` +
`Job` (re-runs OCR after rotation). Detail in
[`19-auto-rotation.md`](19-auto-rotation.md).

testids: `rotate-ccw-button`, `rotate-cw-button`. Optional 180°
button: `rotate-180-button`.

## 8. Export

Opens the `<ExportDialog />` (see [`10-export.md`](10-export.md)). No
direct mutation here.

---

## 9. Page name + source badge + rotation badge

Right side of the row:

```
... | page_name.png    [LABELED|CACHED OCR|RAW OCR|LOADING…|FALLBACK]   [↻ 90 auto]?
```

| testid | Element |
|---|---|
| `page-name-label` | The image filename, monospace |
| `page-source-badge` | The badge |
| `rotation-badge` | Rotation pill (D-029); hidden when `rotation_degrees == 0` |

Badge styles:

- `LABELED` → green (`bg-green-100 text-green-900`)
- `CACHED OCR` → yellow (`bg-yellow-100 text-yellow-900`)
- `RAW OCR` → blue (`bg-blue-100 text-blue-900`)
- `LOADING…` → gray with spinner
- `FALLBACK` → red (`bg-red-100 text-red-900`)

Tooltip on the badge shows full provenance: engine, model versions,
saved_at timestamp.

---

## 10. SaveStatus indicator

A small text below the page name showing autosave activity:

```
"Saved 2s ago"   (after a successful auto-save)
"Save failed"    (sticky, on autosave failure)
"Saving..."      (during)
""               (otherwise)
```

Implementation: `<SaveStatus />` subscribes to `useMutationState({mutationKey:["autosave",...]})`
and a per-page autosave timestamp. Auto-save is server-driven (every
mutation triggers it on the backend); the SPA learns about it via the
notifications stream.

---

## 11. Auto-save semantics

The backend's `core/page_state.py` mirrors the legacy: every mutation
that changes the page (structural edit, bbox edit, validation toggle,
GT edit) triggers `_auto_save_to_cache`. This:

- Writes a `UserPageEnvelope` to `<cache>/page-images/<project>_<page:03d>_envelope.json`
  with `source_lane="cached"`, `saved_by="Auto-save"`,
  `update_page_source=False`.
- Best-effort: errors are logged + warning notification, NOT raised
  to the user-action's response (the user's mutation succeeded).

The visible `page_source` badge does **not** flip on auto-save. That
flip only happens on explicit `Save Page`. Crash recovery uses the
cache-lane envelope; explicit save creates the labeled-projects-lane
envelope.

This is **important** for both data safety and UX continuity. The
legacy depends on this distinction.

---

## 12. Hotkeys

| Key | Action |
|---|---|
| `Ctrl+S` | Save Page |
| `Ctrl+Shift+S` | Save Project (with confirm) |
| `Ctrl+R` | Reload OCR (with confirm) |
| `Ctrl+Shift+R` | Reload OCR (Edited) (with confirm) |
| `Ctrl+L` | Reload page from stored version (with confirm) |
| `Ctrl+G` | Rematch GT (with confirm — destructive) |
| `Ctrl+E` | Open Export dialog |
| `Ctrl+Z` | Undo page edit (suppressed inside text fields) |
| `Ctrl+Shift+Z` | Redo page edit |

These are **new** ([Q10](../../OPEN_QUESTIONS.md)).

`Ctrl` is the natural metakey on Linux/Windows; on macOS, the SPA
uses `Cmd` automatically via `react-hotkeys-hook`'s `Mod+` syntax.

---

## 13. Tests

- Backend: `tests/integration/test_save_load_round_trip.py` — save,
  modify, load, assert state matches save (golden envelope).
- Backend: `tests/integration/test_save_project.py` — multi-page job
  with progress events; failures report properly.
- Backend: `tests/integration/test_rematch_gt.py` — per-word overrides
  cleared; page-wide alignment re-run; auto-saved to cache.
- Backend: `tests/integration/test_image_drift.py` — modify the source
  image on disk between page load and save; expect `409 image_drift`.
- E2E: `test_page_actions.py` — port from legacy:
  - Save Page → badge flips LABELED
  - Reload OCR → busy overlay → completes → page_source=ocr
  - Load Page → previously-unsaved edits gone
  - Rematch GT → per-word edits cleared
  - Save Project → progress overlay → toast summary

---

## 14. Image drift recovery (resolved)

**Decision.** On `409 { reason: 'image_drift' }`, the client automatically
reloads the page (same as a manual page navigation) and shows a toast:
`"Page reloaded — image was updated since last load."` No user confirmation
required.

Implementation:

1. The mutation's `onError` handler intercepts `status === 409` with
   `body.reason === "image_drift"`.
2. Invalidate `["page", pid, idx]` immediately — the refetch loads the
   current page state from the server.
3. Show `toast.info("Page reloaded — image was updated since last load.")`.
4. The user's unsaved edit is discarded; no retry of the original save is
   attempted.

Rationale: the legacy bails to a notification with no recovery action, which
leaves the user confused. Auto-reload matches what a manual "Load Page" would
do, makes the recovery self-describing, and requires no user decision. If the
user had meaningful edits in flight, the cache lane (auto-save) will have
preserved most of them — they can re-apply after the reload.

**Confirm in M8** integration tests and Playwright `test_image_drift.py`.

---

## 15. Cancel during Save Project

Wire a Cancel button in the busy overlay during `SAVE_PROJECT` jobs. The Job
runner supports cooperative cancellation; the handler checks
`runner.is_cancelled(job.id)` between page saves and exits early, reporting
`cancelled_count` in the final `SaveProjectResponse`. The SPA sends
`POST /api/projects/{id}/jobs/{job_id}/cancel`.
