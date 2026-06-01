# Behavior unit spec - Driver compatibility contract

- **Unit type:** component
- **Address:** stable routes and `data-testid` contract for
  `pd-ocr-labeler-driver`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/13-driver-contract.md`
- **Parent unit(s):** app shell, root screen, project page
- **Child unit(s):** hidden compatibility stubs, route redirects
- **Shared unit:** yes
- **Implementation:** `frontend/src/App.tsx`,
  `frontend/src/pages/ProjectPage.tsx`, `frontend/src/components/*`,
  `frontend/src/lib/routes.ts`, `tests/e2e/test_driver_contract.py`
- **Backend / collaborators touched:** SPA route fallback, redirect behavior,
  project/page fetch endpoints

## Behavior records

### B-DRIVER-001 - Stable required test IDs are present or explicitly stubbed

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** Driver or test suite loads a project page and queries required
  `data-testid` values.
- **Preconditions:** Project page has rendered.
- **Observable output:** Required real controls are present and visible where
  documented; intentionally unavailable legacy controls remain in DOM with
  `data-testid-stub="true"` so the driver can distinguish stub from missing.
- **Backend / side-effects:** No backend write; this is a DOM contract.
- **Bad-state / error:** A removed real control without a stub is a test
  failure; a visible action accidentally marked as stub is also a failure.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_driver_contract.py::test_new_contract_testids_present_on_project_page`,
  `tests/e2e/test_driver_contract.py::test_stub_testids_present`,
  `tests/e2e/test_driver_contract.py::test_stub_testids_have_stub_attribute`

### B-DRIVER-002 - Route compatibility keeps legacy driver URLs functional

- **Flow(s):** -
- **Composed by:** B-PROJECT-003
- **Trigger:** Driver opens legacy `/project/{id}/page/{n}` or bare
  `/projects/{id}/pages/{n}` URL.
- **Preconditions:** Project exists.
- **Observable output:** Browser reaches the canonical project/page route and
  `project-page` renders.
- **Backend / side-effects:** Route redirect/resolution loads page data; no
  document mutation occurs.
- **Bad-state / error:** Unknown project keeps chrome mounted with a clear
  inline not-found state.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_driver_contract.py::test_project_page_route_renders`

### B-DRIVER-003 - Hidden compatibility surfaces do not assert user behavior

- **Flow(s):** -
- **Composed by:** B-DRIVER-001
- **Trigger:** Driver-contract test queries old text-tab, page-action, or
  toolbar IDs that are preserved in hidden containers.
- **Preconditions:** Project page rendered after the shell redesign.
- **Observable output:** IDs exist in hidden containers with stub metadata, but
  behavior records for real user workflows point at the visible StudioShell,
  drawer, canvas, right-panel, or compact action controls.
- **Backend / side-effects:** None.
- **Bad-state / error:** A hidden stub must not be used as proof that a visible
  workflow works; behavior tests should interact with visible controls unless
  they are specifically testing the driver contract.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRIVER-004 - App shell anchors and live regions are always mounted

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** SPA renders any route.
- **Preconditions:** React app has mounted.
- **Observable output:** `app-shell`, `header-bar`, app main slot,
  `status-announcer`, and `error-announcer` exist; live regions use status and
  alert roles.
- **Backend / side-effects:** DOM/accessibility contract only.
- **Bad-state / error:** Missing anchors break driver synchronization and
  accessibility announcements.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRIVER-005 - Deprecated header driver IDs stay absent after D-046

- **Flow(s):** -
- **Composed by:** B-DRIVER-001
- **Trigger:** Driver queries legacy header load IDs.
- **Preconditions:** Root or project route rendered.
- **Observable output:** Deprecated header stubs such as `project-select`,
  `load-project-button`, and `source-folder-button` are not reintroduced in the
  header; loaded project pages expose the newer project-route action IDs.
- **Backend / side-effects:** DOM contract only.
- **Bad-state / error:** Reintroducing deprecated hidden header IDs can make the
  driver select dead controls.
- **Tier(s):** A
- **Regression:** yes (#405)
- **Test:** -

### B-DRIVER-006 - Unknown SPA routes fall back to root shell

- **Flow(s):** -
- **Composed by:** B-ROOT-001
- **Trigger:** User or driver opens an unmatched frontend route.
- **Preconditions:** SPA bundle is served successfully.
- **Observable output:** React Router catch-all redirects to `/` with replace;
  root behavior then applies.
- **Backend / side-effects:** Backend SPA fallback serves `index.html` for
  non-API paths; `/api/*` remains normal API 404 behavior.
- **Bad-state / error:** Unknown routes must not produce a blank app or swallow
  backend API 404s.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.
