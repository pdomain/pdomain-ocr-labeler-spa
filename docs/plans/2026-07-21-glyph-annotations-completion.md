---
last_verified: 2026-07-21
created: 2026-07-21
owner: maintainers
kind: plan
status: draft
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
spec: specs/20-glyph-annotations.md
milestone: M11
---

# M11 Glyph Annotations — Residual Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish residual M11 work so glyph annotations are a real user path:
payload round-trip, durable session/store persistence, WordDetail Typography
panel wired to API mutations, chip click → panel, bulk apply invalidation, and
behavior e2e. Leave trainer classifier production and canvas prediction-overlay
polish as optional follow-ups.

**Architecture:** Keep the existing sidecar pattern
(`PageState.glyph_annotations_map` / `glyph_predictions_map`) and the pure
recipe engine in `core/glyph/`. Close the critical read path by injecting those
maps in `page_to_line_matches` / `_page_payload` the same way `char_bboxes_map`
already works. Mount `GlyphAnnotationPanel` in `WordDetail` (not the retired
`WordEditDialog`). Add TanStack Query mutations next to other word mutations.
Persist glyph maps on the event-store path so save/reload keeps tri-state.

**Tech Stack:** FastAPI + pytest; React 19 + Vite + TS + TanStack Query +
Vitest; Playwright e2e. Spec authority: [`specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md).
Driver testids: [`docs/architecture/13-driver-contract.md`](../architecture/13-driver-contract.md) §2.15.

**Out of scope for this plan:**

- `pd-ocr-trainer` classifier weights / non-`none` predictor (adapter seam only).
- Project-wide bulk mark + SSE.
- Canvas predictions-overlay polish (§5.6) unless Slice F capacity remains.
- Restoring standalone `WordEditDialog` (superseded by right-panel `WordDetail`
  per `docs/context/intent-map.md`).

---

## Completeness assessment (2026-07-21)

| Layer | % complete | Summary |
|---|---:|---|
| Backend | **~55%** | Models, routes, bulk recipes, config flag, save warning exist. Payload injection of sidecar maps is missing; durable store write of maps is missing; endpoint tests are shape-only. |
| Frontend | **~40%** | Components + unit tests + bulk dialog mount + WordCell badges/chips + metrics exist. Panel not mounted; no mutation hooks; chip clicks are placeholders; bulk apply does not invalidate page query. |
| E2E / driver | **~20%** | Static bulk button + dialog testids covered. No panel flow e2e, no bulk apply behavior e2e, no persist/reload e2e. |
| **Overall usable surface** | **~35%** | Scaffold is substantial; end-to-end human review path is not shippable yet. |

### What is already shipped

| Area | Evidence |
|---|---|
| Wire models | `src/pdomain_ocr_labeler_spa/core/models.py` — `GlyphAnnotationsModel`, `LigatureMarkModel`, `WordMatch.glyph_*` |
| API routes | `api/words.py` POST `.../glyph-annotations`, `.../accept-prediction`; `api/pages.py` POST `.../glyph-bulk-mark` |
| Bulk recipes | `core/glyph/bulk_mark.py` + `tests/unit/test_glyph_bulk_mark.py` |
| Predictor seam | `core/glyph/predictions.py` `IGlyphPredictor` + `NoneGlyphPredictor` |
| GT ligature reject | `UpdateWordGroundTruthRequest` validator in `api/words.py` |
| Save warning | `AppConfig.glyph_review_required` + `save_page` `glyph_review_incomplete` warnings; FE toasts in `PageActionsCompact` / `ProjectPage` |
| UI components | `frontend/src/components/glyph/{GlyphAnnotationPanel,GlyphChip,BulkGlyphMarkDialog}.tsx` + unit tests |
| WordCell display | Badge colors + chip row from payload fields (`WordCell.tsx`) |
| Bulk entry | `bulk-glyph-mark-button` + dialog mount in `PageActionsCompact.tsx` |
| Metrics | `ProjectPage` computes `glyphs_reviewed`; `WorkspaceMetrics` renders it |
| Driver catalogue | `docs/architecture/13-driver-contract.md` §2.15; e2e testid presence for bulk UI |
| OpenAPI TS types | `frontend/src/api/types.ts` includes glyph routes/schemas |

### Residual gaps (authoritative list)

1. **Critical backend read path:** `glyph_annotations_map` is written by routes
   but never passed into `page_to_line_matches` / applied on `WordMatch`. POST
   success responses and GETs will not surface set annotations.
2. **Critical frontend mount:** `GlyphAnnotationPanel` is not imported by any
   production parent (`WordDetail` has no Typography section; `WordEditDialog`
   does not exist in `frontend/`).
3. **No FE mutation hooks** for set annotations / accept prediction.
4. **Chip clicks are stubs** (`/* future: open panel */` in `WordCell.tsx`).
5. **Bulk apply closes dialog without page query invalidation** → chips/badges
   stale until manual refresh.
6. **Durable persistence incomplete:** event-store save does not serialize
   glyph sidecars; reload loses reviewed state. Legacy v2.2 envelope writer
   path is retired (M5b); need store/extension strategy.
7. **Predictions never attached:** `IGlyphPredictor` not called in payload
   build; `glyph_predictions_map` unused.
8. **Missing tests:** no integration route tests; no
   `test_glyph_annotations_envelope` / back-compat; no
   `test_gt_rejects_ligature_codepoints`; no `test_glyph_panel.py` /
   `test_bulk_glyph_mark.py` behavior e2e.
9. **Small UI/spec mismatches:** ligature kind set incomplete vs spec §3
   (`LONG_ST`, `OE`, `AE`); `predictions-overlay-toggle` absent from driver
   catalogue implementation.
10. **Docs drift:** `AGENTS.md`, `README.md`, `docs/context/current-state.md`,
    and behavior adversarial notes still say glyph FE “not shipped” without
    distinguishing scaffold vs wiring.

### Issue map (#267–#270)

Historical SPA issues (from component headers / milestones; tracker may live
in `ConcaveTrillion/ocr-container-meta` or archived SPA issues):

| Issue theme | Intended surface | Residual |
|---|---|---|
| Data model / envelope | Models + payload + persist | Model done; payload inject + durable store remaining |
| Backend endpoints (#268) | Routes + recipes | Routes exist; need integration tests + map inject |
| Panel / chips (#269) | Panel + WordCell + dialog host | Components exist; mount + hooks remaining |
| Bulk / driver / metrics (#270) | Bulk dialog, testids, glyphs reviewed, save warn | Mostly scaffolded; apply invalidation + e2e behavior remaining |

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `src/.../core/page_to_line_matches.py` | Modify | Accept `glyph_annotations_map` (+ optional predictions map); stamp `WordMatch.glyph_*` |
| `src/.../api/pages.py` | Modify | Pass maps into `page_to_line_matches`; optional predictor attach; bulk/save persistence |
| `src/.../api/words.py` | Modify | Persist glyph mutations on event-store path; ensure refresh returns stamped words |
| `src/.../core/project_state.py` | Maybe | Document / extend sidecar persistence helpers if needed |
| `src/.../core/labeler_extension.py` or store content path | Modify | Durable glyph map persistence across reload (chosen strategy in Task 1) |
| `tests/unit/core/test_page_to_line_matches*.py` or new glyph inject tests | Create/Modify | Sidecar stamp unit coverage |
| `tests/integration/.../test_glyph_routes.py` | Create | HTTP set / accept / bulk dry-run+apply |
| `tests/unit/test_gt_rejects_ligature_codepoints.py` | Create | Spec §10 GT reject |
| `frontend/src/hooks/useWordMutations.ts` | Modify | `useSetGlyphAnnotations`, `useAcceptGlyphPrediction` |
| `frontend/src/hooks/useWordMutations.test.tsx` | Modify | Mutation unit tests |
| `frontend/src/components/right-panel/WordDetail.tsx` | Modify | Mount Typography accordion with panel + hooks |
| `frontend/src/components/right-panel/WordDetail.test.tsx` | Modify | Mount + mutation wiring tests |
| `frontend/src/components/WordCell.tsx` | Modify | Chip click opens edit / selects word + expands typography |
| `frontend/src/components/glyph/BulkGlyphMarkDialog.tsx` | Modify | Invalidate page query after apply; optional use of shared client |
| `frontend/src/components/glyph/BulkGlyphMarkDialog.test.tsx` | Modify | Apply invalidation / fetch tests |
| `frontend/src/components/glyph/GlyphAnnotationPanel.tsx` | Modify | Kind enum parity with spec if needed |
| `tests/e2e/test_glyph_panel.py` | Create | Manual review path |
| `tests/e2e/test_bulk_glyph_mark.py` | Create | Preview + apply badges |
| `tests/e2e/test_driver_contract.py` | Modify | Panel testids when word selected (if stable) |
| `docs/specs/behavior/component-glyph-annotations.md` | Modify | Mark behaviors implemented + test links |
| `docs/specs/behavior/unclear-items.md` | Modify | Clear resolved glyph unclear items |
| `AGENTS.md` / `docs/context/current-state.md` | Modify | Reflect residual vs shipped accurately after close-out |

---

## Task 0 — Confirm fixtures and baseline

**Files:** none (investigation only)

- [x] **Step 1: Confirm current glyph files and open failures**

```bash
cd /workspaces/pdomain/pdomain-ocr-labeler-spa
rg -n "glyph_annotations_map|GlyphAnnotationPanel|future: open panel" src frontend tests
uv run pytest tests/unit/test_glyph_bulk_mark.py tests/unit/test_glyph_endpoints.py tests/unit/test_glyph_predictor_none.py -q
cd frontend && pnpm exec vitest run src/components/glyph src/components/WordCell.test.tsx
```

Expected: unit/vitest suites for existing scaffold pass; grep shows map write sites and unmounted panel / placeholder chip handlers.

Update (2026-09-18): the payload-inject and generation-bump gaps this step
found were already closed on `master` by the time this backend pass started
(commits `eb11eb9`, `89bbe6d`) — see Task 1 below. Frontend mount (Steps
2/5/6) remains unmounted; out of scope for this backend-only pass.

- [x] **Step 2: Record mount decision**

Primary host is `WordDetail` Typography accordion (collapsed by default;
auto-expand when `glyph_predictions != null && glyph_annotations == null`).
Do not resurrect `WordEditDialog`.

Update (2026-09-18, Task 5): implemented as described, with one
deviation — the new accordion item is labeled **"Glyphs"**, not
"Typography". `WordDetail` already has a `value="typography"` item for a
separate, already-shipped feature (`TypographySection`, grapheme/taxonomy
span review — `docs/specs/2026-08-21-typography-review-and-training-export-design.md`,
written after this plan). `WordEditDialog` was not resurrected.

---

## Task 1 — Backend: inject glyph sidecars into `PagePayload` (TDD)

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/core/page_to_line_matches.py`
- Modify: `src/pdomain_ocr_labeler_spa/api/pages.py` (`_page_payload`)
- Create/Modify: unit tests under `tests/unit/core/`

### Why first

Without this, every API mutation that writes `glyph_annotations_map` is
invisible to the SPA. This is the highest-leverage residual bug.

- [x] **Step 1: Write failing unit test — map overrides / stamps WordMatch**

Add a test that builds a tiny Page/word stub, passes
`glyph_annotations_map={"0_0": {"ligatures": [{"kind": "ct", "char_span": [0, 2]}], "long_s_positions": [], "swash": false, "source": "human"}}`,
and asserts `word_matches[0].glyph_annotations.ligatures[0].kind == "ct"`.

Also assert:

- absent key → `glyph_annotations is None` (not reviewed)
- empty dict value `{ligatures:[], long_s_positions:[], swash:false, source:human}` → non-None empty reviewed
- optional `glyph_predictions_map` stamps `glyph_predictions`

Tests added in `tests/unit/core/test_page_to_line_matches.py`.

- [x] **Step 2: Run test — expect fail**

```bash
uv run pytest tests/unit/core/ -k glyph -q
```

Update (2026-09-18): the tests **passed immediately** — see Step 3.

- [x] **Step 3: Implement stamp path**

Mirror `char_bboxes_map` / `char_ranges_map`:

1. Add `glyph_annotations_map` and `glyph_predictions_map` kwargs to
   `_word_to_word_match` / `page_to_line_matches`.
2. Prefer sidecar map over `getattr(word_obj, "glyph_annotations", None)` when
   the key is present (map is SPA authority after human edit).
3. In `_page_payload`, pass `pstate.glyph_annotations_map` and
   `pstate.glyph_predictions_map` into `page_to_line_matches`.

Update (2026-09-18): already implemented on `master` before this pass
(commit `89bbe6d feat: inject glyph sidecars into page payload and
persist`) — `page_to_line_matches.py` already has both kwargs and
`_glyph_from_sidecar`; `api/pages.py::_page_payload` already passes
`pstate.glyph_annotations_map` / `glyph_predictions_map`. No code change
needed for this step; only the regression tests were missing.

- [x] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/unit/core/ -k "glyph or page_to_line_matches" -q
```

5 passed.

- [x] **Step 5: Commit**

```bash
git add src/pdomain_ocr_labeler_spa/core/page_to_line_matches.py \
  src/pdomain_ocr_labeler_spa/api/pages.py tests/unit/core/
git commit -m "fix(m11): inject glyph sidecars into page payload"
```

---

## Task 2 — Backend: integration tests for glyph routes + generation bump

**Files:**
- Create: `tests/integration/api/test_glyph_routes.py` (or nearest integration layout)
- Modify if needed: `api/words.py` / `api/pages.py` for correct status codes

- [x] **Step 1: Write failing integration tests**

Cover:

1. `POST .../glyph-annotations` with CT mark → response `PagePayload` word has annotations.
2. `POST .../glyph-annotations` with `annotations: null` → word returns to unreviewed.
3. `POST .../accept-prediction` with no predictions → 400 `no_predictions`.
4. Seed `glyph_predictions_map`, accept → annotations `source=human_confirmed`.
5. `POST .../glyph-bulk-mark` dry_run on page with GT containing `ct` → preview count.
6. Apply (non-dry-run) → affected words stamped + generation bumped.

Use existing project/page fixtures from other word-mutation integration tests.

Added `tests/integration/test_glyph_routes.py` (flat layout — matches this
repo's existing `tests/integration/` convention, not the
`tests/integration/api/` path the plan's file map suggested).

- [x] **Step 2: Run — expect fail until Task 1 lands; then fix any remaining route bugs**

```bash
uv run pytest tests/integration -k glyph -q
```

Update (2026-09-18): Task 1 was already done (see above), so the set/accept
tests passed immediately. The bulk-mark **apply** test failed with
`TypeError: Object of type UUID is not JSON serializable` — `glyph_bulk_mark`
returned a hand-built `JSONResponse(content=response.model_dump())` (no
`mode="json"`), which chokes on the UUID nested in `page.page_record.page_id`.
Fixed here by returning the declared `GlyphBulkMarkResponse` model instance
directly (mirrors the jobs-API wire-shape fix, commit `324fb8b`). The
separate durable-persistence gap (bulk-mark's STUB store write) is Task 3's
fix, below. All 8 Task-2 tests pass after this fix.

- [x] **Step 3: Add `test_gt_rejects_ligature_codepoints.py`**

Assert POST GT with `ﬁ` or `ſ` returns 400 validation_error (spec §10).

Added as `test_update_word_gt_rejects_ligature_codepoints` /
`test_update_word_gt_rejects_long_s_codepoint` in
`tests/integration/test_glyph_routes.py` rather than a separate file — the
validator (`UpdateWordGroundTruthRequest._reject_forbidden_codepoints`) was
already shipped; only the test was missing.

- [x] **Step 4: Commit**

```bash
git commit -m "test(m11): integration coverage for glyph routes"
```

---

## Task 3 — Backend: durable persistence across save/reload

**Files (choose one strategy; prefer A unless book-tools already owns field):**

**Strategy A (recommended, matches char sidecar reality + labeler extension note):**

- Persist `glyph_annotations_map` on `LabelerPageExtension` or a dedicated
  content sidecar written during `save_page` / `_save_to_store_best_effort`.
- On load (`load_page` / ensure page model / GET path), rehydrate
  `pstate.glyph_annotations_map`.

**Strategy B (if `pdomain_book_tools` Word already supports `glyph_annotations`):**

- Write confirmed annotations onto live `Word` objects on mutate.
- Rely on `save_page_content_to_store` Page serialization.
- Still keep `source` SPA field on the map or extension because book-tools
  type may omit `source`.

- [x] **Step 1: Write failing reload test**

Set annotations → save page → clear in-memory page state / reload from store →
GET page → word still has annotations (None/empty/populated tri-state cases).

Added 4 `@pytest.mark.integration` tests to
`tests/integration/test_glyph_routes.py` (the same file as Task 2, split by
a "Durable persistence" section): populated (with an untouched sibling word
proving the absent case), empty-reviewed, cleared-back-to-absent, and
bulk-mark apply. All 4 failed before Step 2's fix — the single-word ones on
the pre-existing `assert reloaded is not None` guard (bulk-mark never wrote
a content blob at all; single-word routes already did, so those 3 actually
passed against master before Task 1/2 — see Step 2 for what was and wasn't
already fixed), and the bulk-mark one on the same STUB gap.

- [x] **Step 2: Implement persist + hydrate**

- On `set_glyph_annotations` / `accept_glyph_prediction` / bulk apply: write map
  **and** call the same store-best-effort path used by other word mutations
  (do not leave `pass  # STUB: cached-lane retired` without store write).
- On load: restore map before `_page_payload`.

Update (2026-09-18): most of this step was already done on `master` before
this pass. `core/labeler_sidecars.py` (Wave 0.1) already carries
`glyph_annotations_map` alongside `char_bboxes_map` in the content-blob
`labeler_sidecars` section, and `set_glyph_annotations` /
`accept_glyph_prediction` (`api/words.py`) already call
`_save_to_store_best_effort` — the single-word reload tests passed without
any code change. The **one** remaining gap: `glyph_bulk_mark`
(`api/pages.py`) still called `_write_cached_envelope_best_effort`, the
retired no-op STUB the plan's evidence section quotes. Fixed by calling
`_save_to_store_best_effort` there too (mirroring the single-word routes,
including the 503 `store_persist_failed` contract on write failure), and
removed the now-dead `_write_cached_envelope_best_effort` from `api/pages.py`
(its only caller). No load-path change was needed — rehydration already
restores both maps together via `apply_sidecars_to_page_state`.

Review note (2026-09-18): a scratch-worktree review confirmed with the old
code that bulk apply was not merely failing to persist — every non-dry-run
apply crashed outright with a 500 (the Task 2 `TypeError: Object of type
UUID is not JSON serializable` bug), so this branch's Task 2 fix was a
prerequisite for Task 3's reload test to even reach the persistence gap.
The review also added a bulk-apply 503 `store_persist_failed` test
(`tests/integration/test_mutation_store_failure_status.py`), confirmed
failing against the pre-fix STUB, matching the single-word routes' existing
coverage in the same file.

- [x] **Step 3: Document decision**

If strategy differs from retired v2.2 `UserPageEnvelope` text in
`specs/20-glyph-annotations.md` §4, add a short note in
`docs/context/decisions.md` and a residual comment on the spec pointing at
event-store persistence. Do not unilaterally rewrite the whole §4 without
reviewer OK; minimal delta is fine.

Added "2026-09-18 — Glyph annotations reuse the char-sidecar durability path
(Wave 2 T3)" to `docs/context/decisions.md`, and a short residual-note
blockquote at the top of `specs/20-glyph-annotations.md` §4 pointing at it.
§4's body text is untouched.

- [x] **Step 4: Commit**

```bash
git commit -m "feat(m11): persist glyph annotations across save/reload"
```

---

## Task 4 — Frontend mutations: `useSetGlyphAnnotations` + `useAcceptGlyphPrediction`

**Files:**
- Modify: `frontend/src/hooks/useWordMutations.ts`
- Modify: `frontend/src/hooks/useWordMutations.test.tsx`

- [x] **Step 1: Write failing hook tests**

Mock fetch:

- `POST .../words/{li}/{wi}/glyph-annotations` body `{ annotations }`
- `POST .../words/{li}/{wi}/accept-prediction` body `{}` or empty
- On success: invalidate `["page", projectId, pageIndex]`

Update (2026-09-18): also added `useGlyphAnnotationPending` (shared
`mutationKey` + `useIsMutating`, mirroring `useRegionMutations.ts`'s
`useRegionDecisionPending` and `usePageMutations.ts`'s
`useReloadOcrEditedPending`) — not in the plan's original list, added per
this pass's explicit instruction to follow the shared pending-signal
pattern so two components mounting these hooks independently can't fire a
duplicate request.

- [x] **Step 2: Implement hooks**

Follow existing `apiPost` + `wordBase` pattern in `useWordMutations.ts`.
Types come from `frontend/src/api/types.ts`
(`SetGlyphAnnotationsRequest` / OpenAPI operation names already present).

- [x] **Step 3: Run**

```bash
cd frontend && pnpm exec vitest run src/hooks/useWordMutations.test.tsx
```

16 passed.

- [x] **Step 4: Commit**

```bash
git commit -m "feat(m11): add glyph annotation mutation hooks"
```

---

## Task 5 — Mount `GlyphAnnotationPanel` in `WordDetail` (TDD)

> **Known limitation (2026-09-18, record — not a defect of this task):**
> the accept button cannot fire for a real user today. `glyph_predictions_map`
> is never populated by any production code path — `IGlyphPredictor` is
> unwired (Task 10's "Predictions attach", still open). The mark-reviewed
> path (set/clear annotations) works end to end, browser-tested included;
> accept-prediction is wired and unit-tested (mocked predictions) but is
> scaffolding until a real predictor exists and something calls it during
> payload build. Do not read "Task 5 done" as "accept is usable" — it isn't,
> yet.

**Files:**
- Modify: `frontend/src/components/right-panel/WordDetail.tsx`
- Modify: `frontend/src/components/right-panel/WordDetail.test.tsx`

- [x] **Step 1: Write failing tests**

1. Selecting a word renders `glyph-panel-{li}-{wi}`.
2. Clicking `glyph-panel-mark-reviewed-empty` calls set-annotations mutation
   (or `onSetAnnotations` wrapper that posts).
3. With predictions present, accept button invokes accept mutation.
4. Typography accordion default collapsed; auto-open when predictions pending.

Update (2026-09-18): also added two edge-case tests — "collapses by default
with no pending predictions" and "does not auto-open once the word already
has confirmed (even empty) annotations" — beyond the plan's 4, to pin down
the tri-state boundary the auto-open condition depends on.

- [x] **Step 2: Implement mount**

Place a **Typography** accordion item after Style/Component palettes and
before/near Structure (spec originally said between tag chips and preview;
WordDetail layout maps cleanly to an accordion item under the palettes).

Update (2026-09-18): mounted as an accordion item named **"Glyphs"**, not
"Typography" — `WordDetail` already has a `value="typography"` item hosting
`TypographySection`, a distinct grapheme/taxonomy-span review feature from
`docs/specs/2026-08-21-typography-review-and-training-export-design.md`
(shipped after this plan's spec was written). Reusing "Typography" here
would put two differently-behaved triggers with the same label in one
accordion. Positioned as item 4 (after Erase Pixels, before Structure),
matching "near Structure". The whole accordion became controlled
(`value`/`onValueChange`) so the Glyphs item can auto-open once per
newly-selected word without disturbing the other items' open state.

Wire:

```tsx
const setGlyph = useSetGlyphAnnotations(projectId, pageIndex);
const acceptGlyph = useAcceptGlyphPrediction(projectId, pageIndex);

<GlyphAnnotationPanel
  lineIndex={lineIdx}
  wordIndex={wordIdx}
  gtText={word.ground_truth_text}
  annotations={word.glyph_annotations ?? null}
  predictions={word.glyph_predictions ?? null}
  onSetAnnotations={(ann) =>
    setGlyph.mutate({ lineIndex: lineIdx, wordIndex: wordIdx, annotations: ann })
  }
  onAcceptPrediction={() =>
    acceptGlyph.mutate({ lineIndex: lineIdx, wordIndex: wordIdx })
  }
/>
```

- [ ] **Step 3: Kind enum parity (small)**

Align `LIGATURE_KINDS` with backend bulk/spec strings used on wire:
`ct`, `st`, `long_st`, `fi`, `fl`, `ffi`, `ffl`, `oe`, `ae` (lowercase wire
forms already used by bulk_mark `"ct"`). Drop non-spec `ff` unless backend
accepts it.

Not done in this pass — out of the explicit scope given (mount + its
4-test TDD list only); left for a follow-up since it touches
`GlyphAnnotationPanel.tsx` and its existing unit tests, not `WordDetail`.

- [x] **Step 4: Run vitest + commit**

```bash
cd frontend && pnpm exec vitest run src/components/right-panel/WordDetail.test.tsx src/components/glyph
git commit -m "feat(m11): mount GlyphAnnotationPanel in WordDetail"
```

35 passed.

---

## Task 6 — Wire WordCell chips → word edit / Typography

**Skipped in the 2026-09-18 pass** (not attempted — see report). This
task's plan text calls for wiring glyph-chip clicks to `onEditWord(line,
word)`, a callback `docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md`
documents as already dead: `ProjectPage` mounts `WordMatchView` without
passing `onEditWord` at all, so any chip wired to it today would be a
silent no-op, not a working "open the panel" click. That issue is still
open with three undecided questions (retire the driver-contract §2.11
dialog docs, wire the pencil to select-and-open-right-panel or remove it,
and give word merge a home) — Task 6 needs question 2 resolved (or
resolved consistently for chips specifically) before it can wire glyph
chips to anything real. Once decided, Task 6 becomes: select the word
(`selectWord(line, wordIndex)` from `stores/selection-store`, the same
store `WordDetail` already reads) and open the right panel's new "Glyphs"
accordion item (Task 5) — not a standalone dialog — on chip click.

**Files:**
- Modify: `frontend/src/components/WordCell.tsx`
- Modify: `frontend/src/components/WordCell.test.tsx`
- Possibly: parent that supplies `onEditWord` (`WordMatchView` / `ProjectPage`)

- [ ] **Step 1: Write failing test**

Clicking a glyph chip calls `onEditWord(line, word)` (or a new optional
`onOpenGlyphPanel` prop that defaults to edit).

- [ ] **Step 2: Replace placeholder handlers**

Remove `/* future: open panel */`. Prefer reusing `onEditWord` so right panel
opens with the word selected and Typography accordion expanded (pass a store
flag or query param only if needed; simplest is: select word + set a small
`selectionStore` or local UI flag `expandTypography`).

If popover-on-chip from spec §5.1 is still desired later, keep WordDetail as
source of truth for editing; popover can wrap the same panel component.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(m11): open word editor from glyph chips"
```

---

## Task 7 — Bulk dialog: invalidate page + harden apply path

**Files:**
- Modify: `frontend/src/components/glyph/BulkGlyphMarkDialog.tsx`
- Modify: `frontend/src/components/glyph/BulkGlyphMarkDialog.test.tsx`

- [x] **Step 1: Write failing test**

On successful apply, `queryClient.invalidateQueries({ queryKey: ["page", projectId, pageIndex] })`
is called (spy). Optional: accept `onApplied?: () => void` for parent override.

Update (2026-09-18): added the spy test plus two guards — apply failure
does not invalidate, and dry-run preview does not invalidate — so the
invalidation is scoped to a real, successful apply only. Did not add
`onApplied?:` — not needed; the dialog already calls its own `onClose`,
and no caller needed a separate override hook.

- [x] **Step 2: Implement**

Use `useQueryClient` inside the dialog (pattern used by hooks). Prefer shared
`apiPost` helper if easy; raw `fetch` is acceptable if invalidation is fixed.

Keep dry-run path returning preview count (`bulk-glyph-preview-count`).

Kept the existing raw-`fetch`-based `callBulkMark` unchanged; only added
`useQueryClient` + one `invalidateQueries` call in `handleApply`.

- [x] **Step 3: Commit**

```bash
git commit -m "fix(m11): invalidate page query after bulk glyph apply"
```

---

## Task 8 — Progress metric + save warning polish (mostly done)

**Files:** likely no code; verify + small polish only

- [ ] **Step 1: Verify metrics**

With Task 1 fixed, `glyphs_reviewed` in `ProjectPage` becomes truthful.

Confirm `WorkspaceMetrics` shows `N/M glyphs` when total > 0.

- [ ] **Step 2: Verify save warning**

With `glyph_review_required: true` in app config fixture, save emits toast
via existing `data.warnings` handling in `PageActionsCompact` /
`ProjectPage`.

Add a focused backend unit/integration assertion if missing.

- [ ] **Step 3: Optional UX**

If config is false, keep metric muted (current styling is already secondary
ink). No extra work required unless product wants an explicit “optional” label.

---

## Task 9 — E2E behavior (Playwright)

**Files:**
- Create: `tests/e2e/test_glyph_panel.py`
- Create: `tests/e2e/test_bulk_glyph_mark.py`
- Modify: `tests/e2e/test_driver_contract.py` only if new always-on testids appear

- [ ] **Step 1: `test_glyph_panel.py`**

Flow (adapt fixture project with known GT containing `ct`):

1. Load project page; wait for ready.
2. Select a word (edit button or canvas/word cell).
3. Assert `glyph-panel-{l}-{w}` visible.
4. Select char span / kind CT → Add → mark appears.
5. Save page (if required by auto-save policy) → reload page.
6. Re-open word → chip/badge still present (depends on Task 3).

Update (2026-09-18, partial): added `tests/e2e/test_glyph_panel.py`
covering steps 1–3 plus a reduced step 4 — select a word, open the
"Glyphs" accordion item, click "Mark reviewed (no marks)" (rather than
the char-span/kind-CT ligature flow), and assert via an independent GET
that `glyph_annotations` landed on the server. Left unchecked because it
does not cover the full flow above: no char-span ligature mark, and no
save/reload persistence re-check (Task 3's persistence path is already
covered by backend integration tests in `tests/integration/
test_glyph_routes.py`, not re-proven here at the browser level). This
pass's instructions scoped Task 9 to exactly the reduced flow implemented
— see the char-span/predictions gap below.

Accept-a-prediction is not covered by any browser test and is not
plausible to add today: `glyph_predictions_map` is never populated by any
production code path (`IGlyphPredictor` is unwired — Task 10, deferred),
so a fixture seeded the way every e2e in this suite seeds pages
(`_ingest_ocr_result`, no real OCR/classifier) has no way to plant
predictions on a word without reaching past what a browser-driven user
could do. Covered at the vitest level instead:
`WordDetail.test.tsx`'s "accepts a prediction, posting to the
accept-prediction route" test (Task 5).

- [ ] **Step 2: `test_bulk_glyph_mark.py`**

Not attempted in this pass — out of the explicit scope given (Task 9 was
scoped to the select-word/mark-reviewed flow only).

1. Open bulk dialog.
2. Recipe CT; Preview → assert `bulk-glyph-preview-count` text.
3. Apply → dialog closes → green/blue badges appear for affected words.

- [ ] **Step 3: Run**

```bash
make e2e AI=1
# or focused:
uv run pytest tests/e2e/test_glyph_panel.py tests/e2e/test_bulk_glyph_mark.py tests/e2e/test_driver_contract.py -q
```

- [ ] **Step 4: Commit**

```bash
git commit -m "test(m11): e2e glyph panel and bulk mark flows"
```

---

## Task 10 — Optional polish (defer unless capacity)

Only after Tasks 1–9 green:

- [ ] **Predictions attach:** call `NoneGlyphPredictor` (or configured adapter)
  in `_page_payload` to fill `glyph_predictions_map` / WordMatch fields.
  Until this lands, the FE accept-prediction path (Task 5) is scaffolding
  only — no production code ever writes `glyph_predictions_map`, so the
  accept button cannot fire for a real user (see the callout at the top of
  Task 5).
- [ ] **Canvas overlay:** `predictions-overlay-toggle` + ghost outlines §5.6
  (`--predictions-ghost-color`).
- [ ] **Per-mark accept vs wholesale:** UI currently accepts whole prediction
  object; match backend wholesale accept API (already wholesale). Keep
  per-kind testids but implement as wholesale or document limitation.
- [ ] **Reject semantics:** reject currently stamps empty human annotations;
  ensure that matches product intent (reviewed-with-no-marks vs ignore).

---

## Task 11 — Docs / behavior close-out

**Files:**
- `docs/specs/behavior/component-glyph-annotations.md`
- `docs/specs/behavior/unclear-items.md`
- `docs/context/current-state.md`
- `AGENTS.md` / `README.md` glyph status lines
- `docs/architecture/13-driver-contract.md` if toggle added

- [ ] **Step 1:** Point B-GLYPH-001…005 at real tests; update adversarial review
  status from “components do not exist” to residual list or “wired”.
- [ ] **Step 2:** Clear unclear-items glyph bullets that Tasks 1–7 fixed.
- [ ] **Step 3:** Current-state / AGENTS: replace “frontend not shipped” with
  accurate residual (or “shipped” if Tasks 1–9 complete).
- [ ] **Step 4:** Full gate

```bash
make ci AI=1
```

- [ ] **Step 5: Final commit**

```bash
git commit -m "docs(m11): record glyph annotation completion status"
```

---

## Sequencing and dependencies

```text
Task 0
  └─► Task 1 (payload inject) ──► Task 2 (integration routes)
         │                              │
         └─► Task 3 (persist/reload) ◄──┘
                │
                ├─► Task 4 (hooks) ─► Task 5 (WordDetail mount) ─► Task 6 (chips)
                │                          │
                └─► Task 7 (bulk invalidate) ─► Task 8 (metric/warn verify)
                                                │
                                                └─► Task 9 (e2e)
                                                      └─► Task 10 optional
                                                      └─► Task 11 docs
```

Do **not** start e2e (Task 9) before Tasks 1, 3, 5, and 7.

Trainer classifier remains external. Manual mode is the acceptance bar for
“usable M11”.

---

## Acceptance checklist (maps to `specs/20-glyph-annotations.md` + M11 gates)

| Gate | Residual owner |
|---|---|
| Tri-state on payload (None / empty / populated) | Tasks 1–3 |
| Set / clear annotations via API + UI | Tasks 2, 4–5 |
| Accept prediction path (when predictions present) | Tasks 2, 4–5; predictions producer optional Task 10 |
| Bulk dry-run + apply + badges | Tasks 1, 7, 9 |
| Glyphs reviewed metric | Task 8 (truthful after Task 1) |
| `glyph_review_required` save warning | Task 8 (already wired; verify) |
| Driver testids §7 for bulk + panel | Tasks 5, 9; overlay optional |
| E2E panel + bulk | Task 9 |
| Docs status accurate | Task 11 |

---

## Risk notes

- **Sidecar not in payload** is the main footgun; fix first.
- **M5b retired UserPageEnvelope cache writes** — any comment that says
  “auto-saves to cache” is stale; implement event-store writes explicitly.
- **WordEditDialog references in architecture** are historical; implement on
  `WordDetail` and update docs rather than rebuilding the dialog.
- **Re-OCR** will renumber words; same class of risk as `char_bboxes_map`
  (document; no new mitigation required in this plan).
- Do not block on `pdomain_book_tools.ocr.glyph_annotations` package export if
  SPA already owns `GlyphAnnotationsModel` and can persist sidecars.

---

## Estimated effort

| Slice | Size |
|---|---|
| Tasks 1–3 backend truth + persist | M |
| Tasks 4–7 frontend wiring | M |
| Task 9 e2e | S–M |
| Tasks 8, 11 polish/docs | S |
| Task 10 optional overlay/predictor | S (after trainer) |

---

## Stop conditions

Ship when Tasks 1–9 and 11 are green under `make ci AI=1` and a human can:

1. Open a word → Typography → mark CT / mark reviewed / reset.
2. See badges/chips update without full page reload.
3. Bulk CT-mark a page and see chips after apply.
4. Save + reload and still see confirmed annotations.

Optional Task 10 may remain backlog without blocking M11 usable-manual mode.
