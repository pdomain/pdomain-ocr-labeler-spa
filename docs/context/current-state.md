---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-09-18
---

# Current state

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-09-18
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
- **Decisions carry across runs, for confirmed regions with a recorded origin.** A new proposal
  matching a confirmed region, same role and box IoU of at least 0.7, gets a `carried` decision
  naming that region, so a re-run does not bring back reviewed work. The carry runs under the page
  lock. Deleting a region rejects every proposal whose latest decision names it. Two gaps are known,
  not yet owned by a fix: a hand-drawn region, or a confirmed region whose accepting decision is
  missing, matches a new proposal but is not carried
  (`core/jobs/handlers/propose_regions.py::_carry_decisions_for_page` only carries from an origin
  `accepted`/`edited` decision); and a rejected proposal is never matched against at all, so a re-run
  can resurface something a person already declined.
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
- **Not built yet:** drawing a region, resizing a box, editing word membership in the UI, and a
  keyboard path for page kinds.

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

[`../issues/README.md`](../issues/README.md) lists no open issues. The 18
deep-review reports filed under `docs/issues/2026-07-21-*`, the two migrated
GitHub records, and every report filed and closed same-day are resolved and
deleted; each retirement's reasoning is a tombstone in `decisions.md`, which
is the authoritative record, not this list.
[`../plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
prioritized that work across Waves 0–6 and is now a historical record rather
than a live queue — nearly every finding it named carries a 2026-09-17 or
2026-09-18 tombstone.

Glyph annotations (M11) — the manual review path is shipped. A person
selects a word, marks its ligatures, long s or swash, or marks it reviewed
with no marks; the mark persists through save and reload; a bulk apply
persists and refreshes the page. The dataset export writes a
`recognition/glyph_features.json` sidecar so those human marks reach
recognition evaluation, keyed by crop id
(`core/jobs/handlers/glyph_sidecar.py`). No glyph predictor exists and none
will be built here (decided 2026-09-18) — the accept-prediction button never
fires; the seam stays, rendering nothing. A glyph chip click now selects the
word and opens the review panel, same as the pencil button. Browser
coverage: `tests/e2e/test_glyph_panel.py` (single-word mark) and
`tests/e2e/test_bulk_glyph_mark.py` (a real bulk-apply dialog, confirmed
against an independent `GET`). See `decisions.md`'s 2026-09-18 entries and
[`../plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md).
Spec: [`../../specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md) §9.

**What remains, verified against code or `decisions.md` rather than assumed:**

- **Two word-identity bugs**, found and left open on 2026-09-18, documented
  in `tests/e2e/test_parity_persistence.py`'s
  `_prepare_word_for_validation` and `_poll_server_word_by_gt` docstrings:
  - Editing a word's ground-truth text breaks that word's typography-review
    reachability, and so its validate button: `core/page_to_line_matches.py`
    computes the `WordMatch.word_id` a page payload carries from the word's
    OCR text, while `api/typography.py` recomputes the same `stable_word_id`
    from live ground-truth text once one has been entered. The two disagree
    after any GT edit, and a typography lookup keyed by the stale id 404s.
  - A `GET .../pages/{index}` issued right after a mutation such as `/save`
    can transiently return 200 with an empty `line_matches` — reproduced over
    plain back-to-back HTTP calls with no browser involved, so it is a
    genuine backend race, not a rendering issue. The live UI shows "No page
    data" / "Word not found in page data" when it happens.
- **`set_region_word_membership` can renumber every line on a page** — a
  known gap in `stable_word_id` and reading-order keying, recorded in its own
  docstring (`api/regions.py`) and pinned by
  `tests/integration/test_region_membership_word_identity.py`. Outside the
  sidecar-reindex family closed 2026-09-18 (below).
- **Region carry-forward has two gaps**, both in
  `core/jobs/handlers/propose_regions.py`: a hand-drawn region, or a
  confirmed region whose accepting decision is missing, matches a new
  proposal on a re-run but is not carried; and a rejected proposal is never
  matched against at all, so a re-run can resurface something a person
  already declined.
- ~~Whether the OCR engine should warm up at server start~~ — decided
  2026-09-18: no. The predictor stays lazy; see `decisions.md`.
- **Released `v0.3.0` on 2026-09-18**, 561 commits after `v0.2.0`, with the pip
  index regenerated. `docs/runbooks/release.md` has the steps.
- PGDP/pdomain-ui alignment is partial:
  [`../plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md).
  Its status table predates 2026-09-18 — items 7–9 (project-card metadata, root
  filters, the archive decision) that it lists open or partial were resolved
  2026-09-18, see `decisions.md`. Items 4 (jobs pill/drawer) and 10 (shared
  workbench layout) were not touched and are still open as the table
  describes.
- Open findings, keyboard entries now closed (`6db2e42` registered `mod+,`,
  `mod+j` and `mod+shift+r`; BUG-KBD-4 was already done):
  [`open-findings.md`](open-findings.md) still lists the XDG data root
  default, the reload zero-area GT box check, and the hierarchy-coverage E2E
  gap, none touched 2026-09-18.
- Residual test-tsconfig strictness (#366 leftover), untouched 2026-09-18:
  [`../plans/2026-07-21-tsconfig-test-strictness.md`](../plans/2026-07-21-tsconfig-test-strictness.md).
- Already done (do not re-plan): #404 lint-deviations catalogue
  (`docs/process/lint-deviations.md`), #430 CI-equivalence and #433 OpenAPI
  drift (moot — the GitHub workflows they described are deleted), #437
  OpenAPI schema quality tests, #460 resolver narrowing, BUG-KBD-1/4/5.

A family of eleven routes was fixed 2026-09-18 where per-word char-bbox, glyph,
and glyph-prediction sidecar maps did not follow their words through
structural edits (word/line/paragraph delete, merge, split, and add) — see
"Per-word sidecars did not follow their words" in `decisions.md`. Word split
now refuses rather than orphan a word's sidecars; every shifting route
reindexes; `set_region_word_membership` (above) is adjacent and not part of
this family.

## Risks

The behavior specification set remains a living contract and includes explicit
stubs or owner questions. Treat [`../specs/behavior/unclear-items.md`](../specs/behavior/unclear-items.md)
as the current ambiguity inventory, not deleted point-in-time parity audits —
though several of its entries (the word edit dialog, root filter chips) were
settled by 2026-09-18 decisions recorded here and in `decisions.md` before
that file itself was updated to say so; check `decisions.md` first for
anything it flags as still open.
