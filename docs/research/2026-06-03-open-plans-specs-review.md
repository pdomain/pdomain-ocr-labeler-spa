# OCR Labeler SPA — Open Plans & Specs Review

**Date:** 2026-06-03
**Author:** review pass (Claude)
**Scope:** All open/active plans and specs for `pdomain-ocr-labeler-spa`, in this
repo and in the workspace-root `docs/`, plus the upstream capability state in
`pdomain-book-tools`. Produces a catalog, overlap analysis, and an order of
operations to get the app fully working.

> Companion artifact: open-GH-issue cross-reference (this repo +
> `ocr-container-meta` + `pdomain-ui`) — see the issue-overlap section appended
> at the end once gathered.

---

## Executive summary

The app is **further along than CLAUDE.md's "Open work" list implies** — every GH
chore it lists (#286, #267–270, #366, #404, #405) is actually closed,
`OPEN_QUESTIONS.md` is empty, and all three security findings (F-001/F-002/F-003)
are fixed in code. The genuinely-missing functionality reduces to **six feature
gaps** plus **one large architectural migration** plus **infra/CI rollout**:

| What's actually open | Type | Blocked? |
|---|---|---|
| **Page-split event-store migration** (retire `UserPageEnvelope` → ops `PageStore`/`BlobStore`) | Architecture | **No — ready now** |
| **M6 toolbar action grid — frontend wireup** (full Page/Para/Line/Word actions) | Feature (stubbed in code) | **No** — backend done; only the grid click handler is unwired |
| **Header/viewport chrome parity** (layer toggles, selection-mode, erase + dropped action buttons) | Feature (built but unmounted) | **No** — components exist; not rendered / omitted from compact bar |
| **M9.1/M9.2 image rotation** (manual + auto) | Feature (stubbed in code) | **Yes** — needs book-tools rotation module (not built) |
| **M10 text normalization** | Feature | **Yes** — needs `book_tools.text.normalize` (not built) |
| **M11 glyph predictions** (manual half shipped) | Feature | **Yes** — needs `pd-ocr-trainer` glyph classifier (not shipped) |
| local-dev / update-deps / dep-refresh rollout | Infra/CI | No |
| Pre-existing **red CI** (release-workflow, dockerfile, OCR-weights tests) | Release blocker | — |

**Verified upstream state (2026-06-03):** `pdomain-book-tools` `main` has **no**
rotation, geometry/dewarp, or `text.normalize` modules. The page-split migration,
by contrast, is fully unblocked — book-tools `0.17` and `pdomain-ops 0.7.1` are
pinned in `pyproject.toml` and published.

---

## A. Repo-local specs & tracked work (`pdomain-ocr-labeler-spa/`)

| Item | Status | Gap / blocker |
|---|---|---|
| `specs/16-milestones.md` — M0–M10, M9.5, FO/CU all shipped | Mostly done | **M6 grid wireup + M9.1/M9.2 rotate stubbed**; M10 normalize pending upstream |
| **M6 toolbar action grid — frontend wireup** | **Stub** — `ToolbarActionGrid.tsx` renders the full 4×14 Page/Para/Line/Word matrix with correct enable/disable; all backend routes exist (`api/words.py`, `api/lines_paragraphs.py`) | `ProjectPage.tsx:558` `handleToolbarAction(_key)` only calls `invalidatePage()` — dispatches no mutation; Apply-Style is a no-op. Most actions (all paragraph ops, line split/extract, word→line, →paragraph, batch validate/copy, selection refine/expand) have **no working trigger**. A subset (line merge/delete/validate/copy, word merge/split) works via the right panel + hotkeys. Deferral tracked only in **archived** parity docs (`2026-05-14-konva-parity-execution-plan.md`, `PARITY_GAPS_2026_05_14.md §2.5`) + an inline TODO — no live milestone/issue. |
| **Header/viewport chrome parity** | **Partial gap** — most legacy header controls relocated into the slim `HeaderBar` (navSlot = `ProjectNavigationControls`, actionsSlot = `PageActionsCompact`); project-load moved to RootPage; OCR-config trigger orphaned then restored (#405, done). HeaderBar itself was **not** removed — D-046 only deprecated its legacy stub testids | **Two unmounted/dropped clusters:** (1) the whole image-viewport toolbar — Show Para/Lines/Words checkboxes, Select-Para/Line/Word mode radio, Erase Pixels, color legend — is fully built in `ImageTabsHeader.tsx` but **rendered nowhere** (commented out at `ProjectPage.tsx:18`); survives only via canvas store + hotkeys + `canvas-mode-pill`. (2) `PageActionsCompact` omits **Reload OCR (Edited)**, **Save Project**, **Load Page**, and manual **Rotate CW/CCW** — these exist only in the *hidden* full `PageActions` bar (driver-contract testids). Frontend-only mounting gap; backend + components already exist |
| **M9.1 manual rotate** (`core/jobs/handlers/rotate.py`) | **Stub** — job/SSE plumbing only; image never rotated | `book_tools.ocr.rotation.rotate_image` **does not exist** |
| **M9.2 auto-rotate-all** (`auto_rotate_all.py`) | **Stub** — `asyncio.sleep(0)` placeholder | `detect_best_rotation` **does not exist**; depends M9.1 |
| **M10 text normalization** | Pending | `book_tools.text.normalize` **not implemented** |
| `specs/20-glyph-annotations.md` (M11) | Manual half **shipped** (#267/#270 closed) | Predictions half needs `pd-ocr-trainer` `IGlyphPredictor` classifier (unshipped) |
| `specs/17-decisions.md` — D-042 umbrella | Deferred by design | Auth/S3/Postgres/cloud-OCR/optimistic-locking — **do not build without user OK** |
| `OPEN_QUESTIONS.md` | **Empty** — all resolved | — |
| ~~`docs/specs/F-001` path-traversal, `F-002` CORS/auth~~ → **archived** to `docs/archive/specs/` (2026-06-03); F-003 traceback leak | **Fixed in code** (#406/#407/#408 closed) | Done — moved out of active list |
| `docs/archive/research/BUGS_FOUND.md` | **Stale** — entries read "open" but backing issues closed | Doc hygiene only |
| `docs/archive/plans/plan-to-usable.md` | All 11 rows checked — cut-over complete | — |

## B. Workspace docs touching labeler-spa (`/workspaces/ocr-container/docs/`)

| File | Relationship to labeler-spa | Status |
|---|---|---|
| **`plans/2026-06-01-page-split-labeler-spa.md`** | THE major labeler-spa plan — 14 milestones, 94 steps. Retire envelope/lanes/image-cache → `LabelerPageStore` + `extensions["labeler"]`, rebuild pages/words/lines API on ops `PagePayload`, blob-serve images, regen TS, Playwright verify | **NOT STARTED, fully unblocked** |
| `specs/2026-06-01-page-server-extensible-distributed.md` | The **approved v2 design** the above plan implements | Approved 2026-06-01 |
| `specs/2026-05-31-page-record-ops-design.md` | Foundational `Page`/`PageRecord` split design | Base spec; ops/book-tools realizations shipped — kept as reference (labeler consumption pending) |
| `plans/2026-06-02-geometry-correction-book-tools.md` | Upstream — deskew/dewarp/page-side protocols. **This backs M9.1/M9.2** | **Not started** (book-tools `main` has no geometry module) |
| `plans/2026-06-02-textline-disparity-dewarp.md` | Upstream — classical dewarp backend; depends on geometry plan | **Not started** |
| `plans/2026-05-24-local-dev-standardization.md` (#362) | Infra rollout | Active; labeler-spa's `local-*` targets already present |
| `plans/2026-05-24-update-pd-deps.md` (#363) | Infra rollout; blocked_by #362 | Active; `update-pdomain-deps` target already present |
| `plans/2026-05-31-dep-refresh-github-action.md` | Infra — weekly auto dep refresh across 12 repos | Active |
| `plans/2026-05-28-writing-style-rollout.md` | Docs rollout | labeler-spa slice applied; **held** — workspace-wide rollout completion unverified (0/23 boxes, no release proxy) |
| `specs/2026-05-16-cross-cut-design.md` | Extract canvas/word-panel from labeler-spa into `pdomain-ui` | Phase 2 ongoing (pdomain-ui side) |

> **Archived as done this pass (2026-06-03)** — moved to `/workspaces/ocr-container/docs/archive/`:
> `page-split-book-tools.md` (Plan 1, book-tools 0.17 shipped), `page-record-ops-pdomain-ops.md`
> (Plan 2, ops 0.7.1 shipped), the five `pdomain-rename-phase-*.md` + `pdomain-prefix-finalization.md`
> (rename complete & pushed, no open meta issues), and the superseded
> `page-split-downstream-rollout.md` spec. Repo-local: `F-001`/`F-002` security specs →
> `docs/archive/specs/`. **Note:** these plans carried `status: ready` with 0 checked boxes —
> completion was confirmed via shipped package versions + closed GH issues, not in-file checkmarks.

---

## C. Overlap analysis

1. **Page-model work is one program split across docs.** The v2 spec, the
   downstream-rollout spec, the page-record-ops design, and the three page-split
   plans (book-tools / ops / labeler-spa) are all the *same* migration. Only Plan 3
   (labeler-spa) has open work; Plans 1–2 shipped; the rollout spec is superseded.
   **Treat the v2 spec + Plan 3 as the single source of truth and ignore the
   superseded rollout spec's "Phase A" recommendation.**

2. **Rotation feature spans two repos with no integration plan.** M9.1/M9.2
   (labeler stubs) ↔ geometry-correction + textline-dewarp (book-tools, unbuilt).
   The labeler stub imports `book_tools.ocr.rotation.rotate_image`, but the
   book-tools plans build a *different* `geometry_correction` package. **There is
   no plan reconciling the stub's expected import path with what book-tools will
   actually ship** — this is a real gap to close before coding.

3. **Rotation writes through the model the migration deletes.** M9.1's stub writes
   `PageRecord.rotation_degrees`/`rotation_source`; Plan 3 deletes local
   `PageRecord`/`RotationSource` and moves to `extensions["labeler"]`.
   **Implementing rotation before the migration = throwaway code.** Sequence the
   migration first.

4. **M6 grid "shipped" but only render + backend delivered.** Same pattern as
   rotation: the milestone is marked done, but the unified grid's click handler
   (`ProjectPage.tsx:558`) is a deliberate stub and the wireup was knowingly
   deferred — captured only in *archived* parity docs and an inline TODO, with no
   live milestone or issue. This is the single largest *user-facing* parity gap
   vs. the legacy labeler. The grid calls the same `api/words.py` /
   `api/lines_paragraphs.py` endpoints the page-split migration rebuilds, so wiring
   it should coordinate with (ideally follow) Phase 1 to avoid re-touching callers.

5. **Header/viewport chrome parity — same "built but not mounted" pattern.** The
   image-viewport toolbar (`ImageTabsHeader.tsx`) is fully implemented but rendered
   nowhere, and `PageActionsCompact` silently drops four legacy buttons. Like the
   M6 grid, the components and backend exist — only the frontend mounting is
   missing — so the two should be tackled together as one "frontend parity" pass.
   The HeaderBar deprecation (D-046/#401) was *testid* cleanup, not control removal;
   the one control it orphaned (OCR-config, #405) is already restored.

6. **Stale docs create phantom work.** CLAUDE.md "Open work," `BUGS_FOUND.md`, and
   the F-00x "Draft" headers all describe closed/shipped work as open. Cheap to
   fix, prevents wasted re-investigation.

---

## D. Order of operations to get the app fully working

**Phase 0 — Doc hygiene** *(cheap, no code; do first so nobody re-chases closed work)*
- Rewrite CLAUDE.md "Current milestone / Open work" to reflect reality (all listed issues closed).
- Flip F-001/F-002/F-003 spec headers `Draft → Implemented`; prune stale `BUGS_FOUND.md` entries into `BUGS_RESOLVED.md`.
- Add the D-003 data-root-default reversal note flagged by the rename finalization.

**Phase 1 — Page-split event-store migration** *(Plan 3 — the foundation; fully unblocked)*
- Execute `2026-06-01-page-split-labeler-spa.md` under the approved v2 spec. This is
  the largest single piece of open work and everything else writes through the new
  model, so it lands first.
- Gate: ends green with the mandatory Playwright browser verification.

**Phase 2 — Upstream capability builds** *(book-tools / trainer; can run in parallel with Phase 1, different repo)*
- 2a. `geometry-correction` package in book-tools (deskew/dewarp/page-side) — **and**
  reconcile the public rotate-helper API with what the labeler rotate handler
  imports (close overlap #2).
- 2b. `textline-disparity-dewarp` backend (depends on 2a).
- 2c. `book_tools.text.normalize` for M10.
- 2d. `pd-ocr-trainer` glyph classifier (`IGlyphPredictor`) for M11 predictions.

**Phase 3 — Wire the missing features** *(against the new model + Phase 2 capabilities)*
- 3a. **M6 toolbar action grid wireup** — replace the `handleToolbarAction` /
  `handleApplyStyle` stubs with real mutations against the existing
  `api/words.py` / `api/lines_paragraphs.py` routes; port the legacy
  `test_toolbar_{page,paragraph,line,word}_actions.py`. **Only needs Phase 1** (no
  upstream/book-tools dep) — biggest user-facing parity win, do it first in this phase.
- 3a-bis. **Header/viewport chrome parity** — frontend-only, no upstream dep.
  *Quick win:* mount `ImageTabsHeader.tsx` to restore the layer-visibility toggles,
  selection-mode radio, Erase button, and color legend. Then surface the four
  controls `PageActionsCompact` drops (Reload OCR Edited, Save Project, Load Page,
  Rotate CW/CCW) — either in the compact bar or an overflow menu. Group with 3a
  since both are pure frontend mounting against existing components/endpoints.
- 3b. **M9.1 manual rotate** — replace stub; rotate via book-tools helper, re-OCR,
  write rotation state into `extensions["labeler"]`, auto-save. *(needs 1 + 2a)*
- 3c. **M9.2 auto-rotate-all** — wire `detect_best_rotation` + OCR engine. *(needs 3b)*
- 3d. **M10 text normalization.** *(needs 2c)*
- 3e. **M11 glyph predictions half.** *(needs 2d)*

**Phase 4 — Release readiness & infra** *(independent; interleave anytime, but gate any release on the red CI)*
- Fix pre-existing **red CI** (`test_release_workflow.py` ×7, `test_dockerfile.py`,
  OCR-integration weight tests) — flagged as a release blocker by the rename finalization.
- Complete local-dev standardization (#362) → update-pd-deps (#363) → dep-refresh GH action rollout.

**Deferred — do not build without explicit user OK (D-042):** auth, S3, Postgres,
per-user-prefs backend, optimistic locking, cloud OCR engines.

---

**Critical path to "fully working":** Phase 1 (migration) → **3a M6 grid wireup**
(biggest user-facing win, only needs Phase 1) → Phase 2a/2c/2d (upstream caps,
parallel) → rest of Phase 3 (rotation/normalize/glyph). Phases 0 and 4 are
independent and can run alongside.

**Two open decisions before coding starts:**
1. Confirm the migration (Phase 1) goes before rotation so M9.1 isn't written twice.
2. The rotate-handler ↔ geometry-correction API mismatch (overlap #2) has no owning
   plan — it needs one.

---

## E. Open GH issue cross-reference

> Gathered 2026-06-03 across `pdomain/pdomain-ocr-labeler-spa` (4 open),
> `ConcaveTrillion/ocr-container-meta` (21 open; 8 labeler-relevant), and
> `pdomain/pdomain-ui` (**0 open**).

### Headline finding

**The substantive roadmap (P1–P3 feature work) has essentially no GitHub tracking
issues.** The labeler-spa tracker is down to 4 housekeeping chores; pdomain-ui has
zero open issues. Page-split migration core, **M6 grid-action wireup**,
**header/viewport chrome parity**, geometry/rotation, dewarp, text-normalize, the
glyph classifier, and all M9.1/M9.2/M10/M11 wiring are **untracked in GitHub**. If
that work is meant to proceed, issues need to be cut.

### Open issues by tracker

**`pdomain/pdomain-ocr-labeler-spa`** (4 — all housekeeping)

| # | title | labels | roadmap bucket |
|---|---|---|---|
| 460 | Revisit `cast(Page,…)` vs `isinstance(…)` in lift resolvers after M3 PageRecord lands | chore, **blocked**, refactor | **P1** (cleanup tail of page-split; blocked on PageRecord) |
| 437 | [F-032] Route/OpenAPI tests check presence, not schema quality | chore, backlog, tests | **P4** (CI/test gate) |
| 433 | [F-028] OpenAPI drift check compares ignored `frontend/openapi.json` | chore, backlog, ci | **P4** (CI gate) |
| 430 | [F-025] GitHub CI not equivalent to documented `make ci` | chore, backlog, ci | **P4** (red-CI / release blocker) |

**`pdomain/pdomain-ui`** — no open issues. (Its work is tracked in meta #12 + #333.)

**`ConcaveTrillion/ocr-container-meta`** (labeler-relevant subset)

| # | title | bucket |
|---|---|---|
| 386 | `make update-pd-deps`: CWD bug + misdetects local-dev mode from worktree | **P4** (update-pd-deps #363 family — this is the bug behind it) |
| 257 | feat: workspace-wide version bumping + release discipline (all pd-*) | P4 (workspace-wide) |
| 210 | spec: workspace-wide versioning + release discipline (rollout) | P4 (dup of #257) |
| 291 | chore: roll out lint-deviation docs to all pd-* repos | unmapped (docs rollout) |
| 333 | spec: pd-ui design-handoff port (recon + atoms + templates) | unmapped (feeds labeler UI via pd-ui) |
| 12  | pd-ui — new TS/React/Vite shared component library | unmapped (foundational; Phase 2 in progress) |
| 292 | Workspace: torch-free pd-book-tools subset for non-OCR consumers | unmapped (touches the dep root P2a/P2b build on) |
| 290 | Close the cross-cut tracking issue (trainer-retirement) | out of scope (trainer) |

### Overlap / duplication

- **#210 ⟷ #257 (meta) — duplicate.** Same versioning/release-discipline program;
  one is the spec, one the rollout entry point. Consolidate.
- **#430 ⟷ #433 (labeler-spa) — same OpenAPI/CI gate.** Both from the same
  `2026-05-22-deep-code-review-security-scan.md`; fix in one pass.
- **#12 → #333 (meta) — sequential, not duplicate.** #333 (design-handoff port)
  builds on #12 (pd-ui library). Both feed labeler-spa indirectly via shared
  components (PageImageCanvas, AppShell) — the cross-cut design (§B).
- **#460 (labeler-spa)** — cleanup tail blocked on PageRecord landing; becomes
  actionable the moment Phase 1 (page-split) lands. No cross-tracker twin.
- **No cross-tracker duplication** between labeler-spa repo issues and meta plan
  issues. Confirmed the CLAUDE.md "Open work" list (#286/#267-270/#366/#404/#405)
  is fully closed — none appear in the open set.

### Flagged actions

1. **Cut tracking issues for the real work.** P1 page-split core, P2a–P2d upstream
   capabilities, and P3 feature wiring have no GitHub issues. The roadmap above is
   the only record. Sync via `/decompose-spec --sync` on the page-split plan, and
   open book-tools/trainer issues for P2.
2. **Consolidate meta #210 + #257** (release-discipline duplicate).
3. **Fix labeler-spa #430 + #433 together** (OpenAPI/CI gate) — and #430 is the
   red-CI release blocker from Phase 4.
4. **Re-triage #460** once Phase 1 lands — its `status:blocked` clears then.
5. **Meta #386** (update-pd-deps worktree/CWD bug) is the one live infra item
   directly hitting labeler-spa's dep workflow — fold into Phase 4.
