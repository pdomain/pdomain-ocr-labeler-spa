---
kind: plan
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
disposition: Deep multi-agent code review findings and continuation roadmap.
source: multi-agent deep review (8 explore agents + controller verification)
---

# Deep code review and continuation plan — 2026-07-21

## Agent Index

- **Kind:** plan
- **Status:** active
- **Read when:** choosing what to implement next after a full-system review;
  orienting a new agent on pipeline completeness; prioritizing residual work
  beyond the overnight index.
- **Search terms:** deep code review, pipeline gaps, continuation plan,
  residual work, sidecar persistence, M11, export CLI, CI gates

## Goal

**Main finding:** Core OCR labeling (project load, page OCR,
word/line/structure edit, refine, rotate, event-store save, in-app export) is
**substantially shipped**. The largest remaining holes are **sidecar
durability** (char bboxes/ranges and glyphs), **rematch autosave**, **M11 glyph
wiring**, **export list + CLI store parity**, **CI honesty**, and **docs that
still describe the retired envelope write path**.

This plan turns an independent multi-agent audit of `pdomain-ocr-labeler-spa`
into one ordered roadmap. The aim is a trustworthy end-to-end loop: discover →
load → OCR → edit → save → export → train handoff.

**Prioritization authority:** This plan sets the **cross-cutting order** for
residual work. The overnight index and per-topic plans stay the task-level
checklists. When they disagree on sequence, **prefer this plan** (data
integrity before chrome).

Update the overnight index and `current-state.md` to link here when this plan
lands, not later in a docs-only wave.

## Architecture

This plan does not change the product architecture. It assumes the current
shape:

- FastAPI + in-process job runner + filesystem event store (`.pd-pages/`)
- React SPA (pdomain-ui AppShell + ProjectPage workspace)
- Local DocTR OCR via `pdomain-book-tools`
- Deferred axes remain frozen (D-042): multi-user auth, S3, Postgres, cloud OCR

Eight parallel explore agents plus controller spot-checks produced the
evidence. Domains covered:

| Domain | Focus |
| --- | --- |
| Backend API/jobs | Routes, handlers, adapters, stubs |
| Frontend SPA | Mounts, mutations, hotkeys, orphans |
| Full pipeline | Discovery → export → CLI/trainer |
| M11 glyph residual | Plan claims vs code |
| Tests and CI | Coverage heat map, gate parity |
| PGDP + deferred axes | Intentional vs accidental incomplete |
| Persistence/history | Durability, undo, data-loss risks |
| Milestone parity | M0–M11 claimed vs verified |

This roadmap **coordinates** existing plans. Do not duplicate their task
checklists.

Overnight streams A–D stay valid **parallel** work when they do not touch store
serialization:

| Plan | Role vs this roadmap |
| --- | --- |
| [`2026-07-21-overnight-work-index.md`](2026-07-21-overnight-work-index.md) | Night-scoped stream map; subordinate to Waves 0–2 for order |
| [`2026-07-21-glyph-annotations-completion.md`](2026-07-21-glyph-annotations-completion.md) | M11 tasks T0–T11 (Wave 2) |
| [`2026-07-21-open-findings-fixes.md`](2026-07-21-open-findings-fixes.md) | KBD / XDG / RELOAD / HIER (Wave 3) |
| [`2026-07-21-ci-openapi-gates.md`](2026-07-21-ci-openapi-gates.md) | #430 / #433 only (Wave 4) |
| [`2026-07-21-pgdp-alignment-remaining.md`](2026-07-21-pgdp-alignment-remaining.md) | pdomain-ui chrome residual (Wave 5) |
| [`2026-07-21-tsconfig-test-strictness.md`](2026-07-21-tsconfig-test-strictness.md) | Test TS strictness (optional with Wave 4) |

## Tech Stack

No new stack. Implementation keeps using FastAPI, Pydantic v2, event-store page
blobs, React 19, TanStack Query, Playwright, pytest, Vitest, and the Make CI
targets already in the repo.

## Global Constraints

1. **Do not implement D-042 axes** (auth, S3, Postgres, server UI prefs, cloud
   OCR, multi-user locking) without explicit user OK.
2. **Do not port the PGDP 24-stage pipeline** into this SPA (intent-map Rejected).
3. **Do not rebuild glyph UI components.** Mount and wire existing ones.
4. **Specs win over code only after a deliberate change.** When code and
   architecture disagree on the *write* path, prefer the event-store reality
   and update the docs. Do not reintroduce UserPageEnvelope writers.
5. **Always `make ci AI=1` before commit.** Do not push without an explicit ask.
6. **Prefer existing residual plans** for task-level steps. This document owns
   prioritization and the gap inventory that spans those plans.

---

## Pipeline status at a glance

```text
Discovery / session restore ........ SHIPPED
Project load ....................... SHIPPED
Page load + lazy OCR ............... SHIPPED  (empty-OCR UX residual)
GT match / rematch ................. PARTIAL  (rematch not durable)
Edit words / lines / structure ..... SHIPPED  (core content path)
CharFixer / char ranges ............ PARTIAL  (in-memory only)
Glyph review (M11) ................. SCAFFOLD (~35% scaffold / ~20% usable path)
Refine bboxes ...................... SHIPPED
Rotate / auto-rotate ............... SHIPPED
Undo / redo (page content) ......... SHIPPED  (sidecars not in history)
Save page / save project ........... SHIPPED  (dirty-bit edge bugs)
In-app DocTR export ................ SHIPPED  (list API empty)
CLI export ......................... PARTIAL  (legacy envelopes only)
Trainer handoff .................... PARTIAL  (export path real; AppShell suite shim)
Remote OCR / S3 / multi-auth ....... DEFERRED (intentional)
```

**Usable local production loop today:** open project → OCR/edit GT and structure
→ save → export to DocTR training set → (optional) send to trainer when the
suite is installed.

**Not trustworthy yet:** glyph review, CharFixer durability across reload,
headless CLI re-export of SPA-saved projects, export history UI, and advertised
hotkeys that do nothing.

---

## Completeness scorecard

| Layer | Completeness | Notes |
| --- | ---: | --- |
| Core backend labeling | ~90% | Jobs and mutators real; sidecars incomplete |
| Core frontend labeling UX | ~80–85% | Right panel + canvas + drawer largely wired |
| Glyph (M11) scaffold | ~35–40% | Models, routes, components, bulk entry exist |
| Glyph (M11) **usable path** | **~20%** | No payload inject, persist, panel mount, or e2e |
| Export closed loop (SPA) | ~85% | Store-first export works when project loaded |
| Export closed loop (CLI) | ~40% | Still labeled-projects scan only |
| CI merge confidence | ~70% | Dense tests; GH omits local gates; e2e soft |
| Architecture docs accuracy | ~60% | Persistence/envelope docs lag event store |
| PGDP / suite chrome | ~50% | Primitives mostly done; launcher/jobs/history open |

Use **~20% usable path** when talking about human glyph review. Use **~35%
scaffold** only when counting files and seams that already exist.

---

## Critical findings, ranked by severity

### P0 — silent loss, false success, or unusable advertised surface

| ID | Finding | Evidence | Impact |
| --- | --- | --- | --- |
| **P0-SIDECAR-MAP** | Char ranges and char bboxes write in-memory maps and return **200** without event-store serialization (STUB after M5b). Glyph maps share the same STUB pattern but are owned by **P0-GLYPH-*** / Wave 2 T3 issue | `api/words.py` STUB `pass` on set_char_ranges / set_char_bboxes | CharFixer work vanishes on reload even after Save Project |
| **P0-REMATCH** | Rematch updates live `Page` GT in memory, then no-op “envelope” write; does **not** call content-blob autosave | `api/pages.py` rematch + no-op helper | Rematch lost unless a later content mutator or successful save serializes the page |
| **P0-GLYPH-READ** | Glyph maps never injected into page payload | `_page_payload` passes char maps only; `page_to_line_matches` reads word attrs, not sidecar | POST set is invisible even in-session |
| **P0-GLYPH-UI** | `GlyphAnnotationPanel` unmounted; no mutation hooks; chip clicks stubbed; bulk apply no RQ invalidation | `WordDetail.tsx`, `WordCell.tsx`, `BulkGlyphMarkDialog.tsx` | M11 not usable |
| **P0-EXPORT-LIST** | `GET .../exports` always returns `[]` while handler writes doctr-export manifests | `api/export.py` list_exports; `handlers/export.py` `_write_export_manifest` | Export history / discovery broken via API (shape mismatch — see Wave 1.0) |
| **P0-CLI-STORE** | CLI export scans `labeled-projects/` envelopes only; SPA saves to event store | `export_cli.py` `_scan_labeled_pages` | Headless/batch export of SPA projects can be empty |
| **P0-SAVE-DIRTY** | `save_project` and single-page `save_page` advance `last_saved_generation` when `page_id` is unset **or** after changelog-only fallback (no content blob) so the page looks clean without durable content | `handlers/save_project.py` ~164–199; `api/pages.py` ~939–972 | False clean state. (No-store in-memory sessions are intentional; out of scope.) |
| **P0-CI-SOFT** | GitHub e2e is `continue-on-error: true`; hierarchy and other e2e paths soft-skip | `.github/workflows/ci.yml`; `test_ui_coverage.py` HIER-1; multi-line / exercise skips | Green CI with broken UI paths. **Severity note:** process/confidence risk, not user data loss. Hard gate is **P2-E2E-GATE** (mini-plan after HIER-1). Keep visible as P0 for merge confidence only. |

### P1 — correctness, honesty, ops

| ID | Finding | Disposition |
| --- | --- | --- |
| **P1-JOB-SSE** | FE `useJobProgress` expects nested `{job_id,status,progress{…},error_message}`; runner SSE emits flat `{type,status,current,total,message,error}`. First frame often `event: snapshot` (unhandled). Cancel/message/id broken at runtime | **Wave 3a** (or parallel with Wave 1) |
| **P1-JOB-TYPE** | `ProjectPage` synthesizes every tracked job as `type: "reload_ocr_page"`, so BusyOverlay cancel policy is wrong for save/export | **Wave 3a** with P1-JOB-SSE |
| **P1-CANVAS-ERASE** | Canvas erase mode has no `onErasePixels` on `ProjectPage` → erase drag is a no-op (right-panel erase is wired) | **Wave 3** |
| **P1-IMAGE-DRIFT** | `ImageDriftBanner imageDrift={false}` hard-disables 409 recovery UX | **Wave 3** |
| **P1-HOTKEY** | `mod+,` and `mod+j` (and other map entries) advertised, not registered | **Wave 3** (open-findings) |
| **P1-MATCH-NAV** | Matches J/K only update worklist store; do not `selectLine` | **Wave 3** |
| **P1-BBOX-UI** | BBox Refine/Crop buttons call rebox only | **Wave 3** |
| **P1-SUITE** | AppShell `fetchInstalled` / `postLaunch` are shims; backend suite routes exist | **Wave 5** (PGDP item 5) |
| **P1-MUTATION-200** | Best-effort store write failures still return HTTP 200 | **Wave 0.5** |
| **P1-XDG** | Default `data_root` is `~/pdomain-ocr-labeler-spa`, not XDG | **Wave 3** (BUG-SMOKE-3) |
| **P1-NORMALIZE** | `normalize_recognition_labels` on export request not put in job payload | **Wave 1.4** |
| **P1-CANCEL** | Cooperative cancel mainly honored by export, not OCR/`auto_rotate_all` page loop | **Wave 3b** (handler cancel tokens) |
| **P1-JOBS-API** | `GET /api/jobs` dumps runner fields (`job_id`, `job_type`, …) vs OpenAPI Job (`id`, `type`, `progress`) | **Wave 5** contract gate before Jobs pill (like Wave 1.0) |
| **P1-DOC-PERSIST** | `09-persistence.md` still describes UserPageEnvelope write path | **Wave 6** |
| **P1-CI-GATES** | GH missing pre-commit + knip; openapi-drift still mentions gitignored `openapi.json` | **Wave 4** |
| **P1-BEHAVIOR-COV** | `make ci` runs `behavior-coverage`; GH does not (outside ci-openapi plan) | **Wave 4 residual / backlog** |

### P2 — polish, docs, deferred product chrome

| ID | Finding |
| --- | --- |
| **P2-ROOT** | Project cards lack page/progress metadata; non-`all` filters no-op → **Wave 5** |
| **P2-JOBS-UI** | No JobsPill/Drawer; backend job list exists → **Wave 5** (after P1-JOBS-API) |
| **P2-SETTINGS-6** | PGDP item 6: `persistApp` no-op / no server prefs → **Wave 5 honesty only** (server prefs remain D-042) |
| **P2-U-M7** | Event-store history panel designed, not built (undo v1 OK) → **Wave 5 later** |
| **P2-ORPHANS** | `FilterToggle`, `StudioShell` production-orphaned → **Wave 6 or delete with tests** |
| **P2-FS-DURABILITY** | Atomic writers lack fsync before rename → **backlog** (single-user laptop risk) |
| **P2-PROJECT-LOCK** | Project-level lock constructed, never acquired by routes → **backlog** (D-023 single-user) |
| **P2-UNCLEAR** | `unclear-items.md` still claims rotation stubbed / archive inert; BUG-KBD-4 still listed open → **Wave 6** |
| **P2-TS-TEST** | Test tsconfig looser than app (#366 residual) → **Wave 4 optional** |
| **P2-E2E-GATE** | E2e non-blocking + soft-skips beyond HIER-1 → **new mini-plan after Wave 3 HIER-1**; not Wave 4. Inventory: `test_ui_coverage`, multi-line soft-skips, `exercise_real_project` CU-2.2 mass skip |
| **P2-GLYPH-%** | Sibling glyph plan still says “overall usable ~35%” → rewrite to ~20% usable / ~35% scaffold (**Wave 2 T11** / docs) |

### Intentionally out of scope (not pipeline gaps)

Do **not** treat these as “missing pipeline” work:

- Modal / SharedContainer OCR (`NotImplementedYet`)
- S3 storage / JWT auth / Postgres app DB
- PGDP 24-stage stage runner / submit / pack stages
- Server-side UI prefs API (D-042)
- Multi-tab optimistic locking (D-023 last-writer-wins)

---

## Full pipeline status by confidence

### Shipped and verified (high confidence)

1. **Boot, discovery, session restore** — projects list, load, session_state.
2. **Page payload + GT matching on OCR** — event-store load first, OCR fallback.
3. **Word/line/paragraph structural and GT edits** that call store best-effort.
4. **Jobs:** reload OCR, refine, rotate, auto-rotate-all, save_project, export.
5. **Right-panel editing** (WordDetail sections except Typography/glyph).
6. **Canvas selection, worklist, hierarchy navigation, toolbars.**
7. **In-app export** store-first with manifest write.
8. **Undo/redo for page content blobs.**
9. **Cut-over / M0–M10 product path** (with filename drift vs milestone docs).

### Partial or broken residual (product-real)

1. **Sidecar durability** after envelope lane retirement (M5b incomplete).
2. **M11 glyph** scaffold without read path, persist, or FE mount.
3. **CLI export** not on event store.
4. **Export listing API** empty stub.
5. **Job SSE FE↔BE contract** flat vs nested (BusyOverlay / cancel / progress).
6. **Canvas erase** mode unmounted callback; **image_drift** banner hard-off.
7. **Suite launcher** AppShell shims vs real suite mount.
8. **Open findings** keyboard / XDG / reload UX / hierarchy e2e.
9. **CI gate parity** and non-blocking e2e.

### Deferred / out of scope

D-042 managed axes and the PGDP stage product model stay out of scope. See
Out of Scope in
[`docs/plans/2026-07-21-pgdp-alignment-remaining.md`](2026-07-21-pgdp-alignment-remaining.md).

---

## Issue index (split work packages)

Each row is a governed issue under `docs/issues/`. Prefer implementing by issue
(or wave cluster), not by re-reading the full plan body.

| Wave | Issue file | Plan IDs |
| --- | --- | --- |
| 0 | [`docs/issues/2026-07-21-sidecar-char-maps-not-durable.md`](../issues/2026-07-21-sidecar-char-maps-not-durable.md) | P0-SIDECAR-MAP (char), 0.1–0.2, 0.6 |
| 0 | [`docs/issues/2026-07-21-rematch-gt-not-durable.md`](../issues/2026-07-21-rematch-gt-not-durable.md) | P0-REMATCH, 0.3 |
| 0 | [`docs/issues/2026-07-21-save-project-false-clean.md`](../issues/2026-07-21-save-project-false-clean.md) | P0-SAVE-DIRTY, 0.4 |
| 0 | [`docs/issues/2026-07-21-mutation-store-silent-200.md`](../issues/2026-07-21-mutation-store-silent-200.md) | P1-MUTATION-200, 0.5 |
| 1 | [`docs/issues/2026-07-21-export-list-api-empty.md`](../issues/2026-07-21-export-list-api-empty.md) | P0-EXPORT-LIST, 1.0–1.1 |
| 1 | [`docs/issues/2026-07-21-cli-export-not-store-first.md`](../issues/2026-07-21-cli-export-not-store-first.md) | P0-CLI-STORE, 1.2–1.5 |
| 1 | [`docs/issues/2026-07-21-export-normalize-flag-dead.md`](../issues/2026-07-21-export-normalize-flag-dead.md) | P1-NORMALIZE, 1.4 |
| 2 | [`docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md`](../issues/2026-07-21-glyph-m11-usable-path-incomplete.md) | P0-GLYPH-*, Wave 2 / T1–T11 |
| 3a | [`docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md`](../issues/2026-07-21-job-sse-fe-be-shape-mismatch.md) | P1-JOB-SSE, P1-JOB-TYPE |
| 3b | [`docs/issues/2026-07-21-canvas-erase-mode-noop.md`](../issues/2026-07-21-canvas-erase-mode-noop.md) | P1-CANVAS-ERASE |
| 3b | [`docs/issues/2026-07-21-image-drift-banner-hard-off.md`](../issues/2026-07-21-image-drift-banner-hard-off.md) | P1-IMAGE-DRIFT |
| 3b | [`docs/issues/2026-07-21-job-cancel-incomplete.md`](../issues/2026-07-21-job-cancel-incomplete.md) | P1-CANCEL |
| 3b | [`docs/issues/2026-07-21-match-nav-selection-desync.md`](../issues/2026-07-21-match-nav-selection-desync.md) | P1-MATCH-NAV |
| 3b | [`docs/issues/2026-07-21-bbox-refine-crop-misleading.md`](../issues/2026-07-21-bbox-refine-crop-misleading.md) | P1-BBOX-UI |
| 3b | (existing) [`docs/context/open-findings.md`](../context/open-findings.md) + open-findings plan | KBD / XDG / RELOAD / HIER |
| 4 | [`docs/issues/2026-05-22-gh-430-ci-equivalence.md`](../issues/2026-05-22-gh-430-ci-equivalence.md) | P1-CI-GATES |
| 4 | [`docs/issues/2026-05-22-gh-433-openapi-drift.md`](../issues/2026-05-22-gh-433-openapi-drift.md) | P1-CI-GATES |
| 4 | [`docs/issues/2026-07-21-e2e-non-blocking-soft-skips.md`](../issues/2026-07-21-e2e-non-blocking-soft-skips.md) | P0-CI-SOFT, P2-E2E-GATE |
| 5 | [`docs/issues/2026-07-21-suite-launcher-app-shims.md`](../issues/2026-07-21-suite-launcher-app-shims.md) | P1-SUITE |
| 5 | [`docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`](../issues/2026-07-21-jobs-api-openapi-mismatch.md) | P1-JOBS-API |
| 5 | [`docs/issues/2026-07-21-project-list-metadata-filters-noop.md`](../issues/2026-07-21-project-list-metadata-filters-noop.md) | P2-ROOT |

Full catalogue: [`docs/issues/README.md`](../issues/README.md).

---

## Continuation roadmap

Order work by **risk to user data** and **closed-loop usability**, then chrome
and docs. Prefer one worktree per independent stream.

### Wave 0 — Stop silent data loss (1–2 sessions)

**Goal (narrow):** CharFixer maps (ranges/bboxes) and rematch must either
persist via the event store or fail loudly.

Glyph map durability stays in **Wave 2 T3** (same strategy, after payload
inject). CharFixer Apply must not report silent success.

| Task | Work | Existing plan? |
| --- | --- | --- |
| 0.1 | **Decide sidecar durability strategy** and record it in `docs/context/decisions.md`. Options and criteria below. Must cover **undo**: if maps are out-of-blob, undo must clear/rehydrate maps (not leave stale overlays). | New — **gate for 0.2+ and glyph T3** |
| 0.2 | Persist char ranges + char bboxes on mutate using the 0.1 strategy | New (CharFixer) |
| 0.3 | Wire rematch-gt through existing content-blob autosave (`_save_to_store_best_effort` / `save_page_content_to_store`) — rematch mutates live `Page`, not a pure sidecar map | New |
| 0.4 | Fix `save_project` dirty-bit: when `page_id` is unset **or** only changelog-only fallback ran, **do not** advance `last_saved_generation`. Do **not** treat exception-path failures as clean (they already `continue` before advance). | New |
| 0.5 | Surface store-write failures to FE (non-200 or warning field) for content mutators that claim success today | New |
| 0.6 | Integration tests: set char sidecar → reload page → present; rematch → reload → GT mapping kept; skip-page and changelog-only never clean dirty bit; **undo after sidecar mutate** leaves consistent maps + content | New |

**0.1 decision criteria (required before mutator work):**

| Option | Prefer when |
| --- | --- |
| A. Embed maps in content `Page.to_dict()` / word dicts | book-tools `Page`/`Word` already or easily carries the fields; **simplest undo story** (blob restore includes maps) |
| B. Extension / side blob on page aggregate | fields are labeler-only and must not pollute book-tools dict; **must** define undo clear/rehydrate |
| C. Separate LabelerEdited payload fields outside content blob | need independent versioning of maps vs OCR structure; **must** define undo clear/rehydrate |

Default to **A** when product urgency wins and the fields fit word dicts.
Prefer **B** if book-tools rejects unknown keys on round-trip. Record the
choice and one rejected alternative before coding 0.2.

**Acceptance:**

- CharFixer Apply and rematch survive process restart.
- Save Project never marks a page clean for missing `page_id` or changelog-only
  writes.
- Content mutation store failures are visible.
- Undo after char-map mutate leaves maps and content coherent (clear, rehydrate,
  or embed-in-blob).
- Glyph set may stay session-only until Wave 2 T3.

### Wave 1 — Close the export loop (1 session)

| Task | Work | Existing plan? |
| --- | --- | --- |
| 1.0 | **Contract step:** map doctr-export on-disk manifest (`projects[id].exported_at`, `page_count`, tasks) to API `ExportManifest` (`job_id`, `scope`, `created_at`) and FE history. Either expand OpenAPI + FE types to match disk, or define a remapping (e.g. `created_at` ← `exported_at`, synthetic `job_id`/`scope`). Do not code list_exports until this is written (short note in decisions or plan update). | New — gate for 1.1 |
| 1.1 | Implement `GET .../exports` per the 1.0 contract (read `doctr-export` manifest, not invent empty stub) | PGDP item 14 (partial) |
| 1.2 | Make CLI export store-first (reuse in-app resolve/load helpers); write manifest | New |
| 1.3 | Optional: export non-loaded project via store open by `project_id` | New |
| 1.4 | Wire `normalize_recognition_labels` through job payload if product still wants it | New small |
| 1.5 | Integration: SPA save → CLI export non-zero pages | New |

**Acceptance:** An SPA-saved project exports non-empty via CLI. The export
dialog can list prior runs from the API using a documented shape.

### Wave 2 — M11 glyph usable path (multi-session)

Execute
[`2026-07-21-glyph-annotations-completion.md`](2026-07-21-glyph-annotations-completion.md)
in order. Feed the Wave 0.1 strategy into T3:

1. **T1** payload inject (`glyph_annotations_map` / predictions into
   `page_to_line_matches`)
2. **T2** HTTP integration tests (do **not** re-create GT ligature tests —
   already in `test_text_norm_config.py`)
3. **T3** durable persist/hydrate (align with Wave 0)
4. **T4–T7** FE hooks, WordDetail mount, chips, bulk invalidate
5. **T8–T9** metric honesty + e2e
6. **T11** docs close-out
7. **T10** optional predictor/overlay later

**Acceptance:** Set annotation → visible chips → reload → still present → bulk
mark updates UI without manual refresh.

### Wave 3 — Product honesty + jobs wiring (1–2 days)

#### 3a — Job SSE contract (can parallel Wave 1)

| Task | Work |
| --- | --- |
| 3a.1 | Unify wire format: either emit nested OpenAPI-shaped events from the API or adapt flat events in `useJobProgress` |
| 3a.2 | Listen for `snapshot` and `cancelled` SSE event types |
| 3a.3 | Pass real `job_type` from 202 responses into BusyOverlay synthesis (stop hard-coding `reload_ocr_page`) |
| 3a.4 | Unit tests with **flat** backend fixtures (not only nested mocks) |

#### 3b — Open findings + interaction bugs

Execute [`2026-07-21-open-findings-fixes.md`](2026-07-21-open-findings-fixes.md):

- BUG-KBD-1 / KBD-5 (+ prune dead dialog-scope help entries)
- BUG-SMOKE-3 XDG `data_root` (+ migration note for legacy roots)
- BUG-RELOAD-1 empty OCR / zero-area
- BUG-HIER-1 fail-hard hierarchy waits
- Mark BUG-KBD-4 resolved in `open-findings.md` if still listed open

Also:

- **P1-MATCH-NAV** — J/K → `selectLine`
- **P1-BBOX-UI** — wire refine/crop or relabel
- **P1-CANVAS-ERASE** — wire `onErasePixels` or hide erase mode
- **P1-IMAGE-DRIFT** — wire 409 `image_drift` → banner
- **P1-CANCEL** — cooperative cancel checks in `auto_rotate_all` (and OCR-heavy handlers where cheap)

### Wave 4 — CI honesty (0.5–1 day)

Execute [`2026-07-21-ci-openapi-gates.md`](2026-07-21-ci-openapi-gates.md):

- pre-commit job on GH
- knip on GH
- openapi-drift checks only `frontend/src/api/types.ts`

Residual (document even if not coded):

- **P1-BEHAVIOR-COV** — whether to add `behavior-coverage` to GH or accept local-only
- Optional same session:
  [`2026-07-21-tsconfig-test-strictness.md`](2026-07-21-tsconfig-test-strictness.md)

**Out of this wave:** making e2e merge-blocking (**P2-E2E-GATE**). After
HIER-1, write a mini-plan: stable smoke suite list, soft-skip inventory, fail
policy. Until then P0-CI-SOFT remains a **merge-confidence** residual only.

### Wave 5 — Suite / root / jobs chrome (PGDP residual)

From [`2026-07-21-pgdp-alignment-remaining.md`](2026-07-21-pgdp-alignment-remaining.md):

| Priority | Items |
| --- | --- |
| Small / high value | Item 5 suite launcher real endpoints; Item 9 archive decision ADR |
| Medium | Item 14 export history UI (after Wave 1 list API); **Item 4 Jobs pill after P1-JOBS-API contract**; Items 7–8 project metadata + filters |
| Honesty | **Item 6** — document localStorage/`persistApp` no-op as intentional under D-042; do not build `/api/ui-prefs` |
| Docs | Items 2, 3, 11 matrices / drawer docs |
| Later | Items 10, 12, 15 (workbench extract, detail shell, U-M7 panel) |

**Jobs pill gate (like Wave 1.0):** before UI, map runner job dump → OpenAPI
`Job` (`id`/`type`/`progress`) or change OpenAPI to match runner.

### Wave 6 — Doc truth + stale inventory cleanup

| Doc | Action |
| --- | --- |
| `docs/architecture/09-persistence.md` | Rewrite for event-store-first; envelope as historical read-compat |
| `docs/architecture/02-backend.md` | Align path names (`/gt`, `/validated`); drop or mark missing routes |
| `docs/architecture/runtime-flows.md` | Export list + store-first + job SSE reality; retire XHTML claims if obsolete; **stale banner if not fully rewritten yet** |
| `docs/specs/behavior/unclear-items.md` | Remove stale rotation stub / archive inert / WordEditDialog / canvas-erase rows once fixed |
| `docs/architecture/module-map.md` | Drop WordEditDialog / S3 file claims; note ops page types |
| `docs/context/open-findings.md` | Resolve BUG-KBD-4; keep only open rows |
| Glyph plan scorecard | Align to ~20% usable / ~35% scaffold |
| `docs/context/current-state.md` | Keep link to this plan; note residual P0s after each wave |
| Overnight index | **Hard gate:** do not start Streams A–D product-critical work before Wave 0 when data-loss P0s remain open |

---

## Recommended session order

```text
Session A (data integrity)     Wave 0.1–0.6          ← required first for data-loss P0s
Session B (export closed loop) Wave 1
Session B′ (job SSE)           Wave 3a               ← parallel-safe with B
Session C–E (M11)              Wave 2                ← T1 after 0.1; T3 after 0.1 strategy
Session F (findings + erase)   Wave 3b
Session G (CI)                 Wave 4                ← parallel with F safely
Session H (suite + root)       Wave 5
Session I (docs)               Wave 6                ← start early; finish after code
```

**Overnight / parallel gate:** Streams that only touch CI, docs, suite launcher,
or job-SSE may run anytime. Streams that touch store serialization, glyph
persist, or `save_project` must follow Wave 0. Do not schedule overnight glyph
T3 before the 0.1 durability decision.

Safe parallelism:

- **Wave 4 (CI)** ∥ **Wave 3a (job SSE)** ∥ **Wave 3b (findings)** ∥ **Wave 6 docs**
- **Wave 2 T1 (backend glyph inject)** ∥ **Wave 1 (export)** if different files
- Avoid concurrent FE edits to `WordDetail` / `ProjectPage` / `App.tsx` without
  coordination. Glyph, suite, erase, and hotkeys touch adjacent surfaces.

---

## Definition of “full pipeline built”

A future agent may claim the local full pipeline is complete only when **all**
of the following hold:

1. Discover, load, OCR, edit (word/line/structure + char fixers), save, undo,
   rotate, refine, export, CLI re-export, and trainer launch (when installed)
   work on event-store data without silent loss.
2. Job progress SSE and BusyOverlay show real progress/cancel for each job type.
3. Canvas erase and image-drift recovery are wired or intentionally hidden.
4. Glyph review is optional product scope: either shipped end-to-end, or
   explicitly deferred with UI entry points hidden.
5. Advertised hotkeys and help match registered handlers.
6. `make ci` and GitHub CI share the same required gates. E2e smoke is
   merge-blocking, or intentionally split with a documented non-blocking suite.
7. Architecture persistence docs describe the event store as the write path.
8. D-042 / PGDP stage work remains out of scope unless re-authorized.


---

## What this review does not claim

- This review session did not run live `make ci` or a full Playwright green
  suite.
- Sibling `pd-ocr-labeler` binary parity was not re-diffed page-by-page.
- Exact coverage percentages come from prior `htmlcov` snapshots and suite
  inventory, not a fresh coverage gate.
- Security adversarial review was not requested and was not run.
- A later adversarial review (2026-07-21) found **additional** product gaps
  (job SSE shape, canvas erase, image_drift banner) that the first pass missed;
  those are now folded into this plan.

---

## Adversarial recheck (2026-07-21) — gaps closed into this plan

| Missed item | Now tracked as |
| --- | --- |
| Job SSE flat vs nested FE contract | **P1-JOB-SSE**, Wave 3a |
| Hard-coded job type in BusyOverlay synthesis | **P1-JOB-TYPE**, Wave 3a |
| Canvas erase no-op | **P1-CANVAS-ERASE**, Wave 3b |
| ImageDriftBanner always false | **P1-IMAGE-DRIFT**, Wave 3b |
| P1-CANCEL no work package | **Wave 3b** + auto_rotate_all |
| save_project changelog-only clean bit | **P0-SAVE-DIRTY** expanded, Wave 0.4 |
| Undo vs sidecar coherence | Wave 0.1 + 0.6 acceptance |
| Overnight A–D vs Wave 0 order conflict | Overnight gate (this plan + index) |
| Jobs list OpenAPI mismatch | **P1-JOBS-API**, Wave 5 gate |
| PGDP item 6 missing from Wave 5 | **P2-SETTINGS-6** |
| behavior-coverage GH gap | **P1-BEHAVIOR-COV** |
| Glyph % wording conflict | **P2-GLYPH-%** / T11 |

---

## Confidence summary

| Claim | Confidence | Bound by non-claims? |
| --- | --- | --- |
| Core load→edit→save→export path is real, not stub | High | Code-traced; not live e2e proven this session |
| Sidecar / rematch non-persistence is real silent loss | High | Explicit `pass` / no-op paths |
| Glyph payload inject missing + panel unmounted | High | Code-traced |
| CLI export not store-first; list_exports empty | High | Code-traced |
| Job SSE FE↔BE shape mismatch | High | Code-traced (adversarial recheck) |
| Canvas erase unmounted on ProjectPage | High | Code-traced (adversarial recheck) |
| M0–M10 cut-over claim fair for core labeling | **Medium–high** | No full suite run this session |
| M11 ~20% usable / ~35% scaffold | High | Usable path broken; scaffold files present |
| Architecture 09 / unclear-items staleness | High | Doc vs code |
| Multi-tab / multi-process safety | Medium | By design last-writer-wins |
| fsync practical severity on laptop FS | Medium | OS-dependent |

---

## Next steps for an implementer

1. Read this plan’s **Wave 0** and open a worktree.
2. Decide the sidecar durability design (include undo coherence). Write one
   short note in `docs/context/decisions.md` if the choice is non-obvious.
3. Land Wave 0 tests first (TDD), then mutator persist and the save_project
   fix (skip + changelog-only dirty bit).
4. Parallel: Wave 1 export + Wave 3a job SSE.
5. Wave 2 glyph T1 anytime; T3 only after 0.1. Wave 3b for erase/hotkeys/drift.
6. Use overnight index Streams A/B/D/E for parallel-safe work; honor the hard
   gate on glyph T3 and store mutators.

When a wave finishes:

1. Update **Pipeline status at a glance** and **Completeness scorecard** above.
2. Tick completed rows in the wave tables (or strike tasks).
3. Reflect “shipped this session” in `docs/context/current-state.md`.
4. Bump `last_verified` on this plan’s frontmatter.
