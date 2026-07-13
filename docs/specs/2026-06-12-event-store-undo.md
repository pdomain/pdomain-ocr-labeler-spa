---
last_verified: 2026-07-13
created: 2026-06-12
owner: maintainers
kind: spec
repo: pdomain/pdomain-ocr-labeler-spa
status: partial
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

## Capability matrix (v1)

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
  remains in the store but is unreachable from the UI. Crossing this boundary is
  **designed** (CT 2026-06-12) and ships as milestone **U-M6** — see "U-M6 — undo across
  the re-OCR/rotate boundary" below. v1 scope is unchanged.
- Changelog-only saves (`save_page_to_store` fallback, no content blob) are not
  individually restorable; they're skipped in the chain (pre-existing persistence quirk,
  not widened here).

## Out of scope (v1)

- Postgres / managed-adapter persistence (D-042 unchanged).
- Pruning/compaction of truncated redo branches or old blobs — **designed** below
  ("Blob & branch pruning"), ships with U-M6.
- A visible history list / jump-to-version panel — **designed** below ("U-M7 — history
  panel"), ships as U-M7.
- Word-level or selective (partial-page) undo.
- Changes to pdomain-ops (`PageAggregate` API is sufficient as-is — confirmed for
  U-M6/U-M7 too; see the verified-API notes in those sections).

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
- The retired 2026-06-12 parity sweep rows C20 and P7 — retained in Git history.

## Milestone plan

| Milestone | Content | Status |
|-----------|---------|--------|
| v1 (slices H-A…H-D + BV, below) | buttons + hotkeys undo/redo, Reload rename, depth bound | ready to implement |
| **U-M6** (post-v1) | undo across the re-OCR/rotate boundary + blob/branch pruning | designed below |
| **U-M7** (post-v1) | visible history panel + jump-to-version | designed below |

v1 slice content is unchanged by the 2026-06-12 CT resolutions; U-M6/U-M7 are appended.

## Slices (v1)

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
- [ ] Preserve the retired parity row P7 resolution in current architecture.
- [ ] `make ci AI=1` green (includes frontend build); `make e2e AI=1` for the new tests.

## Verification gate (v1)

Done means: a human (or driver agent) can open a page, fix three words, press Mod+Z
three times watching each fix visibly unwind on the canvas, press Mod+Shift+Z to walk
forward again, restart the server and still undo, and never sees a button that claims to
discard edits that don't exist — with no console errors.

## U-M6 — undo across the re-OCR/rotate boundary + pruning (post-v1)

Resolves Q-U1 and Q-U2 (CT 2026-06-12): the history-reset boundary stays in v1, but
crossing it is a designed follow-up milestone, not a maybe. Pruning ships in the same
milestone because the fate of the abandoned aggregate is what the retention policy
governs.

### Boundary mechanism: page-slot re-pointing

Re-OCR/rotate already creates a **new** page aggregate and re-points
`ProjectAggregate.page_ids[idx]` at it (`page_state.py:246-256`). The old aggregate and
its blobs stay in the store untouched — so "undo the re-OCR" is *another* slot re-point,
back at the previous aggregate. No content is recomputed; the whole intra-aggregate undo
chain of the old aggregate becomes reachable again.

**Lineage link (the durable record of the boundary).** At re-OCR/rotate completion, link
the two aggregates via `PageAggregate.set_extension` (fires `ExtensionSet` —
`pdomain_ops/page_aggregate.py:161-184`, verified; replayable, snapshot-safe, zero ops
changes), under a new namespace `extensions["labeler.lineage"]` (the existing
`extensions["labeler"]` view-state model in `core/labeler_extension.py` stays untouched):

- new aggregate: `{"previous_page_id": "<old aggregate id>", "boundary_op":
  "reocr" | "rotate"}`
- old aggregate: `{"superseded_by": "<new aggregate id>"}`

**The event that records the re-point.** Crossing the boundary (either direction) calls
`ProjectAggregate.reorder_pages(page_ids)` with the full list and the one slot swapped —
the appended `PageReordered` event (`pdomain_ops/page_aggregate.py:212-215`, verified:
replaces `record.page_ids` wholesale) is the durable record. Append-only is respected:
the project log honestly records every re-point, exactly as the page log records every
undo marker.

**Undo crossing back.** When the page's chain cursor is at 0 *and* the current
aggregate's `labeler.lineage.previous_page_id` is set, undo offers one more step: the
boundary undo. Executing it re-points the slot to the previous aggregate, reloads the
in-memory `PageState` from that aggregate's head blob, re-stamps `page_id`
(the same stamp discipline as `page_state.py:246-256`), bumps the generation.

**Redo crossing forward.** Symmetric: cursor at chain end *and*
`labeler.lineage.superseded_by` set → redo re-points the slot to the successor
aggregate.

**Abandoned aggregate.** The aggregate not currently pointed at is never deleted from
the event store. Its **blobs** are protected by the pruning live-set (below) as long as
the aggregate is reachable from the slot's current aggregate by walking the lineage
chain (`previous_page_id` / `superseded_by`) — lineage-reachable aggregates within
retention contribute all their `blob_refs` to the live set; beyond retention only the
old aggregate's *version blobs* become prunable (the event log itself stays).

**Linear model at the aggregate level.** A *new* re-OCR performed while sitting on the
old aggregate re-stamps its `superseded_by` to the newest successor (extension
namespaces replace on set), discarding the previous forward branch from reachability —
the same linear truncation rule as U-5, lifted one level.

### Blob & branch pruning (resolves Q-U2)

**Verified pdomain-ops surface (cite, don't invent):**

- `DeadBranch` (`pdomain_ops/pages/provenance.py:33-39`): pure-data pydantic model with
  exactly `tip_id`, `forked_from_id`, `superseded_at`, `retain_until`. **No retention
  enforcement exists in pdomain-ops** — the model is a vocabulary, the policy is ours.
- `ProvenanceGraph.dead_branches: list[DeadBranch]` (`provenance.py:48`) exists, but no
  `PageAggregate` event mutates it — persisting the list would require a new ops event.
  **Not needed:** truncation points are deterministic from `history` + markers, so dead
  branches are **derived at prune time** by the same pure derivation as the cursor model
  and materialized as in-memory `DeadBranch` values (`tip_id` = last node of the
  truncated segment, `forked_from_id` = the restored version, `superseded_at` = the
  truncating node's timestamp — nodes carry `datetime.now(UTC)`, `page_state.py:379` —
  and `retain_until = superseded_at + retention`).
- `BlobStore.prune_orphans(live_refs: set[str]) -> list[str]`
  (`pdomain_ops/blob_store.py:40-47`): deletes **every** blob in the per-project dir not
  in `live_refs`. The dir also holds image/preprocess blobs, so the live set must be
  computed conservatively (below).

**No new pdomain-ops surface is required.** No cross-repo prerequisite.

**Retention default:** `PDLABELER_PRUNE_RETENTION_DAYS = 30`. Rationale: labeling a book
spans days-to-weeks, so a mis-undone branch must survive a multi-week session; blobs are
small content-addressed whole-page JSON, so the carrying cost of 30 days is trivial;
time-based beats N-versions because truncations are bursty and N-versions gives
unpredictable wall-clock protection.

**Trigger:** an explicit maintenance op — `POST
/api/projects/{project_id}/maintenance/prune` (returns deleted-hash count) — plus an
optional automatic run at project open gated by `PDLABELER_PRUNE_ON_OPEN`
(default `false`). **Never on-write:** `prune_orphans` scans the whole blob dir
(O(blobs) I/O per call), the dir is shared with image blobs, and pruning during
interactive editing would race in-flight jobs. Default-off auto-prune keeps deletion
opt-in until U-M6's boundary undo ships (dead-branch blobs are the only recovery path
beyond the depth bound).

**NEVER pruned (the live set).** Computed as *all* `blob_refs` of *all* nodes across
*all* aggregates of the project, **minus** only the prune candidates. A blob is a
candidate only if every node referencing it is (a) a version node of the active chain
older than `PDLABELER_UNDO_DEPTH` versions from the cursor, or (b) a node of a derived
dead branch whose `retain_until` has passed, or (c) a node of a lineage-unreachable or
retention-expired abandoned aggregate's version chain. In particular the current head
chain back to `PDLABELER_UNDO_DEPTH` is never pruned, and non-history blobs
(images, preprocess outputs) are never candidates at all. The conservative inversion
(subtract candidates, don't enumerate keeps) is mandatory because `prune_orphans`
deletes everything outside `live_refs`.

**Config surface:** `PDLABELER_PRUNE_RETENTION_DAYS` (int, default 30),
`PDLABELER_PRUNE_ON_OPEN` (bool, default false), both on `Settings` next to
`PDLABELER_UNDO_DEPTH`.

### U-M6 capability matrix

| ID | Capability | Acceptance criterion (observable behavior) |
|------|------------|--------------------------------------------|
| U-11 | Undo crosses the re-OCR boundary | Edit → Reload OCR → undo at cursor 0 offers the boundary step; executing it shows the **pre-re-OCR** content (canvas, worklist, right panel), and further undo steps walk the old aggregate's chain. Survives restart (slot re-point is a `PageReordered` event). |
| U-12 | Redo crosses forward | After U-11, redo at chain end re-points to the re-OCR'd aggregate and shows the post-re-OCR content. A new re-OCR performed on the old aggregate makes the previous successor unreachable (linear truncation, aggregate level). |
| U-13 | Pruning respects retention and never eats live data | After truncating a redo branch and advancing the clock past `retain_until` (test fixture), the maintenance op deletes the dead branch's exclusive blobs; the head chain back to `PDLABELER_UNDO_DEPTH`, image blobs, and within-retention branches are intact; a pruned project loads and undoes normally. |

U-6's v1 acceptance (buttons disabled after re-OCR + reset warning in the confirm
dialog) is superseded by U-11/U-12 when U-M6 lands: the dialog copy changes from "edit
history resets" to "undo will step back across this reload", and the undo button stays
enabled at the boundary.

## U-M7 — history panel + jump-to-version (post-v1)

Resolves Q-U3 (CT 2026-06-12). Post-v1 milestone — it needs a new endpoint, a derivation
extension, a new drawer tab, and its own e2e pass, so folding it into v1's slice H-C
would widen the BV gate for no v1 benefit; nothing in v1 depends on it.

**Placement:** a new tab in the existing page-scoped **Drawer**
(`frontend/src/components/shell/Drawer.tsx`), alongside worklist/hierarchy/text —
`DrawerTab` union in `frontend/src/stores/ui-prefs.ts:62` gains `"history"`. The
pdomain-ui AppShell right-side settings dock is the *app-scoped* surface
(`App.tsx` `settingsPanels`); page version history is page-scoped, so it belongs with
the other page-scoped lists in the Drawer.

**API:** `GET /api/projects/{project_id}/pages/{page_index}/history/versions` →
ordered version list derived from the same chain derivation:
`[{node_id, label, timestamp, is_current}]`. `label` is derived from the version's
changelog entry (`PageChangeEntry.changes[0].type`, e.g. "Validate word", "Edit text",
"Undo") with the root node labeled from its provenance `source` ("OCR"). Not folded
into `PagePayload` (unlike the v1 `history` flags) — the full list is fetched only when
the tab is open.

**Version row shows:** the op label, relative time from `ProvenanceNode.timestamp`
(e.g. "3 min ago"; timestamps are always set — `page_state.py:379`), and a highlight on
the current-cursor version.

**Jump-to-version semantics:** a restore event, same mechanism as undo. `POST
/api/projects/{project_id}/pages/{page_index}/jump` with the target `node_id` appends a
marker node `extra={"history_op": {"op": "jump", "restores": "<target>", "undoes":
"<current head>"}}`; the derivation treats `op=jump` exactly like undo/redo markers
(cursor → index of `restores` — backward or forward). The linear model is preserved: a
real edit after a backward jump truncates the redo branch from the active chain (U-5
unchanged). 409 when the target is not in the active chain.

**Testids (new — legacy had no history surface):** `drawer-tab-history` (follows the
existing `drawer-tab-<id>` pattern, `Drawer.tsx:52-65`), `history-version-row`
(per-row, with the version's `node_id` as a data attribute), `history-jump-button`
(per-row action). Added to `docs/architecture/13-driver-contract.md` in the U-M7 BV
slice.

### U-M7 capability matrix

| ID | Capability | Acceptance criterion (observable behavior) |
|------|------------|--------------------------------------------|
| U-14 | History tab lists versions | With ≥3 edits made, opening the history drawer tab shows one row per version (plus the OCR root), each with an op label and a relative time, current version highlighted — not just testids present. |
| U-15 | Jump restores any listed version | Clicking jump on an older row restores that version on canvas/worklist/right panel; the row highlight moves; undo/redo buttons reflect the new cursor. Jumping forward (after an undo) works symmetrically. |
| U-16 | Jump obeys the linear model | Jump back two versions → make a real edit → the two newer rows leave the active list (truncated); redo unavailable (consistent with U-5). |

## Resolved questions (CT 2026-06-12)

Formerly the open-questions section; all three resolved by CT on 2026-06-12.

1. **Q-U1 — undo across re-OCR/rotate → RESOLVED.** v1 keeps the history-reset
   boundary; crossing it is a committed follow-up, designed above as **U-M6**
   (lineage extensions + `ProjectAggregate.reorder_pages` slot re-pointing).
2. **Q-U2 — storage growth policy → RESOLVED.** Pruning policy specced now (see "Blob &
   branch pruning"): derived dead branches using the pdomain-ops `DeadBranch` model,
   30-day retention default, explicit maintenance op, conservative live-set. Ships with
   U-M6. No pdomain-ops changes required.
3. **Q-U3 — history UI → RESOLVED.** Wanted, not YAGNI — designed above as **U-M7**
   (history drawer tab + jump-to-version as a restore event). Post-v1.

## Adversarial Review

**Accepted finding:** The v1 undo/redo surface shipped, while U-M6 cross-OCR history and U-M7
visible history remain future work.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.
