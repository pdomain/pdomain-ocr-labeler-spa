---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-11-12
---

# Current state

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-11-12
- **Read when:** orienting on shipped behavior, open work, or repository risk.
- **Search terms:** current state, shipped, open work, risks, roadmap.

## Local P3 and F2 review

The local feature branch adds bounded corpus preparation, native Tesseract
OCR, and composed F2-to-P3-to-OCR alignment. Group review preserves human
text edits and the OCR word topology. Split and joined words use explicit
group bindings; ambiguous, unmapped, and exhausted results remain visible.
Mapped source lines, stanzas, and indentation can survive unambiguous wording
changes. Inline style transfer still requires supported exact grapheme mappings.

The JSON control client uses the domain APIs. Revisioned application events
refresh idle viewers, while explicit commands target one browser tab.
Acknowledgement checks the actual project, page, panel, selected IDs, and
current ready generation. Content changes do not navigate another viewer.
Tesseract is an explicit CPU provider; the default remains DocTR.

The P3-F2 branch merged to master as `1445e173`. `pyproject.toml` requires
`pdomain-book-contracts>=0.3.0`, and `uv.lock` selects published `0.3.0`.
That replaces the reviewed local contracts wheel and the earlier v0.2.1 pin.
See the 2026-11-09 decision in [`decisions.md`](decisions.md).

## Shipped system

F2 and Gutenberg evidence now feeds the existing region proposal job. The
review panel exposes source lines, stanzas, indentation, disagreements, and
unresolved hints. Physical columns retain separate paragraph or poetry roles
with grouping and reading order. Table proposals require source semantics
and matching scan geometry.

Reviewed structure persists with confirmed regions and exports beside the
unchanged version-1 region labels. The explicit region-only export action
supports prepared books without exporting OCR crops. General export keeps
its text and typography review requirements.

Detailed line and stanza writes require the word IDs stored in prepared
bundles. Loose mirrors support ordinary region acceptance and column review.
The published region-review baseline requires `pdomain-book-contracts>=0.3.0`.
`uv.lock` selects published `0.3.0` from the pdomain package index. The
2026-11-09 decision records the merge and the browser check of
`0.6.1.dev16+g1445e1730`.

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
  Both proposal jobs read page images through a verified per-page lease. A region run loads any page
  with stored OCR that nobody has opened, never running OCR itself, so it works right after a
  restart. A run ends with a summary message saying how many proposals it made and why any pages
  were skipped. The folio half of a furniture band is peeled off by a digits-only pattern; a short
  edge token OCR'd with a digit lookalike (`IO` for `10`) is recognized as a folio too, through a
  case-sensitive `I`/`l`/`|`→`1`, `O`→`0` substitution checked only as a fallback, only up to four
  characters, and never for anything spelled entirely in roman-numeral letters
  (`_is_folio_via_lookalikes` in `core/regions/furniture.py`). Recognition changes only which role a
  proposal gets; the OCR'd band text itself is never rewritten, and no folio value is parsed to an
  integer anywhere in this codebase.
- **A person reviews proposals in the SPA.** Key `5` selects the region rail target. A canvas click
  selects the smallest region or proposal under it, and `RegionDetail` accepts, accepts as another
  role, or rejects it, or changes the role of or deletes a confirmed region. From the keyboard, `n`
  and `p` step through undecided proposals, `enter` accepts, `x` rejects, and selection advances by
  itself. The page actions menu starts both proposal runs. `tests/e2e/test_region_review_loop.py`
  drives the loop in a real browser.
- **Decisions carry across runs, both acceptances and rejections, matched the same way.** A new
  proposal matching a confirmed region, same role and box IoU of at least 0.7, gets a `carried`
  decision naming that region; a new proposal matching a proposal a person's own latest decision
  rejected gets a `rejected` decision instead, naming that rejection as its `carried_from_run_id`/
  `carried_from_proposal_id` — a rejection is an answer, and a re-run must not ask it again, the
  same as an acceptance. Both matches use the one IoU rule (`_best_iou_match` in
  `core/jobs/handlers/propose_regions.py`), run under the page lock, and always trace back to a
  person's own decision, never a previous carry. Deleting a region rejects every proposal whose
  latest decision names it. A confirmed region whose accepting decision never made it into the
  decision log (a real shape: `accept_region_proposal` writes the page blob before the decision, so
  a decision-log append failure right after a successful accept leaves this gap) still carries,
  reconstructed from the block's own `source_proposal_id` joined against the proposal log. A
  hand-drawn region deliberately does not carry forward: it has no real proposal behind it, so
  there is nothing a carried decision's `carried_from_*` fields could honestly name — the matching
  proposal is simply left for a person to review once more, which costs a click rather than hiding
  anything. The right panel now counts carried rejections and can reopen one. Reopening appends a decision instead
  of rewriting the original journal.
- **A book-wide review queue.** `GET .../regions/review-queue` returns the book's undecided count, a
  per-page summary, and up to 500 items in reading or confidence order. It uses the same
  undecided rule as the page view. In the SPA, `]` and `[` jump to the next or previous page with
  undecided proposals, the rail's region target shows the book's count as a badge, and emptying a
  page says how many remain in the book. A Queue drawer tab lists the undecided proposals themselves,
  in reading or lowest-confidence-first order, with the detector's evidence; clicking one jumps to it
  and selects it. `tests/e2e/test_review_queue_navigation.py` and `test_review_queue_panel.py` drive
  both.
- **A person reviews page kinds.** `PagePayload` carries the latest `page_kind_proposal`. The page
  toolbar shows the page's kind, confirmed or proposed with its confidence, and confirms or changes
  it. "Review page kinds" opens a book-wide list with filters and checkboxes, backed by
  `GET .../page-kinds` and `POST .../page-kinds/confirm`, which the SPA calls 25 pages at a time.
  Reviewed markers record the kind and whether it was confirmed alone, in bulk, or by undo or redo.
  A confirmed kind survives re-OCR, rotation and auto-rotate-all. Verified on 32 real OCR'd pages
  in `/workspaces/pdomain/.m15f-evidence/real-book-page-kind-review/`.
- **Region editing shipped in v0.6.0:** drawing, resizing, and word membership persist through save and reload.
  Confirmed regions export beside DocTR output in `regions/labels.json`. A page-kind keyboard path remains
  separate work. Commits `29ebcdc6` and `26b2d40f` contain implementation and tests.

Page lifecycle types now have one import owner. Production and test callers
import `PageRecord` and `RotationSource` from `pdomain_ops.pages`; the temporary
`core.models` compatibility exports have been removed. Structural, persistence,
validation, conversion, and rotation tests enforce the boundary.

- **One answer to what to review next.** `GET .../review-queue` reports every kind
  of review work in the order the work has to happen: page kinds, regions, words,
  typography, glyphs. The rail badge names the first kind with work and its count;
  the Queue tab picks a kind and `[` and `]` follow it. A kind that cannot be
  answered says why rather than reporting zero, a blocked kind says what it waits
  for, and a count that may understate reads as "at least". A per-page journal,
  `.pd-pages/word-review-counts.jsonl`, written where a page is already saved, is
  what makes word and typography countable: without it, counting a 300-page book's
  word validation means parsing every page, about 14 seconds.

## The browser suite

151 of 160 browser tests passed, 2 failed, 7 skipped, as of `199aa66`, the last
full-suite count taken on 2026-09-18. One of the two failures was the word-edit
dialog test; that dialog and its test are both gone now (below), so only
`test_validate_and_save_keyboard_only` remains from that count, and it passes
alone and fails only under load in this environment. A run that skips for a
reason outside `tests/e2e/conftest.py`'s allowlist fails, so the suite can no
longer report success while hiding a gap.

Later the same day, a family of eleven routes was found and fixed for
per-word sidecars not following their words through structural edits (below);
those fixes carry integration and unit test evidence in `decisions.md` rather
than a fresh full-suite browser count. `make ci` (unit + integration + build,
not `e2e`) was last documented red at `frontend-knip`, fixed in `972ab61`.

See the 2026-09-18 tombstones in `decisions.md` for what each triage found.

## Open work

The live list is the [roadmap](intent-map.md). This section only names what is in progress now.

Typography suggestion acceptance and predecessor undo are still open. The questions are in
[`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md).

Driver-contract section 2.11 browser coverage, U-M6 history boundaries, stable region-membership word ids, and the
behavior-spec reconcile are recorded under Done in the roadmap.

Closed waves, the six findings, the sidecar reindex, the memfd refusal, glyph-picker parity, export-dialog history,
the local right-panel frame, and test-project `noUncheckedIndexedAccess` are recorded under Done in the roadmap and
in [`decisions.md`](decisions.md). The labeler tag `v0.3.0` is under Done in the roadmap. It is not a contracts release.

## Risks

Verified image loads require Linux memfd sealing. A Python build without it cannot load labeling bundles or book
pages. The API returns `503 unsupported_runtime` and names the missing interfaces. The supported Python version range
does not detect this. An agent chose no fallback on 2026-11-11, and the owner has not reviewed that choice.

The behavior specification set remains a living contract and includes explicit
stubs or owner questions. Treat [`../specs/behavior/unclear-items.md`](../specs/behavior/unclear-items.md)
as the current ambiguity inventory, not deleted point-in-time parity audits —
though several of its entries (the word edit dialog, root filter chips) were
settled by 2026-09-18 decisions recorded here and in `decisions.md` before
that file itself was updated to say so; check `decisions.md` first for
anything it flags as still open.
