# pd-ocr-labeler-spa: HeaderBar Component

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#83

## TL;DR

`<HeaderBar />` is a persistent top-chrome mounted in `App.tsx` above all pages. Contains
`<ProjectLoadControls />` (same file): project dropdown (`project-select`), LOAD button
(`load-project-button`, disabled until selection), folder icon (`source-folder-button`), OCR
config trigger (`ocr-config-trigger-button`). No app title or logo — controls-only, matching
legacy. LOAD button disabled before dropdown selection; enabled after. Empty project list shows
placeholder text in the dropdown.

## Context

`specs/03-frontend.md §HeaderBar` defines the component's role: persistent top chrome, not
inside any page. `specs/13-driver-contract.md §2.1` defines the four required testids. The
driver agent interacts with the header on every session — stability of these testids is
critical. The legacy `pd-ocr-labeler` shows the same controls without a title/logo. Out of
scope: SourceFolderDialog, OCRConfigModal, accessibility keymap, auth/managed-adapter axes.

## Constraints

- **Four required testids:** `project-select`, `load-project-button`, `source-folder-button`,
  `ocr-config-trigger-button`. These must be present on every route, even when no project is
  loaded.
- **`load-project-button` disabled before dropdown selection.** Enabled only when a project is
  selected in the dropdown.
- **Controls-only, no app title.** Matches legacy UI; adding a logo would change the visual
  weight without benefit.
- **`ProjectLoadControls` co-located in `HeaderBar.tsx`.** Not a separate file for v1 — the
  component is not reused elsewhere. If it grows beyond ~100 lines, extract it then.
- **Source folder button and OCR config trigger open their respective dialogs** (SourceFolderDialog,
  OCRConfigModal), which are implemented in separate specs. HeaderBar only renders the trigger
  buttons; dialog state lives in the dialogs.

## Decision

### File structure

`frontend/src/components/HeaderBar.tsx` — exports `HeaderBar` (default) and `ProjectLoadControls`
(named, for testing). `ProjectLoadControls` is a `React.FC` that takes no props (reads from
zustand `useProjectStore` directly).

### HeaderBar layout

```
<header data-testid="header-bar" className="flex items-center gap-2 px-4 py-2 border-b">
  <ProjectLoadControls />
</header>
```

### ProjectLoadControls layout

```
<div data-testid="project-load-controls" className="flex items-center gap-2">
  <Select data-testid="project-select">
    <SelectTrigger ...>
      {projects.length === 0 ? "No projects found" : selectedProject?.name ?? "Select a project"}
    </SelectTrigger>
    <SelectContent>
      {projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
    </SelectContent>
  </Select>

  <Button data-testid="load-project-button"
    disabled={!selectedProject}
    onClick={handleLoad}>
    LOAD
  </Button>

  <IconButton data-testid="source-folder-button" aria-label="Browse source folder">
    <FolderIcon />
  </IconButton>

  <IconButton data-testid="ocr-config-trigger-button" aria-label="OCR configuration">
    <SlidersIcon />
  </IconButton>
</div>
```

When no projects are discovered: `project-select` shows placeholder "No projects found";
`load-project-button` is disabled.

### State

`useProjectStore` (zustand) holds `projects: Project[]`, `selectedProjectId: string | null`.
`ProjectLoadControls` reads from this store and dispatches:

- `setSelectedProjectId(id)` on dropdown change.
- `loadProject(id)` on LOAD click (triggers `POST /api/projects/load`).

Discovery query: `useQuery(["projects"])` → `GET /api/projects` (returns list of discovered
projects). Runs on mount and on source-root change.

### Disabled state rules

`load-project-button` disabled when `selectedProjectId === null` OR when a project-load
mutation is in flight (`useIsMutating(["project", "load"]) > 0`).

## Contract / Acceptance

- `data-testid="project-select"` present on every route when app boots.
- `data-testid="load-project-button"` disabled when no project selected; enabled after selection.
- `data-testid="source-folder-button"` and `data-testid="ocr-config-trigger-button"` present.
- Empty project list: dropdown shows "No projects found"; LOAD is disabled.
- Clicking LOAD fires `POST /api/projects/load`; on success navigates to project page.
- `HeaderBar.test.tsx`: renders with all four testids present; LOAD disabled before selection;
  LOAD enabled after selection; LOAD disabled again during in-flight mutation.

## Trade-offs considered

**`ProjectLoadControls` in same file vs separate file.** Separate file adds an import and a
props interface for a component used in exactly one place. Co-location is simpler for v1.
Extract when the file exceeds ~100 lines or the component is reused. Chosen: co-located.

**Dropdown disabled vs placeholder text when no projects.** Disabled dropdown gives no feedback
on why it's empty; placeholder text "No projects found" is self-documenting. Chosen: placeholder.

**App title/logo in header.** Adds visual weight; the legacy doesn't have one; no product
branding need in v1. Chosen: controls-only.

**Discovery on mount vs on demand.** Running discovery on mount means the dropdown is populated
immediately when the app opens, without requiring a user action. Cost: one GET on every app
load. Acceptable. Chosen: on-mount query.

## Consequences

- If the driver agent clicks LOAD before selecting a project, the button is disabled and the
  click has no effect. The driver must select a project from the dropdown first.
- When SourceFolderDialog changes the source root, `useQuery(["projects"])` must be invalidated
  so the dropdown refreshes. The SourceFolderDialog's `onSuccess` callback handles this.
- `source-folder-button` and `ocr-config-trigger-button` must open their dialogs even when no
  project is loaded. These dialogs are pre-project-load operations.

## Open questions

None.

## References

- `specs/03-frontend.md §HeaderBar` — component role and location in App.tsx
- `specs/13-driver-contract.md §2.1` — required testids
- `specs/02-backend.md §GET /api/projects` — project discovery endpoint
- `frontend/src/components/HeaderBar.tsx` — implementation
- `frontend/src/components/HeaderBar.test.tsx` — unit tests
