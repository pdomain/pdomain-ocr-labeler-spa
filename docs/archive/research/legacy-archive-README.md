# docs/archive — closed entries that no longer belong in active docs

Closed bugs, resolved questions, and other historical records are archived
here so the active docs stay focused on what's still in flight. Entries are
preserved verbatim from their source files; cross-references in active docs
use `docs/archive/<file>.md#<anchor>` links.

## Files

- **[`BUGS_RESOLVED.md`](BUGS_RESOLVED.md)** — closed entries from
  [`../BUGS_FOUND.md`](../BUGS_FOUND.md). Sorted by `B-NN` numerically (oldest
  at top). Closing-commit hash + iter number live in the **Status** line.
- **[`QUESTIONS_RESOLVED.md`](QUESTIONS_RESOLVED.md)** — answered questions
  from [`../../OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md), each with the
  user's resolution and a link to the landing ADR in `specs/17-decisions.md`.
  Includes the canonical Resolution-log table.
- **[`specs/`](specs/)** — predecessor brainstorm / design docs that produced
  the canonical architecture specs under `../architecture/`. The `2026-05-12-*`
  set is the original `spec-from-issue` output that became
  `00-overview.md` through `19-auto-rotation.md` (and `20-glyph-annotations.md`
  in `specs/`). Kept here as historical reference only — `docs/architecture/`
  is the source of truth for shipped behavior.
- **[`plans/`](plans/)** — historical implementation execution plans
  (no longer driving open work).

## Convention — "archive on close"

When closing a bug or resolving a question, move the entry to the matching
archive file **in the same commit** that lands the close (don't leave the
entry in the active list with a `(closed)` tag — active docs are for
in-flight work). The active doc keeps only a one-line pointer to this
folder so the discovery path stays obvious. See
[`../DEVELOPMENT.md` § Archive on close](../DEVELOPMENT.md#archive-on-close)
for the per-step recipe.

## Why a per-repo archive (not the workspace `LOOP_STATE.md`)

Workspace-level `/workspaces/ocr-container/docs/LOOP_STATE.md` records the
chronological iteration log across all `pd-*` repos. The per-repo archive
here is *different*: it preserves the **full bug/question entry** (problem
statement, reasoning, fix details) so future contributors can understand
*why* a closed item was closed without spelunking through commit history.
The iter row is a one-line breadcrumb; the archive is the prose record.
