---
kind: plan
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
source: docs/plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md
---

# PGDP Alignment — Remaining Work (2026-07-21)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Run a spec review before code-quality
> review for each slice. Acceptance must be visible, enabled, effectful
> behavior, not just a `data-testid`.

**Goal:** Ship only the still-open items from the
[2026-06-14 PGDP alignment backlog](2026-06-14-labeler-spa-pgdp-alignment-backlog.md),
verified against current code on 2026-07-21.

**Architecture:** Keep OCR/GT editing, event-store undo, export/trainer handoff,
and labeler domain panels local. Consume `@pdomain/pdomain-ui` for chrome,
jobs, suite launch, worklist shells, and status primitives via adapters.

**Tech Stack:** FastAPI, React 19 + Vite + TS, TanStack Query, Zustand,
`@pdomain/pdomain-ui`, pytest + Vitest + Playwright.

## Out Of Scope (do not implement)

- PGDP 24-stage registry, pipeline shell, stage strip, stage runner, run-all-stale
- PGDP source/image-prep/page-order/text-review/validation/proof-pack/build/zip/
  submit/archive **stage tools**
- Stage settings inheritance, downstream stale propagation, confirm-and-advance
- XState v5 rewrite solely for PGDP parity
- Copying `final/` prototype code or `DesignCanvas`/`DCArtboard` scaffolding

If a task starts to look like a pipeline port, stop and re-read the boundary in
[`docs/context/intent-map.md`](../context/intent-map.md) (Rejected) and the
parent backlog Out-Of-Scope section.

---

## Status table (verified 2026-07-21)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Boundary docs | **shipped** | [`docs/context/intent-map.md`](../context/intent-map.md) Rejected section; plan linked from [`docs/README.md`](../README.md); research retired into intent-map + backlog |
| 2 | UI wrapper audit | **partial** | Button/Input/Chip/KeyCap/StatusPip live on pdomain-ui ([`docs/architecture/03-frontend.md`](../architecture/03-frontend.md) §Shared primitive ownership). No formal migration matrix. Tabs/Accordion owner decision still open in intent-map |
| 3 | Arch/driver docs refresh | **partial** | [`24-shell-layout.md`](../architecture/24-shell-layout.md) D-047 documents AppShell + ProjectPage; [`13-driver-contract.md`](../architecture/13-driver-contract.md) D-046–D-052 remove most stubs. Residual: §2.11 word-edit dialog rot; [`25-drawer-worklist.md`](../architecture/25-drawer-worklist.md) omits WordList adapter |
| 4 | Jobs pill/drawer | **open** | No `JobsPill`/`JobsDrawer` usage. Backend `GET /api/jobs` exists ([`api/jobs.py`](../../src/pdomain_ocr_labeler_spa/api/jobs.py)); SPA uses only per-job `useJobProgress` + `BusyOverlay` |
| 5 | Suite launcher endpoints | **open** | [`App.tsx`](../../frontend/src/App.tsx) `fetchInstalled`/`postLaunch` still hard-coded shims (GAP-3). [`ExportDialogUtils.ts`](../../frontend/src/components/ExportDialogUtils.ts) already hits real `/api/suite/*` |
| 6 | Settings persistence | **partial** | Compute panel registered + warmed ([`App.tsx`](../../frontend/src/App.tsx)); theme/fontScale via localStorage. `persistApp` is a no-op; no `GET/POST /api/ui-prefs` |
| 7 | Project-card metadata | **open** | `ProjectKey` is only `project_id`/`project_root`/`label` ([`api/projects.py`](../../src/pdomain_ocr_labeler_spa/api/projects.py)); cards hard-code null page/progress placeholders ([`RootPage.tsx`](../../frontend/src/pages/RootPage.tsx)) |
| 8 | Root filters | **open** | Non-`all` filters intentionally no-op ([`RootPage.tsx`](../../frontend/src/pages/RootPage.tsx) L350–353); unclear-items still notes this |
| 9 | Archive/restore decision | **partial** | Archive menu removed; delete is permanent with confirm ([`RootPage.tsx`](../../frontend/src/pages/RootPage.tsx)). Decision not yet recorded as a durable ADR/intent entry |
| 10 | Shared workbench layout | **open** | No `WorkbenchLayout` consumption; layout owned by [`ProjectPage.tsx`](../../frontend/src/pages/ProjectPage.tsx) + local shell components |
| 11 | Worklist adapter | **partial** | Drawer uses `@pdomain/pdomain-ui/worklist` `WordList` with GAP-1/GAP-2 shims ([`Worklist.tsx`](../../frontend/src/components/drawer/Worklist.tsx)); filter/count chrome still local; not formally decided/documented as final adapter |
| 12 | Detail panel shell | **partial** | [`RightPanel.tsx`](../../frontend/src/components/shell/RightPanel.tsx) has header/collapse/body routing; frame not extracted or compared to pdomain-ui |
| 13 | Status/confidence chips | **shipped** | `StatusPip` imported from `@pdomain/pdomain-ui/primitives` in worklist, WordHeader, LineDetail, BlockDetail, MultiLineDetail; local StatusPip.tsx deleted |
| 14 | Export job history | **open** | Dialog history is client-only and resets on close ([`ExportDialog.tsx`](../../frontend/src/components/ExportDialog.tsx)). Manifest write exists ([`handlers/export.py`](../../src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py)); `GET .../exports` still returns `[]` ([`api/export.py`](../../src/pdomain_ocr_labeler_spa/api/export.py)) |
| 15 | Event-store history panel | **open** | Undo/redo v1 shipped; U-M7 designed in [`docs/specs/2026-06-12-event-store-undo.md`](../specs/2026-06-12-event-store-undo.md) but not implemented |
| 16 | Glyph panel | **partial** | `GlyphAnnotationPanel`, chips, bulk dialog + backend routes exist under `frontend/src/components/glyph/` and OpenAPI. **Not mounted** in `WordDetail` / RightPanel. Do not re-implement; coordinate with `specs/20-glyph-annotations.md` |

**Shipped (skip):** 1, 13
**Remaining count:** **14** (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16)

---

## Recommended overnight order (smallest valuable first)

| Night | Sequence | Items | Why this order |
|---|---|---|---|
| **Night 1** | A → B → C → D | **9, 2, 3 residual, 5** | Pure docs close debt first, then one high-value wiring change (suite launcher) against endpoints that already exist |
| **Night 2** | E → F → G | **6 residual, 4, 11** | Finish settings honesty, add jobs chrome (backend list already exists), document/tighten worklist adapter |
| **Night 3** | H → I | **14, 8+7** | Persist export history (manifest already written); then project list metadata so filters become real |
| **Later / multi-session** | J → K → L | **12, 10, 15, 16** | Shell extraction, shared workbench, U-M7 history panel, glyph wire-up. Each is multi-session if done properly |

### Night-1 sequence (recommended start)

1. **Item 9** — formalize “no archive; delete is permanent” (docs only, ~30 min)
2. **Item 2** — write migration matrix + resolve Tabs/Accordion ownership (docs only, ~45 min)
3. **Item 3 residual** — refresh drawer + driver-contract rot notes (~45–60 min)
4. **Item 5** — replace suite launcher shims with real `/api/suite/*` (~1–2 h + tests)

If Night 1 has leftover time, start **Item 4** jobs inventory only (do not half-ship the drawer).

---

## Remaining items — tasks

### Item 9 — Archive/restore semantics (docs decision) — Night 1

**Effort:** small (docs). **Do not build archive API.**

#### Tasks

- [ ] **9.1** Record durable decision: labeler does **not** need reversible archive; delete remains permanent with confirm; archive filter chip is either removed or clearly disabled until a future status field exists.
  - Files: `docs/context/intent-map.md` (Deferred/Rejected), optionally `docs/context/decisions.md` or a short ADR under `docs/decisions/`, fix stale note in `docs/specs/behavior/unclear-items.md` (Delete is no longer inert).
- [ ] **9.2** Align root UI copy with the decision.
  - Files: `frontend/src/pages/RootPage.tsx` (archived filter chip: remove or `disabled` + empty-state copy), `frontend/src/pages/RootPage.test.tsx`.

#### Acceptance

- Project manage menu has only real actions (Open, Delete).
- Delete keeps two-step confirm and permanent wording.
- Durable docs state archive is intentionally omitted (not “needs-spec” forever).

---

### Item 2 — Finish UI wrapper audit (migration matrix) — Night 1

**Effort:** small (docs). Code migration for Button/Input/Chip/StatusPip/KeyCap is already done.

#### Tasks

- [ ] **2.1** Add a short migration matrix under architecture (or a subsection of `03-frontend.md`).
  - Files: `docs/architecture/03-frontend.md` (extend §Shared primitive ownership) **or** new `docs/architecture/29-pdomain-ui-primitives.md` + link from `docs/README.md`.
  - Classify each:

    | Local surface | Decision | Notes |
    |---|---|---|
    | Button | replace with pdomain-ui | done; tests import pdui |
    | Input | replace with pdomain-ui | done |
    | Chip / TriStateChip | replace with pdomain-ui | done |
    | KeyCap | replace with pdomain-ui | done (HotkeyHelpModal) |
    | StatusPip | replace with pdomain-ui | done (item 13) |
    | `ui/tabs.tsx` | wrap pdomain-ui | re-export for import stability |
    | `ui/accordion.tsx` | wrap pdomain-ui | composition + tag→tone map |

- [ ] **2.2** Close or restate the intent-map owner decision for Tabs/Accordion.
  - Files: `docs/context/intent-map.md` — recommend **keep local wrappers** unless pdomain-ui gains labeler tag/tone + testid needs; no replacement of Tabs/Accordion without explicit Radix/context satisfaction.

#### Acceptance

- Every former local wrapper has an owner decision + risk note.
- Matrix explicitly says Tabs/Accordion stay wrapped.

---

### Item 3 — Residual architecture / driver-contract refresh — Night 1

**Effort:** small–medium (docs). Core AppShell story already present.

#### Tasks

- [ ] **3.1** Update `docs/architecture/25-drawer-worklist.md` to describe pdomain-ui `WordList`, GAP-1/GAP-2 adapters, and local ownership of filter/count/bulk chrome.
  - Files: `docs/architecture/25-drawer-worklist.md`, cross-link item 11.
- [ ] **3.2** Fix driver-contract residual rot: §2.11 word-edit dialog vs right-panel editing (D-051 / intent-map active item).
  - Files: `docs/architecture/13-driver-contract.md` — mark dialog testids as retired or relocated; point to right-panel testids.
- [ ] **3.3** Bump `last_updated` / `last_verified` on touched architecture docs; ensure 24/13 still say AppShell + ProjectPage is live shell and hidden stubs are not product UI.

#### Acceptance

- Docs describe live shell (already mostly true for 24).
- Driver-contract no longer presents retired dialog stubs as required product UI.
- Drawer docs match `Worklist.tsx`.

---

### Item 5 — Suite launcher real endpoints — Night 1

**Effort:** small–medium (code). Backend routes already mounted.

#### Tasks

- [ ] **5.1** Replace `fetchInstalled` / `postLaunch` shims in `App.tsx` with real fetches.
  - Files: `frontend/src/App.tsx`.
  - Prefer sharing helpers with `ExportDialogUtils.ts` (or move both to `frontend/src/api/suite.ts`) to avoid dual call shapes.
  - Reconcile launch body: ExportDialog uses `POST /api/suite/launch?app_id=`; pdomain-ui expects JSON `{ id }`. Match whatever the mounted backend accepts (check bootstrap/ops suite router); support both if backend accepts query only.
- [ ] **5.2** Tests for success / empty / failure.
  - Files: `frontend/src/App.test.tsx`, `frontend/src/test/handlers.ts`, optional shared suite client unit test.
- [ ] **5.3** Preserve graceful degradation when host config missing or siblings unavailable (launcher error state, not crash).

#### Acceptance

- Launcher shows installed siblings when backend reports them.
- Launch returns backend result (not hard-coded `requires-host-config`).
- Export “Send to trainer” and AppShell launcher use consistent suite client behavior.
- Unit tests cover empty, success, failure.

---

### Item 6 — Settings residual — Night 2 (small residual)

**Effort:** small. Most acceptance already met.

#### Tasks

- [ ] **6.1** Verify settings ⚙ + Compute panel on root and project routes (browser or App test); document intended persistence lane: localStorage for theme/fontScale is accepted until `/api/ui-prefs` exists.
  - Files: `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, note in `docs/architecture/03-frontend.md` or compute plan.
- [ ] **6.2** Either implement minimal `persistApp` semantics for any app-scoped keys already used, or document app prefs as intentionally no-op with a tracked follow-up in intent-map Deferred (already partially there).
  - Do **not** invent a full prefs backend in this slice unless `/api/ui-prefs` already exists upstream.

#### Acceptance

- Settings → Compute visible on every route (confirm).
- Theme/font-scale survive reload via documented lane.
- Compute shows CPU/CUDA + reset (already via `ComputeTargetPanel`).

---

### Item 4 — Jobs pill / drawer — Night 2

**Effort:** medium. Backend list endpoint exists; pdomain-ui adapter may need shaping.

#### Tasks

- [ ] **4.1** Inventory API shape: `GET /api/jobs`, `GET /api/jobs/{id}`, SSE events, cancel.
  - Files: `src/pdomain_ocr_labeler_spa/api/jobs.py`, compare to pdomain-ui `JobsPill`/`JobsDrawer` props (from linked package).
- [ ] **4.2** Add thin adapter hook (e.g. `useJobsList`) polling or refreshing job list; feed AppShell chrome slot if pdomain-ui exposes one, else mount pill in header zone beside launcher.
  - Files: new `frontend/src/hooks/useJobsList.ts`, `frontend/src/App.tsx` / header slot, tests.
- [ ] **4.3** Keep `BusyOverlay` for page-local blocking; do not remove toasts.
  - Files: `ProjectPage.tsx`, `BusyOverlay.tsx` — no behavior regression.

#### Acceptance

- Running export/OCR/save/rotate appears in a persistent jobs surface.
- User can inspect recent job state after leaving the originating dialog.
- Busy overlays + toasts still work.
- Focused unit tests + at least one browser check for a long job.

**Honesty:** If pdomain-ui JobsPill contract mismatches job JSON, ship adapter gap doc first (half-session) rather than forking UI.

---

### Item 11 — Worklist adapter cleanup — Night 2

**Effort:** small–medium (mostly decisions + light code). Integration already shipped.

#### Tasks

- [ ] **11.1** Document intended adapter: `LineMatchWordItem` shim + `worklist-queue` wrapper are permanent unless pdomain-ui accepts generic row constraints / testid prop.
  - Files: `docs/architecture/25-drawer-worklist.md` (with item 3), comment cleanup in `Worklist.tsx`.
- [ ] **11.2** Decide ownership of filter/count chips, density, sort, bulk chrome → **labeler-local** (recommended; already true).
- [ ] **11.3** Explicitly leave `WordMatchView` out of shared worklist alignment unless behavior/test contracts stay intact.

#### Acceptance

- Filtering, selection, keyboard nav, validation actions still work (existing tests green).
- Adapter documented as intended **or** concrete pdomain-ui enhancement request filed.
- No silent undo of WordList integration.

---

### Item 14 — Export job history — Night 3

**Effort:** medium. Manifest write exists; list endpoint stubs empty.

#### Tasks

- [ ] **14.1** Implement `list_exports` from on-disk doctr-export manifest(s).
  - Files: `src/pdomain_ocr_labeler_spa/api/export.py`, unit/integration tests (`tests/integration/test_export_router.py`, export manifest tests).
- [ ] **14.2** On dialog open, hydrate run history from `GET /api/projects/{id}/exports`; show real page/item counts from manifest.
  - Files: `frontend/src/components/ExportDialog.tsx`, `ExportDialog.test.tsx`.
- [ ] **14.3** Keep “Send to trainer” as suite behavior (already present); do not add PGDP submit.

#### Acceptance

- Reopening export dialog shows prior runs from persisted data.
- Displayed counts match manifest on disk.
- Empty history is honest when no exports exist.

---

### Items 7 + 8 — Project-card metadata + effectful filters — Night 3

**Effort:** medium–large (backend summary + UI). **Couple these:** filters need status fields from item 7.

#### Tasks

- [ ] **7.1** Extend project list response (or add summary endpoint) with cheap fields: `page_count`, validation progress (e.g. validated_pages/total), optional `status`, `last_activity`, optional thumbnail URL if cheap.
  - Files: `src/pdomain_ocr_labeler_spa/api/projects.py`, `core/project_enumeration.py`, OpenAPI export → `frontend/src/api/types.ts` via `make openapi-export`.
- [ ] **7.2** Render real values in `ProjectCard` (no `-- pages` / `--%` when data exists).
  - Files: `frontend/src/pages/RootPage.tsx`, `RootPage.test.tsx`.
- [ ] **8.1** Define labeler-meaningful statuses (e.g. `active` = has incomplete pages, `complete` = all pages validated, drop `archived` if item 9 rejected archive).
  - Files: same backend summary + `RootPage.tsx` filter logic.
- [ ] **8.2** Empty states explain active filter/search accurately.

#### Acceptance

- Cards show real page count/progress when derivable.
- Each visible filter changes the result set when matching data exists.
- Progress matches backend-refetched summary.

**Honesty:** Thumbnail generation may be deferred if expensive; progress/status are the valuable core.

---

### Item 12 — Detail panel shell — multi-session (after Night 2–3)

**Effort:** medium. Do not move domain detail behavior.

#### Tasks

- [ ] **12.1** Extract frame props: header/breadcrumb slot, collapse control, scroll body, sticky footer, placeholder — without moving Word/Line/Block detail logic.
  - Files: `frontend/src/components/shell/RightPanel.tsx` → optional `DetailPanelShell.tsx`.
- [ ] **12.2** Compare with any pdomain-ui panel primitive; document adapter or local-keep decision.
- [ ] **12.3** Browser-verify collapse/re-open.

#### Acceptance

- Shell reusable/comparable without weakening detail behavior.
- Collapse/re-open verified.

---

### Item 10 — Shared workbench layout — multi-session

**Effort:** large (design + careful extract). **Not overnight-complete** if shared package changes are required.

#### Tasks

- [ ] **10.1** Write slot map for labeler: toolbar, canvas, drawer/worklist, detail, banners, bulk strip.
  - Files: short design note in plan appendix or `docs/architecture/24-shell-layout.md` subsection; based on live `ProjectPage.tsx`.
- [ ] **10.2** Compare to pdomain-ui `WorkbenchLayout` (if present in linked package). Consume **or** write adapter proposal for pdomain-ui — do not move OCR/selection mutations into shared layout.
- [ ] **10.3** Only then extract layout primitive with existing testids preserved.

#### Acceptance

- ProjectPage layout responsibilities clearer and easier to test.
- No domain mutation behavior in shared layout.

---

### Item 15 — Event-store history panel (U-M7) — multi-session

**Effort:** large. Spec already designed; needs new API + drawer tab + e2e.

#### Tasks

- [ ] **15.1** Implement `GET .../history/versions` and optional `POST .../jump` per U-M7.
  - Files: backend page history routes, derivation in page_state/event-store layer, tests.
- [ ] **15.2** Add Drawer tab `"history"` with read-only version list (cursor, op type, relative time); jump only if API supports it.
  - Files: `Drawer.tsx`, `ui-prefs.ts` `DrawerTab`, new history list component, driver-contract testids.
- [ ] **15.3** E2E: U-14/U-15/U-16 from event-store undo spec.

#### Acceptance

- Users can inspect undo/redo traversal.
- Panel never mutates history outside approved event-store routes.

**Honesty:** This is a full milestone slice (U-M7), not a night-1 task.

---

### Item 16 — Glyph panel (coordinate; do not duplicate) — multi-session

**Effort:** large. Components and backend mostly exist; **wire-up + persistence UX** remain.

#### Tasks

- [ ] **16.1** Mount `GlyphAnnotationPanel` into word detail path with real mutation hooks (glyph-annotations + accept-prediction + bulk mark already in OpenAPI).
  - Files: `WordDetail.tsx` / RightPanel word slot, glyph hooks if missing, `specs/20-glyph-annotations.md` as SoT.
- [ ] **16.2** Reuse StatusPip/Chip primitives (item 13); no parallel glyph design system.
- [ ] **16.3** Browser verification of mark/reset/accept-prediction persistence.

#### Acceptance

- Glyph review visible, effectful, persisted, browser-verified.
- Does **not** reimplement panel chrome already in `components/glyph/`.

**Honesty:** Treat as M11 slice (#267–#270 backlog), not PGDP chrome work. Coordinate; do not dual-track a second glyph plan.

---

## Global constraints

- Preserve driver `data-testid`s and accessibility.
- Prefer `make test AI=1` / `make frontend-test AI=1` / focused pytest; full `make ci AI=1` before commit.
- After FastAPI model changes: `make openapi-export`.
- Specs beat code when they conflict — update the spec first if intentional.
- Auth/S3/Postgres/managed adapters remain deferred (D-042).

## Goal (session outcome)

Close documentation debt (9, 2, 3), wire suite launcher (5), then progress jobs chrome (4) and export history (14) without importing any PGDP pipeline product model.

## Architecture

Adapters over existing labeler domain stores and FastAPI jobs/export/suite routes; pdomain-ui for chrome primitives only.

## Tech Stack

React, TypeScript, Zustand, TanStack Query, FastAPI, `@pdomain/pdomain-ui`.
