# Plan: pd-ocr-labeler-spa → usable

> **Status:** Active gap analysis — 2026-05-15.
> B1/B3/F1 shipped (commit 06094b2). B2 confirmed already fixed (#332 closed).
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

> **All three blockers are now CLOSED.** See commit 06094b2.

| # | What | Status |
|---|------|--------|
| B1 | `GET /api/projects/{id}/pages/{idx}` does not call `ensure_page_model` | ✅ CLOSED #330 — `get_page` now calls `ensure_page_model` when `page_record` is absent; `page_to_line_matches` lifts `Page → (PageRecord, list[LineMatch])`. |
| B2 | `/api/projects/{id}/pages/{idx}/image` route is never registered | ✅ CLOSED #332 — route was already registered at `api/pages.py` (confirmed in prior session); plan was stale. |
| B3 | `POST /api/projects/{id}/pages/{idx}/load` 503s in production | ✅ CLOSED #331 — `_build_page_loader_from_context` shared helper builds `LocalDoctrPageLoader` on-demand; 503 path removed. |

## Functional gaps (fix before cut-over from legacy)

| # | What | Why needed | Size | Spec |
|---|------|------------|------|------|
| F1 | `last_page_index` not written back on page navigation | ✅ CLOSED #333 — `POST /api/projects/{id}/current-page-index` added; writes `session_state.json` on each nav. | — | — |
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

- [x] B1 — `_page_payload` auto-runs OCR via `ensure_page_model` with
      an on-demand `LocalDoctrPageLoader`; first GET on a fresh page
      returns populated `page_record` + `line_matches`. (commit 06094b2)
- [x] B2 — page image URL resolves end-to-end; route was already
      registered. (confirmed, #332 closed)
- [x] B3 — `POST /pages/{idx}/load` returns 200 in production with a
      real `LocalDoctrPageLoader` build path. (commit 06094b2)
- [x] F1 — page-nav writes `last_page_index` into `session_state.json`;
      app restart returns the user to the page they left. (commit 06094b2)
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
