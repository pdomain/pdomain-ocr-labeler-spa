# Unclear behavior inventory

These items were found during behavior capture and need product or
implementation decisions before they can be treated as locked behavior.

## Routes and root

- Legacy `/project/{id}/page/{n}` and bare `/projects/{id}/pages/{n}` route
  support is documented in driver specs, but current SPA route registration
  does not obviously include those routes.
- Unknown project behavior is now redirect-to-root with a warning and
  `skipSessionRedirect`; older docs mention inline "Project not found".
- Root filter chips for active/complete/archived are visible, but metadata for
  those states is not exposed by the current project API, so some chips are
  effectively no-ops.
- Root project card Delete/Archive menu items appear inert. Decide whether to
  hide, disable, implement, or document them as placeholders.
- Direct bad page URLs such as `/pageno/0`, `/pageno/abc`, or out-of-range
  values need a canonical redirect/error behavior.

## Canvas and viewport

- `ProjectPage` does not appear to pass `PageImageCanvas` mutation callbacks for
  selection POST, rebox, add-word, or erase-pixels. Component/backend pieces
  exist, but visible project-page wiring is unclear.
- Specs mention page-level erase-pixels, while current backend exposes
  word-anchored `POST .../words/{line}/{word}/erase-pixels`.
- Click outside any bbox is specified in some places as clearing selection;
  current canvas click miss appears to preserve selection.
- Erase repeated-drag behavior conflicts: some docs say erase remains active,
  current component evidence suggests erase exits after one drag.
- `ImageTabsHeader` was retired (D-050/D-053) and deleted. Layer controls live
  in the Rail (`rail-layer-*`); zoom controls in the canvas overlay (`canvas-zoom-*`).

## Shell and drawer

- QuickSearch was documented as hotkey/help-only or read-only in older docs, but
  implementation filters Worklist text and Escape clears it.
- Rail layer controls were documented as static, but implementation has
  `useUiPrefs` layer toggles.
- Rail Bulk was documented as a stub, but current implementation opens drawer to
  Worklist.
- Drawer tab persistence is described as persisted with invalid-tab fallback,
  but current `drawerTab` looks in-memory without a validation path.
- Some architecture text says inactive breadcrumb `data-active` attributes are
  absent, while implementation/tests use `data-active="false"`.

## Right panel and glyphs

- `GlyphAnnotationPanel` exists, but no production mount point or frontend hook
  for `POST glyph-annotations` / `POST accept-prediction` was found.
- Word glyph chip click handlers look like placeholders. A real user path for
  manual glyph review needs confirmation.
- BBox Refine/Crop and Rebox Snap currently collapse to simpler/manual rebox
  behavior. Decide whether to document current stubs or require real endpoints.
- Erase lasso is sent as an axis-aligned rectangle, not a polygon fill.
- CharFixer `char_bboxes` are surfaced through refreshed page payloads, but
  durable process-boundary persistence and downstream export/consumer semantics
  are still undefined.
- Bulk glyph apply closes the dialog, but page data invalidation/refetch wiring
  was not obvious.
- Glyph annotation null/empty/populated state is modeled in the page payload,
  but there is no behavior test proving it survives a fresh page-store reload.

## Actions, jobs, and persistence

- Rematch GT is synchronous, but earlier docs group it with tracked jobs.
- Frontend job progress expects `{job_id,status,progress,error_message}` while
  backend SSE emits `{type,status,current,total,message,error}`.
- Export dialog cancel appears to call a project-scoped job cancel route, while
  backend exposes `/api/jobs/{job_id}/cancel`.
- Reload OCR (Edited) sends `use_edited_image`; backend request model appears to
  ignore it.
- ToolbarActionGrid is hidden in `ProjectPage`, and its handler mainly
  invalidates the page. Decide whether to capture current stub behavior or the
  intended real action mapping.
- WordEditDialog renders many mutation controls, but visible `ProjectPage`
  passes limited callbacks. Decide whether dialog mutations are active product
  behavior or superseded by right-panel editing.
- Auto-save `SaveStatus` and `image_drift` recovery are documented, but active
  frontend state wiring was not found.
- Rotation handler job plumbing exists, but real image rotation/OCR/save effects
  are explicitly stubbed.
- OCR config sidecar save failures are logged/swallowed while live config still
  applies; confirm whether users need stronger visible feedback.
