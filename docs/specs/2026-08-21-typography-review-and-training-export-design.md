---
kind: spec
status: draft
owner: maintainers
created: 2026-08-21
last_verified: 2026-08-21
repo: pdomain/pdomain-ocr-labeler-spa
---

# Typography review and training export design

Typography review becomes part of page completion, alongside corrected text. The labeler will replace its current
character-range contract with grapheme-based typography annotations, preserve every correction through the event store,
and export immutable records for model training.

## Agent Index

- **Kind:** spec
- **Status:** draft
- **Owner:** maintainers
- **Last verified:** 2026-08-21
- **Read when:** designing or implementing typography review, page completion, contextual annotation, or typography
  training export.
- **Search terms:** typography review, grapheme spans, page completion, corrected training data, contextual crop,
  character ranges.

## The labeler must capture complete text and typography

A labeled page is useful only when it records both what the page says and how its inline text appears. The labeler must
not mark a page done while retained words still have unknown typography.

Page completion requires two independent gates:

- Text review is complete under the existing ground-truth rules.
- Typography review is complete for every retained word.

The UI reports both percentages. The combined page state is done only when both reach 100 percent and no blocking
warning remains.

Every retained word has one of these typography outcomes:

- Confirmed whole-word or grapheme-span labels.
- Explicitly reviewed regular text with no positive inline-style labels.
- Quarantined evidence with a recorded reason that blocks page completion.

Unknown, unreviewed, deferred, stale, and unresolved words do not satisfy the typography gate. Deleted words and
elements excluded from the OCR text stream do not enter its denominator.

## Scope separates inline typography from page structure

The typography editor covers visible inline attributes that can change within a word or line. The first taxonomy follows
the fine-grained typography model design at
`/workspaces/pdomain/pdomain-ocr-training/docs/specs/2026-08-21-fine-grained-typography-model-design.md`.

Trainable inline labels include:

- italic;
- bold;
- small caps;
- letter spacing;
- underline as an audit-only label until the owner approves it for training;
- superscript;
- subscript;
- reviewed font changes whose meaning is defined;
- multiple simultaneous labels when styles overlap.

Drop caps remain word-level structural annotations. They need surrounding page context and must not become arbitrary
grapheme spans. Headings, captions, poetry, block quotations, tables, and other page structures remain owned by the
page-region model.

Ligatures, long-s forms, and swashes remain glyph-form annotations. The UI places them beside inline styles under one
Typography section, but their canonical data remains separate. This prevents a narrow glyph schema from becoming a
catch-all style schema.

## The existing range editor becomes the typography span editor

The SPA will refactor `frontend/src/components/right-panel/sections/CharRangesSection.tsx` rather than add a competing
editor. Its current clickable cells, overlapping ranges, and multi-label selection provide the interaction foundation.

The replacement editor operates on Unicode extended grapheme clusters from corrected ground-truth text. It never indexes
`ocr_text` with JavaScript `Array.from`. Every stored interval is half-open `[start, end)` in grapheme indices.

The editor supports:

- selecting one or more adjacent graphemes;
- assigning several labels to one span;
- preserving overlapping spans;
- adjusting, splitting, merging, and deleting spans;
- choosing punctuation boundaries precisely;
- applying a whole-word label as `[0, grapheme_count)`;
- collapsing uniform full-word spans for compact display without losing the canonical span;
- marking the word reviewed regular;
- reviewing source-derived and model-predicted suggestions;
- rejecting or quarantining bad source evidence;
- correcting ground-truth text before final typography review;
- keyboard operation for every action available by pointer.

The editor groups labels by kind. Inline styles and baseline shifts appear in the span palette. Structural components
such as drop caps do not.

## Suggestions remain distinct from human decisions

PGDP F2 parsing, Gutenberg or Standard Ebooks projection, rules, and model inference can prefill suggestions. A
suggestion never counts as reviewed until a human accepts or edits it.

Each suggestion displays:

- label and span;
- source type and source artifact;
- confidence tier or calibrated probability;
- parser and alignment warnings;
- the model and calibration versions when applicable;
- its source and target text alignment when projection created it.

The reviewer can accept, edit, reject, mark the word reviewed regular, quarantine the evidence, or defer. Accepting or
editing a suggestion creates human evidence. It does not overwrite the suggestion or its source.

The labeler retains rejected predictions. This supports later false-positive analysis and prevents a rejection from
becoming an unlabeled negative without an explicit human decision.

## Review uses surrounding context

Typography often appears through contrast with nearby text. Small caps, subtle weight changes, tracking, and typeface
changes can be ambiguous in an isolated word crop.

The review surface therefore shows:

- a high-resolution target-word crop;
- the complete short line around the target word;
- visible target-word bounds within that line;
- adjacent words and their corrected text;
- an option to widen the view to adjacent lines or the page;
- available baselines, x-heights, character boxes, and line geometry.

The reviewer edits exact target graphemes while using the larger view as evidence. Changing the visible context does not
change annotation offsets.

This same two-view contract feeds model training. Each exported example contains a high-resolution target crop and a
short-line context crop. It also contains the target box in line coordinates, full-line recognized text, word and
grapheme boundaries, and available geometry.

The model design uses two visual views:

- The line view establishes the local norm for height, weight, slant, spacing, and face.
- The word view preserves the fine detail needed for punctuation and mixed-style spans.

The sequence head predicts labels across the short line. A target-word mask identifies the graphemes scored for a word
record. A word-level auxiliary head compares the target with pooled neighboring-word features.

Small-caps training must include local contrasts and counterexamples. Examples include isolated small-cap words,
adjacent small-cap runs, lines entirely in small caps, ordinary all-capital headings, normal capitalized words, and
misleading neighboring fonts. Training masks neighboring context at random so the model remains useful when context is
missing.

The two-view contextual model is now the primary production experiment. The owner approved this change on 2026-08-21
because relative typography is central to the task. It supersedes the earlier sequence in the typography model design.
That sequence placed a word-only experiment first and gated line context on its mixed-span result. The word-only model
remains the smallest baseline, ablation, and inference fallback. It does not gate contextual training.

## Canonical annotations use stable identities and text revisions

`pdomain-book-tools` owns the canonical Python typography types. The FastAPI backend imports their public API and does
not reach into package internals. The React SPA consumes generated TypeScript types from the backend OpenAPI schema. It
never imports Python code.

The canonical annotation contains:

```text
WordTypography
  schema_version
  review_state
  word_id
  page_content_hash
  image_artifact_hash
  corrected_text
  corrected_text_hash
  grapheme_map_version
  graphemes[]
  label_states{}
  whole_word_labels[]
  spans[]
  source_evidence_ids[]
  review_metadata
  warnings[]
```

Each span contains:

```text
TypographySpan
  span_id
  start_grapheme
  end_grapheme
  labels[]
  label_source
  confidence_tier
  prediction_id
  alignment_evidence_id
```

`review_state` distinguishes at least `unreviewed`, `reviewed`, `reviewed_regular`, `quarantined`, and `deferred`. Only
`reviewed` and `reviewed_regular` satisfy page completion.

Labels are independent booleans, not a mutually exclusive class. A grapheme can be bold and italic, or small caps and
letter-spaced, at the same time.

`label_states` maps every label in the active taxonomy to `positive`, `negative`, or `unknown`. Positive means the
reviewer confirmed the label somewhere in the word. Negative means the reviewer explicitly confirmed its absence.
Unknown means the reviewer did not decide that label. A page can satisfy review only when every required launch label is
positive or negative. Audit-only labels may remain unknown without blocking completion.

Spans are the canonical location of positive labels. `whole_word_labels` is a derived view containing labels whose
positive spans cover `[0, grapheme_count)` without a gap. It is never edited or stored as an independent authority.
Validation rejects a positive label with no span and rejects any derived whole-word value that disagrees with the spans.

Stable word IDs replace keys such as `"{line_index}_{word_index}"`. Each annotation also binds to the page content hash,
image hash, and corrected-text hash. A split, merge, deletion, OCR rerun, image rotation, or text edit therefore cannot
silently reuse stale offsets.

The backend validates that every boundary falls on the canonical grapheme map and that
`0 <= start < end <= grapheme_count`. It rejects unknown labels, empty label sets, duplicate span IDs, stale hashes, and
unsupported schema versions.

## A clean schema break replaces character ranges

This project has no large installed base of character-range data. The implementation should favor one correct contract
over compatibility code. Before deletion, a read-only inventory must count every current `char_ranges` payload in
fixtures, page blobs, and event-store heads. The owner will approve a deletion report that lists the affected projects
and records. This inventory informs cleanup only; it does not create a migration or compatibility requirement.

The completed inventory found no persisted records. See
[`../research/2026-08-22-char-range-deletion-inventory.md`](../research/2026-08-22-char-range-deletion-inventory.md).

The change will:

- replace `CharRange` with canonical typography types;
- replace `WordMatch.char_ranges` with typography review state and spans;
- remove the `/char-ranges` endpoint after the replacement endpoint lands;
- replace `PageState.char_ranges_map` with stable-ID typography state;
- delete inclusive code-point semantics;
- remove the old frontend range model and tests;
- regenerate OpenAPI types from the new FastAPI contract;
- reject old range payloads instead of converting or dual-writing them.

No legacy migration adapter, fallback reader, or dual-write period is required. Development fixtures can be regenerated.

## Corrections are append-only event-store records

Every review action creates a correction revision. Later edits supersede earlier revisions without deleting them.

A correction records:

```text
TypographyCorrection
  correction_id
  page_id
  word_id
  base_page_content_hash
  base_corrected_text_hash
  decision
  annotations
  label_states{}
  source_evidence_ids[]
  prediction_ids[]
  reason_codes[]
  note
  reviewer_id
  reviewed_at
  labeler_version
  revision
  supersedes
```

Decisions include `accept`, `edit`, `reviewed_regular`, `reject_source`, `reject_alignment`, `unusable_image`, and
`defer`. Rejected, unusable, and deferred records remain available for audit but do not become training negatives.

`accept` copies the accepted positive spans and preserves explicit label states from the suggestion review. `edit`
stores the reviewer spans and explicit states. `reviewed_regular` sets every required launch label to negative and
leaves audit-only labels unchanged unless the reviewer decided them. Rejecting one suggested label sets only that label
to negative when the reviewer explicitly confirms its absence. `reject_source`, `reject_alignment`, `unusable_image`,
and `defer` do not infer any negative state.

The existing content-addressed event-store path must be extended to persist annotation state and correction provenance
atomically. The stored page content adds a versioned `typography` extension keyed by stable word ID. Each value contains
the current `WordTypography` and its latest correction ID. The appended `LabelerEdited` provenance node contains the
correction ID, decision, superseded correction ID, reviewer ID, base hashes, and new content-blob hash.

One backend operation validates the base hashes, writes the new content-addressed page blob, appends the
correction-bearing event, and advances the aggregate head. The API returns success only after the store confirms the new
head. If blob writing, event append, or head advancement fails, the operation returns an error. It does not update the
in-memory page and cannot report the correction as saved.

Reload reconstructs typography only from the selected event-store head and its referenced page blob. It does not merge
mutable process state into stored truth. Before the feature can be enabled, integration tests must prove mutation,
process-state eviction, reload, and exact reconstruction. They must also prove failure without a false success response.

Undo and redo use the existing page-history mechanism. An undo appends a new event that restores a prior content state.
It does not erase the correction record that was undone.

The mutation API requires the current page content hash and corrected-text hash. A stale browser tab receives a conflict
response and must reload or reapply its draft. This prevents concurrent tabs from silently replacing each other's spans.

## Page-level review balances completeness and speed

Reviewers can work word by word or navigate only unresolved words. The page worklist supports filters for unreviewed,
suggested, mixed-style, quarantined, stale, rare-label, and low-confidence words.

A reviewer may confirm all remaining predicted-regular words after visually reviewing the page. The action:

- applies only to words whose current suggestion is regular;
- excludes stale, warned, quarantined, mixed-style, and low-confidence words;
- records one bulk-confirmation event plus the exact affected word IDs;
- records reviewer, page version, model version, threshold, and timestamp;
- remains undoable;
- contributes reviewed-regular states to page completion;
- marks the resulting examples for sampled quality audit.

There is no unconditional “mark every word regular” action. A bulk operation must list its excluded words before
confirmation.

Page progress shows text reviewed, typography reviewed, quarantined, stale, and remaining counts. The existing page-done
control stays disabled until both review gates pass.

## Source-data bundles can arrive without OCR geometry

`pdomain-source-data` supplies source evidence to the SPA through immutable labeling bundles. A bundle may contain no
OCR geometry because PGDP, Project Gutenberg, and Standard Ebooks usually provide text and markup rather than usable
word boxes.

An inbound bundle contains:

- page image, page identity, and source artifact hashes;
- PGDP F2 bytes, parsed text, markup, notes, and warnings when available;
- matched Project Gutenberg artifacts and alignment evidence;
- matched Standard Ebooks artifacts and alignment evidence;
- work, edition, and derivation relationships among the sources;
- source conflicts and confidence tiers;
- immutable bundle ID, schema version, and configuration hash;
- optional prior OCR and geometry when a reviewed result already exists.

The SPA runs the existing text-recognition and page-region models when OCR results are absent or explicitly refreshed.
It records each model version, configuration, runtime preprocessing contract, and generated page, line, word, and
optional character geometry.

The SPA then aligns source text and typography evidence to its OCR lines and words. OCR supplies geometry and alignment
anchors, not ground truth by itself. The scan image remains authoritative for visible typography. Human review
establishes the final text, geometry, and typography.

`pdomain-source-data` may cache reviewed OCR output returned by the SPA. It does not become another OCR runner.

## Cross-source matching preserves derivation and disagreement

PGDP, Project Gutenberg, and Standard Ebooks records often describe the same work or derive from one another.
`pdomain-source-data` represents these relationships as an evidence graph rather than three independent corpora.

The graph separates:

```text
Work
  Edition
    Source artifact
      Page or text segment
```

An edge records its evidence. Evidence can include a PG ebook number from PGDP metadata, Distributed Proofreaders
credit, publisher and date, volume or translator, source-scan identity, Standard Ebooks source metadata, distinctive
text fingerprints, global alignment score, manual confirmation, and artifact hashes.

Matching starts with the PG ebook number when available, but an identifier alone does not prove physical-edition
identity. The matcher verifies edition matter, scan provenance, DP credit, and distinctive text before projecting
evidence.

Book alignment is global and monotonic. It permits page splits and merges, blank pages, plates, moved notes, joined
page-break words, and post-processing changes. Every accepted and rejected match retains its evidence, thresholds, tool
version, and runner-up margin.

## Page ground truth fuses fields instead of choosing one corpus

No corpus is the best source for every field. Page materialization selects the best supported value per field and
grapheme while preserving every contributing source.

Evidence priority is:

1. The scan image is authoritative for visible typography.
2. Human SPA corrections are authoritative for reviewed text, geometry, and typography.
3. PGDP F2 is the strongest initial page-local typography source because it corresponds to scan pages.
4. Project Gutenberg master artifacts can improve wording and resolve post-processing changes, notes, and final
   formatting.
5. Standard Ebooks provides useful editorial and typographic evidence, but remains weak supervision because it can
   normalize or reinterpret the source.
6. SPA OCR supplies geometry and alignment anchors.
7. Synthetic examples never contribute ground truth for a real page.

A materialized page can therefore use PGDP for span boundaries, Gutenberg for corrected wording, SPA OCR for word boxes,
and a human decision for disputed punctuation. The record explains each choice through field-level and span-level
evidence links.

The fused `PageGroundTruth` contains image and page identity, corrected visible text, graphemes, typography spans,
reviewed geometry, source evidence, conflicts, confidence tiers, review state, and derivation version. Automatic fusion
accepts only deterministic high-confidence agreement. Every ambiguity enters the SPA review queue.

## The exporter creates immutable typography training snapshots

Typography export is a first-class task. It does not overload the existing DocTR recognition and detection export.

The exporter reads explicit event-store heads. It never reads mutable in-memory sidecars as training truth. Each run
writes a content-addressed canonical manifest with the input project, page heads, schema versions, tool version,
configuration hash, deterministic source-version metadata, and output hashes. A separate run receipt may record
wall-clock creation time, operator, destination, and job ID. The receipt is not part of the canonical manifest hash.

Each example preserves:

- project, work, edition, page, line, and stable word identities;
- source image identity and hash;
- page, line, and word crop boxes with named coordinate spaces;
- content-addressed locators and hashes for target-word and short-line context crops;
- source-to-oriented-page and page-to-crop transforms;
- crop-recipe version, context-window rule, padding, orientation, resampling, color conversion, and preprocessing
  hashes;
- original OCR text and corrected ground-truth text;
- full-line recognized and corrected text when available;
- grapheme table and source offsets;
- word and target-grapheme masks;
- canonical spans and whole-word labels;
- structural context, including a separate drop-cap signal;
- available baselines, x-heights, and character boxes;
- original suggestions, human corrections, and review decisions;
- reviewer and correction revision provenance;
- parser, alignment, and labeler warnings;
- page content, image artifact, model, calibration, and schema versions;
- dataset split and leakage-group identity when already assigned.

Only `reviewed` and `reviewed_regular` records enter the promoted training set. Quarantined, deferred, stale, and
unusable records go to separate audit outputs. Rejected predictions remain attached as evidence and do not create
negative labels unless the reviewer explicitly marked the relevant label negative.

Rerunning export against the same heads and configuration must produce byte-identical records and hashes. Training code
consumes this snapshot through a public manifest. It must not read the labeler's event database or internal state
directly.

## Corrected records enter training through a controlled loop

The labeler is the human authority for corrections. The shared `pdomain-source-data` package owns ingestion,
cross-corpus matching, queue construction, audit, split enforcement, and promotion for typography, recognition,
detection, and page-region tasks.

The loop is:

1. Source-data ingestion records immutable images, source text, markup, provenance, and cross-source relationships.
2. Source-data materialization creates a geometry-optional labeling bundle from matched evidence, model output, random
   audit, rare labels, and difficult corpus strata.
3. The SPA loads the image and source evidence, then runs OCR when reviewed geometry is absent.
4. The SPA aligns source evidence to its OCR result.
5. A reviewer corrects text, geometry, and typography or records why the item cannot be used.
6. The event store appends the correction and advances the page head.
7. Typography export freezes selected page heads into a candidate correction bundle.
8. Source-data import validates bundle IDs, hashes, splits, schemas, and review completeness.
9. Audit and adjudication promote accepted records into a new source-data version.
10. Training records the exact promoted-manifest hash in every run.

Validation and test corrections never flow into training. The split manifest controls promotion, even when a reviewer
labels those pages in the same SPA.

Model-driven queues record the selecting model version. Evaluation must disclose when a test or audit set was selected
by the model being measured. Active-learning gains are compared with an equal-size random-review sample.

## Review quality is measurable

Before production review, annotators complete a calibration set with agreed label definitions and difficult boundary
cases. The system retains their results.

Quality reports include:

- agreement per label;
- exact-span agreement;
- boundary-distance disagreement;
- reviewed-regular agreement;
- disagreement reasons;
- correction rates by source, model version, language, period, genre, and scan quality;
- bulk-confirmation audit error rate;
- reviewer and adjudicator provenance.

Selected items receive a second independent review. Disagreements enter adjudication without hiding either original
decision. Promotion thresholds remain owner-approved dataset policy rather than hard-coded SPA behavior.

## Failure handling protects training truth

Text changes make existing spans stale. The UI preserves them as evidence, blocks completion, and asks the reviewer to
remap or replace them.

Word split, merge, deletion, OCR rerun, rotation, and image replacement follow the same rule. Automatic remapping may be
offered only when it records its alignment and still requires human confirmation.

Missing context does not block annotation. The labeler shows the target crop and records which context fields were
unavailable. The model can then learn from the example through its word-only fallback path.

An export fails before writing a promoted manifest when it finds a stale hash, unknown label, invalid grapheme boundary,
missing crop, unsupported schema, incomplete review state, or split conflict. Partial artifacts remain diagnostic only
and cannot be advertised to training.

## Repository boundaries keep responsibilities clear

`pdomain-book-tools` owns canonical typography annotations, corrections, grapheme indexing, validation, and portable
serialization.

`pdomain-ocr-labeler-spa` owns the correction UI, page completion rules, review actions, event-store persistence,
contextual evidence display, and immutable export job.

The proposed `pdomain-source-data` package owns source ingestion, artifact identity, the work and edition evidence
graph, cross-corpus matching, labeling-bundle materialization, correction import, audit, adjudication, split
enforcement, corrected-record materialization, and promotion. Its shared core serves recognition, detection, typography,
glyph-form, and page-region tasks. Task modules own their taxonomies, validation, and materializers.

`pdomain-ocr-training` consumes promoted manifests. It owns contextual and word-only datasets, models, losses,
evaluation, calibration, and model export.

`pdomain-ocr-synth` produces synthetic examples under the same canonical grapheme and label contract. Synthetic data
never satisfies a human review requirement and never enters real validation or test sets.

## Acceptance criteria define a complete correction path

The shared contract is accepted when:

- Unicode grapheme boundaries and half-open spans round-trip exactly;
- overlapping and multi-label spans round-trip exactly;
- unknown and reviewed-regular states remain distinct;
- stale page, image, and text hashes are rejected;
- stable word identities survive page serialization;
- no source evidence is overwritten by a correction.

The manual editor is accepted when a reviewer can:

1. Correct text.
2. Inspect the word and its surrounding line.
3. Create overlapping grapheme spans.
4. Accept or reject a suggestion.
5. Mark a word reviewed regular.
6. Save and reload the exact state.
7. Undo and redo the correction.
8. See stale annotations after changing text.

The page gate is accepted when:

- text and typography progress are reported separately;
- every retained word contributes exactly once to the typography denominator;
- unresolved, stale, quarantined, and deferred words block completion;
- a page reaches done only when text and typography are both complete;
- bulk regular confirmation records its exact scope and excludes unsafe words.

The exporter is accepted when:

- it reads frozen event-store heads;
- every record contains both target and contextual evidence;
- every positive, negative, and unknown label state remains explicit;
- page, text, image, correction, model, and schema versions are present;
- rejected and deferred evidence cannot leak into training as negatives;
- split conflicts stop promotion;
- identical inputs produce byte-identical manifests;
- an end-to-end test proves edit, reload, undo, redo, export, and record equality.

The model integration is accepted when:

- training can load both target-word and short-line views;
- the target mask selects exact scored graphemes;
- missing context uses the recorded fallback path;
- a word-only ablation and contextual model use the same immutable split;
- real-scan evaluation shows whether context improves small caps, letter spacing, weight, face-change, and mixed-style
  metrics;
- immutable real validation and test records remain outside training.

## Rollout and rollback preserve the existing labeler

Implementation starts with canonical types and backend validation. The SPA then replaces the range editor, adds the page
gate, and adds export. Model suggestions arrive only after the manual path passes end-to-end tests.

The feature remains disabled until typography persistence, reload, undo, and export are proven together. During
development, pages keep their existing text-validation state and do not claim the new combined done state.

Rollback disables the typography feature and combined completion gate while preserving event-store records and exported
manifests. It does not reinterpret typography as whole-word OCR style labels or write spans back into the retired
character-range format.

## Approved product decisions

- Page completion requires both text and typography review.
- Every retained word needs confirmed labels or an explicit reviewed-regular state.
- Page-level bulk confirmation is allowed only for safe predicted-regular words after visual review and with audit
  provenance.
- The existing character-range editor will be refactored into the new grapheme-aware editor.
- The project does not need legacy character-range compatibility.
- Surrounding line context is a first-class review and model input.
- The two-view short-line model is the primary production experiment; word-only remains an ablation and fallback.
- The contextual-first decision supersedes the earlier word-first experiment sequence in the typography model design.
- Drop caps remain structural context, not general inline spans.
- Typography export is separate from DocTR recognition and detection export.
- The SPA accepts geometry-optional immutable bundles from `pdomain-source-data` and produces immutable correction
  bundles in return.
- The SPA remains the OCR and geometry producer when source bundles lack reviewed OCR output.
- `pdomain-source-data` fuses PGDP, Gutenberg, Standard Ebooks, OCR, and human evidence per field rather than selecting
  one preferred corpus.

## Unresolved owner decisions

- Choose the exact owner and format for stable word IDs before implementation.
- Choose the first label taxonomy version. Underline remains audit-only until a later owner decision makes it trainable.
- Choose which confidence and warning conditions exclude a word from bulk regular confirmation.
- Choose whether a quarantined word can be excluded from page completion by an explicit adjudicator waiver, or must
  always keep the page incomplete.
- Choose reviewer identity policy for local single-user installations.
- Choose the required double-review rate and promotion thresholds.
- Choose the context window rule by pixel width, neighboring word count, or both.
- Choose JSONL, Parquet, or a paired manifest format for portable typography exports.

## Local evidence

- Current right-panel host:
  [`frontend/src/components/right-panel/WordDetail.tsx`](../../frontend/src/components/right-panel/WordDetail.tsx)
- Current range editor:
  [`frontend/src/components/right-panel/sections/CharRangesSection.tsx`](../../frontend/src/components/right-panel/sections/CharRangesSection.tsx)
- Current mutations: [`frontend/src/hooks/useWordMutations.ts`](../../frontend/src/hooks/useWordMutations.ts)
- Current API contract: [`src/pdomain_ocr_labeler_spa/api/words.py`](../../src/pdomain_ocr_labeler_spa/api/words.py)
- Current sidecar state:
  [`src/pdomain_ocr_labeler_spa/core/project_state.py`](../../src/pdomain_ocr_labeler_spa/core/project_state.py)
- Event-store sidecars:
  [`src/pdomain_ocr_labeler_spa/core/labeler_sidecars.py`](../../src/pdomain_ocr_labeler_spa/core/labeler_sidecars.py)
- Current exporter:
  [`src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py`](../../src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py)
- Related glyph-form spec: [`specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md)
- Typography model design:
  `/workspaces/pdomain/pdomain-ocr-training/docs/specs/2026-08-21-fine-grained-typography-model-design.md`
