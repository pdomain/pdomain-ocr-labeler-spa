# pd-ocr-labeler-spa — Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring pd-ocr-labeler-spa to a fully usable labeling application that faithfully replaces the NiceGUI pd-ocr-labeler.

**Architecture:** FastAPI backend serving a React/Vite/TypeScript SPA; JSON-sidecar persistence; modeled on pd-prep-for-pgdp patterns.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui, pytest, Vitest, Playwright

---

## Status snapshot (2026-05-16)

The repo is at the **cut-over gate**. Milestones M0–M11 minus M11 (blocked on `pd_book_tools.ocr.glyph_annotations`) are shipped; hi-fi redesign Slices 0–27 and the 29 P1–P5 hi-fi-gap slices are shipped; FO-1–FO-9 follow-ons are shipped; M9.5 keyboard audit is shipped (with a browser walk TODO); the 2026-05-16 spec-open-questions and wire-missing-connections plans (11 wiring fixes) shipped within the last 24 hours.

**What is left** is the closing band of work that takes the SPA from "every component compiles and individual flows pass tests" to "CT can open a real scanned-book project and complete a full edit session end-to-end without dropping back to the legacy labeler." The eight milestones below cover that band.

| Plan archive (shipped) | Path |
|---|---|
| Hi-fi redesign (Slices 0–27) | `docs/superpowers/plans/archive/2026-05-15-hifi-redesign-plan.md` |
| Hi-fi gaps P1–P5 (29 slices) | `docs/superpowers/plans/archive/2026-05-15-hifi-gaps-plan.md` |
| Spec open-questions wiring (6 tasks) | `docs/superpowers/plans/archive/2026-05-16-spec-open-questions.md` |
| Wire missing connections (5 tasks) | `docs/superpowers/plans/archive/2026-05-16-wire-missing-connections.md` |

---

## UI style contract (binding for every task in this plan)

Every component built or modified by tasks in this plan MUST follow this contract. New colors, fonts, or hand-rolled affordances are forbidden unless the token list below is expanded first.

1. **Theme & tokens.** Dark default; light via `[data-theme="light"]` override on `<html>`; `prefers-color-scheme: light` fallback when `data-theme` is unset. All colors come from CSS variables defined in `frontend/src/styles/tokens.css`. No raw hex in JSX or Tailwind. Tailwind semantic aliases (`bg-bg-surface`, `text-ink-2`, `border-border-1`, `text-status-exact`, `text-layer-line`, etc.) wired in `frontend/tailwind.config.js` resolve to those variables.
2. **Surface palette.** `bg-page` (root canvas), `bg-surface` (cards), `bg-raised` (hover / active rows), `bg-sunk` (input wells, code blocks). Borders escalate `border-1` (faint dividers) → `border-2` (input borders) → `border-3` (focus / emphasized). Ink escalates `ink-1` (body) → `ink-2` (secondary) → `ink-3` (muted labels) → `ink-4` (placeholder).
3. **Accent + status + layer.** `accent` is the single brand action color (orange in dark, terracotta in light) — used for primary buttons, focus rings, drag-select stroke, active-tab underline. Status: `status-exact` (green), `status-fuzzy` (amber), `status-mismatch` (red), `status-ocr` (blue), `status-gt` (violet). Layer: `layer-block`, `layer-para`, `layer-line`, `layer-word` — read at runtime via `useLayerColors()` for Konva nodes.
4. **Typography.** UI font Inter; mono font JetBrains Mono. Tailwind aliases: `font-ui`, `font-mono`, `font-pgdp` (alias for `font-mono`, stable name for any later real PGDP font swap). Sizes: `text-label` 9.5/1.1, `text-hint` 10/1.2, `text-btn-sm` 11/1.2, `text-body` 12/1.4, `text-heading` 13/1.3. Body default 12px; uppercase section labels at 9.5–10px with `tracking-wide`.
5. **Shell skeleton.** Single Studio Shell (`frontend/src/components/shell/StudioShell.tsx`) — five zones in a CSS grid: `header` (56px) · `rail` (64px) · `drawer` (320px, collapsible via `--drawer-w`) · `canvas` (1fr) · `right` (520px word view, 640px line/block via `--right-w`). Header is rendered at the App level; ProjectPage passes `headerHeight={0}` so the grid row collapses.
6. **Rail.** Vertical 64px column under the header. Three groups stacked top→bottom: `MODE` (V/R/A/E icon-card cells using Lucide `Eye`, `Square`, `Plus`, `Eraser`), `TARGET` (Block / Para / Line / Word as layer-color squares), `LAYERS` (visibility toggles styled as legend swatches). Footer: Bulk + Hotkeys icon buttons. Uppercase section labels above each group. Persist target/mode to localStorage via `frontend/src/stores/rail-store.ts`.
7. **Drawer.** Two tabs: **Worklist** (filter chips, status-count chips, sort dropdown, virtualised row list — each row has 4 px left status bar, mono ID stamp, status pip, confidence %, OCR→GT diff line, bulk-select checkbox) and **Hierarchy** (collapsible tree, layer-color square + mono ID stamp on each node, filter pills above). Tab counts as small chips on each tab trigger. BulkActions bar appears at the bottom when ≥1 row is checked.
8. **Canvas.** Konva Stage + Image only; no inline toolbar. `ImageTabsHeader` above the stage carries: mode-indicator pill (top-left), layer toggles, Selection / Rebox / Add / Erase mode radios, **Fit** and **100 %** zoom buttons. Bulk-action strip slides in above the stage when 2+ words are selected. Drag-rect stroke uses the `accent` token (dashed, 1 px). Bbox layer strokes from `--layer-*` via `useLayerColors`; active target layer at full opacity, others dimmed to `--ink-4` opacity.
9. **Right panel.** Header is a Breadcrumb (`Project › Block N › Para N › Line N › Word N`) + collapse button. Body switches on `selectionStore.level`:
   - `word` → `WordDetail` — identity row (`Line N · Word N` mono + StatusPip + per-word pager), Word image preview (76 px serif glyph in a cream-tinted well), OCR/GT compare row (mono OCR well + GT `<Input>` with copy-OCR-to-GT button + `Ω chars` button that opens UnicodePicker inline), STYLE chip palette (tri-state), COMPONENT chip palette, then a six-section accordion: **Bounding Box** (numeric inputs + Refine / Expand+Refine / Nudge sub-rows + crop), **Rebox** (Konva mini-canvas, `tag="accent"`), **Erase Pixels** (`tag="mismatch"`, brush/lasso/rect over Konva), **Structure** (neighbor strip + merge-preview + gap-picker), **Char Ranges**, **Character Fixer**. Sticky three-button footer: ✓ Validate / Skip / 🗑 Delete with keycap labels.
   - `line` → `LineDetail` — Tabs(Line | Words); Line tab has zoomed line image + structure box + consolidated GT row + Validate-all footer; Words tab is a `LineWordsCard` with per-word checkboxes + bulk-action bar (Validate / Skip selected, wired to `validate-batch` scope=`word`).
   - `block` → `BlockDetail` — Tabs(Layout | Items); Layout tab is a Structural / Content group picker with 19 layout-type shape-glyph cards + model-suggested callout + Accept; Items tab is a density-toggle tree of paras + lines.
10. **Header bar.** 56 px. Left: orange-bullet `OCR Labeler` logo + breadcrumb chip (Projects / project-name) + metrics strip (`N words · N exact · N fuzzy · N ✗ · N/M validated`). Center: inline pager `◀ <input> ▶ /392`, then `⌘K` QuickSearch input wired to `worklistStore.searchQuery`. Right: header action buttons (Reload OCR, Rematch, ✓ Save page, Export ▾) and `UserMenu` (theme toggle + Sign out stub).
11. **Primitives.** All from `frontend/src/components/ui/`: `Button` (primary/secondary/ghost/danger × sm/md/lg, focus-visible ring on `--accent`); `Chip` (static or tri-state with dashed-border `mixed`); `StatusPip` (8 px dot in `--status-*`); `KeyCap` (mono pill in `--bg-sunk` border `--border-2`); `Input` (sunk well, accent focus); `Accordion` (Radix-backed, accent / mismatch left-edge stripe variants); `Tabs` (underline tabs, 2 px `--accent` bar under active); `Tooltip`, `Dialog`, `DropdownMenu` from shadcn.
12. **Interaction.** Hotkeys are registered via `useGlobalHotkeys` + scoped hooks (`useViewportHotkeys`, `useMatchesHotkeys`, `useDialogHotkeys`, `useRailHotkeys`, `useBreadcrumbHotkeys`, `useBlockHotkeys`). Every hotkey is registered in `frontend/src/lib/hotkey-registry.ts` and rendered in the help modal using `KeyCap`. `?` opens the help modal. Toasts go through `frontend/src/lib/toast.ts` (Sonner wrapper) with status-colored left edges; sticky page banners stay in `InlineBanners`.
13. **A11y.** Every interactive element has `data-testid` (driver contract, see `docs/architecture/13-driver-contract.md`), an `aria-label`, and a visible focus ring (`focus-visible:ring-1 ring-accent`). All forms are controlled inputs; validation errors surface as field-level toasts (Pydantic `details` array). No layout shift on focus.
14. **Konva.** `react-konva` + `use-image@^1.1`; Konva nodes carry no `data-testid` (impossible) — sidecar `<div data-testid="...">` is rendered absolutely-positioned with `pointer-events: none` for the driver contract. `useLayerColors()` reads CSS vars via `getComputedStyle(document.documentElement)` and subscribes to `data-theme` changes via `MutationObserver`.

Reference screenshots: `docs/Screenshot from 2026-05-15 17-45-55.png` (shipped state). The full visual contract is encoded in the surviving Phase / Slice tables of `docs/superpowers/plans/archive/2026-05-15-hifi-redesign-plan.md` and the gap list in `docs/superpowers/plans/archive/2026-05-15-hifi-gaps-plan.md` — those archives are the visual law for any future polish.

---

## Plan structure

Each milestone below is **bounded enough for one agent session**. Tasks are TDD: write a failing test, run it to confirm fail, implement, run to confirm pass, commit. File paths are absolute from the repo root `pd-ocr-labeler-spa/`.

Verification gates per milestone:

- `make ci AI=1` must remain green.
- `make e2e AI=1` (Playwright) must remain green for any milestone that touches user-facing surfaces.
- `make openapi-export AI=1` runs whenever a FastAPI request/response model changes.

---

## Milestone CU-1 — Glyph annotations data-model preflight (M11 unblock-or-defer)

**Outcome.** Either land the v2.2 envelope reader and an `IGlyphPredictor` Protocol behind a feature flag (so M11 frontend can ship later without a schema re-bump) OR formally defer M11 to the post-cut-over backlog with an ADR. Q-A7 (`OPEN_QUESTIONS.md`) is closed.

**Spec refs.** `specs/20-glyph-annotations.md` §3, §11; `specs/16-milestones.md` §M11; `OPEN_QUESTIONS.md` Q-A7.

**Files touched.**

- `OPEN_QUESTIONS.md` (archive Q-A7 entry to `docs/archive/QUESTIONS_RESOLVED.md`).
- `specs/17-decisions.md` (append ADR D-044 — provenance granularity decision).
- `src/pd_ocr_labeler_spa/core/persistence/user_page_envelope.py` (add v2.2 schema reader with v2.1 back-compat, no-op writer until M11 frontend lands).
- `src/pd_ocr_labeler_spa/core/glyph/__init__.py` (new package marker).
- `src/pd_ocr_labeler_spa/core/glyph/predictions.py` (new — `IGlyphPredictor` Protocol with `none_` adapter only).
- `tests/unit/test_glyph_envelope_back_compat.py` (new — v2.1 envelopes parse with all `glyph_annotations = None`).
- `tests/unit/test_glyph_envelope_round_trip.py` (new — v2.2 envelope round-trips tri-state preserved).

### Task CU-1.1 — Resolve Q-A7

- [ ] Step 1: Read `OPEN_QUESTIONS.md` Q-A7 and `specs/20-glyph-annotations.md` §3 / §11.
- [ ] Step 2: Append ADR D-044 to `specs/17-decisions.md` adopting **Option (A) — object-level provenance** per the spec author recommendation, citing D-032 (rotation provenance) as precedent and explicitly naming "v2.3 bump deferred until mixed-source granularity is observed in real annotation traffic" as the escape hatch.
- [ ] Step 3: Move the full Q-A7 entry from `OPEN_QUESTIONS.md` to `docs/archive/QUESTIONS_RESOLVED.md` with a `Resolution: D-044` line. In the same commit, `OPEN_QUESTIONS.md` Open list becomes empty (only the archive pointer remains).
- [ ] Step 4: Commit `chore(adr): resolve Q-A7 — D-044 object-level provenance is sufficient for v1`.

### Task CU-1.2 — v2.2 envelope reader + back-compat tests

- [ ] Step 1: Read the existing reader in `src/pd_ocr_labeler_spa/core/persistence/user_page_envelope.py` and the v2.1 fixtures under `tests/fixtures/envelopes/`.
- [ ] Step 2: Write the failing back-compat test in `tests/unit/test_glyph_envelope_back_compat.py`:

```python
"""v2.1 envelopes must parse with every word's glyph_annotations == None."""
from pathlib import Path

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import parse_envelope


def test_v21_envelope_loads_with_glyph_annotations_none() -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "envelopes" / "v21_minimal.json"
    envelope = parse_envelope(fixture.read_text())
    assert envelope.schema_minor == 1
    # Every WordMatch in the page must accept a glyph_annotations attr returning None.
    for line in envelope.payload.page["lines"]:
        for word in line["words"]:
            assert word.get("glyph_annotations") is None
```

- [ ] Step 3: Run `uv run pytest tests/unit/test_glyph_envelope_back_compat.py -v` — confirm FAIL (fixture or parser missing).
- [ ] Step 4: Add the minimal v2.1 fixture at `tests/fixtures/envelopes/v21_minimal.json` (lift from an existing labeled-envelope fixture in the repo — see `tests/fixtures/` for shape).
- [ ] Step 5: Implement v2.2 reader: bump the version pattern in `parse_envelope` to accept both `"2.1"` and `"2.2"`; on `"2.1"` ensure every `WordMatch` dict has an explicit `glyph_annotations: None` injected on parse (so callers can read without `KeyError`). Raise `IncompatibleEnvelopeError` for any `major != "2"`.
- [ ] Step 6: Run the test — confirm PASS.
- [ ] Step 7: Add the round-trip test `tests/unit/test_glyph_envelope_round_trip.py`:

```python
"""v2.2 envelope round-trips with tri-state glyph_annotations preserved."""
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    parse_envelope,
    serialize_envelope,
)


def test_v22_round_trip_preserves_tri_state(v22_envelope_str: str) -> None:
    env = parse_envelope(v22_envelope_str)
    s = serialize_envelope(env)
    env2 = parse_envelope(s)
    for line in env2.payload.page["lines"]:
        for w_in, w_out in zip(line["words"], env.payload.page["lines"][0]["words"]):
            assert w_in.get("glyph_annotations") == w_out.get("glyph_annotations")
```

Add a `v22_envelope_str` fixture in `tests/conftest.py` with one word `glyph_annotations=None`, one `=={"long_s_positions": []}`, one `=={"long_s_positions": [3], "source": "human"}`.

- [ ] Step 8: Run the round-trip test — FAIL (no v2.2 writer).
- [ ] Step 9: Extend `serialize_envelope` to emit `schema_version: "2.2"` and preserve `glyph_annotations` field verbatim per word. Run — PASS.
- [ ] Step 10: `make openapi-export AI=1` if any FastAPI model picked up the new optional field. Commit `feat(envelope): v2.2 schema reader + writer with v2.1 back-compat (M11 preflight)`.

### Task CU-1.3 — IGlyphPredictor protocol + none adapter

- [ ] Step 1: Create `src/pd_ocr_labeler_spa/core/glyph/__init__.py` (empty) and `src/pd_ocr_labeler_spa/core/glyph/predictions.py` containing:

```python
"""IGlyphPredictor — Protocol for glyph-annotation predictions.

Mirrors IOCREngine's seam pattern. v1 ships only `none_`; pd-ocr-trainer
delivers the local classifier when its glyph-feature work lands.

Predictions are NOT persisted — they are recomputed at page-fetch time.
The frontend renders them as greyed-out chips with accept/reject.
"""

from __future__ import annotations

from typing import Protocol

from pd_ocr_labeler_spa.core.models import WordMatch


class IGlyphPredictor(Protocol):
    """Predict glyph annotations for a list of words."""

    def predict(self, words: list[WordMatch]) -> list[dict | None]:
        """Return one prediction dict (or None) per input word, same order."""
        ...


class NoneGlyphPredictor:
    """Default adapter — always returns None for every word."""

    def predict(self, words: list[WordMatch]) -> list[dict | None]:
        return [None] * len(words)
```

- [ ] Step 2: Write a unit test `tests/unit/test_glyph_predictor_none.py`:

```python
from pd_ocr_labeler_spa.core.glyph.predictions import NoneGlyphPredictor


def test_none_predictor_returns_none_per_word() -> None:
    pred = NoneGlyphPredictor()
    out = pred.predict([object(), object(), object()])  # type: ignore[list-item]
    assert out == [None, None, None]
```

- [ ] Step 3: Run — PASS. Commit `feat(glyph): IGlyphPredictor Protocol + NoneGlyphPredictor adapter`.

**Acceptance.** `make ci AI=1` green; `OPEN_QUESTIONS.md` Open section is empty; v2.1 fixtures still parse; v2.2 round-trip preserves tri-state per word.

---

## Milestone CU-2 — Smoke run + bug triage gate (first contact with real data)

**Outcome.** A fresh checkout, against a real fixture project on disk, completes one full user journey end-to-end. Every bug found is filed; nothing else in this plan starts until the smoke run is green or every bug uncovered has a triage outcome.

**Spec refs.** `docs/plan-to-usable.md` (Smoke run row); `docs/full-exercise-workflow.md` Phases 1–6.

**Files touched.**

- `tests/e2e/exercise_real_project.py` — extend to cover the eleven sub-phases listed below if a sub-phase is missing.
- `docs/BUGS_FOUND.md` — new entries per finding.
- No production code edits unless a bug is single-line and risk-free (e.g. a typo in a `data-testid`); larger fixes get their own milestone.

### Task CU-2.1 — Refresh the smoke harness

- [ ] Step 1: Read `tests/e2e/exercise_real_project.py` and `tests/e2e/test_ui_coverage.py`. List every Phase / sub-phase number from `docs/full-exercise-workflow.md` covered by a test function (`grep -nE "P[0-9]+\.[0-9]+|Phase " tests/e2e/*.py`).
- [ ] Step 2: For every sub-phase 1.1 through 6.10 not covered, append a new test function (or a `pytest.mark.skip` placeholder with the sub-phase number as the reason) so the matrix is complete on paper. Commit `test(e2e): inventory full-exercise-workflow into Playwright matrix`.

### Task CU-2.2 — Smoke run by an agent on a real fixture

- [ ] Step 1: Provision a real fixture project under `~/ocr-fixtures/<project>/` containing ≥3 `.png` page images and a `pages.json` ground-truth file. Use the existing `tests/fixtures/sample_project/` if no real fixture is on disk.
- [ ] Step 2: Run `make run` (production-style build) in a background shell. Confirm `device: …` banner prints and `http://127.0.0.1:8080` responds 200 to `/healthz`.
- [ ] Step 3: Walk the eleven phases in order, capturing observed-vs-expected discrepancies. Each discrepancy gets one new entry in `docs/BUGS_FOUND.md` using the existing schema (Status / Severity / Where / Issue / Why-it-matters / Suggested-fix).
- [ ] Step 4: If zero bugs are found, append a `## 2026-05-16 — smoke run` line to `docs/plan-to-usable.md` marking the "Smoke run" checkbox closed. Commit `docs(plan-to-usable): close smoke-run row — agent walked 10 pages cleanly`.
- [ ] Step 5: If bugs are found, commit `docs(bugs): file <N> smoke-run findings <comma-separated ids>` and stop. Subsequent milestones cannot start until CT has triaged the new bugs.

**Acceptance.** Either `docs/plan-to-usable.md` Smoke-run row is checked, or `docs/BUGS_FOUND.md` has new entries with severities assigned.

---

## Milestone CU-3 — M9.5 keyboard-only audit close-out

**Outcome.** The browser-walk TODO items in `docs/M9.5-keyboard-audit.md` are confirmed against the live UI; the document's Section 5 "Outstanding" list collapses to zero items.

**Spec refs.** `specs/16-milestones.md` §M9.5; `docs/architecture/12-hotkeys-a11y.md`; D-022 in `specs/17-decisions.md`.

**Files touched.**

- `docs/M9.5-keyboard-audit.md` — flip every "TODO: verify in browser" line to "Verified: …" or "Bug filed: #N".
- `frontend/src/lib/hotkeyMap.ts` and `frontend/src/lib/hotkey-registry.ts` — add any missing entries.
- `frontend/src/components/HotkeyHelpModal.tsx` — group display fixes if any.
- `tests/e2e/test_keyboard_only.py` — extend with regressions for any newly-found gaps.
- `docs/BUGS_FOUND.md` — file bugs for gaps that aren't trivially fixable.

### Task CU-3.1 — Walk the audit document

- [ ] Step 1: Read `docs/M9.5-keyboard-audit.md` end-to-end. For each "TODO: verify in browser" line, attempt to reproduce in a `make dev` session.
- [ ] Step 2: For each verified line, edit the doc to replace `TODO: verify in browser` with `Verified 2026-05-16 — <observation>`.
- [ ] Step 3: For each line that fails (hotkey doesn't fire, focus doesn't move, modal traps focus incorrectly), either:
  - (small fix) edit the offending file inline, add a regression test under `tests/e2e/test_keyboard_only.py`, commit; OR
  - (deeper fix) file the bug in `docs/BUGS_FOUND.md`, link the TODO line to the bug number, and leave the TODO marked `Blocked on bug #N`.

### Task CU-3.2 — Hotkey help modal completeness check

- [ ] Step 1: Render the help modal in a Vitest test (`frontend/src/components/HotkeyHelpModal.test.tsx`) and assert that for every hotkey registered in `frontend/src/lib/hotkey-registry.ts`, there is a corresponding `KeyCap` in the modal output. Run — should already pass per FO-6, but lock the invariant.
- [ ] Step 2: Commit `test(hotkeys): lock invariant — every registered hotkey appears in the help modal`.

**Acceptance.** `docs/M9.5-keyboard-audit.md` Section 5 has zero open TODOs; `make ci AI=1` green.

---

## Milestone CU-4 — Block-level data flow (FO-7 close)

**Outcome.** `PagePayload.line_matches[].block_index` is populated by the backend; the Hierarchy tab and Breadcrumb walk blocks correctly; selecting a block in the Hierarchy shows `BlockDetail` and clicking the block chip in the breadcrumb walks to a sibling block.

**Spec refs.** `docs/architecture/23-page-payload-backend.md` §3; `docs/architecture/24-shell-layout.md` §5 (Breadcrumb); `docs/architecture/25-drawer-worklist.md` §4 (Hierarchy); `docs/hifi-followons.md` FO-7.

**Note.** FO-7 memory says block_index was already added; verify against current backend before claiming this is a no-op. If LineMatch.block_index already exists in `core/page_to_line_matches.py`, this milestone collapses to "verify + add tests."

**Files touched.**

- `src/pd_ocr_labeler_spa/core/page_to_line_matches.py` — confirm `block_index` is lifted from `Page.blocks[i].lines[j]` and set per LineMatch.
- `src/pd_ocr_labeler_spa/core/models.py` — confirm `LineMatch.block_index: int | None`.
- `frontend/src/api/types.ts` — regenerated.
- `frontend/src/lib/selection-walk.ts` — verify `nextSibling` walks blocks when present.
- `frontend/src/lib/selection-walk.test.ts` — add block-walk cases.
- `frontend/src/components/drawer/Hierarchy.tsx` — verify block nodes are clickable; add `data-testid="hierarchy-node-block-{idx}"`.
- `frontend/src/components/shell/Breadcrumb.tsx` — verify block chip click selects sibling block.

### Task CU-4.1 — Backend block_index round-trip

- [ ] Step 1: Add a failing test in `tests/unit/test_page_to_line_matches.py`:

```python
def test_line_match_carries_block_index() -> None:
    page = make_fixture_page_with_2_blocks()  # block 0: 1 paragraph; block 1: 2 paragraphs
    record, line_matches = page_to_line_matches(page)
    assert [lm.block_index for lm in line_matches] == [0, 1, 1]
```

- [ ] Step 2: Run — if it passes, skip to CU-4.2. If it fails, implement: in `page_to_line_matches`, iterate `page.blocks` and tag each `LineMatch` with its block index. Update `core/models.py` `LineMatch` to declare the field. Re-run — PASS.
- [ ] Step 3: `make openapi-export AI=1` so `frontend/src/api/types.ts` picks up the field. Commit `feat(page-payload): lift block_index onto LineMatch (FO-7)`.

### Task CU-4.2 — selection-walk block walk

- [ ] Step 1: Read `frontend/src/lib/selection-walk.ts` to confirm whether `nextSibling` at `level === "block"` walks blocks or returns the input unchanged.
- [ ] Step 2: If unchanged, write a failing test in `frontend/src/lib/selection-walk.test.ts` that on a page with 3 blocks, calling `nextSibling({ blockId: "1" }, page, +1)` yields `{ blockId: "2" }`. Run — FAIL.
- [ ] Step 3: Implement: walk the unique `block_index` values across `page.line_matches`. Re-run — PASS. Commit `feat(selection): walk blocks via LineMatch.block_index (FO-7)`.

### Task CU-4.3 — Hierarchy + Breadcrumb block UI

- [ ] Step 1: Add a Vitest test `frontend/src/components/drawer/Hierarchy.test.tsx` asserting that for a 2-block page, clicking `hierarchy-node-block-0` calls `selectBlock(0)` and that `selectionStore.getState().level === "block"`.
- [ ] Step 2: Run — if it passes (Hierarchy already renders block nodes), skip to step 4. If it fails because there is no block node, extend `Hierarchy.tsx` to render one block node per unique `block_index`, each with a `layer-block` color square + mono ID + count of contained paragraphs.
- [ ] Step 3: Re-run — PASS.
- [ ] Step 4: Add a Vitest test in `frontend/src/components/shell/Breadcrumb.test.tsx` asserting that the block chip is rendered when `selectionStore.level === "block"` and that clicking it walks sibling blocks. Run; implement if missing; re-run.
- [ ] Step 5: Commit `feat(hierarchy,breadcrumb): block-level navigation (FO-7)`.

**Acceptance.** `make ci AI=1` green; block selection round-trips Hierarchy ↔ Breadcrumb ↔ RightPanel.

---

## Milestone CU-5 — Block layout-type save round-trip

**Outcome.** `BlockDetail`'s Layout tab persists the chosen layout type to the backend; reloading the page (or restarting the server) shows the same layout type. The "Apply at block scope" toggle propagates to every paragraph inside the block.

**Spec refs.** `docs/architecture/23-page-payload-backend.md` §6 (paragraph PATCH); `docs/hifi-followons.md` FO-1.

**Files touched.**

- `src/pd_ocr_labeler_spa/api/lines_paragraphs.py` — confirm `PATCH .../paragraphs/{pi}` accepts `layout_type`. Memory says it's wired (FO-1 shipped); confirm in code.
- `tests/integration/test_block_layout_save.py` (new) — round-trip via TestClient.
- `frontend/src/components/right-panel/BlockDetail.tsx` — confirm `onLayoutSave` calls the generated mutation; if it still labels itself a stub, wire it.
- `frontend/src/components/right-panel/BlockDetail.test.tsx` — add round-trip test using MSW.

### Task CU-5.1 — Backend round-trip integration test

- [ ] Step 1: Write `tests/integration/test_block_layout_save.py`:

```python
def test_paragraph_layout_type_round_trip(seeded_client, project_id, page_idx):
    """PATCH paragraphs/0 with layout_type='heading'; GET page reflects it."""
    resp = seeded_client.patch(
        f"/api/projects/{project_id}/pages/{page_idx}/paragraphs/0",
        json={"layout_type": "heading"},
    )
    assert resp.status_code == 200
    page = seeded_client.get(
        f"/api/projects/{project_id}/pages/{page_idx}"
    ).json()
    para = page["paragraphs"][0]
    assert para["layout_type"] == "heading"
```

- [ ] Step 2: Run — if PASS, confirm the endpoint is fully wired and continue to step 4. If FAIL, fix by adding `layout_type` to the request model and threading it through the mutation handler (mirror the pattern of `set_line_gt` from the recently-shipped wiring plan).
- [ ] Step 3: `make openapi-export AI=1`. Commit `feat(paragraphs): PATCH layout_type round-trip (FO-1)`.

### Task CU-5.2 — Frontend round-trip via MSW

- [ ] Step 1: Open `frontend/src/components/right-panel/BlockDetail.test.tsx`. Add a test that mocks `PATCH /api/projects/p1/pages/0/paragraphs/0` via MSW, clicks the `heading` layout-type card, clicks `block-detail-save`, and asserts the MSW handler captured `{ layout_type: "heading" }`.
- [ ] Step 2: Run — if FAIL because the component still labels itself as stub, edit `BlockDetail.tsx`: in the `onLayoutSave` handler, call `useParagraphMutations(projectId, pageIndex).updateLayout.mutate({ paragraphIndex, layout_type })`. The mutation hook lives at `frontend/src/hooks/useParagraphMutations.ts`; create it if absent following the `useLineMutations.ts` pattern.
- [ ] Step 3: Run — PASS.
- [ ] Step 4: Block-scope: when the scope toggle is set to "block", iterate every `paragraph_index` in the current block and fire the mutation per paragraph. Add a second test asserting two MSW calls when the block has two paragraphs. Re-run.
- [ ] Step 5: Commit `feat(block-detail): wire layout-type save round-trip + block-scope apply (FO-1)`.

**Acceptance.** Reloading a page preserves the layout type just saved; `make ci AI=1` green.

---

## Milestone CU-6 — Erase-pixels backend wire + Char-fixer persistence

**Outcome.** The Erase Pixels section's "Apply" button calls a real backend endpoint that erases pixels in the underlying image (or the canonical "marked for erasure" sidecar) and re-renders the canvas; the Char Fixer section's per-char bbox + GT-per-char edits persist round-trip.

**Spec refs.** `docs/architecture/27-right-panel-sections.md` §3 (ErasePixels), §5 (CharFixer); `docs/hifi-followons.md` FO-9.

**Files touched.**

- `src/pd_ocr_labeler_spa/api/words.py` — confirm `POST .../erase-pixels` endpoint exists and acts (memory says it's already there); add `GET /api/refine/available` capability probe if missing.
- `src/pd_ocr_labeler_spa/api/refine.py` — `/available` capability probe.
- `frontend/src/hooks/useRefineAvailable.ts` — confirm it queries the right endpoint; if it queries a stub, point it at the real one.
- `frontend/src/components/right-panel/sections/ErasePixelsSection.tsx` — confirm `Apply` is enabled when `useRefineAvailable() === true`; add a Vitest test pinning the enable/disable invariant.
- `frontend/src/components/right-panel/sections/CharFixerSection.tsx` — confirm POST round-trip via memory's `char-bboxes` endpoint; add a round-trip test.

### Task CU-6.1 — Erase-pixels capability probe and round-trip

- [ ] Step 1: Read `src/pd_ocr_labeler_spa/api/refine.py`. If `GET /api/refine/available` is missing, add it returning `{ "erase_pixels": True, "refine_bboxes": True }` (or whatever the predictor cache resolves).
- [ ] Step 2: Write `tests/integration/test_refine_available.py`:

```python
def test_refine_available_returns_capability_flags(client):
    resp = client.get("/api/refine/available")
    assert resp.status_code == 200
    body = resp.json()
    assert "erase_pixels" in body
    assert "refine_bboxes" in body
```

- [ ] Step 3: Run — PASS (or implement first). Commit `feat(refine): /available capability probe`.
- [ ] Step 4: Add a Vitest test in `frontend/src/components/right-panel/sections/ErasePixelsSection.test.tsx` asserting:
  - When MSW returns `{ erase_pixels: false }` from `/api/refine/available`, the Apply button is disabled with a tooltip "Backend not wired".
  - When MSW returns `{ erase_pixels: true }`, the Apply button is enabled and clicking it posts to `POST /api/projects/p1/pages/0/words/.../erase-pixels` with the marked-pixel polygon payload.
- [ ] Step 5: Run — if FAIL, wire `useRefineAvailable` to `/api/refine/available` and gate the Apply button. Commit `feat(erase-pixels): gate Apply on /api/refine/available (FO-9 close)`.

### Task CU-6.2 — Char-fixer per-char persistence

- [ ] Step 1: Read `frontend/src/components/right-panel/sections/CharFixerSection.tsx` and `src/pd_ocr_labeler_spa/api/words.py` — locate `char-bboxes` endpoint. Memory says the endpoint exists.
- [ ] Step 2: Write a Vitest round-trip in `frontend/src/components/right-panel/sections/CharFixerSection.test.tsx`: MSW captures `POST .../words/{li}/{wi}/char-bboxes` and asserts the body has the expected `{ char_bboxes: [{x,y,w,h}, …] }` shape after a user drag-resizes a per-char handle and clicks Apply.
- [ ] Step 3: Run — if FAIL, wire the mutation; re-run.
- [ ] Step 4: Add a backend test in `tests/integration/test_char_bboxes_round_trip.py`: POST char-bboxes → GET page → assert `word_matches[…].char_bboxes` equals the posted list.
- [ ] Step 5: Commit `feat(char-fixer): per-char bbox persistence round-trip`.

**Acceptance.** `make ci AI=1` green; user can mark erase regions and apply; per-char bboxes persist.

---

## Milestone CU-7 — ImageTabs sub-tabs design decision (#295)

**Outcome.** The legacy labeler's ImageTabs (Matches / Ground Truth / OCR sub-tabs above the canvas) either land in the SPA or the decision to drop them is formalized via an ADR. `docs/plan-to-usable.md` polish row closes.

**Spec refs.** `docs/architecture/04-image-viewport.md` §3 (Image-tabs header); `docs/architecture/13-driver-contract.md` §image-tabs; GitHub issue #295.

**Files touched.**

- `specs/17-decisions.md` — ADR D-045.
- `frontend/src/components/ImageTabsHeader.tsx` — sub-tabs row OR not, per ADR.
- `docs/architecture/13-driver-contract.md` — updated testid list if ImageTabs are dropped.

### Task CU-7.1 — File ADR D-045

- [ ] Step 1: Read the legacy ImageTabs implementation at `../pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py:280-285` (cited in `specs/16-milestones.md`).
- [ ] Step 2: Compare to the shipped `ImageTabsHeader.tsx`. Document the gap (the SPA has layer toggles + mode radio + Fit/100% buttons, but no Matches / Ground Truth / OCR text overlay sub-tabs).
- [ ] Step 3: Append ADR D-045 to `specs/17-decisions.md`. Recommendation: **drop the sub-tabs**; the Drawer Worklist + RightPanel + Plaintext sub-mode in LineDetail already cover the three views; restoring the sub-tabs duplicates UI without new affordances. Cross-reference: `docs/architecture/04-image-viewport.md` §3.
- [ ] Step 4: If ADR adopts the drop, edit `docs/architecture/13-driver-contract.md` to remove the `text-tab-matches` / `text-tab-gt` / `text-tab-ocr` testids and `docs/architecture/04-image-viewport.md` §3 accordingly. Otherwise, hand off to CU-7.2.
- [ ] Step 5: Commit `chore(adr): D-045 — ImageTabs sub-tabs dropped in favor of Drawer + RightPanel surfaces (#295 close)`.

### Task CU-7.2 — Optional: restore ImageTabs sub-tabs (only if ADR adopts restore)

- [ ] Step 1: Add a `Tabs` row above the canvas in `ImageTabsHeader.tsx` with three triggers: `text-tab-matches`, `text-tab-gt`, `text-tab-ocr`. Default to `matches`.
- [ ] Step 2: For `matches`, overlay nothing extra; for `gt` overlay GT text positioned over each word's bbox; for `ocr` overlay OCR text similarly.
- [ ] Step 3: Add Vitest tests + an E2E test under `tests/e2e/test_image_tabs.py` covering all three modes.
- [ ] Step 4: Commit `feat(image-tabs): restore Matches/Ground Truth/OCR sub-tabs (#295)`.

**Acceptance.** GitHub #295 closed; `docs/plan-to-usable.md` polish row checked.

---

## Milestone CU-8 — Cut-over polish + legacy-superseded banner

**Outcome.** The legacy `pd-ocr-labeler` README carries a "superseded by `pd-ocr-labeler-spa`" banner; `docs/plan-to-usable.md` "Legacy README" row closes; the SPA's README "Status" block updates to reflect post-cut-over reality; a new screenshot lands at `docs/Screenshot-hifi-gaps-closed.png`.

**Spec refs.** `docs/plan-to-usable.md` cut-over checklist; `docs/superpowers/plans/archive/2026-05-15-hifi-gaps-plan.md` Acceptance section.

**Files touched.**

- `../pd-ocr-labeler/README.md` (route to the `pd-ocr-labeler` agent — this repo's agent cannot edit it).
- `pd-ocr-labeler-spa/README.md` Status block.
- `docs/plan-to-usable.md` — flip both remaining checkboxes.
- `docs/Screenshot-hifi-gaps-closed.png` (new — take from `make dev` against a real project).

### Task CU-8.1 — Take the cut-over screenshot

- [ ] Step 1: Run `make dev`. Load a fixture project. Open the page that exercises every shell zone (header, rail, drawer with worklist + bulk actions visible, canvas with overlays, right panel showing WordDetail).
- [ ] Step 2: Capture a screenshot at 1920×1080 and save to `docs/Screenshot-hifi-gaps-closed.png`.
- [ ] Step 3: Side-by-side compare to `docs/Screenshot from 2026-05-15 17-45-55.png` and the original design handoff in `ocr labeler.zip`. If any element diverges visibly, file a bug in `docs/BUGS_FOUND.md` — do not retouch the design without a paper trail.
- [ ] Step 4: Commit `docs(screenshot): cut-over reference 2026-05-16`.

### Task CU-8.2 — Update SPA README Status

- [ ] Step 1: Edit `README.md` Status block to: `**Status (2026-05-16):** Cut-over complete. Hi-fi P1–P5 shipped; smoke run green; legacy pd-ocr-labeler superseded.` Add a single paragraph linking `docs/plan-to-usable.md`.
- [ ] Step 2: Commit `docs(readme): cut-over status update`.

### Task CU-8.3 — Route legacy README update

- [ ] Step 1: This task cannot be completed in-tree. Hand off to the `pd-ocr-labeler` agent with prompt: "Add a top-of-README banner to `/workspaces/ocr-container/pd-ocr-labeler/README.md` reading `> **Superseded by [`pd-ocr-labeler-spa`](../pd-ocr-labeler-spa/). This NiceGUI labeler is no longer under active development as of 2026-05-16.**`. Commit message: `docs(readme): mark legacy NiceGUI labeler as superseded`."
- [ ] Step 2: Once the sibling agent confirms the commit, flip the corresponding row in `docs/plan-to-usable.md` to checked. Commit `docs(plan-to-usable): close legacy-superseded row`.

**Acceptance.** Both `docs/plan-to-usable.md` checkboxes are checked; legacy README has the banner; SPA README Status is current.

---

## Cross-cutting invariants for every milestone

1. **Spec-first.** If a task uncovers a divergence between the spec set (`docs/architecture/*` + `specs/16,17,20`) and reality, change the spec first, then the code. Do not silently re-shape an API.
2. **Driver contract.** No `data-testid` is renamed or removed except via an explicit ADR. Adding new testids is fine. The driver-contract conformance E2E (`tests/e2e/test_driver_contract.py`) must stay green.
3. **OpenAPI drift.** Every backend Pydantic model change is followed by `make openapi-export AI=1` and a commit that includes the regenerated `frontend/src/api/types.ts`.
4. **Archive on close.** When a question is resolved, a bug is closed, or a plan completes, cut its entry from `OPEN_QUESTIONS.md` / `docs/BUGS_FOUND.md` / `docs/plans/` into `docs/archive/QUESTIONS_RESOLVED.md` / `docs/archive/BUGS_RESOLVED.md` / `docs/superpowers/plans/archive/` in the **same commit** that lands the resolution.
5. **Token discipline.** No new color hex values, font sizes, or spacing constants in components. Tokens live in `frontend/src/styles/tokens.css` (variables) + `frontend/tailwind.config.js` (aliases). A token addition is its own commit with a test asserting the variable resolves.
6. **TDD.** Every task in every milestone above lists "Step 1: write failing test". Skipping this step is a process violation; the commit log must show the test commit before the implementation commit (or the test added in the same commit, but visible in the diff before the implementation).

---

## Out of scope for this plan

These items are deferred to follow-up plans and explicitly **not** addressed here:

- **Postgres / managed-storage / multi-user adapters** (D-042).
- **Cloud-mode wheel** (modal / shared_container OCR — D-018).
- **pd-index PEP 503 self-hosted wheel publishing** (separate workstream).
- **M11 glyph annotations frontend** beyond the v2.2 envelope preflight in CU-1 — blocked on `pd_book_tools.ocr.glyph_annotations` upstream + a `pd-ocr-trainer` glyph-feature classifier.
- **New features not listed in the spec set.** Any addition needs a spec edit first (CU-7's ADR-D-045 pattern is the template).

---

## Self-review checklist (for the plan author, before merging)

- [x] Every shipped milestone (M0–M10, M9.1, M9.2, M9.5, hi-fi P1–P5, FO-1–FO-9, two 2026-05-16 plans) is acknowledged in the Status snapshot and not duplicated as a task.
- [x] Every remaining item in `docs/plan-to-usable.md` (smoke run, legacy README banner) maps to a task.
- [x] M11 (glyph annotations) is split into a preflight (CU-1) plus an explicit "frontend deferred" note.
- [x] Every `docs/architecture/*` spec is covered by at least one milestone or explicitly noted as "shipped, no further work":
  - 00 overview — context, no task.
  - 01 data-models — CU-1 v2.2 envelope.
  - 02 backend, 03 frontend — CU-2 smoke validation.
  - 04 image-viewport — CU-7 ImageTabs ADR.
  - 05 word-matches — shipped (hifi P2, P5.f).
  - 06 toolbar-actions — shipped (legacy stubs preserved; right-panel is canonical now).
  - 07 word-edit-dialog — shipped (demoted, right-panel sections are canonical).
  - 08 page-actions — shipped.
  - 09 persistence — CU-1 envelope.
  - 10 export — shipped.
  - 11 notifications — shipped.
  - 12 hotkeys-a11y — CU-3 audit close-out.
  - 13 driver-contract — invariant in every milestone.
  - 14 testing — CU-2 harness refresh.
  - 15 deployment-dev — no change.
  - 18 text-normalization — shipped (M10).
  - 19 auto-rotation — shipped (M9.1, M9.2).
  - 21 konva-renderer — shipped.
  - 22 page-surface-wireup — shipped (#314).
  - 23 page-payload-backend — CU-4 (block_index), CU-5 (paragraph layout_type round-trip), CU-6 (refine /available).
  - 24 shell-layout — CU-4 (Breadcrumb block walk).
  - 25 drawer-worklist — CU-4 (Hierarchy block nodes).
  - 26 right-panel-detail — CU-5 (BlockDetail save).
  - 27 right-panel-sections — CU-6 (Erase + CharFixer).
  - 28 palettes-pickers — shipped.
- [x] No placeholders (TBD, TODO, "similar to Task N", "add appropriate error handling") in task bodies. Every code snippet is concrete; every file path is absolute.
- [x] Type names match across tasks (`IGlyphPredictor`, `NoneGlyphPredictor`, `SetLineGtRequest`, `useParagraphMutations.updateLayout`, etc.).
- [x] Every task includes commit-message guidance (Conventional Commits, present tense imperative).
- [x] Out-of-scope list explicitly names every deferred surface.

**Task count: 19 tasks across 8 milestones.** Estimated scope: 4–6 agent sessions (CU-2 smoke run is the long pole — it may surface bugs that fan out into additional sessions before CU-3 can start).
