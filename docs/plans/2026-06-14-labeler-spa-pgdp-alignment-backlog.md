# Labeler SPA PGDP Alignment Backlog

> **For agentic workers:** use `superpowers:subagent-driven-development` for
> implementation work. Run a spec review before code-quality review for each
> slice. Acceptance must be visible, enabled, effectful behavior, not just a
> `data-testid`.

**Goal:** Align `pdomain-ocr-labeler-spa` with the shared PGDP/pdomain-ui visual
language and common app patterns, without porting the PGDP 24-stage pipeline
into the labeler.

**Source gap analysis:**
`docs/research/2026-06-14-pgdp-design-handoff-labeler-spa-gap-analysis.md`

## Principles

- Treat current labeler work as baseline. The app already has a real AppShell,
  token bridge, canvas host, workspace toolbar, drawer, right panel, OCR/GT
  review, undo/redo, export, and trainer handoff.
- PGDP is a design-system and shared-pattern reference for this repo, not a
  product-scope mandate. Pipeline/stage tools stay in `pdomain-prep-for-pgdp`.
- Prefer `@pdomain/pdomain-ui` for common atoms, shell chrome, workbench layout,
  and operational panels when its contracts fit.
- Keep labeler domain behavior local: OCR/GT edits, bbox/rebox/erase/add-word,
  validation, event-store page history, export manifests, and trainer handoff.
- Do not remove local wrappers until their behavior, accessibility, test IDs,
  and visual contracts are matched by the replacement.
- Every shipped change needs focused unit tests plus browser verification for
  user-facing workflow changes.

## P0 - Scope And Documentation Guardrails

### 1. Adopt this gap analysis as the PGDP boundary record

**Why:** The PGDP handoff can easily be misread as a request to add the full
PGDP pipeline to the labeler.

**Work:**

- Link the research doc from `docs/README.md` active documents or a relevant
  planning index.
- Add a short note to the next labeler SPA roadmap: PGDP pipeline surfaces are
  out of scope; shared shell/workbench patterns are in scope.

**Acceptance:**

- Future implementation plans can reference a single boundary doc.
- No backlog item asks for PGDP stage folders, stage registry, submit-check, or
  cold-storage/archive stage behavior in this app.

### 2. Audit local UI wrappers against `pdomain-ui`

**Why:** Local `Button`, `Input`, `KeyCap`, `Chip`, and `StatusPip` overlap with
shared primitives, while Tabs and Accordion have documented incompatibilities.

**Work:**

- Create a short migration matrix for:
  `components/ui/button.tsx`, `Input.tsx`, `KeyCap.tsx`, `Chip.tsx`,
  `StatusPip.tsx`, `tabs.tsx`, and `accordion.tsx`.
- Classify each as `replace with pdomain-ui`, `wrap pdomain-ui`, `keep local`,
  or `needs pdomain-ui enhancement first`.
- Identify any `pdomain-ui` changes needed before migration.

**Acceptance:**

- Each local wrapper has an owner decision and migration risk.
- Tabs and Accordion are not replaced unless their Radix/context and visual
  requirements are explicitly satisfied.

### 3. Refresh stale architecture and driver-contract docs

**Why:** The parity matrix still notes driver-contract rot and hidden/stale
surfaces. PGDP's handoff is explicit about prototype scaffolding versus real UI.

**Work:**

- Update `docs/architecture/24-shell-layout.md`,
  `docs/architecture/25-drawer-worklist.md`, and
  `docs/architecture/13-driver-contract.md` against the live route.
- Mark hidden driver-contract stubs as temporary compatibility debt and list the
  visible replacement surface.

**Acceptance:**

- Docs describe `pdomain-ui AppShell` plus `ProjectPage` body grid as the live
  shell.
- Driver-contract docs no longer imply hidden stubs are acceptable product UI.

## P1 - App Chrome And Operations

### 4. Wire shared jobs pill/drawer

**Why:** PGDP and `pdomain-ui` expect long-running jobs to be inspectable in app
chrome. Labeler currently has toasts, `useJobProgress`, busy overlays, and
dialog-local export progress, but no app-shell jobs drawer.

**Work:**

- Inventory backend jobs APIs already available to the SPA.
- Add a labeler adapter that feeds `pdomain-ui` `JobsPill` / `JobsDrawer` if the
  API shape fits; otherwise document the minimal `pdomain-ui` adapter gap.
- Keep `BusyOverlay` for page-local blocking states, but make global jobs visible
  in chrome.

**Acceptance:**

- A running export/OCR/save/rotate job appears in a persistent jobs surface.
- Users can inspect recent job state after leaving the originating dialog.
- Existing busy overlays and toasts still work.

### 5. Replace suite launcher shims with real endpoints

**Why:** `SuiteSiblingsProvider` is mounted, but `fetchInstalled` returns `[]`
and `postLaunch` returns `requires-host-config`.

**Work:**

- Wire `fetchInstalled` to `/api/suite/installed`.
- Wire `postLaunch` to `/api/suite/launch`.
- Reconcile the launch call shape: `ExportDialogUtils.launchTrainer` currently
  uses `POST /api/suite/launch?app_id=<id>`, while the `App.tsx` shim and
  `pdomain-ui` launcher helper expect a JSON `{ id }` body.
- Preserve graceful error behavior for missing host config or unavailable
  siblings.

**Acceptance:**

- The launcher shows installed sibling apps when the backend reports them.
- Launch attempts return the backend result rather than a hard-coded shim.
- Tests cover success, empty, and failure states.

### 6. Finish settings reachability and persistence

**Why:** Compute panel content is registered, but prefs are partly local and app
prefs are a no-op.

**Work:**

- Verify that AppShell settings are visible on root and project routes.
- Persist shared prefs through backend endpoints if available; otherwise add a
  tracked backend route plan.
- Keep OCR configuration separate from compute-device selection.

**Acceptance:**

- Users can open settings and view Compute on every route.
- Theme/font-scale changes survive reload through the intended persistence lane.
- Compute panel shows CPU/CUDA state and reset behavior.

## P1 - Project Landing

### 7. Add real project-card metadata

**Why:** Root cards currently show placeholder page count and validation
progress because `ProjectKey` lacks metadata.

**Work:**

- Extend or supplement the project list API with page count, validation progress,
  thumbnail URL, status, and last activity if those are cheap to derive.
- Render those fields in `ProjectCard`.

**Acceptance:**

- Cards no longer show placeholder `-- pages` / `--%` values when data exists.
- Card progress matches a backend-refetched project summary.

### 8. Make root filters effectful

**Why:** Non-`all` filters currently show all projects because status metadata is
not exposed.

**Work:**

- Define labeler project statuses that are meaningful for this app.
- Filter by real status fields or remove filters that cannot be made real.

**Acceptance:**

- Each visible filter changes the result set when matching data exists.
- Empty states explain the active filter/search state accurately.

### 9. Decide archive/restore semantics

**Why:** PGDP's project machine distinguishes archive, restore, and permanent
delete. Labeler currently has delete, while archive was removed because no API
semantics existed.

**Work:**

- Decide whether labeler needs reversible archive.
- If yes, design archive/restore in backend and UI with two-step permanent
  delete.
- If no, document that delete remains permanent and archive is intentionally
  omitted.

**Acceptance:**

- Project manage actions are not placeholders.
- Destructive actions have consistent confirmation behavior.

## P1 - Workspace, Review, And Detail Surfaces

### 10. Extract or consume a shared workbench layout

**Why:** Labeler and PGDP both have dense page workbenches, but their route grids
are independently shaped.

**Work:**

- Define the labeler layout slots: toolbar, canvas/viewer, drawer/worklist,
  detail panel, page-local banners, bulk/action strip.
- Compare against any `pdomain-ui` `WorkbenchLayout` or planned equivalent.
- Either consume the shared layout or write an adapter proposal for `pdomain-ui`.

**Acceptance:**

- `ProjectPage` layout responsibilities are clearer and easier to test.
- No labeler-specific selection, OCR, or mutation behavior moves into the shared
  layout.

### 11. Tighten the existing shared worklist adapter

**Why:** Labeler has `WordMatchView` and drawer `Worklist`; PGDP has generic
review queue/filter/density patterns. The drawer `Worklist` already uses
`@pdomain/pdomain-ui/worklist` `WordList`, so the next step is adapter cleanup,
not replacing the list shell.

**Work:**

- Review the `LineMatchWordItem` shim fields that satisfy `WordListItem`
  (`text`, `bounding_box`) and decide whether `pdomain-ui/worklist` needs a more
  generic row constraint.
- Track the current `data-testid` workaround: `WordList` does not accept a
  direct test id, so the labeler wraps it in `worklist-queue`.
- Decide which layer owns filter/count chips, density, sort, and bulk action
  chrome: labeler-local, shared `pdomain-ui`, or a thin adapter.
- Evaluate `WordMatchView` separately; it is a virtualized text-review view and
  should only align with shared worklist pieces if behavior and test contracts
  stay intact.

**Acceptance:**

- Worklist filtering, row selection, keyboard navigation, and validation actions
  still work.
- The existing `WordList` integration is either documented as the intended
  adapter or backed by a concrete `pdomain-ui` enhancement request.
- No change undoes the shipped shared worklist integration without an explicit
  replacement rationale.

### 12. Standardize detail panel shell, not detail behavior

**Why:** Right panel routing and detail views are labeler-specific, but the
panel frame is a common app pattern.

**Work:**

- Extract common frame concerns: breadcrumb/header, collapse control, scroll
  body, sticky footer, placeholder state.
- Keep `WordDetail`, `LineDetail`, `BlockDetail`, `MultiWordDetail`, and
  `MultiLineDetail` local.

**Acceptance:**

- The right-panel shell can be reused or compared with `pdomain-ui` without
  weakening labeler detail behavior.
- Collapse and re-open flows are browser-verified.

### 13. Normalize status and confidence chips

**Why:** PGDP and labeler both use exact/fuzzy/mismatch/OCR/GT status tones.
Labeler has local `StatusPip`; `pdomain-ui` has shared badge/status primitives.

**Work:**

- Map every labeler status/confidence chip to shared tone names.
- Decide whether local `StatusPip` wraps a shared primitive or remains local for
  testid/shape reasons.

**Acceptance:**

- Exact/fuzzy/mismatch/OCR/GT tones are visually consistent across worklist,
  right panel, canvas overlays, and export/status rows.

## P2 - Labeler Domain Follow-Ups

### 14. Improve export job history

**Why:** The parity matrix calls out export history and display defects. PGDP's
pack tail is out of scope, but its persistent status/history pattern is useful.

**Work:**

- Back export history with persisted manifest/job data rather than dialog-local
  state only.
- Fix run-history counts to report actual pages/items exported.
- Keep "send to trainer" as labeler/trainer suite behavior, not PGDP submit.

**Acceptance:**

- Reopening the export dialog shows prior export runs from persisted data.
- The displayed counts match the manifest on disk.

### 15. Add a visible history panel for event-store undo

**Why:** The event-store undo spec already designs a future U-M7 history panel.
This maps to PGDP's "derived projection" principle without adopting PGDP
pipeline machines.

**Work:**

- Surface page history as a read-only list with current cursor, operation type,
  timestamp, and restore/jump affordances only if supported by the spec.
- Keep append-only provenance as the source of truth.

**Acceptance:**

- Users can inspect what undo/redo will traverse.
- The panel never mutates history outside the approved event-store routes.

### 16. Revisit glyph annotation panel after the blocker clears

**Why:** Glyph annotation remains blocked in the parity docs, but it is a
labeler-native surface that could share chip/palette/status primitives.

**Work:**

- Re-check the current Q-A7/M11 blocker.
- When unblocked, implement with the same primitive/workbench alignment rules as
  the rest of this backlog.

**Acceptance:**

- Glyph review is visible, effectful, persisted, and covered by browser
  verification.

## Out Of Scope For This Backlog

- PGDP 24-stage registry, pipeline shell, stage strip, stage runner, and
  run-all-stale.
- PGDP source/image-prep/page-order/text-review/validation/proof-pack/build/zip/
  submit/archive stage tools.
- PGDP stage settings inheritance, downstream stale propagation, and
  confirm-and-advance gates.
- XState v5 rewrite solely for PGDP parity.
- Copying `final/` prototype code or `DesignCanvas`/`DCArtboard` scaffolding.
