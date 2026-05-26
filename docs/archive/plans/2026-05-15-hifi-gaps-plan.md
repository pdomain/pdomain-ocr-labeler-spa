# Hi-fi gaps — implementation plan (2026-05-15)

> **Status:** Active. P1–P5 sequenced; each phase decomposes into slices sized
> for one subagent session.
> **Authority:** Post-hi-fi audit (Opus review, 2026-05-15) producing 61 gaps
> against `docs/specs/2026-05-15-hifi-redesign-plan.md` and the design handoff.
> Closes the visual / behavioural gap between the currently shipped shell
> (Slices 0–27 ✅) and the original hi-fi vision so CT can retire the legacy
> NiceGUI `pd-ocr-labeler`.
> **Tracked issues:** #336–#364 (`label:hifi:P1..P5`) — one issue per slice.

## Slice → issue index

| Slice | Issue | Slice | Issue | Slice | Issue |
|---|---|---|---|---|---|
| P1.a | #336 | P2.a | #342 | P3.a | #349 |
| P1.b | #337 | P2.b | #343 | P3.b | #350 |
| P1.c | #338 | P2.c | #344 | P3.c | #351 |
| P1.d | #339 | P2.d | #345 | P3.d | #352 |
| P1.e | #340 | P2.e | #346 | P4.a | #353 |
| P1.f | #341 | P2.f | #347 | P4.b | #354 |
|  |  | P2.g | #348 | P4.c | #355 |
| P5.a | #356 | P5.d | #359 | P5.g | #362 |
| P5.b | #357 | P5.e | #360 | P5.h | #363 |
| P5.c | #358 | P5.f | #361 | P5.i | #364 |

## Context

Hi-fi redesign Slices 0–27 shipped the design-system foundation, shell zones
(StudioShell, Rail, Drawer, HeaderBar, RightPanel), the 6-section WordDetail
accordion, LineDetail, BlockDetail, BulkActions, theme toggle, hotkey overlay
and RootPage refresh. Follow-ons FO-1..FO-9 + M9.5 closed the immediate wiring
gaps. The shipped surface is *functionally* complete — every mutation
endpoint can be reached, every layer toggled.

What the audit surfaced is a different problem: the **visual fidelity and
density** of the shipped components diverges from the high-fidelity design.
Headers are too short, the right panel is too narrow, mode cells are bare
letters instead of icon-card pairs, accordion triggers are bare Radix
defaults instead of uppercase-label + helper-text + keycap rows, and the
flagship Word Editor is missing its identity row, OCR/GT compare row, the
style/component chip palette, the rebox mini-canvas, the erase-pixels
auto-detect canvas, and the validate/skip/delete footer.

These are not regressions in the sense of "previously worked, now broken" —
they were never built in the first pass; they were deferred to keep slice
size manageable. Closing them is the cut-over gate for the legacy labeler.

## Scope freeze

- **In scope.** All 61 audit gaps. Some are already partially closed by the
  2026-05-15 fix-agent pass (Gaps 1/9/17/23/27 — DONE noted inline below).
- **Out of scope.** M11 glyph annotations (#43, #267-#270 — blocked on Q-A7).
  D-042 deferrals (Postgres, multi-user, S3, JWT). The pd-index PEP 503
  publishing workstream. ImageTabs sub-tabs (#295 — design Q for CT).

## Phase map

| Phase | What it ships | Why first | Slices | Wave |
|---|---|---|---|---|
| **P1** | Header + Rail rebuild | Header is the brand-shaped frame everything else lives in; Rail is the most obviously-wrong surface (bare V/R/A/E letters). Visual lift here makes the rest of the work feel coherent during review. | 6 | independent |
| **P2** | Word Editor identity + OCR/GT + style/component palette + accordion redesign | The Word Editor is the labeler's primary editing surface. P2 closes the **critical-gaps** band (Gaps 27–32, 41, 54) so word editing matches the hi-fi mock. | 7 | independent of P1 but blocks P3/P4 |
| **P3** | Word Editor geometry sections (BBox / Rebox mini-canvas / Erase Pixels / Structure) | Konva-heavy work; depends on P2 having shipped the accordion redesign so each section header reads correctly. | 4 | needs P2 |
| **P4** | Char editing + Unicode picker | Lower-frequency tasks; depends on P2 chip palette landing first. | 3 | needs P2 |
| **P5** | Drawer + canvas + line/block views + root page polish | Polish band — items that improve density and information scent but are not on the word-editing critical path. | 8 | independent; bundles remaining medium/low gaps |

Phases P1 and P2 can dispatch concurrently. P3 and P4 both consume P2 output.
P5 is independent and can be picked up by parallel agents whenever capacity
allows.

## How to read the slice tables

Each row is one subagent session of ~200–400 LOC. The bolded **Gaps:** column
lists the audit-gap numbers a slice closes. **Files** lists the primary
file(s); secondary edits (tests, stores) are implied. **Model** is the
recommended dispatch (haiku for token swaps, sonnet for standard feature
work, opus for drag interactions / Konva mini-canvases). **Effort** is S /
M / L (small ≤2h, medium 2–6h, large 1–2 sessions).

A slice closes when (a) gaps in the table are visually present in
`make frontend-dev`, (b) Vitest tests pass for the touched files, (c) `make
ci` is green, (d) the relevant driver-contract testids are intact.

---

## P1 — Header + Rail rebuild (6 slices, independent)

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P1.a | **Header project breadcrumb + metrics strip.** Add the `Projects / <project-name>` breadcrumb chip on the left of the existing header title. Replace the current loose info text with the metrics strip: `N words · N exact · N fuzzy · N ✗ · N/M validated` rendered as a horizontal pill row using existing tokens. Wire counts from `useProject` + `usePage`. | 3, 5 | `frontend/src/components/HeaderBar.tsx`, `frontend/src/components/shell/Breadcrumb.tsx` | sonnet | M |
| P1.b | **Header action buttons + inline pager.** Move Prev/Next page controls into the header as an inline pager (`◀ <input> ▶ /392`). Add visible header action buttons: Reload OCR, Rematch, ✓ Save page, Export ▾. Existing `ProjectNavigationControls` and `PageActions` get re-skinned, not duplicated. | 4, 7 | `frontend/src/components/HeaderBar.tsx`, `frontend/src/components/ProjectNavigationControls.tsx`, `frontend/src/components/PageActions.tsx` | sonnet | M |
| P1.c | **Header ⌘K search field.** Add a non-functional `⌘K` search input in the header centre (placeholder text + keycap chip). Wire the keycap to the existing hotkey overlay open. Search submit is a follow-up. | 6 | `frontend/src/components/HeaderBar.tsx`, new `frontend/src/components/shell/QuickSearch.tsx` | sonnet | S |
| P1.d | **Rail mode cards with icon + label.** Replace bare V/R/A/E letters with icon-card cells (Lucide `Eye`, `Square`, `Plus`, `Eraser`) + label. Use existing `bgSunk` token. Cells stack vertically. Keep current data-testid contract intact. | 10, 11, 12 | `frontend/src/components/shell/Rail.tsx` | sonnet | M |
| P1.e | **Rail layer swatches + section labels + footer.** Add `MODE`/`TARGET`/`LAYERS` uppercase section labels. Render layer toggles as visual legend swatches (Block / ¶Para / Line / Word). Add bottom footer with Bulk / Hotkeys buttons. | 11, 13, 15 | `frontend/src/components/shell/Rail.tsx`, `frontend/src/hooks/useLayerColors.ts` | sonnet | M |
| P1.f | **Rail target add `para`.** Add `para` to the target group between `line` and `block`. Update `rail-store` enum + tests. Update driver-contract spec entries. | 14 | `frontend/src/components/shell/Rail.tsx`, `frontend/src/stores/rail-store.ts`, `docs/architecture/13-driver-contract.md` | haiku | S |

P1 also bundles the **already-DONE** gaps from the 2026-05-15 fix pass: Gap 1
(header 40→56px), Gap 9 (rail 40→64px), Gap 23 (ImageTabsHeader tokens). No
slice needed — these are landed but should be referenced in the slice-a
acceptance check so a regression catches them.

---

## P2 — Word Editor identity + OCR/GT + style palette (7 slices)

This phase reshapes `WordDetail` and the section accordion. Each slice
modifies `frontend/src/components/right-panel/WordDetail.tsx` plus its
section file(s); they serialise rather than parallelise cleanly.

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P2.a | **Word-panel header row** — identity strip above the accordion: `Line 7 · Word 1` mono ID + status pip + per-word pager (◀ ▶) for in-line word navigation. | 28 | `frontend/src/components/right-panel/WordDetail.tsx`, new `frontend/src/components/right-panel/WordHeader.tsx` | sonnet | M |
| P2.b | **Word image preview.** Replace whatever placeholder sits at the top with the 76px serif preview box (cream background, centred glyph) + OCR/GT confidence bars beneath. Reuse `WordImageCanvas` for the image source. | 29 | `frontend/src/components/right-panel/WordDetail.tsx`, new `frontend/src/components/right-panel/WordImagePreview.tsx`, `frontend/src/components/WordImageCanvas.tsx` | sonnet | M |
| P2.c | **OCR/GT compare row + Ω chars inline trigger.** Two-column row: OCR text in a code-style well, GT in an `<Input>` with a copy-OCR-to-GT button and an `Ω chars` button that opens the existing `UnicodePicker` inline (not a modal). | 30 | `frontend/src/components/right-panel/WordDetail.tsx`, `frontend/src/components/right-panel/UnicodePicker.tsx` | sonnet | M |
| P2.d | **STYLE chip palette (whole-word).** Render the style chip palette block (bold, italic, small-caps, sub/superscript, strike, underline) using existing `Chip` primitive in tri-state. Wires to `useWordMutations.applyStyle` with `scope:"whole"`. | 31, 53 (style half) | `frontend/src/components/right-panel/WordDetail.tsx`, new `frontend/src/components/right-panel/StylePalette.tsx`, `frontend/src/components/ui/Chip.tsx` | sonnet | M |
| P2.e | **COMPONENT chip palette.** Same shape as P2.d but for component tags (drop-cap, footnote-ref, page-num, etc.); wires to `useWordMutations.applyComponent`. Both palettes share a `ChipPalette` building block. | 31, 53 (component half) | `frontend/src/components/right-panel/WordDetail.tsx`, new `frontend/src/components/right-panel/ComponentPalette.tsx` | sonnet | M |
| P2.f | **Validate / Skip / Delete footer.** Sticky three-button footer at the bottom of `WordDetail` with keycaps. Wires to validate / skip / delete word mutations. | 41 | `frontend/src/components/right-panel/WordDetail.tsx`, new `frontend/src/components/right-panel/WordFooter.tsx` | sonnet | S |
| P2.g | **Accordion trigger redesign.** Replace bare Radix triggers with the spec'd row: uppercase label · helper text · keycap on the right. Apply across all six WordDetail sections + BlockDetail + LineDetail accordion uses. | 32, 54 | `frontend/src/components/ui/accordion.tsx`, all `*/sections/*Section.tsx`, `frontend/src/components/right-panel/{Block,Line}Detail.tsx` | sonnet | M |

---

## P3 — Word Editor geometry sections (4 slices, P2 dependency)

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P3.a | **BBox Refine / Expand+Refine / Nudge / Crop sub-rows + coordinate readout.** Replace flat button row with the structured sub-rows from the mock: nudge has step input + L/R/T/B button group; coord readout in the section header. | 33, 34 | `frontend/src/components/right-panel/sections/BBoxSection.tsx` | sonnet | M |
| P3.b | **Rebox mini-canvas.** Replace legacy WordRefineNudgeRows with an inline Konva mini-canvas: Snap / Draw / Pan toggle, zoom buttons, Apply rebox button. This is the flagship section — interactive drag handles, react-konva. | 35 | `frontend/src/components/right-panel/sections/ReboxSection.tsx`, new `frontend/src/components/right-panel/sections/ReboxCanvas.tsx` | opus | L |
| P3.c | **Erase Pixels auto-detect canvas + ops list + commit footer.** Auto-detect runs the existing `/api/refine/available` probe; brush / lasso / rect tools render to a Konva overlay; ops list rolls up; commit footer applies. Stub-canvas acceptable for first cut, but the tool-switching UI must be wired. | 36 | `frontend/src/components/right-panel/sections/ErasePixelsSection.tsx`, new `frontend/src/components/right-panel/sections/EraseCanvas.tsx` | opus | L |
| P3.d | **Structure neighbors-strip + merge preview + gap-picker + vertical-split.** Replace current Structure placeholder with neighbor cards, merge-preview row, gap-picker slider, vertical-split affordance. | 37 | `frontend/src/components/right-panel/sections/StructureSection.tsx` | sonnet | M |

---

## P4 — Char editing + Unicode (3 slices, P2 dependency)

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P4.a | **CharRanges per-char glyph editor + overlap markers + style/component kind switcher.** Per-character glyph editor row, overlap visualisation when ranges intersect, STYLE/COMPONENT kind switcher on each range card. | 38 | `frontend/src/components/right-panel/sections/CharRangesSection.tsx` | sonnet | M |
| P4.b | **CharFixer per-char bbox visualisation + drag handles.** Konva-light overlay showing per-character bboxes with draggable handles; reuses ReboxCanvas tooling where possible. | 39 | `frontend/src/components/right-panel/sections/CharFixerSection.tsx`, possibly `frontend/src/components/right-panel/sections/ReboxCanvas.tsx` | opus | M |
| P4.c | **Unicode picker redesign.** Sets-row across the top (Latin / Greek / punctuation / symbols / …), code-point cards in the body, `\emdash`-style slash-command input at the bottom. | 40 | `frontend/src/components/right-panel/UnicodePicker.tsx` | sonnet | M |

---

## P5 — Drawer + canvas + line/block + root (8 slices, independent)

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P5.a | **Worklist row redesign.** 4px color bar on left + mono ID stamp + status pip + confidence % + OCR→GT diff line. | 20 | `frontend/src/components/drawer/Worklist.tsx` | sonnet | M |
| P5.b | **Worklist filter row redesign.** Replace the active-filter selector with status-count chip row + sort dropdown. | 19 | `frontend/src/components/drawer/Worklist.tsx`, `frontend/src/stores/worklist-store.ts` | sonnet | M |
| P5.c | **Hierarchy nodes + filter pills.** Kind chip + mono ID stamp on each node; filter pills above tree + node count. | 21, 22 | `frontend/src/components/drawer/Hierarchy.tsx` | sonnet | M |
| P5.d | **Canvas mode-indicator pill + bulk-actions strip + Fit/100% zoom buttons.** Pill in top-left of canvas showing current mode; bulk-actions strip when 2+ words selected; Fit + 100% zoom buttons. | 24 | `frontend/src/components/PageImageCanvas.tsx`, `frontend/src/components/ImageTabsHeader.tsx` | sonnet | M |
| P5.e | **LineDetail tab redesign.** Zoomed line image at the top + structure box + consolidated GT row + validate-all footer button. | 42, 43 | `frontend/src/components/right-panel/LineDetail.tsx` | sonnet | M |
| P5.f | **Line·Words cards redesign.** Group header + per-word serif preview + OCR/GT stack + per-word checkboxes for bulk selection; bulk action bar at top. | 44, 45 | `frontend/src/components/right-panel/LineDetail.tsx`, possibly new `frontend/src/components/right-panel/LineWordsCard.tsx` | sonnet | M |
| P5.g | **Block layout-type picker + footer.** Structural / Content groups · 19 layout types · shape glyph cards; "Save layout type" footer; model-suggest callout + preview pane; Items tab View sub-toggle; Para layout tab + scope. | 47, 48, 49, 50, 51 | `frontend/src/components/right-panel/BlockDetail.tsx` | sonnet | L |
| P5.h | **Root page redesign.** Project cards with thumbnail + page count + progress bar + source path + action button; search field + filter chips + hero band. | 59, 60 | `frontend/src/pages/RootPage.tsx` | sonnet | M |

### P5 micro-polish bundle

Bundles all remaining low-priority gaps into one cleanup slice — single dispatch:

| # | Slice | Gaps | Files | Model | Effort |
|---|---|---|---|---|---|
| P5.i | **Token cleanup + small bugs.** Logo orange "O" badge (2); drawer tab icons + count badges + collapse chevron (18); BBoxOverlay selection → accent token (25); drag-select rect → accent token (26); breadcrumb terminal chip kind-color fill (55); StatusPip ocr/gt variants (57); remaining 8/16/52/56/58/61 polish. | 2, 8, 16, 18, 25, 26, 52, 55, 56, 57, 58, 61 | mixed — primarily `frontend/src/components/{BBoxOverlay,FilterToggle,ImageTabsHeader,shell/Drawer,shell/Breadcrumb,ui/StatusPip}.tsx` | haiku | M |

---

## Already-DONE band (from 2026-05-15 fix-agent pass)

These were closed by ad-hoc fixes during the post-redesign cleanup pass and
must be referenced in P1/P2 acceptance to guard against regression:

| Gap | What | Reference |
|---|---|---|
| 1 | Header height 40→56px | covered in P1.a/b acceptance |
| 9 | Rail width 40→64px | covered in P1.d/e acceptance |
| 17 | Drawer width 260→320px | covered in P5.a acceptance |
| 23 | ImageTabsHeader token colors | covered in P5.d acceptance |
| 27 | Right panel 320→520px (`--right-w` CSS var) | covered in P2.a acceptance |
| 46 | Block panel slot width via `--right-w` | covered in P5.g acceptance |
| 54 (B1) | Accordion B1 bgSunk + uppercase | extended in P2.g |

## Total effort estimate

- **P1**: 6 slices (S×1 + M×5) → ~1 session day
- **P2**: 7 slices (S×1 + M×6) → ~1.5 session days
- **P3**: 4 slices (M×2 + L×2) → ~2 session days (Konva-heavy)
- **P4**: 3 slices (M×3) → ~1 session day
- **P5**: 9 slices (M×7 + L×1 + bundle) → ~2 session days

Total: **29 slices**, ~7–8 sessions of bot/agent time. Critical path runs
through P2 → P3, ~3 session days.

## Dispatch waves

| Wave | Issues | Concurrency |
|---|---|---|
| W1 | P1.a–f, P2.a–g (parallel after P1.a header structure lands) | up to 4 agents |
| W2 | P3.a–d (after P2.a/g land), P4.a–c (after P2.d/e land) | up to 4 agents |
| W3 | P5.a–i | up to 6 agents (independent files) |

## Acceptance — cut-over gate

The hi-fi gaps plan is **done** when:

- All 61 gaps marked closed in the table above.
- `make ci` green.
- `make e2e` green (driver-contract testids intact).
- CT runs `make dev`, opens a project, and confirms the UI matches the
  design handoff at the screen-density level (no informal eyeballing —
  side-by-side with `docs/Screenshot from 2026-05-15 17-45-55.png`).
- A new screenshot landed at `docs/Screenshot-hifi-gaps-closed.png` for
  the changelog.

After cut-over:

- Legacy `pd-ocr-labeler` README gets a "superseded by
  `pdomain-ocr-labeler-spa`" banner.
- `docs/plan-to-usable.md` smoke-run row + cut-over banner row check off.
- This plan moves to `docs/archive/plans/`.

## References

- Audit: produced by Opus review pass 2026-05-15 (61 gaps inlined into
  the dispatcher prompt for this session — verbatim list preserved here).
- Hi-fi redesign source: `docs/specs/2026-05-15-hifi-redesign-plan.md`
  (Slices 0–27 ✅).
- Spec authority: `docs/architecture/*` for shipped surfaces;
  `specs/16-milestones.md`, `specs/17-decisions.md` for cross-cutting.
- Follow-ons context: `docs/hifi-followons.md` (FO-1..FO-9 ✅) and
  `docs/next-steps-2026-05-15.md`.
- Path-to-usable context: `docs/plan-to-usable.md`.
