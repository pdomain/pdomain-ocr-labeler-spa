# Parity gap audit — 2026-05-14

**Author.** `pd-ocr-labeler-spa` agent (re-spec pass triggered by CT).
**Trigger.** CT observed that `PageImageCanvas.tsx` is a DOM stub
despite being listed as shipped at M4 (#197/#198), and asked for a
full audit against the legacy NiceGUI labeler.

This report is the source of truth for the parity state going forward.
The legacy `docs/PARITY_STATUS.md` is being rewritten in the same
commit; this file documents *why* the rewrite reads the way it does.

---

## 0. TL;DR

The SPA has had a year of component shipping, but **the components are
not wired into the page**. Of 15 user-facing frontend components only
two (`HeaderBar`, `LineCard`) are actually rendered by the route tree.
The main labeling surface (`ProjectPage`) is a 76-line placeholder
that displays "Project: X — Page Y (full UI in progress)".

On the backend, **every per-page domain endpoint is a 200-OK stub**:
`GET /api/projects/{id}/pages/{idx}` returns `_not_implemented(...)`
([`src/pd_ocr_labeler_spa/api/pages.py:174-178`][be-get-page]), and
all per-word mutation routes return an empty `PagePayload` without
mutating state ([`api/words.py:180-189`][be-page-payload]). The
`reload_ocr` and `save_project` job handlers `await asyncio.sleep(0)`
and return ([`core/jobs/runner.py:239-247`][be-job-stubs]).

Two real backend stories *did* land: **export** (real `handle_export`
handler) and **rotate** (real `handle_rotate_page` /
`handle_auto_rotate_all` handlers). The corresponding frontend
(`ExportDialog`, rotate buttons in `PageActions`) exists but is also
not mounted.

**Net.** The SPA is a thoroughly-built scaffold with no usable user
flow. A new user clicking through the UI today would see a page
header, an empty project picker, and an in-progress stub. They cannot
view a page, read OCR, edit a word, save, or export.

[be-get-page]: ../src/pd_ocr_labeler_spa/api/pages.py
[be-page-payload]: ../src/pd_ocr_labeler_spa/api/words.py
[be-job-stubs]: ../src/pd_ocr_labeler_spa/core/jobs/runner.py

---

## 1. Method

**1a. Legacy inventory.** Read
[`pd-ocr-labeler/docs/architecture/ui-action-buttons.md`][legacy-inv]
(the canonical 114-control list) and
[`pd-ocr-labeler/docs/usage/how-to-label-a-page.md`][legacy-howto] for
user-facing flow. Spot-checks against the source modules under
`pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/` confirmed the
ones cited below.

**1b. SPA inventory.** `grep`/`Read` against
`pd-ocr-labeler-spa/frontend/src/` and
`pd-ocr-labeler-spa/src/pd_ocr_labeler_spa/`. The killer query was
`grep -rln "import.*<Component>"` per major component — a component
that is never imported outside its own test file is, by definition,
not part of any rendered tree.

**1c. PARITY_STATUS.md.** Read all 178 lines. Many rows describe
shipped backend plumbing accurately (M0, M1, parts of M2) but the
frontend table is uniformly `⛔ Q-A8` (claiming Vite isn't bootstrapped)
even though every component referenced in those rows has been written
and tested. The frontend table is stale on a different axis than the
overall PARITY_STATUS framing acknowledges.

**1d. OPEN_QUESTIONS.md.** Two open Q's remain: **Q-A14** (Konva
research spike) and **Q-A7** (glyph annotation per-mark provenance,
M11-only). Q-A14 directly blocks the renderer work — this audit
resolves it via D-043 below.

[legacy-inv]: ../../pd-ocr-labeler/docs/architecture/ui-action-buttons.md
[legacy-howto]: ../../pd-ocr-labeler/docs/usage/how-to-label-a-page.md

---

## 2. Gap analysis by category

### 2.1 Image viewport — PageImageCanvas / BBoxOverlay

**Legacy.** NiceGUI `ui.interactive_image` with SVG overlay strings
built via `_get_viewport_layer_overlay` ([`image_tabs.py:605-621`][lg-overlay]).
Renders the page image (cached at `display_width = min(src,1200)`),
overlays paragraph/line/word rects per layer-visibility checkboxes,
supports drag-rect select with three modifier modes (replace, remove,
toggle), and three exclusive edit modes (rebox, add-word, erase) with
distinct cursors. Cited testid: `viewport-image` (implicit).

**SPA today.**

- `PageImageCanvas.tsx` — DOM `<div>` only. `imageUrl` is destructured
  to `_imageUrl` and dropped on the floor; no image is rendered. Drag
  events are handled via DOM mouse events on a div. No Konva
  `<Stage>`. ([`frontend/src/components/PageImageCanvas.tsx:14-15,91`](../frontend/src/components/PageImageCanvas.tsx))
- `BBoxOverlay.tsx` — Renders a single `<div style="display:none">`
  with `data-fill` / `data-stroke` / `data-item-count` attributes for
  test introspection. No rects ever render. ([`frontend/src/components/BBoxOverlay.tsx:78-101`](../frontend/src/components/BBoxOverlay.tsx))
- Neither component is imported into `ProjectPage` or anywhere else
  in the app shell (`grep` returned zero non-test importers).

**Gap.** **P0 — Image viewport is structurally absent.** The "shipped
at M4" claim in CLAUDE.md / ROADMAP / PARITY_STATUS is a documentation
bug born of D-020's research-spike framing — the component scaffolds
landed, the research spike never happened, the bodies were never
filled in, and downstream issues (#197/#198) were closed on the stub
contracts. There is also a secondary bug in `ImageTabsHeader`:
paragraph-mode radio is permanently `false` due to a hardcoded
`&& false /* paragraph mode not yet mapped */` (line 108) and the
`SelectionMode` type uses `"box" | "line" | "word"` rather than the
spec's `paragraph | line | word`.

**Spec.** This gap is comprehensively re-specced in
[`docs/architecture/21-konva-renderer.md`](architecture/21-konva-renderer.md) (this
commit; moved from `specs/` to `docs/architecture/` after shipping). Resolves Q-A14. Supersedes D-020.

[lg-overlay]: ../../pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py

### 2.2 Page surface — ProjectPage shell

**Legacy.** `pd_ocr_labeler/views/projects/pages/page_view.py` builds
the split-pane page: left = `ImageTabs`, right = `TextTabs`, top =
`PageActions` + `ProjectNavigationControls`. Closes around a single
`PageStateViewModel` and routes events between sub-views.

**SPA today.** [`frontend/src/pages/ProjectPage.tsx:13-76`](../frontend/src/pages/ProjectPage.tsx)
is a 76-line file that renders one `<p>` ("Project: X — Page Y (full
UI in progress)") and 13 `display:none` driver-contract stub buttons
to satisfy `test_driver_contract.py`. None of the real components
(`PageImageCanvas`, `BBoxOverlay`, `ImageTabsHeader`, `TextTabs`,
`PageActions`, `ToolbarActionGrid`, `WordEditDialog`, `WordMatchView`,
`ExportDialog`, `OCRConfigModal`, `HotkeyHelpModal`, `BusyOverlay`,
`InlineBanners`) are mounted.

**Gap.** **P0 — Project page has no real UI.** The driver-contract
test passes because the stub testids exist; the conformance check
doesn't care that the surrounding UI doesn't function. New spec:
[`docs/architecture/22-page-surface-wireup.md`](architecture/22-page-surface-wireup.md).

### 2.3 Per-page backend stubs

**Legacy.** `pd_ocr_labeler/services/page_service.py` plus the
`viewmodels/project/page_state_view_model.py` orchestrator produce
the full page payload (image, words, lines, paragraphs, OCR, GT,
matches, selection) on demand from `PageStateOperations`.

**SPA today.**

| Endpoint | Status | Evidence |
|---|---|---|
| `GET /api/projects/{id}/pages/{idx}` | 501 stub | `pages.py:174-178` |
| `POST .../pages/{idx}/save` | 501 stub | `pages.py:189-192` |
| `POST .../pages/{idx}/load` | 501 stub | `pages.py:202-205` |
| `POST .../pages/{idx}/rematch-gt` | 501 stub | `pages.py:236-240` |
| `POST .../reload-ocr` | 202 + sleep-0 handler | `runner.py:239-241` |
| `POST .../words/{l}/{w}/gt` (and 10 sibling word ops) | 200 empty `PagePayload` | `words.py:180-189` |
| `POST .../lines/...` / `paragraphs/...` (5 ops) | 200 empty `PagePayload` | `lines_paragraphs.py:130-200` |
| `POST .../refine` | 202 + handler | `refine.py:83` (real?) |
| `POST .../export` | 202 + handler | `export.py:75` (real, `handle_export`) |
| `POST .../rotate` | 202 + handler | `pages.py:243` (real, `handle_rotate_page`) |
| `POST .../auto-rotate-all` | 202 + handler | `ocr_config.py:417` (real?) |

**Gap.** **P0 — No domain data flows.** The frontend cannot fetch a
page payload, so any wired component would still see nothing. New
spec: [`docs/architecture/23-page-payload-backend.md`](architecture/23-page-payload-backend.md).

### 2.4 Word match list — WordMatchView

**Legacy.** `word_match_renderer.py` renders paragraph expanders with
nested line cards; each line card has GT→OCR / OCR→GT / Validate /
Delete buttons (controls #58–61); each word has edit/validate icons
(#62-63) and a GT text input (#108) with Tab/Shift-Tab nav. Filter
toggle cycles Unvalidated / Mismatched / All (#102).

**SPA today.** `WordMatchView.tsx` + `LineCard.tsx` exist with real
bodies (118 + 181 LOC), virtualized via `@tanstack/react-virtual`,
and **are not mounted** (zero non-test importers).

**Gap.** **P0 — Word matches not in page tree.** Component is good;
just needs wiring. Covered by spec 22 (page wireup).

### 2.5 Toolbar action grid

**Legacy.** `word_match_toolbar.py` produces the 4-row grid (page /
paragraph / line / word scopes — controls #18-53) plus Apply Style /
Component buttons (#54-56). Total 39 controls.

**SPA today.** `ToolbarActionGrid.tsx` (332 LOC) exists with hookups
to `usePageMutations` / `useLineMutations`; **not mounted**.

**Gap.** P0 wireup gap; spec 22.

### 2.6 Word edit dialog

**Legacy.** `word_edit_dialog.py` — 29 controls. Preview (Prev/Cur/Next
columns), zoom toggle, marker placement, hover guides, erase rects,
GT input, style/component/scope dropdowns, merge/split/delete (#71-75),
crop above/below/left/right (#76-79), refine + expand+refine (#80-81),
8 nudge buttons (#82-89), Reset / Apply / Apply+Refine (#90-92),
Enter-to-commit (#93).

**SPA today.** `WordEditDialog.tsx` (296 LOC) + `WordImageCanvas.tsx`
(375 LOC, **real Konva**) + sub-rows (`WordActionRows`,
`WordRefineNudgeRows`) exist. **Not mounted** — no path opens this
dialog from the rendered tree.

**Gap.** P1 wireup gap (P0 wireup of viewport precedes it). The Konva
*here* is actually wired (`Stage`/`Layer`/`Rect` from `react-konva`).
This is in stark contrast to `PageImageCanvas` — proves the Konva
toolchain itself works end-to-end. Covered by spec 22.

### 2.7 Page actions bar

**Legacy.** `page_actions.py` — Reload OCR (#14), Reload OCR Edited
(#14a), Save Page (#15), Save Project (#15a), Load Page (#16),
Rematch GT (#17). Plus nav controls (Prev/Next/GoTo — #10-12).

**SPA today.** `PageActions.tsx` (313 LOC) — real, includes rotate
buttons added in #263. Imports `useViewportHotkeys` indirectly. **Not
mounted** in `ProjectPage`. Nav controls live as **stub** `display:none`
buttons inside `ProjectPage.tsx:22-49`.

**Gap.** P0 wireup gap; the stub nav buttons are particularly
deceptive — they pass `test_driver_contract.py` but are not real
controls. Covered by spec 22.

### 2.8 Dialogs — OCRConfigModal, ExportDialog, HotkeyHelpModal, ConfirmDialog

**Legacy.** OCR config modal trigger in header (#109-115); export
dialog from page view (`export_dialog.py`); confirm modals via NiceGUI
`ui.dialog`.

**SPA today.** All four components exist:

| Component | LOC | Wired? |
|---|---|---|
| OCRConfigModal.tsx | 398 | Not mounted |
| ExportDialog.tsx   | 431 | Not mounted |
| HotkeyHelpModal.tsx | 101 | Not mounted |
| ConfirmDialog.tsx  | (real) | Not mounted |

The header has no `tune`-icon trigger for OCR config (#109), no export
launcher, no hotkey-help launcher.

**Gap.** P1 — dialogs need launchers in HeaderBar / PageActions.
Covered by spec 22.

### 2.9 Notifications + busy overlays + banners

**Legacy.** NiceGUI `ui.notify` + own progress overlays.

**SPA today.** Full stack landed (#230 NotificationQueue backend,
issue #231 `useNotificationStream` + `sonner` Toaster, issue #232
BusyOverlay + ProjectLoadingOverlay, issue #233 banners). `Toaster` is wired in
`App.tsx:96`; `useNotificationStream` is called in `AppShell`
([`App.tsx:49`](../frontend/src/App.tsx)). **This stack is actually
live.** `BusyOverlay` and `InlineBanners` components have zero
non-test importers, so the banners themselves render nowhere despite
the SSE stream working.

**Gap.** P2 — toasts work; banners and busy-overlay are scaffolded
but not rendered. Covered by spec 22.

### 2.10 Hotkeys

**Legacy.** Five hotkeys total: Enter (in GT input, #93), Enter (in
page GoTo, #13), Enter (in source-folder path, #9), plus implicit Esc
behaviors. No viewport hotkeys.

**SPA today.** Full hotkey system (`useHotkey`, `useGlobalHotkeys`,
`useViewportHotkeys`, `useDialogHotkeys`, `useMatchesHotkeys`,
`hotkeyMap.ts`) per D-022 wishlist. Tests pass. But: the consumer
components (viewport, dialog, matches) aren't mounted, so the hotkeys
never fire in practice.

**Gap.** P2 — same wireup gap. Covered by spec 22.

### 2.11 Save / load / export — real backend, no frontend hook

**Legacy.** Save Page → `PageSaveOperations.save_current_page`;
Save Project → multi-page iteration; Rematch GT →
`GroundTruthOperations.rematch_page`; Export → DocTR labels.json
under `<data root>/exports`.

**SPA today.**

- Save Page / Save Project: 501 stub on `POST .../save`. The Save-lane
  helper `persist_page_to_file` *does* exist in `core/page_state.py`
  (#284 shipped), but no endpoint calls it.
- Rematch GT: 501 stub on `POST .../rematch-gt`.
- Export: real `handle_export` shipping `labels.json` per spec 10;
  endpoint live but no frontend launcher (`ExportDialog` not mounted).

**Gap.** P1 — Save-page endpoint must call `persist_page_to_file`;
rematch-gt needs implementation; export needs a launcher in the UI.
Covered by spec 23 (backend) + spec 22 (wireup).

### 2.12 Text normalization, search, drop-cap, glyph annotations

**Legacy.** Long-S, ligature normalization (D-025) — implemented in
pd-book-tools, surfaced via per-line plaintext rendering. No search.

**SPA today.** Normalize fields landed (#259/#260/#261) on the
backend plus an OCRConfigModal section. **OCRConfigModal not mounted**
so users cannot toggle. PagePayload includes `page_text_ocr` /
`page_text_gt` fields for normalized plaintext.

**Search**: not in legacy, not in SPA.

**Glyph annotations**: M11 work; blocked on `pd_book_tools`
upstream (issues #267-270 are `status:blocked`). Out of scope here.

**Gap.** P2 — OCR config UI wireup is the only thing. Covered by
spec 22.

### 2.13 Auto-rotation

**Legacy.** Not present (M9.1/M9.2 are net-new for SPA).

**SPA today.** Backend rotate handlers shipped (#263, #264); frontend
rotate buttons in `PageActions.tsx` — **not mounted**.

**Gap.** P1 wireup gap; covered by spec 22.

---

## 3. Priority ranking

**P0 — Blocking real use (cannot demo, cannot operate).**

1. **Wire up `ProjectPage`.** Replace the 76-line stub with a real
   shell that mounts `ImageTabsHeader`, `PageImageCanvas` (post-Konva),
   `BBoxOverlay`, `TextTabs` → `WordMatchView`, `PageActions`,
   `ToolbarActionGrid`. Spec: 22.
2. **Konva-wire `PageImageCanvas` + `BBoxOverlay`.** Real `<Stage>`,
   real image, real overlay rects, real drag interactions. Spec: 21.
3. **Implement `GET /api/projects/{id}/pages/{idx}`.** Backend page
   payload assembler — gather `PageRecord`, line matches, encoded
   dims, selection, image cache URL, plaintext. Spec: 23.
4. **Implement `reload_ocr` job handler.** Use the existing
   `ensure_page_model` dispatcher + LocalDoctrPageLoader. Spec: 23.

**P1 — Important UX gaps (demo works but features missing).**

1. **Wire dialogs.** OCR config (HeaderBar `tune` icon), export
   (PageActions or HeaderBar), hotkey help (`?` key handler in
   `App.tsx`). Spec: 22.
2. **Implement word/line/paragraph mutation endpoints.** All 19
   stub endpoints under `api/words.py` + `api/lines_paragraphs.py`
   need real handlers that mutate `ProjectState` + autosave. Spec: 23.
3. **Implement save-page / save-project / rematch-gt endpoints.**
   `persist_page_to_file` exists; just connect it. `save_project` job
   handler real impl. Spec: 23.
4. **Filter toggle in `WordMatchView`.** Unvalidated / Mismatched /
   All cycler at top of right pane. Covered by spec 22.

**P2 — Nice-to-have.**

1. Render `BusyOverlay` + `InlineBanners` (scaffolded but not in tree).
2. ImageTabsHeader paragraph radio bug fix — `&& false /* paragraph
   mode not yet mapped */` (line 108) + type drift `"box" | "line" |
   "word"` vs. spec's `paragraph | line | word`.
3. Add an `ImageTabs` host component (legacy has a tab strip with
   Words / Lines / Mismatches sub-tabs; SPA collapses to a single
   `PageImageCanvas` per spec 04 — verify this is intentional or
   add the sub-tabs).
4. Source-folder dialog (`source-folder-*-button` testids exist as
   stubs — implement the real picker dialog when path-typed entry is
   needed; current `POST /api/projects/source-root` covers config
   persistence but no UI surface drives it).

---

## 4. PARITY_STATUS.md rewrite plan

The current file is 178 lines and most rows are wrong in one of two
ways:

- **Backend rows are mostly right** but the prose claims M2 is "~85%
  shipped" — accurate for the *plumbing* (project discovery, source
  root, session state, ground truth, three-lane persistence) and
  misleading for the *user flow* (no page can actually be viewed).
- **Frontend rows are uniformly ⛔ Q-A8** ("frontend never bootstrapped")
  which is stale — every M1-M9.1 frontend component has shipped (and
  is tested under Vitest) since 2026-05-14. Q-A8 was closed in #246.

The rewrite has three columns: **Capability**, **Status**, **Wire
state** (new). A row can be `✅ done` on the component axis but
`⛔ not mounted` on the wire axis. The third column makes the actual
parity story legible. Rows that resolve to actual gaps cite the new
spec / issue number.

---

## 5. Top-5 P0 gaps with effort estimate

| # | Gap | Effort | Spec | Notes |
|---|---|---|---|---|
| 1 | Konva renderer (`PageImageCanvas` + `BBoxOverlay`) — real Stage / Layer / Image + drag modes | **L** (2-3 sessions) | spec 21 | Image loading via `useImage` hook; overlay rect virtualization; 4 modes; pan/zoom |
| 2 | `ProjectPage` wireup — mount all 13 components, plumb `useProject`/`usePage`/mutations | **M** (1-2 sessions) | spec 22 | Replace the 76-line stub; preserve driver-contract testids |
| 3 | `GET .../pages/{idx}` real impl — assemble `PagePayload` via `ensure_page_model` + `EncodedDims` | **M** (1 session) | spec 23 | Helpers exist in `core/page_state.py`; need router glue + image_url |
| 4 | `reload_ocr` job handler — actually call `LocalDoctrPageLoader.run_ocr` + persist | **M** (1 session) | spec 23 | `PredictorCache` + lane helpers already in place |
| 5 | 19 word/line/paragraph mutation endpoints — real state mutation + autosave | **L** (2-3 sessions) | spec 23 | Each is small individually; the sweep is what's large |

**Cumulative.** ~7-10 sessions to a functional, demo-able SPA. That's
the floor — does not include export-launcher polish, banners,
filter cycler, or M9.2 auto-rotate UI exposure.

---

## 6. Open questions surfaced by this audit

- **Q-A14 (Konva research spike before M4)** — resolved by D-043
  (Konva commitment): the WordImageCanvas already proves Konva
  works at our scale; a separate spike is unnecessary. Spike-as-
  prerequisite framing is dropped.
- **No new open questions.** The spec 21 / 22 / 23 set is intended
  to be answerable from existing data; nothing was deferred to the
  user during writing.

---

## 7. What CT needs to decide before next steps

1. **Approve D-043.** Konva is the renderer; no raw-canvas fallback.
   D-020 is superseded. This is a commitment, not a research question.
2. **Approve the P0 priority order.** Spec 21 → 23 → 22, in that
   order, so that a wired page has something to render and something
   to fetch.
3. **Confirm "wire-up first, polish after".** Order P0 items 1-4
   before any P1 work; P1 lives behind ToolbarActionGrid / dialogs /
   filter which are component-shape gaps, whereas P0 items are
   end-to-end gaps.

---

## 8. References

- Legacy UI inventory: [`pd-ocr-labeler/docs/architecture/ui-action-buttons.md`](../../pd-ocr-labeler/docs/architecture/ui-action-buttons.md)
- Legacy usage docs: [`pd-ocr-labeler/docs/usage/how-to-label-a-page.md`](../../pd-ocr-labeler/docs/usage/how-to-label-a-page.md)
- SPA image viewport spec: [`docs/architecture/04-image-viewport.md`](architecture/04-image-viewport.md)
- Konva spec: [`docs/architecture/21-konva-renderer.md`](architecture/21-konva-renderer.md)
- Page wireup spec: [`docs/architecture/22-page-surface-wireup.md`](architecture/22-page-surface-wireup.md)
- Backend payload spec: [`docs/architecture/23-page-payload-backend.md`](architecture/23-page-payload-backend.md)
- ADR D-043: [`specs/17-decisions.md`](../specs/17-decisions.md#d-043)
