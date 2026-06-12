---
repo: pdomain/pdomain-ocr-labeler-spa
status: draft — awaiting CT review
date: 2026-06-12
---

# Per-page undo/redo from the event store — spec + implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> or superpowers:executing-plans to implement this plan slice-by-slice. Each slice is TDD
> (failing test first), committed independently. Acceptance criteria are written as
> **observable user behavior** — a control is only "done" when it is **visible, enabled,
> and produces its effect**, verified in a real browser. A `data-testid` existing in the
> DOM is NOT acceptance (per the 2026-06-05 spec-format lesson).

**Goal:** Give the labeler real per-page undo/redo, powered by the version history the
event store already records, and retire the now-meaningless "Load Page (discard unsaved
edits)" semantic (P7 / C20) by renaming the control to plain "Reload".

**Architecture:** Every page mutation already persists a whole-page content blob and
advances the aggregate's provenance head (`save_page_content_to_store`,
`core/page_state.py:332-384`). Undo/redo is therefore **blob-version restore**: a pure
derivation over `ProvenanceGraph.history` yields a linear version chain + cursor; undo
and redo each **append a new event** that re-points the head at an existing content blob.
No event is ever deleted or rewritten — the eventsourcing log stays append-only.

**Tech Stack:** FastAPI + pdomain-ops `PageAggregate`/`PagesApplication` (eventsourcing,
SQLite), content-addressed `BlobStore`; React 19 + TanStack Query + Zustand; pytest,
vitest, Playwright.

## Why (spec-gap record — resolves P7/C20)

CT decision 2026-06-12. The legacy "Load Page = revert to last save" semantic is gone by
construction: every mutation auto-persists to the event-store head, and `load_labeled`
reads the *head* blob (`adapters/ocr/local_doctr.py:327`), so there are never "unsaved
edits" to discard (sweep row C20, verified live: validate-all → Save → unvalidate-all →
Load Page returns the *unvalidated* state). Rather than resurrect a save/working split,
CT chose to **build event-store-powered undo**: the history is already durable, so undo
falls out of data we already store — and "Load Page" becomes an honest "Reload".

### Key design choice: append-only revert events over head-pointer rewinds

Persistence is **head-blob-per-mutation**, not fine-grained replayable deltas:
`save_page_content_to_store` serializes the whole `page.to_dict()` to a content-addressed
blob per mutation and fires `LabelerEdited` with a provenance node carrying that blob;
reads resolve `head.blob_refs[0]` (`api/_page_content.py:38-41`). So undo is "load the
previous blob version", not "replay events to N-1".

Mechanism: undo/redo each append a **new `LabelerEdited` event** whose provenance node

- carries `blob_refs=[<hash of the restored content blob>]` (content-addressed → zero
  blob duplication; the hash already exists),
- carries a marker `extra={"history_op": {"op": "undo"|"redo", "restores":
  "<version-node-id>", "undoes": "<version-node-id>"}}`,
- sets `parent_ids=[<current head id>]` (provenance honestly records that the revert
  happened *after* the state it reverts).

Rationale for this over a dedicated `MutationReverted` aggregate event or a mutable head
pointer:

1. **Append-only respected.** `ProvenanceGraph.add_node` always advances `head_id` and
   appends to `history`; the eventsourcing log is immutable. A "rewind the head" command
   would still have to be an appended event — so the head always moves *forward* while
   content moves *backward*.
2. **Zero pdomain-ops changes.** `labeler_edited(provenance_node, changes)` already
   supports everything needed (`pdomain_ops/page_aggregate.py:117-125`). A typed
   `MutationReverted` event would require an ops release + transcoding churn for no
   observable gain; it can be promoted later without migration (old marker nodes keep
   working — the derivation reads `extra`, not the event class).
3. **Cross-session durability for free.** The undo stack *is* provenance history; it
   survives restarts because `load_labeled` reconstructs from the store.
4. **Auditability.** The provenance graph honestly records that an undo happened and
   what it restored — nothing is hidden from the changelog.

### Version-chain derivation (the cursor model)

A pure function (no I/O) over `ProvenanceGraph.history`, processed in order:

- **Version node** = a history entry whose node has non-empty `blob_refs` and **no**
  `extra.history_op` marker (i.e. the initial `OcrCompleted` node plus every real
  content-bearing edit). Changelog-only nodes (`save_page_to_store` fallback, empty
  `blob_refs`) are skipped — they are not restorable states.
- **Real version encountered:** truncate the chain at the cursor (linear undo — a new
  edit after undo discards the redo branch from the *active* chain; the truncated nodes
  remain in the graph as data), append the new version, cursor → last.
- **Marker `op=undo` / `op=redo`:** cursor → index of `restores` in the chain (the
  recorded id makes replay deterministic; no positional guessing).
- Undo available iff `cursor > 0`; redo available iff `cursor < len(chain) - 1`.
- Robustness: the OCR root node id appears **twice** in `history` (graph construction +
  `ocr_completed` both append it — `local_doctr.py:196-220`); the derivation must dedupe
  consecutive identical ids. Graphs written before this spec (no markers) degrade
  gracefully: all real versions, cursor at the end, undo immediately usable.

Executing an undo: read the restored blob, `Page.from_dict`, append the marker event via
the existing `LabelerPageStore`, swap the in-memory `PageState.page_record` payload
(re-stamp `_labeler_page_id`), bump the project-state generation (SSE consumers refresh).
Redo is symmetric.

## Capability matrix

| ID | Capability | Acceptance criterion (observable behavior — never "testid exists") |
|------|------------|--------------------------------------------------------------------|
| U-1 | Undo restores the previous page state | After any undoable mutation (e.g. validate a word), clicking `undo-button` (or Mod+Z outside a text field) returns the page to the prior state: canvas overlay, worklist row, and right-panel detail all show the pre-mutation content after the page query refetch. |
| U-2 | Redo re-applies an undone state | After U-1, clicking `redo-button` (or Mod+Shift+Z) returns the page to the post-mutation state, observable on the same three surfaces. |
| U-3 | Controls reflect availability | `undo-button` is disabled when the cursor is at the oldest version (fresh OCR, nothing to undo); `redo-button` is disabled when at the newest. Both disabled while the page is busy (in-flight job), consistent with the other page actions. |
| U-4 | History survives restart | Make an edit, restart the backend process, reload the page: undo is *available* and clicking it restores the pre-edit state. After an undo + restart, the page loads in the *restored* state (head points at the restored blob). |
| U-5 | Linear truncation | Edit A → edit B → undo (back to A) → edit C: redo is now unavailable; undo from C returns to A, not B. |
| U-6 | Re-OCR/rotate boundary | Reload OCR (and rotate, which re-OCRs) creates a new page aggregate: afterwards both buttons are disabled (fresh history). No crash, no stale-aggregate writes. The Reload-OCR confirm dialog warns that edit history resets. |
| U-7 | "Load Page" becomes "Reload" | The `load-page-button` control (PageActions + PageActionsCompact + overflow) is labeled "Reload", its tooltip/confirm copy no longer claims to "discard unsaved edits" (ProjectPage.tsx:572), and clicking it refreshes the page from the store head — same behavior as today, honest label. Testid unchanged (driver contract). |
| U-8 | Depth bound | The UI offers at most `PDLABELER_UNDO_DEPTH` (default 50) undo steps; older versions stop being reachable via the button but remain in the store. |
| U-9 | Undo is itself provenance | After an undo, the page changelog/provenance records a labeler history-op entry (changes list contains `{"type": "undo", ...}`) — verifiable via the aggregate in an integration test. |
| U-10 | Text-field hotkey safety | With focus inside any text input/textarea/contentEditable, Mod+Z performs the native text-edit undo and does NOT fire page undo; Mod+Z elsewhere fires page undo. |

## Scope

- **Per-page** undo/redo, within and across sessions. No project-wide undo.
- **Undoable (v1):** every mutation routed through `save_page_content_to_store` — word
  GT edits, validate/unvalidate, copy GT↔OCR, line/paragraph/block structure ops, word
  add/delete, erase ops, refine (`core/jobs/handlers/refine.py:147`), rematch-GT
  (`api/pages.py:843`), explicit Save (`save_project.py:158`). Each mutation = one undo
  step (coarse whole-page restore per step — acceptable v1 per CT).
- **Not undoable (v1):** Reload OCR and rotate. Both produce a **new** `page_id` /
  aggregate (`page_state.py:246-256`), so the version chain restarts; the old aggregate
  remains in the store but is unreachable from the UI. See Q-U1.
- Changelog-only saves (`save_page_to_store` fallback, no content blob) are not
  individually restorable; they're skipped in the chain (pre-existing persistence quirk,
  not widened here).

## Out of scope

- Postgres / managed-adapter persistence (D-042 unchanged).
- Pruning/compaction of truncated redo branches or old blobs (`dead_branches` machinery
  exists in pdomain-ops but stays unused here — see Q-U2).
- A visible history list / jump-to-version panel (see Q-U3).
- Word-level or selective (partial-page) undo.
- Changes to pdomain-ops (`PageAggregate` API is sufficient as-is).

## API surface

- `PagePayload` gains a `history` field: `{undo_available: bool, redo_available: bool,
  cursor: int, depth: int}` — folded into the existing page query so every mutation's
  invalidation refreshes button state with no extra round-trip.
- `POST /api/projects/{project_id}/pages/{page_index}/undo` and `.../redo` — 409 (or
  conventional error shape) when unavailable; success returns the same shape the other
  page mutations return and bumps the generation. Run `make openapi-export` after.

## Driver-contract testids

- New: `undo-button`, `redo-button` (legacy NiceGUI labeler had no undo surface, so new
  testids are permitted). Placed in the page-actions bar (both `PageActions.tsx` and
  `PageActionsCompact.tsx` variants).
- Unchanged: `load-page-button` keeps its testid through the "Reload" rename.
- `docs/architecture/13-driver-contract.md` updated in the BV slice.
- Hotkeys: `Mod+Z` / `Mod+Shift+Z` registered via the real `useHotkey` path AND listed in
  the hotkey map + help modal in the same slice (F20 lesson: never advertise unbound
  hotkeys, never bind unadvertised ones).

## Key references (grounded)

- `core/page_state.py:332-384` — `save_page_content_to_store`: whole-content blob +
  `LabelerEdited` per mutation (the fact that makes this blob-version design correct).
- `api/_page_content.py:38-41` — reads resolve `head.blob_refs[0]`.
- `adapters/ocr/local_doctr.py:140-239, 327-390` — OCR ingest node shape (root-node
  double-entry in `history`), restart read path.
- `.venv/.../pdomain_ops/page_aggregate.py:117-125` — `labeler_edited` event;
  `pdomain_ops/pages/provenance.py:42-62` — `ProvenanceGraph.head_id` / `history` /
  `add_node` semantics.
- `core/jobs/handlers/rotate.py:163, 190-216` — rotate re-OCRs then persists rotation
  metadata (why rotate is a history boundary).
- `frontend/src/pages/ProjectPage.tsx:572` — the stale "discard any unsaved changes"
  confirm copy to rewrite.
- `docs/research/parity-audit/sweep-2026-06-12-c-system.md` row C20,
  `PARITY-GAP.md` row P7 — the findings this spec resolves.

## Slices

### Slice H-A — version-chain derivation (pure, backend)

**Files:** create `src/pdomain_ocr_labeler_spa/core/page_history.py` + tests.

- [ ] Failing tests first, on synthetic `ProvenanceGraph`s: fresh-OCR graph (cursor 0,
      no undo, tolerates the root-node double-entry); N edits (cursor N); undo marker
      moves cursor by recorded `restores` id; redo marker; truncation on real-edit-after-
      undo (U-5); changelog-only (empty `blob_refs`) nodes skipped; legacy graph with no
      markers; depth cap applied.
- [ ] Implement `derive_history(graph, *, depth) -> HistoryState` (pure, no I/O) and the
      marker-node builders for undo/redo.
- [ ] `make test AI=1` green; commit.

### Slice H-B — undo/redo endpoints + durable round-trip

**Files:** `api/pages.py` (or a new `api/history.py`), `core/page_state.py` glue,
`PagePayload` model + `make openapi-export`.

- [ ] Failing tests: POST undo restores the prior blob's content in the returned payload
      and in a **fresh** `LabelerPageStore` read (restart simulation — the U-4 contract);
      redo round-trips; 409 at bounds; marker event lands in the aggregate changelog
      (U-9); in-memory `PageState` payload swapped + generation bumped; re-OCR'd page
      (new aggregate) reports empty history (U-6 backend half).
- [ ] Implement; wire `history` into `PagePayload`.
- [ ] `make test AI=1` green; `make openapi-export AI=1`; commit.

### Slice H-C — frontend: buttons, hotkeys, Reload rename

**Files:** `PageActions.tsx`, `PageActionsCompact.tsx`, `ProjectPage.tsx` (hotkeys +
confirm copy), mutation hook, hotkey map + help modal.

- [ ] Failing tests (vitest): buttons render with `undo-button` / `redo-button`, disabled
      per `history` flags and while busy (U-3); click fires the mutation; Mod+Z /
      Mod+Shift+Z dispatch outside text fields and do NOT dispatch when a text input has
      focus (U-10); "Reload" label + rewritten confirm copy with `load-page-button`
      testid intact (U-7); help modal lists the new hotkeys.
- [ ] Implement (TanStack mutation invalidating the page query; reuse the existing
      busy-gating the other page actions use).
- [ ] `make frontend-test AI=1` green; commit.

### Slice H-D — depth setting + Reload-OCR warning copy

- [ ] Failing tests: `Settings` gains `undo_depth: int = 50` (`PDLABELER_UNDO_DEPTH`);
      derivation respects it (U-8). Reload-OCR confirm dialog mentions that edit history
      resets (U-6 frontend half).
- [ ] Implement; green; commit.

### Slice BV — Browser Verification (MANDATORY, last)

- [ ] e2e (tests/e2e, existing Playwright harness + exercise fixture):
  - validate a word → undo → canvas/worklist/right panel show the pre-edit state →
    redo → post-edit state (U-1, U-2).
  - undo → make a different edit → redo disabled (U-5).
  - edit → restart the app server fixture → undo available and works (U-4).
  - fresh page: undo disabled; after Reload OCR: both disabled (U-3, U-6).
  - focus a GT text input, type, Mod+Z → text-field undo only, page state unchanged
    (U-10).
  - "Reload" button present under `load-page-button`, confirm dialog shows the new
    copy, click refreshes without error (U-7).
- [ ] Update `docs/architecture/13-driver-contract.md` (`undo-button`, `redo-button`,
      Load Page → Reload note) and `docs/architecture/08-page-actions.md` +
      `12-hotkeys-a11y.md`.
- [ ] Update `docs/research/parity-audit/PARITY-GAP.md` row P7 + its "deliberately not
      sliced" entry to point at this spec (resolved-by-design).
- [ ] `make ci AI=1` green (includes frontend build); `make e2e AI=1` for the new tests.

## Verification gate

Done means: a human (or driver agent) can open a page, fix three words, press Mod+Z
three times watching each fix visibly unwind on the canvas, press Mod+Shift+Z to walk
forward again, restart the server and still undo, and never sees a button that claims to
discard edits that don't exist — with no console errors.

## Open questions (CT)

1. **Q-U1 — undo across re-OCR/rotate.** v1 resets history at the new-aggregate
   boundary. The old aggregate persists, and `ProjectAggregate.reorder_pages` could
   re-point `page_ids[idx]` back to it, making "undo the re-OCR" possible later. Want
   that as a follow-up, or is the boundary acceptable long-term?
2. **Q-U2 — storage growth policy.** Undo adds no new blobs (content-addressed reuse),
   but the per-mutation blob stream and truncated redo branches accumulate. v1 ships no
   pruning. Should a pruning policy (e.g. pdomain-ops `DeadBranch.retain_until`) be
   specced before real multi-hundred-page sessions, or deferred until observed?
3. **Q-U3 — history UI.** v1 is buttons + hotkeys only. Is a visible version list
   ("jump to any prior state", timestamps from provenance) wanted as a follow-up, or
   YAGNI?
