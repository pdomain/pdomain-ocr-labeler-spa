---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-21
---

# Decisions

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-21
- **Read when:** looking for durable migration, lifecycle, or changed-direction rationale.
- **Search terms:** decisions, tombstones, retirement, changed direction, docgraph,
  sidecar durability, char_ranges_map, labeler_sidecars.

## 2026-07-13 — Retire retrieval-hostile historical scaffolding

### Context

Docgraph initialization found 681 issues across 135 documents. Archived plans,
draft specs, resolved ledgers, and point-in-time research dominated stale,
orphan, missing-section, and dangling-link findings. Read-only reviewers checked
each legacy document against current code, tests, git history, and graph links.

### Decision

Remove the retired `docs/archive/**` tree and completed or superseded research,
plan, and spec artifacts from live retrieval. Git history preserves their exact
text and binary evidence. Present-tense behavior stays in `docs/architecture/`;
residual intent stays in [`intent-map.md`](intent-map.md); current operations stay
in `docs/process/`, `docs/runbooks/`, and `docs/usage/`.

### Consequences

Search results no longer present historical gaps as current truth. Historical
provenance requires Git history, while current readers get a smaller,
evidence-backed graph.

### Supersedes / Superseded-by

This decision supersedes the repository convention of keeping closed bug,
question, plan, and spec ledgers in the live `docs/archive/` retrieval tree.

## Migration tombstones

### Retired archive collection

- Old paths: every tracked file formerly under `docs/archive/`, including the
  11 plan files, 7 research files, 26 spec files, archive placeholders, and two
  research binary artifacts present at migration start.
- Outcome: implemented, superseded, stale, or retired according to the
  evidence-backed 2026-07-13 sweep.
- Replacement: `docs/architecture/00-overview.md` through
  `docs/architecture/28-palettes-pickers.md`, `specs/17-decisions.md`, this
  decision log, and Git history.
- Removal commit: `ee95c83`.
- Rationale kept: shipped design and changed directions are in current
  architecture and the context docs.
- Remaining work: glyph annotations and other residual items are in
  [`intent-map.md`](intent-map.md).

### Retired point-in-time research collection

- Old paths: `docs/research/2026-05-22-deep-code-review-security-scan.md`,
  `2026-05-23-ci-e2e-root-cause.md`, `2026-05-31-doc-audit.md`,
  `2026-06-03-open-plans-specs-review.md`,
  `2026-06-14-pgdp-design-handoff-labeler-spa-gap-analysis.md`, and every file
  formerly under `docs/research/parity-audit/`.
- Outcome: implemented, superseded, or stale.
- Replacement: current architecture, runbooks, behavior specifications, and
  the partial PGDP alignment backlog.
- Removal commit: `ee95c83`.
- Rationale kept: the PGDP scope boundary and remaining alignment intent are in
  [`intent-map.md`](intent-map.md).
- Remaining work: see the Active, Deferred, and Blocked intent sections.

### Retired current-tree execution artifacts

- Old paths: `docs/plans/2026-06-03-labeler-spa-legacy-parity.md`,
  `docs/specs/2026-06-05-selection-operations-parity.md`,
  `docs/specs/2026-06-06-word-edit-dialog-wiring.md`,
  `docs/superpowers/plans/2026-06-14-component-migration-to-pdomain-ui.md`, and
  `docs/superpowers/plans/2026-06-14-upstream-first-pdomain-ui-component-migration.md`.
- Outcome: implemented or superseded.
- Replacement: behavior specifications, right-panel architecture, current
  `pdomain-ui` shell architecture, and Git history.
- Removal commit: `ee95c83`.
- Rationale kept: the right-panel and upstream-first changed directions are
  recorded in current architecture and [`intent-map.md`](intent-map.md).
- Remaining work: the partial PGDP alignment backlog remains active.

## 2026-07-13 — Rotation is shipped behavior

### Context

Older milestone and bug text said manual and batch auto-rotation only had job
and SSE plumbing. Current handlers rotate the image, rerun OCR, persist
metadata, protect manual overrides, and report progress. E2E tests exercise the
round trip.

### Decision

Treat manual and batch auto-rotation as built architecture. Future docs must use
the handlers and `tests/e2e/test_rotate_parity.py` as evidence.

### Consequences

Rotation is no longer listed as stubbed work. Product-level configuration or UI
enhancements may still be planned separately.

### Supersedes / Superseded-by

Supersedes the stale rotation warning formerly in `CLAUDE.md` and the retired
bug/parity ledgers.

## 2026-07-13 — Preserve the behavior flow taxonomy

### Context

`docs/specs/behavior/flows.md` declared `behavior-flow-spec` in its Agent Index
but inherited the generic `spec` kind during metadata normalization.

### Decision

Keep the more specific `behavior-flow-spec` kind in both metadata sources.

### Consequences

Behavior-flow retrieval retains its established taxonomy without changing the
document's lifecycle status.

### Supersedes / Superseded-by

Supersedes the generic kind written during this uncommitted migration batch.

## 2026-07-14 — Retire the PageRecord import convergence plan

### Context

The PageRecord import convergence plan completed its test-first migration.
Production and test callers now import shared lifecycle types from
`pdomain_ops.pages`, and `core.models` no longer exposes the compatibility
names.

### Decision

Remove the completed execution checklist from live retrieval. Keep the shared
schema boundary and shipped evidence in
[`../architecture/01-data-models.md`](../architecture/01-data-models.md#pagerecord)
and
[`../decisions/2026-07-13-shared-page-record-boundary.md`](../decisions/2026-07-13-shared-page-record-boundary.md).

### Consequences

Docgraph retrieval points readers to present-tense architecture instead of a
completed command checklist. Git history preserves the exact plan.

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-07-14-pagerecord-import-convergence.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/01-data-models.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: shared ownership and evidence are in the architecture and
  decision records linked above.
- Remaining work: none.

## 2026-07-19 — Preserve typed resolver narrowing from GitHub issue #459

### Context

Commit `b66fc19` typed both page resolvers as `Page | None`, changed the loader
payload boundary from `Any` to `object`, and removed six `reportAny`
suppressions. It used casts after the envelope guard because tests supplied
duck-typed page stubs. Later PageRecord work retained the typed boundary but
replaced the cast with runtime and `.lines` narrowing.

### Decision

Keep `Page | None` as the resolver contract and narrow the `object` payload at
the resolver boundary. Treat the historical cast as superseded implementation
detail, not current architecture.

### Consequences

Callers use typed page, line, and word attributes without `reportAny`
suppressions. Duck-typed test objects remain supported by the current `.lines`
gate.

### Supersedes / Superseded-by

This records the durable outcome and later evolution of GitHub issue #459. The
current implementation lives in `src/pdomain_ocr_labeler_spa/api/words.py` and
`src/pdomain_ocr_labeler_spa/api/pages.py`.

## 2026-07-19 — Retire the closed GitHub issues archive

### Context

Commit `5cdb276` captured all 425 closed GitHub issues in one lossless archive.
The archive contains each issue's metadata, full body, public comments, and raw
record digest. Its SHA-256 is
`6f27ae91252d0d0470cab287b4cf184aeca785fdb5c41a1bf5b949ebb55f3e99`.

### Decision

Remove the 852 KB archive from live retrieval after its dedicated commit. Keep
the compact reconciliation ledger live and use Git history for verbatim issue
recovery.

### Consequences

Current docgraph searches avoid 425 historical issue bodies. Migration review
can still recover the exact archive before any GitHub deletion.

### Supersedes / Superseded-by

- Old path: `docs/decisions/2026-07-19-closed-github-issues-archive.md`.
- Outcome: archived in Git and retired from the live tree.
- Superseded by: `docs/context/completed-github-issues-ledger.md`, current
  architecture, and context decisions.
- Archive commit: `5cdb276`.
- Recovery command:
  `git show 5cdb276:docs/decisions/2026-07-19-closed-github-issues-archive.md`.
- Remaining work: complete architecture coverage and deletion readiness for
  every ledger row before remote issue deletion.

## 2026-07-19 — Retire the pdomain-ui primitive migration plan

### Context

All six migration slices shipped. The final implementation kept local
composition boundaries for BusyOverlay, Tabs, and Accordion where the labeler
contract differs from the shared primitives.

### Decision

Remove the completed execution checklist from live retrieval. Keep shared
primitive ownership and the shipped wrapper deviations in current architecture.

### Consequences

Architecture now directs future wrapper work. The unresolved upstream-versus-
local ownership question remains in [`intent-map.md`](intent-map.md).

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-06-16-pdomain-ui-primitive-migration.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/03-frontend.md`,
  `docs/architecture/11-notifications.md`,
  `docs/architecture/26-right-panel-detail.md`, and
  `docs/architecture/28-palettes-pickers.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: current architecture and Git history.
- Remaining work: the wrapper ownership decision in `intent-map.md`.

## 2026-07-19 — Retire the confirmed bug-fixes plan

### Context

The compute-device preference, reload OCR timeout, OCR concurrency cap,
API-client correction, and dependency-pin follow-up all shipped. The temporary
dependency deferral was later resolved by the current dependency floor.

### Decision

Remove the completed execution checklist from live retrieval. Keep the device,
timeout, concurrency, and API contracts in current architecture.

### Consequences

Source and test provenance now points to architecture instead of a completed
plan. No residual plan work remains.

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-07-14-review-fixes.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/02-backend.md` and
  `docs/architecture/03-frontend.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: current architecture and Git history.
- Remaining work: none.

## 2026-07-21 — Char sidecar durability (Wave 0.1)

### Context

CharFixer `char_ranges_map` / `char_bboxes_map` lived only on in-memory
`PageState` after M5b retired the envelope write. Routes returned HTTP 200
without event-store serialization, so maps vanished on restart even after
Save Project. Deep-review Wave 0.1 required choosing among embed-in-word-dicts
(A), extension/side blob (B), and separate LabelerEdited fields (C), with an
explicit undo story.

Probe: book-tools `Word.to_dict` / `from_dict` drops unknown keys; there is no
first-class `char_ranges` / `char_bboxes` field (unlike `glyph_annotations`).
Content durability already uses whole-page `page.to_dict()` blobs under
`LabelerEdited`. Undo restores those blobs into the live `Page` but did not
rehydrate `PageState` maps.

### Decision

**Content-blob sidecar section (B-shaped carrier, A-shaped undo).**

1. Serialize maps under a reserved top-level key `labeler_sidecars` in the same
   content JSON blob written by `save_page_content_to_store` (alongside
   `Page.to_dict()` fields). `Page.from_dict` ignores unknown keys, so OCR
   structure round-trips unchanged.
2. On every content save from a live `PageState`, re-attach the current
   char maps so later GT/structure saves do not wipe CharFixer data.
3. On load from store, undo, and redo: extract `labeler_sidecars` and replace
   `PageState.char_ranges_map` / `char_bboxes_map` (clear + rehydrate — never
   leave maps from a different version).
4. Glyph annotation maps stay out of scope until Wave 2 T3; they will reuse
   this key when implemented.

### Consequences

- CharFixer Apply + rematch (content path) and undo share one blob for
  coherence; no second blob_ref or extension-only path for char maps.
- Export and `Page.from_dict` consumers keep working without book-tools
  changes.
- Implementers must pass current sidecars through all
  `save_page_content_to_store` call sites that hold a `PageState`.

### Rejected alternative

**A — embed on `Word` dict fields without book-tools changes.** Unknown keys
are dropped on round-trip; pure setattr does not survive `to_dict`. Adding
first-class fields in book-tools would be cleaner long-term for glyphs (already
present) but blocks Wave 0 char durability on an upstream release.

**C — maps only on LabelerEdited changelog outside the content blob.** Undo
restores content via `blob_refs` only; out-of-blob maps need a separate
clear/rehydrate protocol and drift more easily from the restored page.

## 2026-07-21 — Export list API ↔ disk manifest (Wave 1.0)

### Context

`GET .../exports` was an empty stub. On-disk
`<data_root>/doctr-export/manifest.json` uses schema
`pdomain.doctr-export-manifest` with a per-project map
(`exported_at`, `page_count`, `tasks`). The OpenAPI placeholder
`ExportManifest` used `job_id`, `scope`, `created_at` only.

### Decision

**Remap disk → API** (keep list of `ExportManifest`, one row per project
entry; disk currently stores a single latest export per project):

| API field | Source |
| --- | --- |
| `created_at` | `projects[id].exported_at` |
| `page_count` | `projects[id].page_count` |
| `tasks` | `projects[id].tasks` (task → `{item_count}`) |
| `job_id` | synthetic `doctr-export:{project_id}:{exported_at}` (no job id on disk) |
| `scope` | fixed `"project"` (disk is project-level merge, not per-scope history) |

Expand the pydantic model with `page_count` and `tasks`; keep
`job_id`/`scope`/`created_at` for FE compatibility.

### Rejected

**Expand OpenAPI to the full multi-project disk document.** Would break the
`list[ExportManifest]` route shape and FE history consumers for little gain;
history is already keyed by `project_id` in the path.

## 2026-08-08 — Wave 0 and Wave 1 issue reports retired

The `fix/wave0-sidecar-durability` branch merged into master as `439fd15`,
resolving six deep-review reports. Each is deleted per this repo's issue
convention, which keeps `docs/issues/` as an index of open work only.

Verified before retirement: `make ci` passes on the merged tree, and every
report has a matching integration test in the merge.

### [2026-08-08] Retired: char-fixer maps are not durable

- Old path: `docs/issues/2026-07-21-sidecar-char-maps-not-durable.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/core/labeler_sidecars.py`
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: char range and bbox maps now serialize under
  `labeler_sidecars` in the same `LabelerEdited` content blob as
  `Page.to_dict`, hydrate on load and undo, and re-attach on every content
  save. Evidence: `tests/integration/test_char_sidecar_store_roundtrip.py`.
- Remaining work: none

### [2026-08-08] Retired: rematch GT is not durable

- Old path: `docs/issues/2026-07-21-rematch-gt-not-durable.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/pages.py` (`rematch_gt`)
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: rematch writes a content blob instead of the old no-op
  envelope stub, and returns 503 `store_persist_failed` when the store write
  fails rather than reporting success. Evidence:
  `tests/integration/test_rematch_store_roundtrip.py`.
- Remaining work: none

### [2026-08-08] Retired: save-project reports false clean

- Old path: `docs/issues/2026-07-21-save-project-false-clean.md`
- Outcome: implemented
- Superseded by:
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/save_project.py`
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: the dirty bit clears only after a content blob is written,
  or after a deliberate no-store path. A skipped page and a changelog-only
  save no longer advance the clean marker. Evidence:
  `tests/integration/test_save_dirty_bit.py`.
- Remaining work: none

### [2026-08-08] Retired: word mutations return 200 on store failure

- Old path: `docs/issues/2026-07-21-mutation-store-silent-200.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/words.py`
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: word mutators surface store write failures as 503
  `store_persist_failed` instead of swallowing them behind a 200. Evidence:
  `tests/integration/test_mutation_store_failure_status.py`.
- Remaining work: none

### [2026-08-08] Retired: export list API always empty

- Old path: `docs/issues/2026-07-21-export-list-api-empty.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/export.py` (`list_exports`)
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: `list_exports` reads `doctr-export/manifest.json` from disk
  through `_export_manifests_for_project` and remaps this project's entry to
  `ExportManifest`, replacing the empty stub. Evidence:
  `tests/integration/test_export_list_and_cli_store.py`.
- Remaining work: none

### [2026-08-08] Retired: export CLI is not store-first

- Old path: `docs/issues/2026-07-21-cli-export-not-store-first.md`
- Outcome: implemented
- Superseded by:
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py`
- Resolved by: `439fd15` (merge of `fix/wave0-sidecar-durability`)
- Rationale kept: the CLI opens the SPA event store for page discovery rather
  than scanning envelopes only, and writes the doctr-export manifest after a
  successful run. Evidence:
  `tests/integration/test_export_list_and_cli_store.py`.
- Remaining work: none

### Kept open

`docs/issues/2026-07-21-export-normalize-flag-dead.md` is NOT retired. The
merge fixed its first two defects, the payload drop and the handler ignore,
but the third stands: `ExportDialog.tsx:198` and `BulkActions.tsx:109` still
hardcode `normalize_recognition_labels: false`, so the backend capability has
no UI control. The report is annotated in place.

`docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md` is NOT retired.
The merge landed M11 T1 and T3 only, which its own commit message calls
partial.

## 2026-08-22 — Typography uses current persisted-page epochs

### Context

Legacy character ranges and direct OCR style labels could not provide stable
Unicode grapheme spans, immutable correction history, or safe concurrent
export. Text edits also change stable word identities, so old heads must remain
auditable without satisfying current completion.

### Decision

Use `TypographySection` as the sole inline-typography authoring surface and an
append-only v1 correction journal as review history. The server derives the
structured persisted-page lineage epoch from ordered line and word boundaries,
stable active word IDs, corrected text, geometry, and image/page bindings.
Typography review and correction-bundle export use only active heads rooted in
the current epoch. General export gates on the review result but does not carry
journal heads. Older epochs remain audit-only.

Keep text validation independently achievable. Require both persisted text
validation and required SPA v1 typography review only for final completion and
export. General export freezes content-addressed page JSON and image bytes.
Correction-bundle export separately selects and carries exact reviewed heads.
Retire range routes, direct word-style routes, toolbar style authoring, and
dual writes.

Suggestion acceptance/editing and predecessor-based compensating undo remain
unimplemented and must not be described as shipped.

### Clarification

General export freezes content-addressed page JSON and image bytes, but does not
carry correction heads. Correction-bundle export is the separate artifact that
selects and carries current journal heads and portable provenance. The phrase
“freeze exact reviewed heads” above applies to correction-bundle export, not the
general export job.

## 2026-09-17 — Two product-honesty issue reports retired

Both reports described a surface that looked like it worked and did not. Each
is deleted per this repo's issue convention, which keeps `docs/issues/` as an
index of open work only. Verified before retirement: the full backend, frontend
and browser gates pass on the merged tree.

### [2026-09-17] Retired: `get_page` hid OCR loader failures

- Old path: `docs/issues/2026-08-08-get-page-hides-ocr-failures.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/pages.py` (`get_page`,
  `PageLoadError`)
- Resolved by: `7d15545` (merge of `fix/get-page-hides-ocr-failures`)
- Rationale kept: a loader failure logs at WARNING with `exc_info`, and the
  payload carries a typed `page_load_error` the SPA shows, so a failed page no
  longer looks like a page whose OCR found no text. A missing OCR install is a
  separate `ocr_unavailable` code, warned once per project rather than once per
  page, and the client-facing message names the exception type without its text,
  so server paths do not reach the browser. Evidence:
  `tests/unit/api/test_get_page_load_error.py`.
- Remaining work: none

### [2026-09-17] Retired: canvas erase mode was a no-op

- Old path: `docs/issues/2026-07-21-canvas-erase-mode-noop.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/pages.py`
  (`erase_page_pixels`) and `frontend/src/hooks/usePageMutations.ts`
  (`useErasePagePixels`)
- Resolved by: `fe396c3` (merge of `fix/canvas-erase-noop`)
- Rationale kept: a page-scoped erase route shares one helper with the
  word-scoped route, so the canvas drag erases pixels through the same code the
  right-panel path uses, and it works on a page with no words. The rail no longer
  claims `Shift+E` and `Shift+A`, which the viewport owns, so erase mode can be
  entered from the keyboard. Evidence:
  `tests/integration/test_page_erase_pixels_router.py` and
  `tests/e2e/test_canvas_erase.py`.
- Remaining work: none

### [2026-09-17] Retired: keyboard line navigation moved only the worklist

- Old path: `docs/issues/2026-07-21-match-nav-selection-desync.md`
- Outcome: implemented
- Superseded by: `frontend/src/stores/worklist-focus.ts` (`focusWorklistLine`)
- Resolved by: `f1d227f` (merge of `fix/match-nav`)
- Rationale kept: `j` and `k` used to move `worklistStore.selectedLineIndex`
  while a row click also called `selectLine`, so the canvas, breadcrumb and
  right panel stayed on another line and an action hotkey could act on a line
  the rest of the UI did not show as selected. Both paths now call one
  function, and nothing else writes that index. Evidence:
  `frontend/src/stores/worklist-focus.test.ts` and
  `tests/e2e/test_match_nav_selection_sync.py`.
- Remaining work: none

### [2026-09-17] Retired: the image drift banner could never appear

- Old path: `docs/issues/2026-07-21-image-drift-banner-hard-off.md`
- Outcome: implemented, in the half that a banner can honestly cover
- Superseded by: `src/pdomain_ocr_labeler_spa/api/pages.py`
  (`_image_drift_for_page`, `ImageDrift`) and
  `docs/architecture/08-page-actions.md` §14
- Resolved by: `81a0325` (merge of `fix/image-drift`)
- Rationale kept: the banner was mounted with its flag hard-coded off, and the
  deeper problem was that no part of the backend reported drift at all. The page
  fetch now compares the page's OCR-time image digest against the file on disk,
  comparing size and modification time first and hashing only when those move,
  and the payload carries what changed. A page whose OCR ran on erased bytes
  carries a durable marker on its provenance node, so it is not reported as
  drifted for the rest of its life. Book-labeling projects are skipped, because
  their manifest-verified lease already refuses a changed file. Evidence:
  `tests/unit/api/test_image_drift.py`,
  `tests/integration/test_image_drift_route.py`.
- Remaining work: the save-time half. Nothing yet refuses an edit written
  against an image that changed underneath it; `08-page-actions.md` §14 now says
  so plainly instead of describing it as resolved.

### [2026-09-17] Retired: Cancel marked a job cancelled while the work ran on

- Old path: `docs/issues/2026-07-21-job-cancel-incomplete.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/core/jobs/runner.py`
  (`JobRunner.is_cancelled`), the handlers under `core/jobs/handlers/`, and
  `frontend/src/hooks/useCancelJob.ts`
- Resolved by: `10ba8b6` (merge of `fix/job-cancel`)
- Rationale kept: only the export handler ever noticed a cancel, so cancelling
  an auto-rotate left the book rotating and re-OCRing to the end. Export,
  auto-rotate-all, save-project, propose-page-kinds and propose-regions now share
  one `is_cancelled` check between units of work, finish the page in flight, and
  end with a message saying what they had done. `measure_book` takes a
  `should_stop` hook for the two measuring runs. Cancel is also reachable from
  every place a person starts one of these jobs, which it was not: the overlay
  offered it for two job types, and the toolbar's runs had no affordance at all.
  A best-effort cancel says so rather than implying the work stops at once.
  Evidence: `tests/unit/core/jobs/test_is_cancelled.py`,
  `test_auto_rotate_all_cancel.py`, `test_save_project_cancel.py`, the cancel
  cases in the propose-run handler tests, and `useCancelJob.test.tsx`.
- Remaining work: `rotate_page`, `reload_ocr` and `refine_bboxes` stay
  uncancellable by design, having no unit-of-work boundary to stop at. A
  handler's post-cancel summary still reaches a closed SSE channel, so it is
  shown through a notification toast instead; reaching the live stream would
  mean changing when the job event stream terminates, for every job type.

### [2026-09-17] Retired: the jobs API and its event stream disagreed with their schema

- Old paths: `docs/issues/2026-07-21-jobs-api-openapi-mismatch.md` and
  `docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md`
- Outcome: implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/core/models.py` (`Job`, `JobType`,
  `JobStatus`, `JobResult`) and `core/jobs/runner.py`
  (`JobRunner.to_public_job`)
- Resolved by: `8275e8f` (merge of `fix/jobs-contract`)
- Rationale kept: the routes declared the `Job` model but returned the
  in-process runner's dict, and the event stream emitted a third shape, so the
  generated TypeScript described a response that did not exist and `JobType` was
  missing four job types the runner actually accepts. One adapter now serializes
  both, every frame carries the model plus an `event` naming the frame kind, and
  a typed `result` carries what a handler produced. Two tests keep it honest: a
  handler with no `JobType` member fails, and a payload key a handler writes that
  the public result does not expose fails. Field renames are listed in the
  merge's commits: `job_id` to `id`, `job_type` to `type`, the flat progress
  fields to `progress.current` and `progress.total`, `message` to
  `progress.message`, `error` to `error_message`, the two timestamps to one
  `updated_at`, and the frame's own `type` to `event`. Evidence:
  `tests/unit/core/jobs/test_job_type_contract.py` and
  `tests/integration/test_jobs_wire_contract.py`.
- Remaining work: export stats still appear both flat on the event frame and
  under `result`, kept for older callers; nothing in this frontend reads the flat
  copy. The payload-key test is static, so a key written through a helper in
  another module is still out of its reach, which its docstring says.

### [2026-09-17] Retired: a cold page open looked like a hang

- Old path: `docs/issues/2026-08-08-page-load-progress-unbuilt.md`
- Outcome: implemented, with one stage coarser than the design wanted
- Superseded by: `src/pdomain_ocr_labeler_spa/core/jobs/handlers/load_page.py`,
  `api/pages.py` (`get_page`, `page_load_job_id`) and
  `frontend/src/components/PageLoadStatus.tsx`
- Resolved by: `9768576` (merge of `feat/page-load-progress`)
- Rationale kept: opening a page that was not in the store blocked for up to
  half a minute behind a full-screen spinner reading "Loading project", because
  that overlay was tied to the page fetch. A miss now submits a `load_page` job
  and the fetch returns at once with its id; the job names the store miss and
  the device OCR will run on, and the SPA shows those stages inside the image
  pane while the rest of the shell stays usable. A page already in the store
  still returns immediately and creates no job. Two fetches of the same cold page
  share one job, which keeps the protection against running OCR twice that moved
  out from under the project lock. Evidence:
  `tests/integration/test_load_page_job.py`,
  `frontend/src/pages/ProjectPage.pageLoadProgress.test.tsx`,
  `tests/e2e/test_page_load_progress.py`.
- Remaining work: predictor build and the OCR pass are one stage, not two, because
  `pdomain-book-tools` has no progress callback. The design's open question about
  adding one stays open, as does whether the OCR engine should warm up at server
  start.

### [2026-09-18] Retired: the bbox buttons named actions they did not take

- Old path: `docs/issues/2026-07-21-bbox-refine-crop-misleading.md`
- Outcome: implemented
- Superseded by:
  `frontend/src/components/right-panel/sections/BBoxSection.tsx`,
  `frontend/src/hooks/useBboxRefineTracking.ts` and
  `frontend/src/hooks/useWordMutations.ts` (`useRefineWordBbox`)
- Resolved by: `cb6214f` (merge of `fix/bbox-refine`)
- Rationale kept: Refine, Expand + Refine and Crop all called a plain rebox.
  The first two now submit the real refine job with the matching mode. Crop was
  renamed Expand, because the backend has no crop at all and `expand_only` is
  what the button actually does. Making these real turned a fast local edit into
  a job that takes seconds, which the panel was not built for, so three further
  defects were fixed along the way: a refine result no longer overwrites the
  coordinate field a person is typing in, the job is tracked above the accordion
  that unmounts when collapsed and is tied to the page it started on, and a job
  that never finishes clears itself instead of stranding the controls. Evidence:
  `BBoxSection.test.tsx`, `useBboxRefineTracking.test.tsx`,
  `tests/e2e/test_bbox_refine_buttons.py`.
- Remaining work: only `expand_only` is proven end to end in a browser. The
  other two modes need a page image that a synthetic fixture cannot supply, so
  they are covered by unit tests alone. The fields a resync changes get no
  visual cue.

### [2026-09-18] Retired: the browser suite could pass while proving nothing

- Old path: `docs/issues/2026-07-21-e2e-non-blocking-soft-skips.md`
- Outcome: implemented, local half; the CI half was already moot
- Superseded by: `tests/e2e/conftest.py` (the seeded tiny fixture and the
  skip-budget gate) and `tests/e2e/test_skip_budget_gate.py`
- Resolved by: `fc2be39` (merge of `fix/e2e-fixture`)
- Rationale kept: the tiny fixture's pages were one-pixel placeholders, so every
  test needing word content skipped in every environment, and the suite reported
  success while proving nothing. The fixture now carries real words, seeded the
  way other fixtures seed pages rather than by running OCR; the skips that hid
  gaps are assertions; retired testids were dropped from the driver-contract
  expectations; and a session gate fails a run that skips for a reason outside a
  documented allowlist, scoped so a target whose tests are meant to skip is not
  caught. The GitHub workflows this issue also named were removed on 2026-09-13.
- What it exposed: two real product bugs, both fixed in the same merge. The word
  match list mounted no rows at all once a page had words, because its container
  measured zero height. A metrics chip that only renders when a page has words
  painted over the page-kind button and took its clicks.
- Counts: the suite went from 142 passed, 14 failed, 11 skipped to 151 passed,
  12 failed, 7 skipped. Ten of those failures predate this work and are untouched.
- Remaining work: those ten pre-existing failures, and one deliberately left red
  for a word-edit dialog the driver contract documents but the code does not have.
