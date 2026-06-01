# OCR Labeler Behavior Completion Design

Date: 2026-06-01

## Purpose

Finish the OCR labeler product behavior surface by replacing stale compatibility
assumptions with explicit product workflows, shared pdomain-ui components, and
behavior-first E2E coverage. The current external Claude page-labeling driver is
deferred. For this phase, the app's own E2E suite is the behavior driver.

This design covers project selection/import, action discovery, canvas editing,
word editing, jobs, persistence visibility, and deferred behavior tracking.

## Non-Goals

- Build or maintain an external Claude labeling driver.
- Preserve the old hidden toolbar grid as a long-term driver contract.
- Implement PGDP API import.
- Implement edited-image OCR.
- Implement real rotation side effects beyond current job plumbing.
- Implement page-level persistent erase in this phase.
- Add first-run migration prompts or external migration scripts.

## Route Contract

The SPA supports canonical routes only:

- `/projects/{id}/pages/pageno/{n}`
- `/projects/{id}/pages/index/{idx}`

Legacy routes are unsupported and should not be documented as working:

- `/project/{id}/page/{n}`
- `/projects/{id}/pages/{n}`

Invalid page URLs clamp to the nearest valid page:

- Non-numeric, zero, or negative page numbers route to page 1.
- Page numbers above the project page count route to the last page.
- Missing projects redirect to `/` with `skipSessionRedirect` so session restore
  does not immediately reopen a stale project.

## Managed Project Library

The app uses a canonical managed project library as the primary project store.
The default location is OS-specific and under the user's home directory:

- Linux: `~/.local/share/pdomain-ocr-labeler/projects`
- macOS: `~/Library/Application Support/pdomain-ocr-labeler/projects`
- Windows: `%LOCALAPPDATA%\pdomain-ocr-labeler\projects`

An environment or settings override may point the managed library elsewhere.
The proposed override name is `PDOMAIN_OCR_PROJECTS_ROOT`.

The project picker lists this managed library. External source-root browsing is
not part of the product UI. Existing source-root backend support may remain only
for tests, development, or internal migration support.

## Project Picker

The project picker is implemented as shared pdomain-ui presentation first, then
consumed by OCR labeler through an app-specific adapter.

pdomain-ui owns reusable presentational components such as:

- `ProjectPicker`
- `ProjectRail`
- `ProjectPreview`
- `ProjectStatusBadge`
- `ProjectProgressMini`
- `ProjectPickerEmptyState`

OCR labeler owns:

- project enumeration from the managed library
- import folder action
- disabled reasons for future controls
- open project behavior
- project metadata mapping
- route navigation

The shared component accepts normalized items and callbacks. A representative
item shape:

```ts
type ProjectPickerItem = {
  id: string;
  title: string;
  subtitle?: string;
  author?: string;
  status?: "active" | "complete" | "archived" | "running" | "error" | "unknown";
  disabledReason?: string;
  pageCount?: number;
  progressPercent?: number;
  updatedLabel?: string;
  sizeLabel?: string;
};
```

The OCR labeler picker actions are:

- `Import folder`: enabled.
- `Import from PGDP`: visible, disabled, reason `PGDP import is planned`.

If the shared pdomain-ui Projects design includes a `New project` affordance,
OCR labeler maps the primary creation affordance to `Import folder`. OCR labeler
does not show a separate `New project` action in this phase.

Unsupported controls remain visible but disabled where they represent planned
workflow:

- Active/complete/archived filters are disabled until project status metadata
  exists.
- Archive/delete are disabled until project lifecycle APIs exist.
- Future import variants that do not work yet are disabled with explicit
  reasons.

## Import Folder

Import folder is the current user-facing ingestion path.

Flow:

1. User clicks `Import folder`.
2. User chooses a local folder.
3. The app copies the folder into the managed project library.
4. The app derives a project slug from project metadata or the folder name.
5. If the slug already exists, the app creates a unique suffix such as
   `slug-2`, `slug-3`, or a timestamp suffix.
6. The original source folder is untouched.
7. The project list refreshes.
8. The imported project is selected in the picker preview.
9. User explicitly clicks `Open project`.

Import never overwrites by default. PGDP API import will later use the same
managed-library destination and conflict behavior.

No first-run migration prompt, migration script, or silent auto-import is part
of this design. Existing local projects can be imported manually through the
same Import folder flow.

## Action Discovery And Left Action Rail

The hidden `ToolbarActionGrid` is not the future product surface. It exists only
as temporary compatibility scaffolding and should not drive new behavior.

The product needs a new visible left action rail for page-item operations,
including actions that existed in the prior NiceGUI UI. The action rail is
scope-aware and uses stable `data-testid`s for app E2E.

Before building the rail, create a NiceGUI action inventory:

- enumerate every old action button, menu item, and tool
- classify scope: project, page, paragraph, line, word, character/range,
  selection
- classify trigger: immediate, confirm, modal, batch job, background job
- classify backend support: existing endpoint, partial endpoint, missing
  endpoint, frontend-only
- classify current SPA state: exists, hidden, missing, superseded
- decide target surface: left action rail, right panel, compact page actions,
  jobs view, or retired

NiceGUI behavior is source material, not automatically authoritative. Each
action must be deliberately kept, changed, or dropped.

## Word Editing

`WordDetail` is the primary complete word editor. `WordEditDialog` is demoted to
legacy/compatibility fallback and should not receive new product behavior unless
a compatibility E2E explicitly requires it.

The primary editor lives in the right panel and includes:

- OCR/GT comparison and GT edit
- style palette
- component palette
- bbox section
- rebox section
- erase pixels section
- structure merge/split section
- char ranges
- char fixer
- validate/skip/delete footer
- character-level glyph review section

Glyph review is character-level within the selected word panel:

- the selected word renders as character cells
- users can mark individual characters or ranges
- supported marks include ligature spans, long-s, swash, prediction
  accept/reject, and reviewed-empty state
- glyph chips in word rows are summary indicators
- clicking a glyph chip selects the word and scrolls or focuses the glyph
  section in `WordDetail`
- persistence remains word-scoped, with character/range-indexed annotation data
  inside the word payload

## Canvas Editing

Phase 1 canvas work includes:

- drag selection
- add word by drag
- click-miss clears selection in normal select mode

Selection behavior:

- click word bbox selects the word
- click empty canvas in select mode clears selection
- drag selection selects matching boxes for the active selection level
- click empty canvas while add-word mode is active is a no-op unless a drag
  creates a word
- modal or input focus suppresses canvas shortcuts/click behavior

Deferred canvas work is tracked by strict xfail behavior tests:

- canvas rebox by drag
- page-level persistent erase by drag

Target rebox behavior:

- select word
- enter rebox mode
- drag new bbox
- POST word rebox mutation
- bbox updates
- mode returns to select after success

Target erase behavior:

- enter erase mode
- drag rectangle on the page image
- POST page-level erase endpoint
- image/page refreshes
- erase mode stays active
- Escape or Done exits erase
- tiny drag is a no-op
- backend failure keeps erase mode and shows a recoverable error

## Jobs

Long-running and background operations use a shared pdomain-ui jobs view.
Inline mutations do not enter Jobs.

pdomain-ui owns reusable Jobs UI:

- jobs pill
- jobs drawer/list
- job row
- progress/status/cancel affordance
- empty state

OCR labeler owns mapping backend job events into a shared frontend job view
model:

```ts
type JobViewModel = {
  id: string;
  title: string;
  operation: string;
  projectId?: string;
  projectLabel?: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress?: number;
  current?: number;
  total?: number;
  message?: string;
  error?: string;
  cancelable?: boolean;
  createdAt?: string;
  updatedAt?: string;
};
```

Retention:

- queued/running: visible until terminal
- succeeded: visible for 15 minutes unless dismissed
- canceled: visible for 15 minutes unless dismissed
- failed: visible for 24 hours unless dismissed
- dismissed: removed from visible Jobs immediately

Operations that enter Jobs:

- reload OCR for current page
- save project
- export
- rotate once real side effects exist
- refine if long-running
- manual OCR prefetch
- any batch or multi-page operation

Operations that stay inline/toast:

- save page
- rematch GT
- word edits
- line validate/mark reviewed
- quick page mutations

## OCR Prefetch

Manual OCR prefetch is the first implemented background OCR workflow.

Manual prefetch behavior:

- user starts Prefetch OCR
- app creates a Jobs entry
- backend processes the next N pages or a selected range
- operation is cancelable
- progress appears in the shared Jobs view
- current page editing remains usable

Automatic opportunistic prefetch is deferred and guarded by strict xfail tests.
Target behavior:

- opening page N schedules OCR for N+1/N+2
- scheduler respects concurrency and resource limits
- scheduler skips pages with existing usable OCR/cache
- changing project cancels or deprioritizes prior prefetch work
- Jobs view surfaces progress without stealing focus

## Persistence Visibility

Persistence state is explicit and user-visible.

Visible save states:

- clean
- dirty
- saving
- saved
- error
- conflict

Save Page remains inline and does not create a Jobs entry. Save Project creates
a Jobs entry.

Image drift and generation conflicts are recoverable:

- image drift shows a banner and reload path
- generation conflict keeps local dirty state visible
- failed save does not mark state clean

Cache/labeled/OCR precedence remains internal behavior but must have integration
coverage. OCR config sidecar save failures show a non-blocking warning while
live config can still apply.

## Deferred Features

These features are explicitly deferred and must be represented either in
`unclear-items.md` or strict xfail behavior tests once the intended behavior is
approved:

- PGDP API import
- edited-image OCR
- real image rotation and OCR/save side effects
- page-level persistent erase
- automatic opportunistic OCR prefetch
- external Claude page-labeling driver

## Behavior And E2E Policy

The app E2E suite is the active behavior driver.

Policy:

- Approved and implemented behavior gets passing E2E.
- Approved but missing behavior gets `xfail(strict=True)` E2E.
- Undecided behavior stays in `docs/specs/behavior/unclear-items.md`.
- Tests use visible app UI, not hidden compatibility scaffolding.
- When an xfail starts passing, CI should fail with XPASS so the xfail is
  removed and the behavior becomes locked.

Strict xfail coverage is required for:

- canvas rebox by drag
- page-level persistent erase by drag
- automatic OCR prefetch
- PGDP import
- edited-image OCR
- real rotation side effects
- any approved NiceGUI-derived action not implemented in the visible action rail

## Workstreams

1. Shared project picker
   - port/define pdomain-ui presentational picker components
   - build OCR labeler adapter
   - implement managed project library enumeration
   - implement Import folder
   - show disabled Import from PGDP and lifecycle controls

2. Behavior/E2E hardening
   - codify strict xfail convention
   - build behavior matrix from approved records
   - remove external Claude driver from current scope
   - make E2E interact with visible UI only

3. Action rail
   - inventory NiceGUI actions
   - decide keep/change/drop for each action
   - design visible left action rail
   - map approved missing actions to strict xfails

4. Canvas phase 1
   - wire drag selection
   - wire add word by drag
   - implement click-miss clear
   - add strict xfails for rebox and erase

5. WordDetail completion
   - add character-level glyph review section
   - wire chip-to-section focus
   - keep WordEditDialog legacy-only

6. Jobs view
   - define shared pdomain-ui Jobs components
   - map backend job events to `JobViewModel`
   - implement retention and dismiss behavior
   - implement manual OCR prefetch
   - add automatic prefetch xfails

7. Persistence visibility
   - add visible save state surface
   - add image drift/conflict banners
   - cover cache/labeled/OCR precedence
   - surface OCR config sidecar warning

8. Deferred behavior guards
   - add xfails for PGDP import, edited-image OCR, real rotation, automatic
     prefetch, page-level erase, and approved missing actions

## Acceptance Criteria

- Root project picker uses shared pdomain-ui project picker components.
- Project picker lists the managed library and supports Import folder.
- Imported projects are copied into the managed library without overwriting.
- Imported project is selected in preview after import.
- Legacy route support is removed from behavior docs and tests.
- Invalid page URLs clamp to nearest valid page.
- NiceGUI action inventory exists with keep/change/drop decisions.
- Visible left action rail has E2E-facing test IDs.
- E2E behavior matrix distinguishes passing, xfail, and unclear behavior.
- Canvas drag selection, add word, and click-miss clear behavior are covered.
- WordDetail includes character-level glyph review.
- Shared Jobs view handles long-running operations with retention.
- Manual OCR prefetch is represented as a background job.
- Persistence state is visible and recoverable for save errors/conflicts.
- Deferred approved behavior has strict xfail tests.
