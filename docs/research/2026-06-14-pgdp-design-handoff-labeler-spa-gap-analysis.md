# PGDP Design Handoff Gap Analysis For OCR Labeler SPA

**Date:** 2026-06-14
**Scope:** Compare `pdomain-ocr-labeler-spa` against the PGDP app design package
at
`/workspaces/ocr-container/pdomain-prep-for-pgdp/docs/plans/design_handoff_pgdp_app`.
**Output:** Gaps that matter to the OCR labeler SPA, with existing work treated
as baseline.

## Summary

`pdomain-ocr-labeler-spa` is not the PGDP prep pipeline. It is an OCR labeling
workspace for page image review, OCR/GT correction, word and line mutation,
validation, export, and trainer handoff. The PGDP handoff is still useful as a
design-system and shared-shell reference, but the 24-stage PGDP pipeline should
not be copied into this app.

Current labeler coverage is substantial:

- The outer app already uses `@pdomain/pdomain-ui` `AppShell`, suite provider,
  settings panel plumbing, and shared tokens.
- The project route already has a dense workbench: workspace toolbar, page
  canvas, worklist drawer, hierarchy/text tabs, and context-sensitive right
  panel.
- The canvas already consumes `@pdomain/pdomain-ui/canvas` and fills
  labeler-specific selection/tool slots.
- The app already has OCR/text review, word/line/block detail panels, undo/redo,
  notifications, job progress hooks, compute panel content, and DocTR export /
  trainer integration.

The remaining gaps are concentrated in labeler-aligned shared surfaces:

1. App chrome wiring: jobs drawer/pill, suite launcher endpoints, visible
   settings/compute reachability, and server-backed UI prefs.
2. Project landing metadata: status, real filters, counts/progress, thumbnails,
   activity, archive/delete lifecycle, and post-load/post-import job placement.
3. Local component overlap with `pdomain-ui`: Button, Input, KeyCap, Chip,
   StatusPip, worklist/review rows, and panel shells should be audited before
   more local primitives are added.
4. Workbench normalization: the current labeler workspace is real and useful,
   but should be reconciled with shared `pdomain-ui` workbench/layout components
   rather than letting each app grow its own grid, drawer, and detail shell.

PGDP pipeline stages, pipeline XState machines, stage settings inheritance,
packaging gates, submit-check, and archive remain out of scope for this SPA.

## Source Evidence

PGDP source paths below are relative to
`/workspaces/ocr-container/pdomain-prep-for-pgdp/docs/plans/design_handoff_pgdp_app/`.

- `README.md:9-28` says `final/`, `statecharts/`, and `design-system/` are the
  handoff layers, with final canvases as design references.
- `PROMPT.md:79-82` says generic atoms/chrome promote to `pdomain-ui`; stage
  tools stay app-local.
- `COMPONENT_INDEX.md:21-31` lists repeated helpers: `Body`, `Card`, `Gate`,
  `Seg`, `SetRow`, `Stat`, `Toggle2`, `Tree`, `SettingRow`, and
  `SettingSlider`.
- `COMPONENT_INDEX.md:36-40` lists shared shell and atom kit components:
  `AppHeader`, `AppTemplate`, `Breadcrumb`, `JobsDrawer`, `JobsPill`,
  `Button`, `Input`, `Badge`, `KeyCap`, `StepDots`, and related primitives.
- `statecharts/README.md:21-29` describes the PGDP Projects page machines.
- `statecharts/README.md:80-107` describes the PGDP pipeline shell and shared
  stage runner lifecycle.
- `statecharts/README.md:117-124` describes shared stage review and workbench
  machines.
- `statecharts/README.md:151-184` describes cross-stage patterns, settings
  inheritance, confirm gates, staleness, and the package/submit/archive chain.

Current labeler SPA evidence:

- `frontend/package.json:20-24` depends on `@pdomain/pdomain-ui`.
- `frontend/src/App.tsx:25-36` imports `AppShell`, compute/settings helpers, and
  suite sibling types from `@pdomain/pdomain-ui`.
- `frontend/src/App.tsx:238-365` mounts `AppShell`, header, rail, main routes,
  dialogs, and settings panels.
- `frontend/src/styles/tokens.css:1-44` imports `pdomain-ui` tokens and defines
  labeler-specific status/layer aliases.
- `frontend/tailwind.config.js:20-67` maps Tailwind colors and type sizes to
  design tokens.
- `frontend/src/pages/ProjectPage.tsx:860-1054` composes the live labeler
  workspace: drawer, toolbar, canvas, banners, action grid, right panel, and
  confirm dialog.
- `frontend/src/components/PageImageCanvas.tsx:1-73` documents the migration to
  `@pdomain/pdomain-ui/canvas`.
- `frontend/src/components/shell/WorkspaceToolbar.tsx:12-43` wraps the
  `pdomain-ui` `StageToolbar` primitive.
- `frontend/src/components/drawer/Worklist.tsx:1-22`, `:36-63`, and `:410-439`
  adapt labeler `LineMatch` rows into `@pdomain/pdomain-ui/worklist`
  `WordList`.
- `docs/architecture/24-shell-layout.md:35-67` documents the current
  `pdomain-ui AppShell` plus project body grid split.
- `docs/research/parity-audit/PARITY-GAP.md:85-105` lists still-open parity
  gaps after the June 13 re-verification.

## Already Covered

| Area                     | Current coverage                                                                                                                                                                                                          | Notes                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Shared app shell         | `AppShell`, `SuiteSiblingsProvider`, settings panels, compute warmup, header/rail/main slots (`frontend/src/App.tsx:25-36`, `:238-365`)                                                                                   | The shell is already on the shared library path. Remaining work is wiring hidden/shimmed capabilities, not replacing the shell. |
| Design tokens            | `@pdomain/pdomain-ui/theme/tokens.css` import plus labeler aliases (`frontend/src/styles/tokens.css:1-44`)                                                                                                                | Token values come from the shared package; labeler keeps `--status-*` and `--layer-*` domain names as aliases.                  |
| Tailwind token bridge    | Tailwind maps bg/border/ink/accent/status/layer/font/type to CSS vars (`frontend/tailwind.config.js:20-67`)                                                                                                               | This keeps Tailwind usage tied to design tokens rather than palette literals.                                                   |
| Workspace toolbar        | `WorkspaceToolbar` wraps `pdomain-ui` `StageToolbar` (`frontend/src/components/shell/WorkspaceToolbar.tsx:12-43`)                                                                                                         | This is the right pattern for document/page-scoped controls outside app chrome.                                                 |
| Canvas host              | Labeler `PageImageCanvas` uses `@pdomain/pdomain-ui/canvas` and fills selection/tool slots (`frontend/src/components/PageImageCanvas.tsx:1-73`)                                                                           | Labeler-specific bbox, selection, add-word, rebox, erase, and zoom behavior correctly remain local.                             |
| Project route workbench  | `ProjectPage` composes toolbar, canvas, drawer, action grid, right panel, hidden driver-contract stubs, and confirm dialog (`frontend/src/pages/ProjectPage.tsx:860-1054`)                                                | The route is usable and domain-specific; the gap is standardizing shared layout pieces.                                         |
| Drawer and detail panels | Drawer tabs and right-panel routing are implemented (`frontend/src/components/shell/Drawer.tsx:89-221`; `frontend/src/components/shell/RightPanel.tsx:68-179`)                                                            | PGDP confirms the usefulness of this pattern, but the labeler's data/selection model is distinct.                               |
| Shared worklist adapter  | Drawer `Worklist` uses `@pdomain/pdomain-ui/worklist` `WordList` with a labeler row adapter and `renderRow` override (`frontend/src/components/drawer/Worklist.tsx:1-22`, `:36-63`, `:410-439`)                           | The visual list shell is already shared; remaining work is adapter cleanup and adjacent review surfaces.                        |
| OCR/text review          | Word match virtual list, plaintext views, detail panels, palettes, and action grid exist (`frontend/src/components/WordMatchView.tsx:42-193`; `docs/architecture/26-right-panel-detail.md:37-91`)                         | These are labeler product surfaces, not PGDP stage tools.                                                                       |
| Export/trainer           | Export dialog, job progress, manifest writing, client-local run history, and trainer launch utilities exist (`frontend/src/components/ExportDialog.tsx:1-40`, `:185-220`; `frontend/src/components/ExportDialogUtils.ts`) | Persistent export history is still thin; this maps to training-data export, not PGDP build/zip/submit/archive.                  |
| Event-store undo         | Per-page undo/redo is designed and wired around append-only events (`docs/specs/2026-06-12-event-store-undo.md:16-29`, `:99-112`)                                                                                         | This aligns with PGDP's server-authoritative/event-driven philosophy, but not with PGDP pipeline machines.                      |

## Partial Coverage

| Area                  | Current labeler coverage                                                                                                                                                                                                                                         | PGDP handoff pattern                                                                                                                                                      | Gap to close                                                                                                                                                             | Keep app-local                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Projects landing      | Cards, search, filter chips, open-folder, delete, session resume (`frontend/src/pages/RootPage.tsx:324-477`)                                                                                                                                                     | PGDP projects page has active/archived rail, project detail, lifecycle, recent activity, attributes, manage actions, and post-import jobs (`statecharts/README.md:21-29`) | Add real project metadata, status filters, thumbnail/progress data, archive lifecycle, and activity/detail affordances only if useful to labeler workflows               | PGDP pipeline mini/status, source-ingest semantics, and PGDP project lifecycle             |
| Jobs                  | `useNotificationStream`, `useJobProgress`, busy overlays, export progress (`frontend/src/hooks/useNotificationStream.tsx`; `frontend/src/hooks/useJobProgress.ts`; `frontend/src/components/BusyOverlay.tsx`)                                                    | PGDP shell includes `JobsPill` and `JobsDrawer` (`COMPONENT_INDEX.md:36-37`)                                                                                              | Wire shared jobs pill/drawer or an app-specific adapter over existing job APIs                                                                                           | PGDP stage-runner queue semantics                                                          |
| Settings              | Compute panel content, theme/font-scale UI prefs, local storage persistence (`frontend/src/App.tsx:97-139`, `:393-432`)                                                                                                                                          | PGDP has project settings, stage settings, inheritance banners, and default/modified/preset state (`statecharts/README.md:158-161`)                                       | Make labeler settings reachable and server-backed; add labeler project/app settings only where real prefs exist                                                          | Stage settings inheritance and downstream stale warnings                                   |
| Suite launcher        | `SuiteSiblingsProvider` mounted, but callbacks return shims (`frontend/src/App.tsx:435-470`)                                                                                                                                                                     | PGDP shell assumes suite chrome and jobs placement                                                                                                                        | Replace shim callbacks with real `/api/suite/*` endpoints                                                                                                                | PGDP app catalog behavior beyond available suite APIs                                      |
| Workbench layout      | Project body grid has canvas/worklist/detail columns (`frontend/src/pages/ProjectPage.tsx:1019-1037`)                                                                                                                                                            | PGDP page workbench has a reusable control/viewer/sidecar/footer pattern (`statecharts/README.md:86`, `:121-124`)                                                         | Extract or consume a shared `WorkbenchLayout`/panel shell once `pdomain-ui` has it                                                                                       | PGDP stage control schemas and Apply-&-Continue tuning loop                                |
| Review/worklist queue | Drawer `Worklist` already adapts line rows into `pdomain-ui` `WordList`; `WordMatchView` remains a separate virtualized text-review surface (`frontend/src/components/drawer/Worklist.tsx:1-22`, `:410-439`; `frontend/src/components/WordMatchView.tsx:86-193`) | PGDP has `reviewQueue`, `imageStageReview`, filter counts, density, bulk bar (`statecharts/README.md:119-124`, `:151-157`)                                                | Tighten the existing adapter: shim fields, missing `data-testid` support, filter/count/density/bulk shell ownership, and whether `WordMatchView` should align separately | PGDP per-stage flag taxonomy                                                               |
| Local primitive kit   | Local `Button`, `Input`, `KeyCap`, `Chip`, `StatusPip`, Tabs, Accordion, plus CSS primitives (`frontend/src/components/ui/*`; `frontend/src/styles/primitives.css:40-260`)                                                                                       | PGDP and `pdomain-ui` both provide shared atoms and chrome                                                                                                                | Audit each local primitive for replacement, wrapper, or justified local ownership                                                                                        | Labeler-specific Radix Tabs/Accordion wrappers until `pdomain-ui` supports their structure |
| Export tail           | DocTR export dialog, manifest writing, client-local run history, and send-to-trainer utilities; persistent `/exports` history is still not complete                                                                                                              | PGDP validation -> build package -> zip -> submit-check -> archive (`statecharts/README.md:176-184`)                                                                      | Improve labeler export job/history UX and trainer handoff                                                                                                                | PGDP package, zip, submit, and archive route behavior                                      |

## Remaining Gaps

### 1. App Chrome And Operational Surfaces

| Gap                                           | Evidence                                                                                                                                                                         | Why it matters                                                                            |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Jobs pill/drawer not wired                    | Parity audit still lists F15 jobs panel missing (`docs/research/parity-audit/PARITY-GAP.md:97-104`)                                                                              | PGDP shell expects long-running jobs to be inspectable outside transient toasts/overlays. |
| Suite launcher callbacks are shims            | `fetchInstalled` returns `[]`; `postLaunch` returns `requires-host-config` (`frontend/src/App.tsx:435-458`)                                                                      | The shared AppShell launcher exists but does not yet expose sibling apps.                 |
| Settings/UI prefs are partly local            | `persistApp` is a no-op and common prefs persist only to localStorage (`frontend/src/App.tsx:393-432`)                                                                           | PGDP-style app suites need stable settings behavior across sessions and routes.           |
| Compute panel reachability needs verification | Compute panel content is registered (`frontend/src/App.tsx:97-139`) but parity docs still flag settings/compute reachability (`docs/research/parity-audit/PARITY-GAP.md:97-104`) | Users need reachable CPU/CUDA selection and diagnostics before OCR work.                  |

### 2. Project Landing And Lifecycle

The labeler root page already has project cards, search, filter chips, delete,
and open-folder behavior (`frontend/src/pages/RootPage.tsx:324-477`). The
PGDP design exposes richer project state: status rail, attributes, recent
activity, manage actions, and post-import jobs (`statecharts/README.md:21-29`).

Labeler-relevant gaps:

- Real project metadata for card page counts, progress, thumbnails, and status.
- Functional status filters instead of metadata-limited placeholders
  (`frontend/src/pages/RootPage.tsx:350-353`).
- Archive/restore semantics if labeler projects need a reversible delete lane.
- Activity/history summaries if they can reuse event-store data without adding
  PGDP pipeline semantics.

### 3. Shared Component Duplication

Local wrappers overlap with `pdomain-ui` primitives:

- `Button` (`frontend/src/components/ui/button.tsx:6-52`)
- `Input` (`frontend/src/components/ui/Input.tsx:3-24`)
- `KeyCap` (`frontend/src/components/ui/KeyCap.tsx:1-22`)
- `Chip` (`frontend/src/components/ui/Chip.tsx:4-94`)
- `StatusPip` (`frontend/src/components/ui/StatusPip.tsx:13-48`)

Do not replace these blindly. Some local wrappers are intentionally different:

- Tabs uses raw Radix because `pdomain-ui` active styling does not match Radix
  `data-state` (`frontend/src/components/ui/tabs.tsx:10-63`).
- Accordion uses raw Radix because the labeler trigger has keycap/hint/tag
  layout not supported by the `pdomain-ui` wrapper
  (`frontend/src/components/ui/accordion.tsx:37-114`).

The gap is a migration matrix, not a broad refactor.

### 4. Workbench And Review Queue Standardization

The labeler workbench is a production surface, but its composition is
app-local. A shared `pdomain-ui` workbench family would reduce drift across
labeler, PGDP, trainer, and future apps:

- `WorkbenchLayout`: toolbar, canvas/viewer, drawer/worklist, right detail, and
  optional footer/bulk-action slots.
- `ReviewFilterToolbar`: filter chips, counts, density, selected count, and
  action slot.
- `ReviewQueueList`: the drawer already uses the shared `pdomain-ui` `WordList`
  shell; future work should tighten that adapter and decide whether
  `WordMatchView` should align separately.
- `DetailPanelShell`: header/breadcrumb/collapse/body/footer shell for
  selection detail surfaces.

These should be shared only after adapters prove they can carry labeler data
without hiding domain behavior in generic components.

### 5. Documentation And Driver Contract Drift

The repo has detailed architecture docs, but some are stale relative to the
current code. The parity matrix still tracks testid rot and hidden driver
contract debt (`docs/research/parity-audit/PARITY-GAP.md:97-105`,
`:126-134`). The PGDP handoff reinforces a stricter separation between:

- Actual visible, enabled, effectful UI.
- Story/prototype scaffolding.
- Test-driver compatibility shims.

Future labeler work should retire hidden driver-contract stubs when the visible
surface is the supported contract.

## Out Of Scope For This SPA

Do not add these to `pdomain-ocr-labeler-spa` just because they appear in the
PGDP handoff:

- The 24-stage PGDP pipeline shell, stage strip, stage runner, and run-all-stale
  coordinator (`statecharts/README.md:80-107`).
- PGDP stage tools: source, grayscale, crop, threshold, deskew, denoise, dewarp,
  page order, scannocheck, hyphen join, text review, regex, validation,
  proof-pack, build-package, zip, submit-check, and archive
  (`statecharts/README.md:128-149`).
- Stage settings inheritance/default/preset behavior, except as inspiration for
  real labeler settings.
- PGDP package/submit/archive gates (`statecharts/README.md:176-184`).
- XState v5 conversion solely for PGDP parity. Labeler can adopt state machines
  for hard local workflows, but the PGDP machines model a different app.

## Recommended Next Step

Use the companion backlog doc,
`docs/plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md`, to sequence
labeler-relevant convergence work without turning this app into the PGDP prep
pipeline.
