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

## 2026-09-18 — The browser suite's long-standing failures, triaged

Ten browser tests had been failing on master for weeks with nobody looking at
them, and two more appeared when the suite's fixtures were given real content.
All were triaged on 2026-09-18 and fixed in `199aa66`. The suite went from 142
passed, 14 failed to 160 passed, 2 failed.

**Eight were stale tests, all from one commit.** `6a04cbe` (2026-08-22, the
grapheme review editor) retired whole-word styling, deleting the component, the
hook and the API route, and made text and typography review a precondition for
validating a word and for exporting. It updated five test files and missed
these eight. Two were deleted because their capability is gone; the rest now
drive the review the product requires.

**Five hotkeys the app advertised did nothing.** `?` and `mod+,` broke at the
2026-09-13 react-hotkeys-hook 4 to 5 bump, which matches on physical key code;
that bump adapted the test fixtures to the new library rather than the product,
and no test pressed a key, so nothing caught it. `mod+o`, `mod+j` and
`mod+shift+r` had never been registered at all. All five now work, and `?` and
`,` match the character a person types rather than a US keyboard position.
`mod+,` also turned out to be split into two dead hotkeys by the library's own
comma delimiter.

**The hotkey help dialog rendered off-screen**, its close button unreachable.
It carried both pdomain-ui's shared `.dialog` transform and Tailwind's
`-translate-x-1/2 -translate-y-1/2`, which this build emits as the `translate`
longhand. Those are separate CSS properties that compose, so the box moved by
twice what was intended. The confirm and source folder dialogs had the same
duplication. Nobody had seen it because the shortcut that opens the dialog had
been dead for five days.

**What this says about the pattern.** Each fix exposed the next: a dead
shortcut hid a broken dialog, blank fixtures hid a list that rendered nothing,
and a test suite that skipped instead of failing hid all of it. Two findings
were filed rather than fixed, in `docs/issues/2026-09-18-*`.

Remaining: `test_word_edit_dialog_testids_present`, tracked in its own issue,
and `test_validate_and_save_keyboard_only`, which passes alone and fails only
under load in this environment.

### [2026-09-18] Retired: the export request's dead normalize flag

- Old path: `docs/issues/2026-07-21-export-normalize-flag-dead.md`
- Outcome: removed, not implemented
- Superseded by: `src/pdomain_ocr_labeler_spa/api/export.py` and
  `core/jobs/handlers/export.py`, which no longer mention it
- Resolved by: `c68661d` (merge of `fix/export-normalize`)
- Rationale kept: `ExportRequest` accepted `normalize_recognition_labels`,
  documented as long s and ligature normalization; the SPA sent it hardcoded
  false, and the handler's normalizer called `core.text_normalize`, which probes
  for a `pdomain-book-tools` module that has never existed. So even the wired
  path was a permanent no-op. No long s or ligature normalizer exists in any
  sibling repo, so making the flag work would have meant inventing a text
  normalization feature to justify an option nobody could use. It was removed
  instead, and `docs/architecture/18-text-normalization.md` now says
  normalization is not offered. Pydantic ignores unknown fields, so a caller
  still sending it gets an ordinary 202, which a regression test pins.
- What it exposed: the normalize capability itself, filed as
  `docs/issues/2026-09-18-text-normalization-waits-on-a-module-...`. A route, a
  probe and a page-text call all wait on that same missing module and report the
  feature as one upgrade away.

### [2026-09-18] Retired: the suite launcher showed nothing and launched nothing

- Old path: `docs/issues/2026-07-21-suite-launcher-app-shims.md`
- Outcome: implemented
- Superseded by: `frontend/src/api/suite.ts`,
  `frontend/src/components/shell/SuiteLauncher.tsx` and `HeaderBar`'s new
  `rightSlot`
- Resolved by: `df005c0` (merge of `fix/suite-launcher`)
- Rationale kept: `App.tsx` passed stubs, so the installed list was always empty
  and every launch answered that it needed host configuration, which the local
  launcher this app runs can never return. Fixing that exposed a second defect:
  `AppShell` only assembles the built-in header that mounts `LauncherSlot` when
  no custom header is passed, and this app always passes one, so working stubs
  would still have shown nothing. The launcher is now rendered explicitly
  through `HeaderBar`. One client with runtime validation serves both the
  launcher and the export dialog, which had its own duplicate fetches. A
  disabled sibling is not offered as a tile, and a refused launch says why.
  Evidence: `frontend/src/api/suite.test.ts`,
  `frontend/src/components/shell/SuiteLauncher.test.tsx`,
  `ExportDialogUtils.test.ts` and `tests/e2e/test_suite_launcher_empty.py`.
- Remaining work: only the empty state is proven in a browser, because no
  sibling app can be installed in this environment. Listing and launching are
  covered at the unit level.

### [2026-09-18] Retired: two tooling reports that time had already answered

Both were verified on 2026-09-18 and neither needed a change.

**Ruff version skew**, old path `docs/issues/2026-08-08-ruff-version-skew.md`.
Fixed the same day it was filed, in `54a05337`, and the fix has held through
later dependency bumps. Both gates now run ruff 0.16.7: the hook pin, the
project floor and the lockfile agree, with a comment in `pyproject.toml` saying
the floor must track the hook. All 53 findings were fixed rather than
suppressed, 51 of them by making FastAPI route handlers keyword-only, and
nothing was added to `docs/process/lint-deviations.md`. Verified today: `uv run
ruff check` is clean, and a full `make pre-commit-check AI=1` over every tracked
file leaves the tree byte-identical, so the hook no longer edits source.

**Dependency refresh cannot auto-land**, old path
`docs/issues/2026-08-08-dep-refresh-cannot-auto-land.md`. It described a failure
mode of `.github/workflows/dep-refresh.yml`, a workflow that had never run. All
GitHub workflows were deleted in `df3f5ff` when the project moved to releasing
from here, so the workflow the report is about no longer exists. If scheduled
dependency refreshes return, the report's warning is worth re-reading in git
history first: a dated branch per run with nothing reconciling a failed week's
leftovers is what produced four stuck pull requests in `pdomain-ui`.

## 2026-09-18 — Project-list metadata: page count yes, progress no (P2-ROOT)

### Context

`docs/issues/2026-07-21-project-list-metadata-filters-noop.md` (P2-ROOT):
`ProjectKey` carried only `project_id` / `project_root` / `label`, so root-page
cards showed permanent `"— pages"` / `"—%"` placeholders and the Active /
Complete / Archived filter chips were wired but inert (no status field to
filter on). The issue asked for two things to be measured before building
anything: what a project's page count and validation progress cost to compute
without opening it, and what "archived" means here.

**Page count** — cheap. It is one extra `iterdir()` per project directory,
counting `.png`/`.jpg`/`.jpeg` files — the same cost class project enumeration
already pays. Measured on this repo's dev fixtures: 20 projects × 50 files,
filesystem-only, ~22ms total.

**Review progress** — expensive, measured rather than assumed. "How many pages
are validated/reviewed" only exists in the per-project `.pd-pages/` event
store (`core.persistence.page_store.LabelerPageStore`, an
`eventsourcing.sqlite`-backed `PagesApplication`); there is no lighter-weight
summary field maintained anywhere. A `ProjectAggregate.get_project()` read is
cheap (~1ms even at 200 pages), but it only returns the page-id list — nothing
about which pages were edited. Determining "reviewed" requires reading each
page's `PageAggregate` and checking its changelog. Measured on the same
fixture shape: opening a fresh `LabelerPageStore` and walking every page for
one 200-page project cost ~35ms; 20 projects × 50 pages, all cold, cost ~206ms
total (vs. ~22ms for page-count-only on the same fixture) — and that cost
scales with total pages across every project in the list, on every
`GET /api/projects` call. `write_project_json` (which would let a cached
`Project.saved_pages` value stand in for this) is fully implemented but is
never called anywhere in this codebase today — wiring a save-time cache is a
distinct, larger change to `core/jobs/handlers/save_project.py`'s behavior,
not a drive-by addition to a list-metadata fix.

**"Archived"** — undefined. `grep -rni archiv` over `src/` turns up nothing
that defines project-archive semantics; the per-card "Archive" menu stub was
already removed in an earlier change with the same rationale ("no archive
endpoint or project-status field in the API; re-add it once the semantics are
specced (needs-spec, parity C14)", `frontend/src/pages/RootPage.tsx`). PGDP
item 9 tracks the semantics decision and is explicitly out of scope here.

### Decision

1. Ship `ProjectKey.page_count: int | None` (`core.project_enumeration.
   EnumeratedProject.page_count` underneath), computed by directory scan. A
   directory that can't be read (permission error, removed mid-scan) degrades
   that one entry to `None` rather than failing the whole list —
   `core.project_enumeration._count_pages` catches `OSError` per project.
2. Do **not** ship progress this iteration. No field, no computed value, no
   fake percentage. The root cards drop the progress bar entirely instead of
   leaving it permanently at a placeholder 0%.
3. Remove the Active / Complete / Archived filter chips rather than wire them
   to page-count-only data that can't honestly represent any of the three:
   "archived" has no definition anywhere in this codebase, and "complete"
   needs the progress data item 2 deliberately does not compute. Only the
   text-search filter (label / project_id / project_root) survives, and it
   already worked correctly before this change.

### Consequences

- `GET /api/projects` and `POST /api/projects/source-root` responses gain
  `page_count` (nullable); `frontend/src/api/types.ts` regenerated via
  `make openapi-export`.
- Root-page cards show a real page count (`"N pages"` / `"1 page"`) or "Page
  count unavailable" for the unreadable case — never a placeholder dash.
- The filter-chip row (`root-filter-chips` and its four `root-filter-chip-*`
  testids) no longer renders. Re-adding Complete/Archived filtering needs
  either PGDP item 9 (archive semantics) or a follow-up progress-cost decision
  (cached `saved_pages`, a cheaper progress proxy, or an explicit "OK to be
  slow" call) — not a repeat of this measurement.
- `docs/issues/2026-07-21-project-list-metadata-filters-noop.md` stays open:
  its "Defects to fix" items 1–3 are addressed (page count exists, cards show
  it, dishonest chips are gone); item 4 (status field for Active/Complete/
  Archived filtering) is intentionally still open pending the archive-semantics
  decision this entry does not make.

### Review follow-up (same day): shape detection, and a cost caveat

A reviewer found the first cut of `page_count` counted only top-level image
files, which is one of three project shapes this repo supports. A
`book-labeling-manifest.json` project (a materialized typography book) stores
each page under its own per-page materialization directory, and a
`labeling-bundle.json` project (a single-page portable review bundle) embeds
its one image in a descriptor — neither keeps top-level image files. Both are
selectable from the same source root as an ordinary filesystem-image project.
The top-level-only scan therefore reported `page_count: 0` for a real,
possibly-hundreds-of-pages book: a confident wrong number, worse than the dash
it replaced.

Fixed by detecting the same three shapes `api.projects.load_project` already
detects, in the same order, in `core.project_enumeration._count_pages`:

1. `book-labeling-manifest.json` present → `len(manifest.pages)`, read from
   that one JSON file only (NOT `load_book_labeling_manifest_directory`,
   which additionally opens one directory per page and hashes every
   match-graph file — O(pages) filesystem opens that would defeat the point
   of a cheap list scan). A present-but-malformed manifest degrades to
   `None`, same as an unreadable directory — never a wrong count.
2. `labeling-bundle.json` present → always `1`. `LabelingBundle` has exactly
   one `page_id` / `image_sha256` by construction, so this is a structural
   fact of the shape; the file doesn't need to be opened at all.
3. Neither present → the original top-level image-file count.

Tests: `tests/unit/core/test_project_enumeration.py` covers all three shapes,
a malformed manifest, manifest-wins-over-bundle precedence, and a
manifest-backed project with a known 300-page count (the reviewer's exact
repro shape). `tests/integration/test_projects_router.py` covers the same two
non-default shapes end to end through `GET /api/projects`. A further test
covers the unreadable-project case failing partway through the per-entry scan
(a per-file `is_file()` raising, not just the directory `iterdir()` itself) —
the code already handled that correctly (one `try` wraps the whole scan), but
nothing had proved it before.

**Cost caveat, unchanged by the shape fix:** the scan is uncached — every
`GET /api/projects` call re-walks every project from scratch — and its
aggregate cost scales with the total number of files/pages across every
discovered project, not with the number of projects. One project with 10,000
loose top-level files costs about the same as 200 projects of 50 files each.
Fine at today's measured scale (~22ms for 20 projects × 50 files); revisit if
a source root's total file/page count grows much larger, or if
`GET /api/projects` starts being called often enough (e.g. polling) for
per-call cost to matter.

## 2026-09-18 — Project-list progress: shipped, once the counts journal made it cheap (progress-P2-ROOT-followup)

### Context

The P2-ROOT entry above deferred progress because the only source at the
time was a live per-page event-store walk — ~200ms for a 20-project, 50-
page-each fixture, scaling with total pages across every project on every
`GET /api/projects` call. Two things changed since: `core/review_counts.py`
landed a `WordReviewCountsJournal` — one small per-project JSONL file,
written where a page is already saved, read back with `latest_by_page()` —
and archive semantics were decided closed ("the labeler has no archive",
same day, below), which is what let the Active/Complete filter chips come
back without an Archived third.

### Decision

1. `EnumeratedProject` (`core/project_enumeration.py`) and `ProjectKey`
   (`api/projects.py`) both gain `progress: ProjectProgress | None`,
   following `page_count`'s precedent for failure exactly: a project whose
   journal can't be read degrades that one entry's `progress` to `None`,
   never the whole list.
2. `progress` is `None` — not a `ProjectProgress` with zeros — whenever
   there is no honest number: a `book-labeling-manifest.json` or
   `labeling-bundle.json` project (neither ever writes to this journal;
   they validate through `ImportedTextValidationLog` instead of
   `save_page_content_to_store` — `api.review_queue`'s `_word_entry` drew
   the same line first), an unknown `page_count` (no denominator), an
   unreadable journal, or a journal with no rows yet. That last case is the
   ruling this entry is built around: a project that has never had a page
   saved since the journal existed is unknown, not 0% — it is modeled the
   same as an unavailable page count, and the root card says "Progress not
   tracked" rather than showing a bar at 0.
3. Partial coverage is never silently collapsed into a percentage over the
   counted subset. `ProjectProgress` carries `pages_counted`,
   `pages_not_counted`, and `is_lower_bound` — the same shape
   `api/review_queue.py`'s `ReviewQueueKindEntry` already uses for the same
   problem — and the card renders "N% of M tracked pages · K not yet
   tracked" instead of a bare percentage whenever `pages_not_counted > 0`.
4. **Complete** means every page counted (`pages_not_counted == 0`) AND
   every counted word validated AND at least one word counted — never
   `True` over a subset. A project complete over 40 of its 300 pages is not
   complete; it is `pages_not_counted: 260, complete: false`.
5. The Active / Complete filter chips (removed by P2-ROOT above) come back.
   No Archived chip — that is not a gap, it is "the labeler has no archive"
   (below) made permanent. "Active" is the complement of "Complete", not of
   "has some progress" — a project with unknown progress counts as Active,
   because unknown progress is not proof of completion either.

### Cost, measured before committing to this design

Reading one project's journal costs about the same order of magnitude as
the `page_count` scan it sits next to: ~2.6ms/project for 20 projects of
300 pages each in the journal's steady state (one row per page, ~51ms
total), ~2.3ms/project at 200 projects (~454ms total). A journal sitting
right at its own pre-compaction ceiling (`WordReviewCountsJournal` compacts
past 10 rows per page) costs substantially more — ~37ms/project for the
same 20-project fixture (~738ms total) — because every extra row is parsed
and discarded on every read until the next append triggers compaction.
End to end, through the real `GET /api/projects` route (`TestClient`, not
just the journal read in isolation): ~58ms/call for 20 projects × 300 pages
with `page_count` alone, ~143ms/call with `progress` added — call it
+85ms, or about +4ms/project, at a fixture size an order of magnitude
above anything this repo's dev fixtures have needed so far. Acceptable at
today's scale; revisit together with `page_count`'s own cost caveat if
either the per-call cost or the compaction ceiling becomes a problem in
practice, e.g. if `GET /api/projects` starts being polled.

### Tests

`tests/unit/core/test_project_enumeration.py` — no journal (unknown, not
zero), full coverage complete, full coverage not-yet-complete, partial
coverage (lower bound, never complete), `pages_not_counted` clamped at 0
rather than going negative, page-count-unknown forces progress unknown too,
journal-read failure degrades one entry, both non-journal shapes stay
`None` even with a stray journal file present, and the dataclass is frozen.
`tests/integration/test_projects_router.py` — the same cases through
`GET /api/projects` and through `POST /api/projects/source-root` (which
was serializing `ProjectKey` by hand; switched to `model_dump` so a future
field addition can't go missing from that route the way `progress` would
have had to be added twice otherwise). Frontend: `RootPage.test.tsx` covers
all four card states ("not tracked", validated percentage, "Complete", and
the partial lower-bound caption) and the Active/Complete/no-Archived filter
behavior, including that "Active" includes unknown-progress projects.

## 2026-09-18 — Glyph annotations reuse the char-sidecar durability path (Wave 2 T3)

### Context

`specs/20-glyph-annotations.md` §4 still describes durable glyph persistence
as a `UserPageEnvelope` schema bump (v2.1 → v2.2), keyed by stable `word_id`,
written by `core/persistence/user_page_envelope.py`. That envelope lane was
retired by the M5b event-store adoption, before this task started — §4 is
stale text describing a carrier that no longer exists, not a live design.

The 2026-07-21 "Char sidecar durability (Wave 0.1)" decision above already
anticipated this and reserved the slot: *"Glyph annotation maps stay out of
scope until Wave 2 T3; they will reuse this key when implemented."* By the
time this task started, `PageState.glyph_annotations_map` was already wired
into `LabelerSidecars` (`core/labeler_sidecars.py`) alongside
`char_bboxes_map`, and `set_glyph_annotations` / `accept_glyph_prediction`
already called `_save_to_store_best_effort` (the same content-blob write
`char-bboxes` and word-validation mutations use). The one gap: the bulk-mark
route (`POST .../pages/{idx}/glyph-bulk-mark`) still called
`_write_cached_envelope_best_effort`, a no-op STUB left over from the retired
envelope lane, so bulk-applied marks vanished on reload even though
single-word marks already survived it.

### Decision

**Strategy A — reuse the Wave 0.1 `labeler_sidecars` content-blob key, not a
new envelope schema bump.** No new decision was needed for the single-word
routes; this entry exists to record that Wave 2 T3 finished the bulk-mark
route the same way:

1. Keyed the same as `char_bboxes_map`: `"{line_index}_{word_index}"`, not
   the spec §4 `word_id` shape. Rehydration on load already restores both
   maps together (`apply_sidecars_to_page_state`); no new load-path code
   needed.
2. Fixed `glyph_bulk_mark` to call `_save_to_store_best_effort` (writes the
   content blob) instead of the retired `_write_cached_envelope_best_effort`
   STUB, and to surface a 503 `store_persist_failed` on write failure —
   matching every other word/page mutation route's contract instead of
   silently dropping the write.
3. Removed the now-dead `_write_cached_envelope_best_effort` STUB from
   `api/pages.py` (its only caller); `api/words.py` keeps its own
   identically-named backward-compat no-op for an unrelated
   `lines_paragraphs.py` import.
4. `glyph_bulk_mark` also returned a hand-built `JSONResponse(content=
   response.model_dump())` (no `mode="json"`), which raised
   `TypeError: Object of type UUID is not JSON serializable` on any non-empty
   apply (`page.page_record.page_id` is always a UUID). Fixed by returning
   the declared `GlyphBulkMarkResponse` model instance directly — the same
   fix `324fb8b` applied to `/api/jobs` ("Routes return typed Job/list[Job]
   instances instead of a raw JSONResponse dump, so response_model actually
   validates them").

### Consequences

- Glyph annotations share one blob and one undo/redo story with char bboxes;
  no second `word_id`-keyed carrier, no envelope schema bump, no legacy
  `pd-ocr-labeler` compatibility question to resolve.
- `specs/20-glyph-annotations.md` §4 is not rewritten by this entry — it
  remains a historical description of the retired envelope plan. Read this
  decision instead of §4 for how glyph durability actually works.
- Predictions (`glyph_predictions_map`) are still never persisted — this was
  already true and remains correct (spec §4.2, §9): they are recomputed at
  payload-build time, not carried in the content blob.

### Tests

`tests/integration/test_glyph_routes.py` — set/clear/accept/bulk-mark HTTP
round trips (Task 2) plus fresh-store reload coverage for all three
`glyph_annotations` tri-states (absent / empty-reviewed / populated) and for
bulk-mark apply specifically (Task 3, the STUB this entry fixes).

### [2026-09-18] Glyph annotations: the review path works, the predictor does not exist

- Issue: `docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md`, narrowed
  rather than retired
- Resolved by: `0f8f20b` (backend) and `c0cbf76` (frontend)
- What was wrong: annotations reached in-memory maps and stopped there, the
  panel was never mounted, the mutation hooks did not exist, and a bulk apply
  did not refresh the page it had just changed. Worse than unsaved: every
  non-dry-run bulk apply raised on the page id it could not serialize, so the
  feature failed outright. Verified against the pre-fix commits.
- What works now: select a word, mark its ligatures, long s or swash, or mark it
  reviewed with no marks. The mark reaches the server, comes back on the next
  read, and survives a save and reload, carried by the same content-blob sidecar
  the character maps use. A bulk apply persists and refreshes the page.
  `tests/e2e/test_glyph_panel.py` drives it and checks the server, not the
  screen.
- What is still scaffolding: nothing produces glyph predictions. `IGlyphPredictor`
  is unwired, so the accept button cannot fire for anyone. That is Task 10 of
  `docs/plans/2026-07-21-glyph-annotations-completion.md`, and the plan now says
  so where a reader will meet it.
- One naming call: the panel sits in a "Glyphs" accordion item, not the plan's
  "Typography", because a separate typography review feature already owns that
  label. Two adjacent items named Glyphs and Typography is the state; whether
  that reads well to a person reviewing a word is worth a look.

### [2026-09-18] Decided: the labeler has no archive, and delete stays permanent

- Question: what "archived" means for a project, the last thing standing between
  the project list and a working status filter.
- Decision: there is no archive. Delete remains permanent, behind its
  confirmation. No archive API, no archived status, no archived filter.
- Why: `docs/plans/2026-07-21-pgdp-alignment-remaining.md` item 9 already reached
  this conclusion and says plainly "do not build archive API"; it was never
  recorded anywhere durable, so the question kept coming back. A reversible
  archive is a stage tool from the PGDP submit workflow, and this product labels
  pages rather than managing a submission pipeline.
- Already done: the Active, Complete and Archived chips were removed on
  2026-09-18 in `3200aa7`, so nothing in the product advertises a status it
  cannot offer.
- What this unblocks: nothing further is owed for archive. Project progress is a
  separate question and now has a cheap answer that did not exist when it was
  deferred: the per-page counts journal added in `f175297` carries validated and
  total words per page, so a project's progress is one small file read rather
  than a parse of every page.

### [2026-09-18] Retired: the per-word validate button could never validate a word

- Report: `WordFooter`'s validate button was disabled until the page's typography
  review was complete, and completion required every word on the page already
  validated. The first unvalidated word on any page had no sequence of clicks
  that worked, so the button functioned only as a one-shot unvalidate.
- Decision: gate the validate direction on that word's own grapheme review, not
  the page's. Option 2 of the issue.
- Why: the gate's intent reads as "do not validate a word whose graphemes nobody
  has looked at", and that intent survives at word scope without the
  circularity. Dropping the gate entirely would discard the intent; keeping the
  page gate and removing the button would leave per-word validation to bulk
  paths that check nothing at all.
- How: a new `typography_reviewed` field on `TypographyHeadResponse`, the one
  per-word endpoint that works for ordinary projects as well as bundles. It is
  computed by `_typography_reviewed`, extracted from the inline rule
  `typography_page_review` already used, so the per-word gate and the page-wide
  count cannot drift apart. `_current_head` epoch-filters the correction before
  the check, so no separate staleness test is needed there.
- Deliberately excluded: the page rule's other half, `text_reviewed`. For an
  ordinary project that means "carries the `validated` label", which is the same
  flag the button toggles. Gating on it would rebuild the same circularity at
  word scope.
- Still open, and pre-existing: the toolbar's page-scope validate batch and
  `LineDetail`'s line-scope batch check nothing. A word can still be bulk
  validated with no typography review at all. They ignored the old page gate
  too, so this change neither introduces nor worsens it, but the intent is now
  enforced on one path and not the others.
- Shipped in `f42179b`.

### [2026-09-18] Retired: text normalization waited on a module that never existed

- Old path:
  `docs/issues/2026-09-18-text-normalization-waits-on-a-module-that-has-never-existed.md`
- Outcome: removed, not implemented
- Superseded by: `docs/architecture/18-text-normalization.md`, now titled "Not
  offered"
- Resolved by: `fix/normalize-remove` (branch)
- Rationale kept: `core/text_normalize.py` probed for
  `pdomain_book_tools.text.normalize.normalize_string`, a module that has
  never existed in any version of `pdomain-book-tools`. `is_available()` was
  therefore permanently `False`, `GET /api/normalize/available` existed only
  to report that probe, the SPA's OCR config modal gated its "Text
  normalization" section on the route, and `api/pages.py`'s plaintext-tab
  renderer called `normalize_string` behind a flag every caller already
  hardcoded to `False`. All four had zero effect: deleting them changes
  nothing observable. This is the same defect this repo already retired once
  for the export request's `normalize_recognition_labels` flag
  (2026-09-18, above) — that fix left the probe and the UI gate in place,
  which is what this entry removes. A real normalizer exists upstream
  (`pdomain_book_contracts.text.text_normalize.apply_text_normalizations`),
  but it does curly quotes and em dashes, not the long s and ligatures this
  capability's comments described, and this product transcribes historical
  text to ground truth — rewriting punctuation by default is the wrong
  product decision, not a missing import.
- Removed: `src/pdomain_ocr_labeler_spa/core/text_normalize.py`,
  `src/pdomain_ocr_labeler_spa/api/normalize.py` and its router registration
  in `bootstrap.py`, the `normalize_string` call and `normalize_tabs`
  parameter in `api/pages.py::_render_plaintext`, the OCR config modal's
  "Text normalization" section and `NormalizeSettings` type in
  `OCRConfigModal.tsx`, and the tests that existed only to cover the probe
  or the route (`tests/unit/test_text_normalize.py`,
  `tests/integration/test_normalize_router.py`). `PagePayload` field tests
  and the unrelated `ExportRequest` normalize-field regression tests moved to
  `tests/unit/test_page_text_and_export_fields.py`.
- Left in place, flagged as a separate finding: `AppConfig.
  normalize_for_gt_matching`, `normalize_plaintext_tabs`, `normalize_profile`
  (unread by any handler) and `WordMatch.normalized_match` (never set `True`,
  never rendered). These predate this capability and are not wired to it;
  removing them is a distinct decision nobody has made.
- `GET /api/normalize/available` was a public route with no known external
  caller — checked via this app's own git history and the driver-agent
  contract (`docs/architecture/13-driver-contract.md`), neither references
  it outside the now-removed `OCRConfigModal.tsx` probe.

### [2026-09-18] Decided: the labeler will not build a glyph predictor

- Question: Task 10 of `docs/plans/2026-07-21-glyph-annotations-completion.md`.
  `IGlyphPredictor` has one implementation, `NoneGlyphPredictor`, which returns
  `None` for every word, so the accept-prediction affordance can never fire.
  `specs/20-glyph-annotations.md` names `pd-ocr-trainer` as the producer of the
  real adapter. That repository is retired.
- Decision: no predictor will be written here, and the seam stays. What changes
  is the roadmap, which had been waiting on a repository that no longer exists.
- What the search found, on 2026-09-18:
  - A predictor over OCR codepoints is a few lines, and would fire on nothing.
    Scanned the only real project store on this machine, 2,722 OCR words across
    18 pages: zero contain U+017F or any of U+FB00–U+FB06. DocTR does not emit
    those forms on this corpus, so a text scan has no signal to read.
  - `pdomain-pgdp-measure` is a pinned dependency and does not classify glyph
    type. Its `glyph_shape.py` says so itself: it flags ink unlike a
    character's usual shape and "never reads or proposes a label". No
    occurrence of ligature or swash anywhere in its source. Its `glyphs` CLI is
    an offline corpus tool that needs a finished PGDP alignment as input.
  - `pdomain-ocr-training`, which supersedes `pd-ocr-trainer`, consumes glyph
    features rather than producing them, and has no classifier planned.
  - `pdomain-book-tools` defines the annotation schema and no detection logic.
- Cost of keeping the seam: near zero, and unlike the normalization probe it
  advertises nothing to a person. The chips and the accept button render only
  when a prediction exists, so today they render nothing. `glyph_predictions`
  is already threaded from `ProjectState` through to `WordMatch`; the map is
  simply never written.
- What to do instead: make the human marks pay off downstream. See the next
  entry.

### [2026-09-18] Decided: the labeler's dataset export writes the glyph-feature sidecar

- Question: `pdomain-ocr-training`'s `docs/context/intent-map.md` carries this
  under "Needs owner decision" — whether dataset export or the trainer SPA
  writes the glyph-feature JSON sidecar that lets recognition eval slice CER
  and WER by ligature, long s and swash.
- Decision: the labeler's dataset export writes it.
- Why: the export is the only place where both facts exist at the same moment,
  the person's glyph annotations for a word and the recognition crop filename
  that word becomes. The trainer SPA would have to rebuild that join from
  nothing. The contract is `dict[crop_id, {ligatures, long_s, swash}]` keyed by
  the DocTR recognition val-set label key, defined by `GlyphFeatureSet` in
  `pdomain-ocr-training`'s `protocols.py`.
- One rule the shape imposes: a crop absent from the sidecar means unknown, not
  feature-free. `_emit_glyph_slices` excludes an absent crop from both the
  positive and the negative set. So only a word somebody actually reviewed gets
  an entry; writing all-false for an unreviewed word would assert the absence of
  something nobody checked.
- What this unblocks: the manual glyph path stops being a dead end. A person's
  marks reach recognition eval without any classifier existing.

### [2026-09-18] Retired: a selection jumped to another item on page change

- Report:
  `docs/issues/2026-09-17-a-word-or-line-selection-jumps-to-another-item-on-page-change.md`
- Decision: `SelectionPath` carries the page index it was selected on, and a
  selection whose page disagrees with the loaded page resolves as empty. Option
  2 of the issue.
- Why this over clearing on page change: the store is untouched, so paging back
  restores what was selected. Clearing would have thrown the selection away.
- Found while wiring it, beyond the issue's list: the toolbar's batch dispatch
  and the style and component apply buttons read the raw store, so an action
  taken after paging away could batch-mutate the new page's lines under the old
  page's selection. Those now resolve through the same guard.
- Regions were left alone. They already clear outright on page change through
  their own effect and were never promised the return-and-find-it behaviour.
  Unifying them onto this mechanism is a follow-up, not a defect.
- Shipped in `0da64f9` and `5e31506`.

### [2026-09-18] Retired: the word edit dialog the driver contract documented

- Report:
  `docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md`,
  rewritten rather than deleted, because part of it survives.
- Decision: retire the dialog. Driver contract section 2.11 records it as
  retired, the contract test asserting its testids is deleted rather than
  weakened, and the 18 dialog-scope hotkey entries go along with the scope
  itself.
- The pencil now does what its own docstring said it should: select the word
  and open the right panel. `WordDetail` already covers the ground the dialog
  was meant to.
- What survives, narrower: word merge has no home. `ToolbarActionGrid`'s word
  scope map has no merge key, so `toolbar-word-merge` is a permanent stub cell.
  The issue now covers only that, and needs a ruling on both the surface and
  the merge semantics.
- Shipped in `f06d5eb`, `b681caa`, `0b30628`, `8d83d21`.

### [2026-09-18] Retired: the typography count had no answer on a real book

- Report: `docs/issues/2026-09-18-typography-numerator-needs-a-per-page-rollup.md`
- Decision: write a per-page rollup where a correction is accepted, and drop
  the 512 KiB availability ceiling entirely.
- Why it was needed: the route read the whole book's corrections journal and
  parsed every row into a pydantic model, about 80 microseconds a row. Measured
  143 ms at 10% coverage and 1,521 ms at full coverage. The ceiling was honest
  but meant a book with real correction history could never get a count.
- Keyed by `logical_page_id`, not `page_index`. Typography corrections are
  addressed by the project's or the bundle's own page identity, so keying by
  the labeler's page ordinal would have mis-keyed every bundle project's rows.
- The count is recomputed from that one page's corrections at write time rather
  than carried as a delta, so a revision that drops a word below the
  completeness bar lowers the next row. One page's rows is cheap; the whole
  book's is the thing being avoided.
- A page with corrections but no rollup row is excluded from the totals and
  counted in `pages_not_counted`, the same treatment the word kind gives a page
  it has never saved. A book corrected before this existed therefore reads as
  incomplete rather than as a confident zero.
- Staleness is still not checked, unchanged from before, so typography's
  outstanding count remains a floor and `is_lower_bound` stays true.
- `core.typography_review.reviewed_word_keys` is deleted; it had no other
  caller once the route stopped reading the raw journal.
- Shipped in `f6f180a`.

### [2026-09-18] Retired: project list metadata and its inert filter chips

- Report: `docs/issues/2026-07-21-project-list-metadata-filters-noop.md`
- All four of its defects are now answered, across two decisions the same day.
  Items 1 to 3, page count and honest cards, were settled in the entry
  "Project-list metadata: page count yes, progress no". Item 4, a status to
  filter on, is answered by the progress entry above it.
- Item 4 had been waiting on two things that both arrived today: the archive
  decision, which removed Archived from the question entirely, and the per-page
  counts journal, which made progress cheap enough to compute. Neither existed
  when the earlier decision deliberately declined to ship progress.
- What the chips are now: Active and Complete, where Complete means every page
  counted and every counted word validated. A project whose progress is unknown
  counts as Active rather than vanishing from both chips, because Active is the
  complement of Complete and not of "has some progress".
- One cost to watch, measured and recorded in the progress entry: a journal
  sitting at its pre-compaction ceiling of ten rows a page costs about 37 ms a
  project to read, against 2.6 ms in the steady state, because every stale row
  is parsed and discarded until the next append compacts it. At 200 projects
  that is the difference between half a second and seven. Nothing is wrong
  today; it is the number to look at first if the list ever feels slow.

### [2026-09-18] Retired: two migrated GitHub issues that were already implemented

- Both records carried `status: implemented` and `Resolution: Implemented
  locally` since their 2026-07-19 export, and both had sat in `docs/issues/`
  ever since, where the index reads as open work. They were resolved records
  filed in the open drawer.
- `2026-05-22-gh-437-openapi-schema-quality.md`: the repository enforces the
  OpenAPI response contracts the original report asked for. Nothing remained.
- `2026-05-23-gh-460-resolver-narrowing.md`: asked to replace casts once
  `PageRecord` landed. Resolvers use `isinstance(payload, Page)` with a guarded
  structural `.lines` fallback, and the repository accepted and documented that
  nominal-plus-structural policy. Pure nominal narrowing failed 52 tests,
  because the suite deliberately uses duck-typed stub pages; the fallback keeps
  those working without loosening the public return type.
- Their upstream GitHub issues were still open at export and this does not
  close those. The local records are what is retired.

### [2026-09-18] Retired: word merge had nowhere to live

- Report:
  `docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md`,
  rewritten earlier the same day to cover only word merge after the dialog was
  retired.
- Decision, and it was mine: merge lives on the toolbar's word scope cell over
  a two-word selection. Text concatenates with no separator, because the reason
  a person merges is that OCR split one word. The boxes union. The merged
  content takes the first word's slot. The surviving word becomes the
  selection.
- Refuse rather than orphan: if either word carries char bboxes, glyph
  annotations or typography corrections, the merge is declined with a reason.
  Those are review work nobody can get back, and the common case, fixing a raw
  OCR split, happens before anyone annotates.
- Where my framing was wrong, corrected by the implementer: the issue said word
  merge had nowhere to live, and the right panel's `StructureSection` already
  had a live merge-with-prev-next feature with its own endpoint. It expresses
  "these two" by adjacency rather than by selection. The toolbar cell is a
  second surface for the same operation, not the only one.
- A live data-loss bug found and fixed on the way: that existing route
  delegated to `pdomain-book-tools`' `merge_word_left` and `merge_word_right`,
  which clear `ground_truth_text` for **every word in the line**, not just the
  merged pair. Anyone using those buttons lost the line's ground truth. Both
  routes now share one core built on `Word.merge` directly, which does not do
  that.
- One detail the ruling got wrong about identity: typography's `word_id` is
  derived from reading order and text rather than stored, so a merged word
  cannot literally keep the first word's id. Nothing in this codebase makes
  that possible. The refusal check means neither word has typography history
  before a merge proceeds, so it costs nothing.
- Still open, found while doing this: `delete_words_batch` does not reindex the
  char bbox or glyph annotation maps after removing a word, so later words in
  the line inherit the wrong sidecars. Word merge reindexes; delete does not.
- Shipped in `3ee93c6`.

### [2026-09-18] Retired as moot: the two GitHub CI issues

- Reports: `docs/issues/2026-05-22-gh-430-ci-equivalence.md` and
  `docs/issues/2026-05-22-gh-433-openapi-drift.md`.
- Both describe `.github/workflows/ci.yml`. That file, and every other workflow
  in the repository, was deleted on 2026-09-13 in `df3f5ff` by owner request,
  with branch protection turned off at the same time. Nothing runs on GitHub
  automatically any more.
- So 430, "GitHub CI does not run every check in `make ci`", is answered
  trivially and permanently: GitHub CI runs nothing, in either direction. And
  433's ineffective diff target has no file left to live in.
- Implementing either would have meant recreating GitHub Actions CI to satisfy
  issues about a workflow the owner deliberately killed. The implementer
  stopped and reported rather than building through the wrong premise, which
  was the right call. Same treatment as the two sibling reports already retired
  this way, `2026-08-08-dep-refresh-cannot-auto-land.md` and the CI half of
  `2026-07-21-e2e-non-blocking-soft-skips.md`.
- 433's reasoning was verified anyway, since it would still apply if CI ever
  returns. `frontend/openapi.json` is gitignored and never tracked, so a
  `git diff` against it cannot fail. A probe field added to a request model and
  exported showed up in `frontend/src/api/types.ts` and changed the diff's exit
  code; adding `openapi.json` to the same command changed nothing. No class of
  schema change was found that reaches the backend and not the types file. If a
  drift gate is ever rebuilt, check the types file and drop the other target.
- `docs/plans/2026-07-21-ci-openapi-gates.md` predates the removal and still
  tells a reader to edit `ci.yml`. Corrected alongside this.
- Found at the same time and unrelated to either issue: `make ci AI=1` is red
  on master at `frontend-knip`, on eight pre-existing unused exports and
  exported types. Everything before it in the chain passes.

### [2026-09-18] Retired: the M11 glyph usable path

- Report: `docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md`, open
  since July and narrowed twice today.
- Everything it named is now closed. The review path shipped earlier; the three
  residuals it still carried were closed in this pass, and the predictor
  question was answered by deciding not to build one.
- Task 8, the `glyphs_reviewed` metric and the `glyph_review_incomplete` save
  warning, had never been verified by anyone. Both turn out to be correct. The
  metric reads the tri-state properly, counting a word reviewed whether it
  carries marks or an empty annotation object, and the warning counts against
  the same map the payload reads, so the number a person sees and the number
  that raises the warning cannot drift. Three integration tests now hold it.
  This was the one gap that might have been a defect and was not.
- Task 9's bulk glyph mark browser test was called for and never written. It
  now opens the real dialog, previews, confirms the dry run mutated nothing,
  applies, and then makes an independent GET to prove the mark reached the
  server and that the recipe's selectivity ran: the word containing a ct
  ligature carries it, the word without stays null.
- Reject-prediction had no test anywhere. I ruled that rejecting stamps
  reviewed-with-no-marks, because a person who rejects has looked at the word
  and judged it carries no such mark, and treating reject as ignore would leave
  it unreviewed and ask the same question forever. The code already did that,
  so nothing changed. The test sits beside accept's, because with no predictor
  nothing can plant a prediction for a browser to reject.
- Deliberately left open, and not worth an issue: the canvas predictions
  overlay and per-mark rather than wholesale accept, both of which only matter
  once predictions exist; ligature-kind parity in Task 5 Step 3; and whether
  two adjacent accordion items named Glyphs and Typography read well to a
  person reviewing a word. That last is cosmetic feedback with no defect
  behind it, and renaming without seeing the two panels side by side would be
  churn.

## 2026-09-18 — Per-word sidecars did not follow their words

### What was wrong

`PageState.char_bboxes_map`, `glyph_annotations_map` and `glyph_predictions_map`
are keyed `"{line_index}_{word_index}"`. Every structural edit that changes a
word's position shifts those indices, and until today nothing re-keyed the maps.
So a person's hand-drawn character boxes and glyph marks silently moved onto
neighbouring words. Nothing was lost and nothing errored, which is why it
survived this long.

Eleven routes were affected. Found in sequence, each fix exposing the next:
word delete, then line delete and merge, paragraph delete, merge and split,
line split, both extract-words-to-new-line routes, group-words-to-paragraph,
word split, and word add.

### How each is fixed, and why they differ

- **Word delete** uses a formula: words shift within one line, and
  `Page.delete_words` documents removing highest index first, so a batch
  replays in that order. Word operations never reorder within a line, so a
  formula is honest here.
- **Line and paragraph operations** use an identity snapshot: record each word's
  key by object identity before the mutation, look again after, and re-key to
  wherever the word actually went. This exists because my proposed formula was
  wrong and the implementer said so. `Block.merge` extends the word list and
  then re-sorts by x position, so merged words interleave rather than append and
  no offset describes where one lands.
- **Word split refuses** when the word carries any sidecar entry. Splitting
  destroys the original word object and creates two new ones, so neither
  approach can say where its entries belong. Dividing character boxes at a split
  point is a real feature with its own design. Later words in the line still
  reindex.
- **Word add** needs no refusal. It constructs one new word and re-sorts;
  no existing word object is replaced, so the snapshot carries all of them.

### What this cost, and the pattern worth keeping

Every one of these was found by writing a failing test first and watching it
fail for the predicted reason. Four of five word-delete tests failed on the
first run with exactly the symptom predicted; the line-level tests showed a
deleted line's own entries surviving under their old keys.

The family is closed: all six shifting routes reindex, and rebox, nudge, GT
rematch and the style and component toggles were confirmed to mutate in place.

### Adjacent, still open

`api/regions.py::set_region_word_membership` moves words between `page.lines`
entries and can renumber every line on the page. Its own docstring already
records this as a known flaw in `stable_word_id` and reading-order keying,
owned elsewhere and pinned by
`tests/integration/test_region_membership_word_identity.py`. Not part of this
family and not touched.

### [2026-09-18] Fixed: word identity diverged from OCR text the moment ground truth was corrected

- Found while making `tests/e2e/test_parity_persistence.py` honest — see that
  file's `_prepare_word_for_validation` docstring, Finding 2, for the original
  report.
- `core/page_to_line_matches.py` minted a word's `word_id` from its OCR text,
  once, when building the page payload. `api/typography.py`'s `_review_words`
  recomputed the same word's identity from its *live* `ground_truth_text` on
  every call instead. The two agreed only while ground truth read the same as
  OCR. The moment a person corrected a word's ground truth — the core activity
  of this product — every `/typography/words/{word_id}/...` lookup for that
  word 404d, permanently, unless the edit was later reverted to exactly match
  the OCR text. That fed straight into the per-word Validate button's gate
  (`typography_reviewed` on `TypographyHeadResponse`, added earlier the same
  day — see "Retired: the per-word validate button could never validate a
  word," above): once corrected, a word could be unvalidated but never
  validated again, reintroducing that morning's retired bug through a
  different door.
- Decision: word identity is derived from OCR text everywhere, matching
  `page_to_line_matches.py` and the upstream contract's own stated invariant
  — `pdomain_book_contracts.typography.review.make_word_id`'s docstring reads
  "Corrections never reissue this ID." Position-only identity (reading order
  with no text) was rejected: it survives text edits but not the word
  add/delete/merge/split routes already in the API surface, which would have
  meant reindexing every open review on every structural edit. A genuinely
  stored id, assigned once and carried in the content blob, is the more
  robust long-term answer, but every existing project has no such carrier —
  that migration is a larger, separate change (tracked nowhere yet; flagged
  here as future work), not bundled into this fix.
- Corrections already recorded under the old (ground-truth-derived) id are
  not orphaned: `_canonical_word_id_map` resolves both the current
  (OCR-derived) id and the legacy (ground-truth-derived) id for each on-page
  position to the same canonical id, so a lookup under either finds the same
  word's history. New corrections continue an existing lineage's own stored
  id (so `TypographyCorrectionLog`'s exact-match revision-chain validation —
  deliberately word-id-scheme-agnostic, unmodified by this fix — keeps
  matching it) and only start a fresh lineage under the current id when no
  prior review exists.
- One field was deliberately left alone: `_current_page_content`'s own
  internal `"word_id"` hash ingredient (feeding `page_sha256`) still reads
  ground-truth text, unchanged. That value is never returned to a caller —
  only hashed — and switching it to OCR-derived text would change
  `page_sha256` for every already-reviewed word on a page the instant this
  shipped, breaking every open correction's epoch continuity on first load.
  `"corrected_text"`, hashed alongside it, already changes on every
  ground-truth edit, so nothing is lost by leaving it alone.
- A related, pre-existing behaviour surfaced while testing this and was called
  expected staleness here. **That was wrong, and it was fixed the same day.**
  `TypographyBinding.page_sha256` was a whole-page hash, so editing any one
  word's ground truth invalidated every word's correction epoch on that page.
  Combined with the validate gate above, correcting one word made every other
  word on the page un-validatable until re-reviewed, and correcting words is
  the main activity. See the next entry.
- Tests: `tests/integration/test_typography_word_id_survives_gt_edit.py` —
  the 404 reproduction, the end-to-end review-survives-an-edit case, and a
  direct proof that a correction filed under the legacy id resolves through
  the current one. `tests/unit/api/test_typography_corrections.py`'s fixtures
  encoded the old (ground-truth-derived) id scheme directly and were updated
  to the OCR-derived one.
- Shipped in `fix/word-id-gt-divergence`.

### [2026-09-18] Fixed: a review went stale when a neighbouring word changed

- A typography correction was bound to `page_sha256`, a hash over every word's
  ground-truth text and bounding box. Any edit anywhere on the page broke the
  epoch for every word on it. With the same day's validate gate reading that
  epoch, correcting one word's ground truth made every other word on the page
  impossible to validate until its graphemes were reviewed again.
- Decision: a correction is a statement about one word's graphemes, so it goes
  stale when that word's own content or position changes, not when a neighbour
  does. The hash now covers structure only: reading order, word count and OCR
  text.
- Bounding boxes came out of the hash too, which I had not asked for and the
  implementer argued for. Nudging a box is as routine an edit as correcting
  text, so leaving it in would have reproduced the same bug through another
  door. The cost, stated rather than hidden: a word's own bbox nudge no longer
  stales its own review either, because the upstream contract hard-validates
  `WordTypography.text_sha256` against a literal hash of the text and leaves no
  per-word slot to carry bbox currency. Documented in `_current_page_content`
  and pinned by a test.
- Still stale a review, because they genuinely change what it was about: adding,
  deleting, merging and splitting a word.
- Corrections under the old hash are bridged, not orphaned. The structural hash
  is tried first, then the old whole-page formula recomputed from live state. A
  pre-existing correction reads as current on deploy, goes stale on the next
  unrelated edit exactly as it always did rather than worse, and the gap closes
  for good once that word is reviewed again.
- A latent bug fell out of it: the per-word staleness check compared a word's
  **first** correction in the epoch against live text rather than its latest.
  The whole-page reset had masked it, because first and latest were almost
  always the same record. Fixed in `typography_page_review` and the export
  bundle.
- Shipped in `cc41211`.

### [2026-09-18] Poetry is proposed by a rule, not a model

- The labeling track's roadmap deferred finding poetry to a vision-language
  model, because geometry supposedly could not separate poetry from blockquote.
  Measured the same day over five aligned books against PGDP's own formatting
  markup, that premise did not hold. See
  `pdomain-ocr-synth/docs/research/2026-09-18-ragged-right-finds-poetry-blockquote-has-no-geometric-signature.md`.
- What ships: `core/regions/poetry.py`, a detector using right-edge raggedness
  and a rule checking whether each line starts with a capital. Both are computed
  per paragraph. Text decides when a block's own OCR is usable, raggedness when
  it is not, chosen per block by that block's own text quality rather than by a
  corpus-wide switch.
- Thresholds come from the measurement and are named constants a person can
  tune. One does not: the OCR-usability share that picks between the two rules
  is this module's own glue, and the measurement never measured such a cutoff.
  It says so in the code.
- Confidence is the measured pooled precision of whichever rule decided, 0.954
  for text and 0.875 for geometry, and is documented as pooled rather than
  calibrated. The corpus figure leans on one book that is a poetry anthology;
  per-book precision across the other four ranges from 12.5 to 88.9 percent.
  That is honest about what the number is worth, which the existing furniture
  detector's uncalibrated confidences are not.
- One real divergence from the measurement, stated in the module docstring: the
  measurement segments blocks itself from ink-band row projections, and the
  detector reads the page's already-computed paragraph structure instead. The
  raggedness and indent formulas are the measurement's own. Only the
  segmentation differs, in favour of structure this codebase already maintains
  and already hashes as a facet. The measured precision may not carry over
  exactly.
- Blockquote is not attempted, and should not be until it has ground truth. Its
  best rule reached 2.3 percent precision over 44 heterogeneous spans.
- A provenance bug fell out of it: the proposal run handler hardcoded
  `depends_on` to a geometry-only facet set whatever the detector was, which is
  wrong for any detector that reads OCR text. A detector now declares its own
  facets and the handler reads them.
- Indent is recorded in the evidence dict and never gates the decision, because
  the measurement found it adds noise rather than signal: verse lines fall short
  of the measure and so read as indented on both sides.
- What this unblocks: the first `region-decisions.jsonl` this system has ever
  had. Nothing has ever reviewed a region proposal, so there is no data on where
  role detection fails. Every future role claim needs that.
