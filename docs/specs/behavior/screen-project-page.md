# Behavior unit spec - Project page

- **Unit type:** screen
- **Address:** `/projects/:projectId/pages/pageno/:pageNumber`,
  `/projects/:projectId/pages/index/:pageIndex`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/03-frontend.md`, `13-driver-contract.md`,
  `22-page-surface-wireup.md`, and `runtime-flows.md`
- **Parent unit(s):** app shell
- **Child unit(s):** studio shell, canvas, drawer worklist, right panel,
  page actions, dialogs
- **Shared unit:** no
- **Implementation:** `frontend/src/pages/ProjectPage.tsx`,
  `frontend/src/hooks/useProject.ts`, `frontend/src/hooks/usePage.ts`,
  `frontend/src/lib/routes.ts`
- **Backend / collaborators touched:** `GET /api/projects/{id}`,
  `GET /api/projects/{id}/pages/{idx}`, session state, page image URL/blob
  serving

## Behavior records

### B-PROJECT-001 - Project page loads the full labeling workspace

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-ROOT-002
- **Trigger:** User navigates to a canonical project page route.
- **Preconditions:** Project exists and page index is in range.
- **Observable output:** `project-page`, `studio-shell-canvas`,
  `studio-shell-drawer`, `studio-shell-right`, `image-pane`, and
  `project-top-toolbar` are present; current page filename and page number are
  visible.
- **Backend / side-effects:** `GET /api/projects/{id}` and
  `GET /api/projects/{id}/pages/{idx}` return `ProjectPayload` and
  `PagePayload`; page image is served from the payload `image_url`; no save
  occurs.
- **Bad-state / error:** Unknown project redirects to root through
  B-PROJECT-006; bad page index shows an inline page error where route parsing
  reaches the project page.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_project_page_smoke.py::test_project_page_loads_with_tiny_fixture`

### B-PROJECT-002 - Page navigation updates route and page payload

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User clicks `nav-next-button`, `nav-prev-button`, or enters a
  page number and clicks `nav-goto-button`.
- **Preconditions:** A loaded project has at least one page.
- **Observable output:** Route changes to the target canonical `pageno` URL;
  `project-toolbar-page`, `page-name-label`, canvas, and detail data update to
  the new page.
- **Backend / side-effects:** Frontend fetches the target
  `GET /api/projects/{id}/pages/{idx}`; B-PROJECT-005 persists the current page
  cursor; no page content persistence write occurs.
- **Bad-state / error:** Prev is disabled on the first page and Next on the
  last page; out-of-range Go To keeps the user on the current valid page and
  shows/retains an error state without fetching an invalid payload.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_project_page_smoke.py::test_navigate_prev_next`

### B-PROJECT-003 - Legacy and alternate routes resolve to canonical page form

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User opens `/projects/{id}` or
  `/projects/{id}/pages/index/{idx}`.
- **Preconditions:** Project exists.
- **Observable output:** The labeling workspace renders and browser location
  ends in the canonical `/projects/{id}/pages/pageno/{n}` form.
- **Backend / side-effects:** Route resolution may load project/page state; no
  document mutation occurs.
- **Bad-state / error:** Unknown project follows B-PROJECT-006. Legacy driver
  route expectations are tracked as unclear until confirmed against current
  router registrations.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-PROJECT-004 - Project route injects header controls and metrics

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-PROJECT-001
- **Trigger:** User navigates to a loaded project page.
- **Preconditions:** Project/page queries either have data or are pending.
- **Observable output:** App header remains mounted; route-provided project
  name, navigation controls, compact page actions, and optional metrics strip
  appear when data is present. Root route does not show real project actions.
- **Backend / side-effects:** Header slots read the same project/page queries as
  the page body; no mutation occurs.
- **Bad-state / error:** If data is absent, breadcrumb/metrics are omitted while
  app shell and main slot remain mounted.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-PROJECT-005 - Project page persists current page cursor

- **Flow(s):** -
- **Composed by:** B-PROJECT-002
- **Trigger:** `ProjectPage` mounts or the resolved page index changes.
- **Preconditions:** `projectId` and `idx0` are valid route values.
- **Observable output:** No direct visible change; later session restore resumes
  at this page.
- **Backend / side-effects:** After debounce the frontend posts
  `POST /api/projects/{id}/current-page-index`; backend updates
  `ProjectState.current_page_index` and session state.
- **Bad-state / error:** Cursor write failures are ignored by the frontend;
  backend rejects unknown projects/pages without touching session state.
- **Tier(s):** A
- **Regression:** yes (#333)
- **Test:** -

### B-PROJECT-006 - Missing project route redirects to root safely

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User opens `/projects/{missing}/pages/pageno/{n}`.
- **Preconditions:** Project query returns 404.
- **Observable output:** Warning toast is requested and navigation replaces the
  URL with `/`, passing `skipSessionRedirect` so B-ROOT-005 applies.
- **Backend / side-effects:** Failed project query only; no document mutation.
- **Bad-state / error:** App shell remains mounted and no fatal console error
  or blank route is produced.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-PROJECT-007 - Initial page fetch shows loading overlay

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** Project route renders while the page query is pending.
- **Preconditions:** Route is valid and project/page data is not loaded yet.
- **Observable output:** `project-loading-overlay` is present over the project
  surface.
- **Backend / side-effects:** Pending `GET /api/projects/{id}/pages/{idx}`; no
  mutation.
- **Bad-state / error:** If the query stalls, the overlay remains instead of a
  blank app.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.
