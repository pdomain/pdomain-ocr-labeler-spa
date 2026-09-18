---
status: active
owner: maintainers
created: 2026-09-18
last_verified: 2026-09-18
kind: issue
level: I1
---

# The typography review count has no answer once a book has real correction history

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Medium. The route degrades honestly today — it reports
  `available: false` with a reason rather than a slow or wrong count — but a
  book with enough typography correction history can never get a typography
  count from this route until this is built.
- **Affected version:** master at `2cfc834` (review-queue slice)
- **Read when:** touching `api/review_queue.py`'s typography entry,
  `core/typography_review.py`, or anything that reads
  `TypographyCorrectionLog.records()` for more than one word.
- **Search terms:** typography numerator, review-queue, reviewed_word_keys,
  TypographyCorrectionLog, corrections journal, per-page rollup,
  word-review-counts journal.
- **Relates to:** pdomain-ocr-synth's
  `docs/specs/2026-09-18-one-answer-to-what-to-review-next.md`.

## Summary

`GET /api/projects/{project_id}/review-queue`'s `typography` entry counts
reviewed words by reading the whole `typography-corrections.jsonl` journal
and parsing every row into a pydantic `TypographyCorrection`/`WordTypography`
model. That costs about 80 microseconds a row. Above 512 KiB (about 224
rows) the route stops computing the count at all and reports
`available: false`, because the read no longer stays in the low tens of
milliseconds that the rest of this route holds to. The real fix — a
per-page rollup written where a correction is accepted, the same shape as
the word-review-counts journal this route's other kinds already read — has
not been built. This issue is that work.

## Impact

- A book whose typography-corrections journal grows past 512 KiB cannot get
  a typography count from the review-queue route at all — the rail badge and
  the Queue drawer's kind selector (once built) have nothing to show for
  that kind on that book.
- Every other kind on this route (page kind, region, word) answers in low
  single-digit milliseconds regardless of book size, because each reads a
  small per-page journal. Typography is the one kind whose cost still grows
  with the *whole book's correction history*, not with page count.
- Nothing is lost or wrong: the size gate is honest, and a correction
  journal under the threshold still produces a correct count (see
  `core.typography_review.reviewed_word_keys`, which this issue's rollup
  would not replace, only avoid calling on every request).

## Evidence — the measured cost

Fixture journal at the same 18,463-word scale as the book this route's
design was measured against, with real correction rows at several coverage
levels. Timed `TypographyCorrectionLog.records()` plus
`reviewed_word_keys()` together:

```
corrections   rows    file size    time
1% of words    184     421 KB       15 ms
5% of words    923     2.1 MB       68 ms
10% of words 1,846     4.2 MB      143 ms
25% of words 4,615    10.6 MB      355 ms
100% of words 18,463  42.3 MB    1,521 ms
```

Isolating where the cost goes, at 10% coverage: raw file read + `json.loads`
alone cost 36 ms; `TypographyCorrectionLog.records()` (which additionally
validates every row into a pydantic `TypographyJournalEnvelope`) cost
143 ms; the reviewed-word filter itself, given already-parsed records, cost
3 ms. The cost is pydantic model construction, not I/O and not this route's
own aggregation logic.

512 KiB was chosen as the availability threshold because it is the size at
which the read still stays in the low tens of milliseconds (about 16 ms
measured) — see `api/review_queue.py`'s
`_TYPOGRAPHY_CORRECTIONS_MAX_BYTES` for the full reasoning. A book actively
worked on by more than a handful of people, or one with several typography
correction revisions per word (each revision is its own appended row),
reaches that size well within a normal review session.

## Root-cause hypothesis

There is exactly one hypothesis: **no per-page rollup exists for
typography**, unlike words. `core.review_counts.WordReviewCountsJournal`
exists specifically because parsing a page's content blob to count validated
words is too expensive to do on every request — the same shape of problem,
solved by writing a small summary row at the point a word's validated state
actually changes (`save_page_content_to_store`), so a later count reads that
summary instead of re-deriving it. Typography's numerator never got the
equivalent: it still re-derives from the full history on every request.

## Defects to fix

1. **No per-page (or per-`logical_page_id`) typography rollup.** Build one,
   written where a correction is accepted — `api/typography.py`'s
   `append_typography_correction`, after `log.append(correction, ...)`
   succeeds, mirroring `save_page_content_to_store`'s "append only after the
   head write has succeeded" ordering and its best-effort, logged-and-
   swallowed failure handling. (Primary)
2. **`api/review_queue.py`'s `_typography_entry` still reads the raw
   corrections journal.** Once the rollup exists, this entry should read the
   rollup instead of `TypographyCorrectionLog.records()`, the same way the
   `word` entry reads `WordReviewCountsJournal` instead of parsing page
   blobs. The 512 KiB availability gate goes away entirely once this lands.

## What it would cost to build

Comparable scope to the word-review-counts journal built in commit
`866e9f6`: a new small journal module (`core/typography_review_counts.py` or
similar), a dataclass row shape (page identity, total words, typography-
reviewed words, same as `PageWordCounts`), an append call at the one place a
correction lands (`append_typography_correction`), a `latest_by_page`-style
reader, and the review-queue route swapped over. One nuance the word journal
did not have to solve: a typography correction journal is append-only per
*word*, not per *page* — a rollup row has to represent "reviewed count as of
this correction," which means either recomputing the page's full reviewed
count at each accepted correction (cheap — one page's worth of corrections,
not the whole book) or maintaining a running per-page counter carefully
enough that a correction that *un-reviews* a previously-reviewed word (a
revision that fails the completeness bar) decrements rather than only ever
incrementing. The former is simpler and matches the word journal's own
approach (count from the content actually written, never a delta). A day or
two of focused work, including tests mirroring
`tests/unit/core/test_review_counts.py` and
`tests/integration/test_review_queue_router.py`'s typography section.

## What it would save

- Removes the 512 KiB availability ceiling entirely — every book gets a
  typography count from this route, regardless of correction history depth.
- Drops the typography entry's per-request cost from O(book's total
  correction rows) to O(1) file reads, the same as every other kind on this
  route.
- Makes the numerator computable incrementally rather than by rescanning
  the whole book's history on every request, which is also what would make
  it affordable to eventually add the staleness check this route's
  typography count still skips (see the design's "Typography's per-head
  staleness check" — that is future work in its own right, not part of this
  issue, but a cheap rollup is a precondition for it being affordable at
  all).

## What is NOT broken

- The size gate itself is correct and honest — `available: false` with a
  reason is exactly what pdomain-ocr-synth's design calls for when a kind
  cannot be answered, and it costs one `stat()` to evaluate.
- `core.typography_review.reviewed_word_keys` computes the right answer
  when the journal is small enough to read; this issue is about avoiding
  the read, not fixing its result.
- The word, region, and page-kind kinds on this route are unaffected; each
  already reads its own small per-page journal.

## Resolution

*Open.*
