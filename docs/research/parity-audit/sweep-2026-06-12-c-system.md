# Sweep 2026-06-12 — Dimension C (document / project / system actions)

Live-verified refresh of the dimension-C parity rows. Method: seeded
exercise-fixture server (event-store seed via `_ingest_ocr_result` +
`_register_page_in_project`, same as `tests/e2e/exercise_real_project.py`),
driven in a real Chromium via Playwright MCP; durability checked via API
re-fetch and files on disk.

Acceptance per row = **VISIBLE + ENABLED + real EFFECT** (durable where
applicable). A testid existing is not parity.

Server: worktree `agent-ae30520f4d388f99c` @ `d0ba846` (rebased onto local
main), fresh `make frontend-build`, `http://127.0.0.1:8931`,
data roots under `/tmp/c-audit/run/`.

## Verdict table

| Row | Capability (legacy ref) | Verdict | Evidence |
|---|---|---|---|
| C01 | List/select projects (legacy C-09 dropdown) | PASS (resurfaced) | RootPage card grid replaces dropdown; `project-card-exercise-fixture` visible; search + filter chips work. No `project-select`/`load-project-button` testids anywhere (legacy testids dropped — driver-contract note). |
| C02 | Load/open project (C-10) | PASS | `project-card-open-…` click → POST /api/projects/load 200 → navigates to `/projects/{id}/pages/pageno/1`. |
| C03 | Open source-folder dialog (C-01) | PASS (resurfaced) | "Open source folder" button on RootPage filter bar (no testid; legacy `source-folder-button` exists only as hidden `data-testid-stub`). Dialog opens with all controls visible+enabled. |
| C04 | Picker: browse into child dir (C-02) | PASS | `fs-ls-entry-dummy-proj` click descends; current-path label updates. |
| C05 | Picker: Home (C-03) | PASS | label → `~` (home) after click. |
| C06 | Picker: Up (C-04) | PASS | `/tmp/c-audit/run/source` → `/tmp/c-audit/run`. |
| C07 | Picker: Open Typed Path (C-05) | PASS | typed `/tmp/c-audit/alt-source` + click → browses there *without* applying. |
| C08 | Picker: Use Current (C-06) | PASS | copies browsed dir into path input. |
| C09 | Apply source root (C-07) | PARTIAL | Works on default port 8080: POST /source-root 200, `config.yaml` written (`source_projects_root` line verified on disk), project list re-scanned (dummy-proj card appears), restore round-trip OK. **BUG: on any non-default port the browser POST 403s** — `LocalTrustMiddleware` (`middleware/local_trust.py:64`) rejects any `Origin` not in a fixed allowlist (8080/5173/bare) even when `Sec-Fetch-Site: same-origin` passed. Reproduced: `Origin: http://127.0.0.1:8931` + `Sec-Fetch-Site: same-origin` → 403; same POST with `Origin: …:8080` → 200. e2e suites miss it because they seed via httpx (no Origin) and run on random ports. Dialog shows "Request failed (403)" and root never changes. |
| C10 | Cancel source-folder dialog (C-08) | PASS | typed `/tmp` then Cancel → GET /api/projects root unchanged. |
| C11 | Deep link `/projects/{id}` (C-12) | PASS | redirects to `pageno/1`. |
| C12 | Deep link `/projects/{id}/pages/pageno/{n}` (C-13) | PASS | pageno/3 loads page 3 (`nav-page-input` = 3). 0-based `/pages/index/2` → `pageno/3` redirect also works. |
| C13 | Switch project while one is loaded (legacy header select, C-09/C-10) | FAIL | Project-route header has NO project-select / source-folder / change-project control (`change-project-button` exists only in a comment, ProjectLoadControls.tsx:15). `projects-home-link` click → `/` → session auto-resume bounces straight back to the loaded project (verified live). The RootPage grid is only reachable through the 404-redirect error path (`skipSessionRedirect`). A user cannot switch projects from the UI without restarting the server or hand-typing another project's URL. |
| C14 | Project delete / archive (SPA-new; backend DELETE exists) | FAIL | `project-card-delete-…` and `project-card-archive-…` render in card menu but `onClick` only closes the menu (RootPage.tsx:265–281) — pure stubs; `DELETE /api/projects/{id}` never called from UI. |

| C15 | Page nav prev/next buttons (C-14/C-15) | PASS | clicks navigate pageno 1↔2; URL + page content update. |
| C16 | Jump to page — input + Enter (C-16) | PASS / **Go button FAIL** | Enter in `nav-page-input` navigates (4 → 4 verified). The visible "Go" button (`nav-goto-button`) **can never navigate to a typed value**: the input's `onBlur` clears `gotoValue` before the button's `onClick` runs, so `onGoTo()` falls back to the current page (no-op). Verified live (fill 5 + click → stays on 1) and in code (`ProjectNavigationControls.tsx:122-124` onBlur reset vs `:71-76` onGoTo fallback). |
| C17 | First/last/prev/next hotkeys (SPA-new mod+Arrows/Home/End) | PASS | all four verified (1→8, 8→1 etc.). Suppressed while page input focused (correct). |
| C18 | Nav bounds disable | PASS | prev disabled on page 1, next disabled on page 8. |
| C19 | Save current page (C-17) | PASS | `page-actions-compact-save-page` → 200, "Page saved" toast; content blob written via `save_page_content_to_store` (pages.py:769-…). Mutations durable (see C21). |
| C20 | Load saved page from disk (C-19) | PARTIAL | Button visible+enabled (PageActions overflow → `load-page-button`) and reloads from store. **But the legacy revert-to-last-save semantic is gone**: every mutation immediately advances the event-store head (auto-persist), and `load_labeled` reads the *head* blob (local_doctr.py:327), not the last explicit-save snapshot. Verified live: validate-all → Save → unvalidate-all → Load Page returns the *unvalidated* state, not the saved one. "Load Page (discard unsaved edits)" is effectively a refresh; there is nothing to discard. |
| C21 | Auto-save of mutations (no explicit save) | PASS | validate-all on page 3, navigate away + back: validated count retained (33/33). Event-sourced head advance is the persistence path; `load_cached` is a retired stub (M5b). |
| C22 | Save project / save-all (C-18) + skipped-page warning (S5) | PASS | overflow → `save-project-button` → 202 job; toasts "Project saved" + "Saved 1 page(s) for project exercise-fixture" (dirty-only save: only the one mutated-unsaved page). Skip warning implemented: `core/jobs/handlers/save_project.py:196-218` appends "N unsaved (not registered): pages […]" to the job message; not triggerable here since all 8 fixture pages have page_ids. |

| C23 | Reload OCR — original image (C-26) | PASS | `page-actions-compact-reload-ocr` visible+enabled → 202 + job_id; real DocTR predictor loads (`db_resnet50`/`crnn_vgg16_bn` in server log); "Running OCR…" then "OCR complete for page 1" toasts. Positive proof on real-text project `ocr-real`: cold OCR produced 26 correct words ("The quick brown fox …"). On exercise-fixture page 1 reload replaced the seeded 4-line content with 0 words — correct, because the committed fixture PNG is actually blank (white + black bar); the seeded envelopes don't match the pixels (fixture quirk worth knowing). |
| C24 | Reload OCR — edited image / preserve edits (C-27) | PASS (gating verified) | Overflow → `reload-ocr-edited-button` visible; correctly disabled with title "No edited image available" when the page has no erase-edits (binding `pageRecord.extensions.labeler.has_edited_image`, ProjectPage.tsx:802). Full erase→re-OCR loop not exercised here (erase is dim-B). |
| C25 | Rematch GT (C-28) | PASS | `page-actions-compact-rematch-gt` visible+enabled → 200, generation bumps, payload reassembled. |
| C26 | Refine all bboxes on page (C-29/C-30) | PASS (surface) | `toolbar-page-refine` + `toolbar-page-expand-refine` visible+enabled → 202 job completes. On the blank fixture page no bbox delta is observable (0 words); deep per-word refine verification is dim-B's lane. `GET /api/refine/available` → `{available: true}`. |
| C27 | OCR engine choice DocTR/Tesseract | N-A | Legacy has a `TESSERACT` enum in `ocr_service.py:16` but no view/CLI ever exposes engine selection (grep of legacy `views/` + `cli.py` — zero hits); default DOCTR is the only reachable engine. SPA equally DocTR-only (zero `tesseract` hits). No parity gap — the legacy capability was service-layer-only dead code. |
| C28 | Manual rotate CW/CCW/180 (SPA M9.1/S8) | **FAIL (3 of 5 links broken)** | (1) **Buttons invisible**: `rotate-cw/ccw/180-button` exist only inside the `display:none` PageActions wrapper (ProjectPage.tsx:797-800 `data-testid-stub="page-actions-hidden"`); count 1 each, `is_visible()=False`; no other surface renders them. (2) **Pixel rotation works + durable**: POST rotate (degrees=90) → job complete → on-disk `001.png` rotated 1200x1600→1600x1200 (verified by re-reading the file), served image + `encoded_dims` follow. (3) **Rotation metadata persists in the store** (direct store read: `rotation_degrees=90, rotation_source="manual"`) **but the API payload never surfaces it** — `page_record.rotation_degrees` stays `0/none` even after POST /load, so the rotation badge can't render. (4) **Re-OCR after rotate does not take effect**: served words/bboxes are byte-identical to pre-rotate (portrait coords, max x+w=767 in a 1600-wide image) in both the in-memory GET and a forced store re-probe — overlays are now misaligned with the rotated pixels. (5) 180° button exists (S8.4) but same invisibility. |
| C29 | Auto-rotate-all (M9.2/S8.3) | **FAIL** | No UI trigger at all: zero non-generated frontend references to `auto-rotate-all` (types.ts only). Backend via curl: job completes, but production detection path crashes per page — "detection failed for page=1: incorrect input shape: all pages are expected to be multi-channel 2D images" on a plain RGB PNG; result `rotated=[] skipped=[0]`. The manual-rotation skip honor (`overwrite_manual=False` skips page with `rotation_source="manual"`) does work. |
| C30 | Auto-rotate config (toggle + method) | PASS (config only) | `auto-rotate-checkbox` + `auto-rotate-method-select` in OCRConfigModal persist to ocr-config (`auto_rotate_on_load: true`, `auto_rotate_available: true`). Effect-on-load not separately verified (detection path broken per C29). |
| C31 | Job progress feedback during OCR jobs | PASS (toast-level) | "Running OCR…" loading toast during job, success toast on completion (screenshots b3-reload-progress / b3-after-reload). No progress *bar* outside ExportDialog; no jobs panel (see C-jobs row below). |
| C32 | Jobs list / queue UI | FAIL (unchanged) | `GET /api/jobs` works (returned 4 completed jobs) but remains backend-only; no jobs panel UI anywhere. |
| C33 | Generic job cancel | PARTIAL (unchanged) | `POST /api/jobs/{id}/cancel` exists; only ExportDialog exposes a cancel button (verified in C-export rows). |

## Notes

- Hidden `data-testid-stub="true"` duplicates exist for many legacy testids
  (source-folder-\*, ocr-\* etc.). Selectors must exclude them
  (`:not([data-testid-stub])`); they otherwise mask the real elements.
- Playwright MCP browser wedged on this host (stale-DISPLAY issue per
  `tests/e2e/conftest.py`); sweep driven with repo-pinned Playwright +
  `DISPLAY` popped.
