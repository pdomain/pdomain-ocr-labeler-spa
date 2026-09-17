---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-21
---

# Current state

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-09-17
- **Read when:** orienting on shipped behavior, open work, or repository risk.
- **Search terms:** current state, shipped, open work, risks, roadmap.

## Shipped system

Fine-grained typography phase one is shipped on this branch. The SPA uses
`TypographySection`, server-authoritative grapheme/taxonomy metadata, and an
append-only v1 correction journal. Persisted-page lineage epochs keep old heads
as audit history while typography review and correction-bundle export select
only current active heads. General export gates on that review result but does
not carry journal heads.
Text validation is independent. Page completion and export combine text and
typography gates. General export freezes content-addressed page and image
snapshots. Correction-bundle export separately carries selected journal heads.
Suggestion acceptance/editing and predecessor undo remain open.

The FastAPI and React SPA is the production labeler. The cut-over, hi-fi work,
selection operations, right-panel editing, event-store undo/redo, manual
rotation, and batch auto-rotation are implemented. Current architecture lives
in [`../architecture/`](../architecture/00-overview.md), with executable
evidence in `src/`, `frontend/src/`, and `tests/`.

Manual rotation and auto-rotation now rotate source images, rerun OCR, and
persist rotation metadata. The implementation is in
`src/pdomain_ocr_labeler_spa/core/jobs/handlers/rotate.py` and
`src/pdomain_ocr_labeler_spa/core/jobs/handlers/auto_rotate_all.py`; browser coverage is in
`tests/e2e/test_rotate_parity.py`. Earlier documentation that called these
handlers stubs was stale.

The labeling track runs end to end on a real book: a machine proposes regions from real OCR output
and a person reviews them. It was designed in `pdomain-ocr-synth` and built here.

**It was verified on real data on 2026-09-17.** 80 real pages of `projectID657550412c8dc` went
through DocTR OCR, page-kind proposal, region proposal and an accept: 29 proposals on 15 pages, and
the accepted header served back at exactly its pixel box. That first real run also found that the
pipeline had never worked on real data. DocTR emits word boxes normalized to 0 to 1, and every
region test built pixel-space pages. Region boxes now convert at the API boundary the way word boxes
always have, in `core/regions/coordinates.py`, and `tests/integration/conftest.py` has a
`normalized_page_loaded` fixture shaped like real OCR output. Evidence is in
`/workspaces/pdomain/.m15f-evidence/real-book-region-run/`.

As of 2026-09-17:

- **Page kind** is proposed by a book-scoped `propose_page_kinds` job, which measures every page
  through `pdomain-pgdp-measure` and classifies the book against its own fitted templates. A person
  confirms it through `POST .../pages/{index}/page-kind`. `PagePayload` carries `page_kind` and
  `page_kind_reviewed` as typed fields.
- **Regions** are `Block` objects in the page tree, marked by a `region_id` in
  `additional_block_attributes`. Eight routes cover create, edit, delete, word membership, list
  proposals, accept, reject, and the book-scoped `POST .../regions/propose`. Proposals and decisions
  live in JSONL journals under the project's `.pd-pages/`, never in the page blob. A repeat reject
  records nothing new.
- **Proposals come from a geometry engine.** `propose_regions` measures the whole book and runs
  `FurnitureDetector` by default. It proposes a `page header` and a `page number` from each page's top
  furniture bands, splitting head from folio at a gap threshold fitted to each book's own word gaps.
  Both proposal jobs read page images through a verified per-page lease. A run ends with a summary
  message saying how many proposals it made and why any pages were skipped.
- **A person reviews proposals in the SPA.** Key `5` selects the region rail target. A canvas click
  selects the smallest region or proposal under it, and `RegionDetail` accepts, accepts as another
  role, or rejects it, or changes the role of or deletes a confirmed region. From the keyboard, `n`
  and `p` step through undecided proposals, `enter` accepts, `x` rejects, and selection advances by
  itself. The page actions menu starts both proposal runs. `tests/e2e/test_region_review_loop.py`
  drives the loop in a real browser.
- **Decisions carry across runs.** A new proposal matching a confirmed region, same role and box IoU
  of at least 0.7, gets a `carried` decision naming that region, so a re-run does not bring back
  reviewed work. The carry runs under the page lock. Deleting a region rejects every proposal whose
  latest decision names it.
- **A book-wide review queue.** `GET .../regions/review-queue` returns the book's undecided count, a
  per-page summary, and up to 500 items in reading or confidence order. It uses the same
  undecided rule as the page view. In the SPA, `]` and `[` jump to the next or previous page with
  undecided proposals, the rail's region target shows the book's count as a badge, and emptying a
  page says how many remain in the book. `tests/e2e/test_review_queue_navigation.py` drives it.
- **A person reviews page kinds.** `PagePayload` carries the latest `page_kind_proposal`. The page
  toolbar shows the page's kind, confirmed or proposed with its confidence, and confirms or changes
  it. "Review page kinds" opens a book-wide list with filters and checkboxes, backed by
  `GET .../page-kinds` and `POST .../page-kinds/confirm`, which the SPA calls 25 pages at a time.
  Reviewed markers record the kind and whether it was confirmed alone, in bulk, or by undo or redo.
  A confirmed kind survives re-OCR, rotation and auto-rotate-all. Verified on 32 real OCR'd pages
  in `/workspaces/pdomain/.m15f-evidence/real-book-page-kind-review/`.
- **Not built yet:** drawing a region, resizing a box, editing word membership in the UI, and a
  keyboard path for page kinds.

Page lifecycle types now have one import owner. Production and test callers
import `PageRecord` and `RotationSource` from `pdomain_ops.pages`; the temporary
`core.models` compatibility exports have been removed. Structural, persistence,
validation, conversion, and rotation tests enforce the boundary.

## Open work

Cross-cutting prioritization (deep review Waves 0–6, verified 2026-07-21):
[`../plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md).

**Split work packages (implement by issue):**
[`../issues/README.md`](../issues/README.md) — 17 deep-review issues under
`docs/issues/2026-07-21-*` plus prior #430/#433.

Standing overnight stream index:
[`../plans/2026-07-21-overnight-work-index.md`](../plans/2026-07-21-overnight-work-index.md).

- **Highest product risk (deep review + adversarial recheck):** char/glyph
  sidecar maps and rematch can return 200 without durable event-store write;
  export list API is empty while manifests exist; CLI export is not store-first;
  job SSE FE↔BE shape mismatch; canvas erase unmounted; image_drift banner
  hard-off. See Waves 0–1 and 3a/3b issues.
- PGDP/pdomain-ui alignment is partial. Remaining slices:
  [`../plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md)
  (source backlog:
  [`../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md`](../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md)).
- Glyph annotations (M11) are scaffolded (~35% scaffold / ~20% usable path).
  Residual wire-up:
  [`../plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md).
  Spec: [`../../specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md).
- Active local issues: CI vs `make ci` (#430) and OpenAPI drift (#433) —
  [`../plans/2026-07-21-ci-openapi-gates.md`](../plans/2026-07-21-ci-openapi-gates.md).
- Open findings (keyboard, XDG data root, reload, hierarchy E2E):
  [`open-findings.md`](open-findings.md) and
  [`../plans/2026-07-21-open-findings-fixes.md`](../plans/2026-07-21-open-findings-fixes.md).
- Residual test-tsconfig strictness (#366 leftover):
  [`../plans/2026-07-21-tsconfig-test-strictness.md`](../plans/2026-07-21-tsconfig-test-strictness.md).
- Already done (do not re-plan): #404 lint-deviations catalogue
  (`docs/process/lint-deviations.md`), #437 OpenAPI schema quality tests, #460
  resolver narrowing, BUG-KBD-4 ConfirmDialog Escape.

## Risks

The behavior specification set remains a living contract and includes explicit
stubs or owner questions. Treat [`../specs/behavior/unclear-items.md`](../specs/behavior/unclear-items.md)
as the current ambiguity inventory, not deleted point-in-time parity audits.
