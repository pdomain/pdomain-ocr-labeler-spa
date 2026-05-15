# Plan: pd-ocr-labeler-spa → usable

> **Status:** Active gap analysis — 2026-05-15.
> **Authority:** This plan is informed by `PARITY_STATUS.md` §5+§7,
> `docs/architecture/*`, `specs/16-milestones.md`, and direct reads
> of the implementation tree. Spec authority is unchanged: items below
> point at specs; this plan does not invent contract.

## Context

M0–M10 + M9.5 + FO-1–FO-9 are shipped. The SPA can boot, mount the
real `ProjectPage` shell, render Konva overlays, drive every word and
line mutation endpoint, and queue export / save-project / reload-OCR
jobs. The driver-contract conformance E2E test passes. M11 (glyph
annotations) is correctly blocked on Q-A7.

What does **not** yet work is the end-to-end first-time-user path. The
defined goal of "usable":

> CT opens the SPA in a browser, loads a real scanned-book project
> (PNG files + GT text under a project directory), steps through the
> pages, reviews / edits OCR word output against ground truth, saves,
> exports — fully replacing the legacy NiceGUI `pd-ocr-labeler`
> workflow.

This plan classifies the remaining gaps as **blockers**, **functional
gaps**, and **polish**, then prescribes a cut-over checklist.

## Blockers (must fix before any real page can be labeled)

| # | What | Why blocked | Size | Spec |
|---|------|-------------|------|------|
| B1 | `GET /api/projects/{id}/pages/{idx}` does not call `ensure_page_model` | Fresh project with no labeled/cached envelope returns `page_record=None` / `line_matches=[]`. User sees only the image; word panes are empty until they manually trigger Reload OCR per page. | M | `api/pages.py:312-418` (`_page_payload`); `core/page_state.py:186-257` (`ensure_page_model`); `core/jobs/handlers/reload_ocr.py:112-155` (the on-demand `LocalDoctrPageLoader` build pattern to copy). |
| B2 | `/api/projects/{id}/pages/{idx}/image` route is never registered | `_build_image_url` (`api/pages.py:259-276`) emits URLs of this shape. No router serves them — only `/image-cache/{key:path}` exists (`api/static_mounts.py:80`). Every page image 404s in the running SPA. | M | spec 04-image-viewport §1; `core/persistence/image_cache.py` already has the cache-population helpers; either register the route, or change `_build_image_url` to emit a content-addressed `/image-cache/page-images/<project>_<page:03d>_<hash>.png` URL after first cache-populate. |
| B3 | `POST /api/projects/{id}/pages/{idx}/load` 503s in production | The route at `api/pages.py:564-580` reads `runner.context["page_loader"]` and 503s when absent. Bootstrap (`bootstrap.py:355-364`) wires only the fallback keys (`predictor_cache`, `ocr_config_carrier`, `settings`); the `reload_ocr` handler builds a loader on-demand from those keys (`core/jobs/handlers/reload_ocr.py:112-155`) but the `load` route was never updated to the same pattern. | S | Refactor `_get_page_loader` (currently in `core/jobs/handlers/reload_ocr.py`) into a shared helper used by both the handler and the `load` route. |

These three are the minimum set. With B1 + B2 + B3 fixed, a user can
load a project, page through it, see the image and the OCR word panes,
edit, and save. Without B1, every page requires a click. Without B2,
no image renders. Without B3, the "Load Page" button never works.

## Functional gaps (fix before cut-over from legacy)

| # | What | Why needed | Size | Spec |
|---|------|------------|------|------|
| F1 | `last_page_index` not written back on page navigation | `session_state.json` only writes on initial `POST /api/projects/load` (`api/projects.py:491`). React Router URL changes don't roundtrip the server, so on next launch the user resumes at page 1, not where they left off. Legacy parity: the NiceGUI labeler tracks `current_page_index` on every nav. | S | Add `POST /api/projects/{id}/current-page-index {page_index}` (or extend an existing route) that calls `state.set_current_page_index(...)` + `save_session_state(...)`. Frontend pings on `useEffect([page])` in `ProjectPage`. |
| F2 | Source-folder picker UI is stub-only | Backend `POST /api/projects/source-root` exists and persists into `config.yaml`. Frontend has buttons that do not open a real picker dialog. | M | spec 22 §10 — `<SourceRootPicker>` dialog. Maps to `ProjectLoadControls` + new dialog component. |
| F3 | `WeightsResolver` resolves to `None` for non-stock model keys | The `OCRConfigModal` lets users pick custom HF revisions and local fine-tuned pairs (M3-iter-14). The picker emits the keys; the resolver returns `None` so `PredictorCache` falls through to stock DocTR. Custom weights cannot actually be loaded today. | M | `core/ocr/predictor.py` resolver injection point; `adapters/ocr/local_doctr.py` resolver wiring. Risk register §1 in `PARITY_STATUS.md`. |
| F4 | Image-cache population on lane resolution | The cached lane (`<cache_root>/page-images/...`) and the on-disk source image both exist; the SPA's image URL needs to point at *something* that resolves. If B2 takes the content-addressed-URL path, the page model's first `ensure_page_model` call must run `ensure_image_cached(...)` (helper at `core/persistence/image_cache.py:174`) so the URL is valid before the frontend fetches it. | S | Part of the B1+B2 design; document the contract explicitly in spec 04 or spec 23. |
| F5 | M9.5 keyboard-only end-to-end editing audit | Hotkeys shipped (#235–#238) and axe-core audit landed (#238), but no dedicated session walk exists. Without it, focus-trap / tab-order regressions can ship unnoticed. | M | spec 16-milestones M9.5; tracked as issue #286. Acceptance: `docs/M9.5-keyboard-audit.md` report. |
| F6 | `useProject` hook shape drift | Memory note `project_useProject_shape_drift.md` flags that `GET /api/projects/{id}` returns a flat `Project`, not the `LoadProjectResponse` shape; hook types may diverge from runtime. | S | Audit `frontend/src/hooks/useProject.ts` against `api/types.ts`; align or document the divergence in spec 03. |

## Polish (nice to have, not on cut-over critical path)

- ImageTabs sub-tabs vs single-canvas decision (#295 — design Q for CT).
- Architecture spec docs for shipped specs 21/22/23: today these specs
  live only in `specs/`. Promote the rationale parts into
  `docs/architecture/` once the implementation stabilizes; spec 21 is
  already implementation-spec-shaped, so promotion is cheap.
- `B-42` low-severity `IAuth.verify` signature drift (one-line fix).
- Cleanup of `_stub_page_payload` legacy lines/paragraphs routes once
  the SPA confirms they are no longer hit by the driver agent.

## Cut-over checklist

This is the gate for declaring the SPA the production tool and
retiring the legacy `pd-ocr-labeler`:

- [ ] B1 — `_page_payload` auto-runs OCR via `ensure_page_model` with
      an on-demand `LocalDoctrPageLoader`; first GET on a fresh page
      returns populated `page_record` + `line_matches`.
- [ ] B2 — page image URL resolves end-to-end (route or
      content-addressed cache); SPA renders the page image without
      browser-console 404s.
- [ ] B3 — `POST /pages/{idx}/load` returns 200 in production with a
      real `LocalDoctrPageLoader` build path.
- [ ] F1 — page-nav writes `last_page_index` into `session_state.json`;
      app restart returns the user to the page they left.
- [ ] F2 — source-folder picker dialog lets the user pick a new
      `source_projects_root` from the UI.
- [ ] F3 — custom HF revision and local fine-tuned model keys actually
      load via `PredictorCache` (no silent fall-through to stock).
- [ ] F5 — M9.5 keyboard-only session audit report committed.
- [ ] F6 — `useProject` hook types match the runtime response shape.
- [ ] Smoke run: CT opens the built wheel against a real scanned-book
      project, walks 10 pages, edits at least one word per page,
      saves, exports.
- [ ] Legacy `pd-ocr-labeler` repo gets a "superseded by
      `pd-ocr-labeler-spa`" note in its README; no further development.

## Out of scope for cut-over

- M11 glyph annotations (#43, #267–#270): blocked on Q-A7; not
  required for parity with the legacy labeler since the legacy never
  shipped glyph annotations.
- Postgres / managed-storage / multi-user adapters: deferred per
  D-042; local mode is the only target for cut-over.
- Cloud-mode wheel (modal / shared_container OCR): deferred per
  D-018; local CPU/GPU DocTR is the only target.
- pd-index PEP 503 self-hosted wheel publishing: separate workstream;
  the wheel-from-source install via `make build` is the cut-over path.
- ImageTabs sub-tabs (#295): single-canvas with layer toggles is the
  current design; legacy parity here is a UX decision pending CT
  input, not a usability blocker.

## References

- `docs/PARITY_STATUS.md` §5 (outstanding integration gaps) and §7
  (recommendation: next priorities).
- `docs/architecture/00-overview.md` — entry-point map.
- `docs/architecture/02-backend.md`, `09-persistence.md`,
  `04-image-viewport.md` — the three specs the blockers touch.
- `specs/16-milestones.md` — milestone roadmap.
- `specs/23-page-payload-backend.md` — page-payload contract.
- `OPEN_QUESTIONS.md` — Q-A7 is the only remaining open question;
  it does not block the cut-over.
