# Behavior unit spec - Root screen

- **Unit type:** screen
- **Address:** `/`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/03-frontend.md`, `24-shell-layout.md`, and
  `runtime-flows.md`
- **Parent unit(s):** app shell
- **Child unit(s):** project load controls, project cards, source folder dialog
- **Shared unit:** no
- **Implementation:** `frontend/src/pages/RootPage.tsx`,
  `frontend/src/components/ProjectLoadControls.tsx`
- **Backend / collaborators touched:** `GET /api/session-state`,
  `GET /api/projects`, `POST /api/projects/load`,
  `POST /api/projects`, `DELETE /api/projects/{id}`,
  `POST /api/projects/{id}/archive`, source-root filesystem browser

## Behavior records

### B-ROOT-001 - Empty project state renders project browser

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User opens `/` with no restorable last project.
- **Preconditions:** Server is running; source projects may be empty or present.
- **Observable output:** `data-testid="app-shell"` is visible; the root screen
  shows `empty-project-state`, `root-search-filter-bar`, and either
  `root-projects-grid` or `root-empty-projects`.
- **Backend / side-effects:** `GET /api/session-state` returns no active
  project; `GET /api/projects` enumerates source projects; no files are
  changed.
- **Bad-state / error:** Projects enumeration fails -> root chrome remains
  mounted and a project-card error or empty-state message is shown instead of a
  blank screen.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ROOT-002 - Opening a project loads it and navigates to the labeling route

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** -
- **Trigger:** User clicks `project-card-open-{project_id}` or selects a
  project and clicks `load-project-button`.
- **Preconditions:** The project exists under the configured source root.
- **Observable output:** Browser navigates to
  `/projects/{project_id}/pages/pageno/1`; `project-page` becomes visible.
- **Backend / side-effects:** `POST /api/projects/load` initializes
  `ProjectState`, writes/restores session state, and does not mutate page
  content persistence records.
- **Bad-state / error:** Missing or invalid path -> user stays on root; visible
  error is attached to the relevant project card or load control; no session
  state is advanced to that project.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ROOT-003 - Root search and filter reduce the visible project set

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User types in `root-search-input` or clicks a
  `root-filter-chip-*` chip.
- **Preconditions:** Multiple projects are discoverable.
- **Observable output:** `root-projects-grid` updates to matching project
  cards; if none match, `root-empty-search` appears.
- **Backend / side-effects:** Filtering is client-side over the projects query
  result; no backend write occurs.
- **Bad-state / error:** Empty query/filter state resets to the full project
  list; malformed project metadata renders an individual card error.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ROOT-004 - Restorable session hydrates project before redirect

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** -
- **Trigger:** User opens `/` and session state has `last_project_path`.
- **Preconditions:** The saved project path still maps to a project returned by
  project enumeration.
- **Observable output:** Root content stays in the pending state while restore
  resolves; on success the browser replaces the URL with
  `/projects/{project_id}/pages/pageno/{last_page_index + 1}`.
- **Backend / side-effects:** Frontend reads session state and projects, then
  posts `POST /api/projects/load`; backend hydrates `ProjectState` and writes
  refreshed session state.
- **Bad-state / error:** Failed restore falls back to the project browser and
  must not navigate to a stale project route.
- **Tier(s):** A
- **Regression:** yes (#327)
- **Test:** -

### B-ROOT-005 - Project-not-found redirects suppress auto-restore

- **Flow(s):** -
- **Composed by:** B-PROJECT-006
- **Trigger:** Root renders with route state `skipSessionRedirect`.
- **Preconditions:** Session state may still contain a previous project.
- **Observable output:** Project browser renders and no immediate restore
  navigation occurs.
- **Backend / side-effects:** Session/projects queries may run; frontend must
  not post a restore load for the skipped session.
- **Bad-state / error:** Without this guard, a missing project redirect can loop
  back into the last saved session.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ROOT-006 - Source folder action opens the global dialog

- **Flow(s):** F-SOURCE-ROOT-01
- **Composed by:** B-ACTIONS-006
- **Trigger:** User clicks the root screen source folder control.
- **Preconditions:** Root project browser is visible.
- **Observable output:** `source-folder-dialog` opens from the app-level dialog
  mount and can be closed without navigating.
- **Backend / side-effects:** Opening the dialog does not write state; applying
  a folder belongs to B-ACTIONS-006.
- **Bad-state / error:** If the dialog store cannot open, the root route has no
  visible path for changing the source root.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.
