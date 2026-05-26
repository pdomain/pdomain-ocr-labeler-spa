# Plan: pdomain-ocr-labeler-spa → usable

> **Status:** Cut-over complete — 2026-05-21.
> B1/B2/B3/F1/F2/F3/F4/F6 closed. F5 audit doc committed; browser walk TODOs
> remain for CT to confirm before final M9.5 sign-off (only remaining open row).
> Smoke-run row closed 2026-05-16. Legacy README banner added 2026-05-16.
> Cut-over reference screenshot taken 2026-05-21 (`docs/Screenshot-hifi-gaps-closed.png`).
> SPA README Status block updated 2026-05-21. CU-8 polish complete.
> **Authority:** This plan is informed by `docs/architecture/*`,
> `specs/16-milestones.md`, and direct reads of the implementation
> tree. Spec authority is unchanged: items below point at specs; this
> plan does not invent contract.

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
| F2 | Source-folder picker UI is stub-only | ✅ CLOSED #294 — `SourceFolderDialog.tsx` fully implemented; wired in `App.tsx`; all 9 driver-contract testids present; `source-folder-button` in `ProjectLoadControls` opens it via `dialogStore`. | — | — |
| F3 | `WeightsResolver` resolves to `None` for non-stock model keys | ✅ CLOSED #334 — `core/ocr/weights_resolver.py` implements `build_weights_resolver(local_models_root)`; wired into `PredictorCache` in `bootstrap.py`. Handles `HF_LATEST_KEY` (via `pd_book_tools.hf.hf_download`) and `"<profile>/<signature>"` local keys. Stock pass-through preserved. | — | — |
| F4 | Image-cache population on lane resolution | ✅ RESOLVED (no code needed) — `GET /api/projects/{id}/pages/{idx}/image` reads source files directly (`project.image_paths[page_index]`); no content-addressed JPEG cache is required for the image URL to resolve. The `_write_cached_envelope` in `run_ocr` handles the OCR result cache. `write_cached_image` (JPEG overlay cache) is a future polishing item, not a cut-over blocker. | — | — |
| F5 | M9.5 keyboard-only end-to-end editing audit | 🟡 PARTIAL — `docs/M9.5-keyboard-audit.md` committed (#335). Full hotkey inventory + focus-management code review done. Browser walk items listed as TODOs; requires CT confirmation before final sign-off. | M | spec 16-milestones M9.5; tracked as issue #286 → #335. |
| F6 | `useProject` hook shape drift | ✅ RESOLVED (no code needed) — `frontend/src/hooks/useProject.ts` already defines hand-written `ProjectResponse` interface matching the flat `Project` shape returned by `GET /api/projects/{id}`; hook comment explicitly documents the divergence from `LoadProjectResponse`. | — | — |

## Polish (nice to have, not on cut-over critical path)

- ~~ImageTabs sub-tabs vs single-canvas decision (#295)~~ — resolved per D-045
  (2026-05-16): no image-viewport text-overlay sub-tabs; `mismatches-only-toggle`
  is the shipped resolution; right-pane `TextTabs` covers GT/OCR views.
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
- [x] F2 — source-folder picker dialog lets the user pick a new
      `source_projects_root` from the UI. (#294 closed)
- [x] F3 — custom HF revision and local fine-tuned model keys actually
      load via `PredictorCache` (no silent fall-through to stock). (#334)
- [x] F4 — image URL resolves end-to-end; image route reads source files
      directly; no JPEG cache pre-population required.
- [~] F5 — M9.5 keyboard-only session audit report committed
      (`docs/M9.5-keyboard-audit.md`); browser walk TODOs pending CT.
- [x] F6 — `useProject` hook types already match runtime response shape;
      divergence from `LoadProjectResponse` is documented in the hook.
- [x] Smoke run: BUG-SMOKE-1 (word GT edit 404 on cached lane) and
      BUG-SMOKE-2 (save 409 on first save) both verified fixed
      2026-05-16 — `POST .../words/0/0/gt` → 200, `POST .../save`
      with generation from GET → 200.
- [x] Legacy `pd-ocr-labeler` repo gets a "superseded by
      `pdomain-ocr-labeler-spa`" note in its README; no further development.
      — 2026-05-16 (commit 81c5c7d in pd-ocr-labeler)

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
- ImageTabs sub-tabs (#295): resolved per D-045 (2026-05-16) — no
  image-viewport text-overlay sub-tabs will be added; this item is
  fully closed.

## References

- `docs/architecture/00-overview.md` — entry-point map.
- `docs/architecture/02-backend.md`, `09-persistence.md`,
  `04-image-viewport.md` — the three specs the blockers touch.
- `specs/16-milestones.md` — milestone roadmap.
- `docs/architecture/23-page-payload-backend.md` — page-payload contract.
- `OPEN_QUESTIONS.md` — Q-A7 is the only remaining open question;
  it does not block the cut-over.
