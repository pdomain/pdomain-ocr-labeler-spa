---
kind: architecture
status: built
owner: maintainers
created: 2026-11-12
last_verified: 2026-11-13
---

# Repository boundaries

## Agent Index

- **Kind:** architecture
- **Status:** built
- **Owner:** maintainers
- **Last verified:** 2026-11-13
- **Read when:** deciding whether a new job belongs in this SPA or in a sibling repository.
- **Search terms:** repository boundaries, sibling repos, book-tools, source-data, training, synth, predictor.

This labeler owns review and correction of one book's pages. Shared contracts, OCR, source preparation, training, and
the PGDP pipeline already live in other repositories. Do not grow those jobs inside this SPA.

## What this repository owns

The FastAPI and React app owns the labeling UI, page completion, the per-page event store, review actions, and the
export job that hands a finished book to Trainer.

That includes region and page-kind review, word and line editing, typography review, manual glyph marks, rotation, and
the driver `data-testid` contract. The [typography contract](31-typography-review.md) and the
[module map](module-map.md) name the code.

## What sibling repositories already own

These checkouts sit next to this repo under `/mnt/work/projects/pdomain/`. Versions below are the ones this repo
requires today.

| Repository | Owns | How this labeler uses it |
| --- | --- | --- |
| `pdomain-book-tools` | OCR runtime and page models. Requires `>=0.31.3,<0.32`. | DocTR prediction, layout, and image rotation. Do not reach into its internals. |
| `pdomain-book-contracts` | Shared annotation, layout, glyph, and alignment contracts. Requires `>=0.3.3`. The lockfile selects `0.3.3`. | Region roles, page kinds, glyph wire values, and P3-F2 alignment. |
| `pdomain-ops` | Suite page records, paths, provenance, and export schemas. Requires `>=0.12.6`. | `PageRecord` and shared lifecycle types. Labeler-only view state stays in `extensions["labeler"]`. |
| `pdomain-pgdp-measure` | Page measurement. Requires `>=0.1.0`. | Book-scoped page-kind proposals. |
| `pdomain-ui` | Shared shell, canvas, and worklist chrome. The frontend requires `^0.13.0`. | App shell and shared primitives. Domain panels stay local. |
| `pdomain-prep-for-pgdp` | The PGDP stage pipeline. | Structural reference only. Do not port its 24-stage product here. |
| `pdomain-pgdp-api-client` | PGDP API access. | Not a labeler feature. |
| `pdomain-source-data` | Shared public-domain source preparation, schemas, and manifests. Raw corpora stay outside Git. | Prepared bundles may feed region review. Do not reimplement ingestion here. |
| `pdomain-ocr-training` | Detection and recognition training, evaluation, and model export. | The labeler does not train models. Consuming typography bundles there is still future work. |
| `pdomain-ocr-trainer-spa` | Trainer UI for profiles, datasets, runs, evaluation, and model publish. | DocTR export can launch it. Training screens do not belong in the labeler. |
| `pdomain-ocr-synth` | Synthetic OCR image and text pairs. | Synthetic rows never satisfy human review and never enter real validation or test sets. |
| `pdomain-ocr-cli` | Batch OCR from the command line. | Separate from this UI. |

`pdomain-ocr-simple-gui` is another OCR interface. Do not fold it into this labeler or split a third UI out of this
repo for the same job.

Two directories, `ml-training` and `ml-validation`, also exist beside this repo. They were not reviewed, so this
document assigns them no work.

## Work that stays out of this repository

- A glyph predictor. The 2026-09-18 decision rejected one in this app. The accept-prediction control stays inert. If a
  predictor is built later, put inference with the OCR runtime in `pdomain-book-tools`, or training in
  `pdomain-ocr-training`. Do not start a new repository for it.
- Finer predictor-build progress. The missing callback belongs in `pdomain-book-tools`. This app already shows the
  coarser load stages. See [page loading](29-page-loading-and-history.md).
- Typography training loops, losses, and model export. The labeler can write an immutable correction bundle.
  Consumption of that bundle in `pdomain-ocr-training` and `pdomain-ocr-trainer-spa` is still
  [roadmap](../context/intent-map.md) work, not shipped behavior.
- Source ingestion, cross-corpus matching, and adjudication. `pdomain-source-data` already exists for that.
- Managed auth, S3, Postgres, and managed adapters. D-042 in [`specs/17-decisions.md`](../../specs/17-decisions.md)
  defers them. Do not open a deployment repository until there is a deployment to run.
- The PGDP stage registry, stage folders, proof pack, and submit workflow.

## Evidence

- Code: `pyproject.toml` dependency block and `frontend/package.json` `@pdomain/pdomain-ui` range.
- Lockfile: `uv.lock` selects `pdomain-book-contracts` `0.3.3`, `pdomain-book-tools` `0.31.3`, and `pdomain-ops` `0.12.6`.
- Decision: [`docs/context/decisions.md`](../context/decisions.md) entry "2026-11-09 — Use published contracts v0.3.0".
- Verified: 2026-11-13 by reading those manifests and the sibling `README.md` or `AGENTS.md` files named above.
