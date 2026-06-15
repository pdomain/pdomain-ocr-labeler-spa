# 22 — ProjectPage wireup — mount the real labeling surface

> **Status**: Active (shipped — all spec-22-* child issues closed 2026-05-15).
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#290
> **Depends on**: [`21-konva-renderer.md`](21-konva-renderer.md)
> (real `PageImageCanvas` available), [`23-page-payload-backend.md`](23-page-payload-backend.md)
> (real `GET .../pages/{idx}` payload).
> **Last updated**: 2026-05-14

Replaces the 76-line `ProjectPage.tsx` stub with the full labeling
surface — image viewport on the left, text tabs on the right, page
actions on top, dialogs wired to launchers. The components all exist
(see audit [`../PARITY_GAPS_2026_05_14.md`](../PARITY_GAPS_2026_05_14.md) §2); this spec assembles
them.

---

## 1. Goal

After this spec lands a user who:

1. Loads a project via the `HeaderBar` project dropdown,
2. Lands on `/projects/:id/pages/pageno/1`,

sees the page image, the right-pane word matches list, the toolbar,
the page actions bar, and can use Prev / Next / GoTo for navigation —
and dialogs (OCR config, export, word-edit, hotkey help) open from
their respective launchers.

This is **wireup-only.** Each component already exists and is unit-
tested; this spec changes how they compose, not what they do.

---

## 2. Non-goals

- New components. Everything mounted is already in
  `frontend/src/components/`.
- Backend changes — those live in spec 23.
- Source-folder picker dialog implementation (the testid stubs in
  ProjectPage today are `display:none`; this spec keeps them
  stubbed and defers to a future spec).

---

## 3. Layout

```text
<AppShell>
  <HeaderBar>
    <ProjectLoadControls />               ← shipped
    <button data-testid="ocr-config-trigger-button">tune</button>
    <button data-testid="export-trigger-button">file_download</button>
    <button data-testid="hotkey-help-trigger-button">keyboard</button>
  </HeaderBar>
  <main>
    <Routes>
      <Route ROOT          element={<RootPage />} />
      <Route PROJECT       element={<ProjectRootRedirect />} />
      <Route PROJECT_PAGE  element={<ProjectPage />} />     ← rewritten
    </Routes>
  </main>
  <Toaster />                              ← shipped
  <OCRConfigModal />                       ← mounted at AppShell
  <ExportDialog />                         ← mounted at AppShell
  <HotkeyHelpModal />                      ← mounted at AppShell
  <WordEditDialog />                       ← mounted at ProjectPage
  <ConfirmDialog />                        ← mounted at ProjectPage
</AppShell>
```

`ProjectPage` interior:

```text
<ProjectPage>
  <ProjectLoadingOverlay />                ← shows when usePage is loading first time
  <PageHeader>
    <ProjectNavigationControls />          ← Prev / Next / GoTo (NEW small wrapper)
    <PageActions />                        ← Reload / Save / Save Project / Load / Rematch / Rotate
  </PageHeader>
  <ToolbarActionGrid />                    ← Page / Paragraph / Line / Word rows + Apply Style/Component
  <Splitter direction="horizontal">
    <LeftPane data-testid="image-pane">
      {/* ImageTabsHeader retired D-050/D-053 — controls in Rail + canvas overlay */}
      <BusyOverlay />                      ← shipped — overlay on loading
      <PageImageCanvas />                  ← shipped post-spec-21
        <BBoxOverlay layer="paragraphs" … />
        <BBoxOverlay layer="lines" … />
        <BBoxOverlay layer="words" … />
        <BBoxOverlay layer="selection-*" … />
      <InlineBanners />                    ← OCR-failed / not-found / image-drift
    </LeftPane>
    <RightPane data-testid="text-pane">
      <TextTabs>
        <Tab name="matches">
          <FilterToggle />                 ← NEW small — cycles unvalidated/mismatched/all
          <WordMatchView>
            <LineCard /> × N (virtualized via react-virtual)
          </WordMatchView>
        </Tab>
        <Tab name="gt"><PlaintextEditor source="gt" /></Tab>
        <Tab name="ocr"><PlaintextEditor source="ocr" /></Tab>
      </TextTabs>
    </RightPane>
  </Splitter>
</ProjectPage>
```

`Splitter` lives in `frontend/src/components/Splitter.tsx` (new — tiny
wrapper around an existing utility or a 30-line resizable div) per
spec 03 §splitter. `PlaintextEditor` is a 50-line new component
showing `PagePayload.page_text_gt` / `page_text_ocr` in a
`<textarea>` with `read-only` mode in v1 (legacy doesn't allow editing
the raw text either; per-word edit is the canonical path).

---

## 4. Data flow

Top-level data hooks per route:

- `RootPage` → `useSessionState()` → `EmptyProjectState` or
  `<Navigate to=…>` (shipped #84/#274).
- `ProjectPage` → `useProject(projectId)` + `usePage(projectId, idx0)`
  → renders. Both hooks shipped (#192).

Mutation hooks per component:

- `PageActions` → `usePageMutations()` (#215, shipped).
- `ToolbarActionGrid` → `useWordBatchMutations()` + scope-specific
  hooks. Some shipped (#202 line mutations, #215/#216 page mutations);
  paragraph batch and word-scope-batch are still gap rows — see
  spec 23.
- `WordMatchView` / `LineCard` → `useLineMutations()` + `useWordMutations()`.
- `PageImageCanvas` callbacks → corresponding mutation hooks (rebox,
  add-word, erase, selection POST).

QueryClient invalidation pattern: every mutation invalidates
`["page", projectId, idx0]` so `usePage` re-fetches. Spec 03 §state
already locks this contract; just verify on wireup.

---

## 5. Dialog launchers

| Dialog | Launcher | testid |
|---|---|---|
| OCR config | HeaderBar icon button | `ocr-config-trigger-button` |
| Export | HeaderBar icon button | `export-trigger-button` (NEW — legacy `export-dialog-trigger-button`; choose legacy name) |
| Hotkey help | HeaderBar `?` icon + global `?` key | `hotkey-help-trigger-button` (NEW) + `useGlobalHotkeys.openHotkeyHelp` |
| Word edit | `LineCard` per-word pencil icon | `edit-word-button` (per-word; shipped in LineCard) |
| Confirm (destructive ops) | called imperatively from mutation hooks via `useConfirm()` | `confirm-dialog` (shipped #236) |

Dialog **state** lives in a single `useDialogStore` (Zustand) with
shape:

```ts
interface DialogStore {
  ocrConfig: { open: boolean };
  export: { open: boolean };
  hotkeyHelp: { open: boolean };
  wordEdit: { open: boolean; lineIdx?: number; wordIdx?: number };
  confirm: { open: boolean; title?: string; body?: string; onConfirm?: () => void };
  // setters …
}
```

This replaces ad-hoc `useState` inside each dialog component. The
dialogs themselves are already rendered (per §3) and subscribe to
their own slice.

---

## 6. Header trigger buttons (new in HeaderBar)

The legacy header layout (see
[`pd-ocr-labeler/docs/architecture/ui-action-buttons.md`](../../../pd-ocr-labeler/docs/architecture/ui-action-buttons.md))
shows OCR config (#109) next to the project load controls. SPA mirrors:

```tsx
<header data-testid="header-bar">
  <ProjectLoadControls />
  <button
    data-testid="ocr-config-trigger-button"
    onClick={() => dialogStore.open('ocrConfig')}
    aria-label="OCR configuration"
    disabled={isControlsDisabled}
  >tune</button>
  <button
    data-testid="export-trigger-button"
    onClick={() => dialogStore.open('export')}
    aria-label="Export"
    disabled={isControlsDisabled}
  >file_download</button>
  <button
    data-testid="hotkey-help-trigger-button"
    onClick={() => dialogStore.open('hotkeyHelp')}
    aria-label="Hotkey help (?)"
  >keyboard</button>
</header>
```

`isControlsDisabled` mirrors the legacy `ProjectStateViewModel.is_controls_disabled`
(no project loaded / mid-load). Reads `useProject().status`.

---

## 7. Navigation controls

`ProjectNavigationControls` is a new ~80-LOC component combining the
three existing nav stub testids (`nav-prev-button`, `nav-next-button`,
`nav-goto-button`, `nav-page-input`, `nav-page-total-label`) into a
real, working bar at the top of `ProjectPage`. Behavior:

- Prev / Next — call `navigate(`${projectId}/pages/pageno/${newPageNo}`)`,
  disabled at boundaries.
- GoTo input — number input bound to local state; Enter or click
  GoTo button navigates.
- Total label — `${currentPageNo} / ${project.total_pages}`.

The `display:none` stub block in `ProjectPage.tsx:22-49` is **deleted**
when this component is wired (it was always a driver-contract
appeasement, never a real UI surface).

---

## 8. FilterToggle (new tiny component)

Cycles through Unvalidated / Mismatched / All. Bound to
`usePrefsStore.matchFilter` (already exists). 30 LOC. Lives in
`frontend/src/components/FilterToggle.tsx`. Plumbed into
`WordMatchView` props so the virtualized list shows only matching
lines.

---

## 9. Splitter

30-LOC controlled component. State persisted in
`usePrefsStore.splitterRatio` (D-021). Min/max enforced (20%/80%);
double-click resets to 50%. Tested with Vitest using `fireEvent.mouseDown`
/ `mouseMove` / `mouseUp` on the divider element.

---

## 10. Driver-contract preservation

The stub `display:none` blocks in `ProjectPage.tsx:22-73` carry every
nav-control and source-folder-dialog testid required by
`test_driver_contract.py`. After wireup:

- **Nav controls.** Move to the real `ProjectNavigationControls`
  — the testids stay; only the `display:none` wrapper goes away.
- **Source-folder dialog stubs.** Remain `display:none` until a
  future spec implements the picker. Move from `ProjectPage` to
  `HeaderBar` (where the legacy source-folder dialog lives) — this
  preserves the testid but anchors it to a more accurate location.

Run `make e2e` after the wireup; the conformance test must remain
green.

---

## 11. Notifications integration

Already wired (`Toaster` in `App.tsx`, `useNotificationStream` in
`AppShell`). After this spec lands:

- `BusyOverlay` mounted inside `LeftPane` — subscribes to
  `useJobProgress(projectId, page_index)`; shows during reload-OCR /
  rotate / refine.
- `InlineBanners` mounted inside `LeftPane` — subscribes to
  `useNotificationStream` for `ocr_failed` / `project_not_found` /
  `image_drift` notifications.
- Toasts continue to fire for transient successes.

---

## 12. Acceptance gates

1. `make frontend-test` — all existing tests pass; new tests cover
   `ProjectPage` mount-and-render, `ProjectNavigationControls`,
   `FilterToggle`, `Splitter`, `useDialogStore`.
2. `make e2e` — `test_driver_contract.py` remains green; new
   `test_project_page_smoke.py` loads a project, navigates Prev/Next,
   opens OCR config dialog, opens word-edit dialog, closes.
3. `make ci AI=1` — clean.
4. Manual smoke (CT pass): load a tiny fixture project, see image,
   click a word, edit GT, save, see no errors.

---

## 13. Issue plan

Three issues:

1. **spec-22-A** Dialog wireup — `useDialogStore`, HeaderBar
   trigger buttons, dialog components mounted at AppShell.
2. **spec-22-B** Splitter + ProjectNavigationControls + FilterToggle
   components.
3. **spec-22-C** ProjectPage real shell — assemble §3 layout, remove
   `display:none` stubs, plumb hooks.

Land in order A → B → C. A and B can also run in parallel.

---

## 14. Refs

- Audit: [`../PARITY_GAPS_2026_05_14.md`](../PARITY_GAPS_2026_05_14.md)
- Spec 21 (Konva): [`21-konva-renderer.md`](21-konva-renderer.md)
- Spec 23 (backend payload): [`23-page-payload-backend.md`](23-page-payload-backend.md)
- Spec 03 (frontend shell): [`03-frontend.md`](03-frontend.md)
- Spec 04 (image viewport): [`04-image-viewport.md`](04-image-viewport.md)
- Legacy `page_view.py`: [`pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/page_view.py`](../../../pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/page_view.py)
