---
kind: handoff
status: "active"
created: "2026-07-17"
created_at: "2026-07-17T09:19:40Z"
owner: CT
branch: master
scope: issue-tracker-migration
worktree: /workspaces/pdomain/pdomain-ocr-labeler-spa
base_commit: 8547be6da60d5d24e37682195799a278a1d5a1cb
supersedes: ""
---

# Issue tracker migration — pickup prompt

## Agent Index

- Kind: handoff
- Status: active
- Read when: you are asked to migrate, clean up, or close out this repo's
  GitHub issue tracker, or to pick up the "issue tracker migration" scope.
- Search terms: issue tracker migration, roadmap, close issues, archive
  issues, docs/roadmap.md, docs/decisions archive, gh issue delete

## Goal

Clear this repo's GitHub issue tracker of stale open backlog by migrating it
into durable docs, then delete the migrated issues from GitHub. Concretely:

1. Migrate the open backlog into a new `docs/roadmap.md`.
2. Archive each migrated issue's full text (body + comments) into Git
   history via a `docs/decisions/` doc that is committed and then removed.
3. Delete the migrated issues from GitHub with `gh issue delete`.

This is the same pattern already run to completion in two sibling repos:
`pdomain-ocr-cli` (50 issues migrated) and `pdomain-ocr-simple-gui` (37
issues migrated, roadmap-first). Follow that pattern here, adapted to this
repo's much smaller open backlog.

## Current state

As of `base_commit` above, working tree clean, `gh` authenticated with admin
access on `pdomain/pdomain-ocr-labeler-spa`.

- **Open issues: 4.** All four are `kind:chore`. Label breakdown across the
  four:
  - `status:blocked` — 1 (`#460`)
  - `status:backlog` — 3 (`#437`, `#433`, `#430`)
  - `area:refactor` — 1, `area:tests` — 1, `area:ci` — 2
  - `priority:low` — 1, `priority:medium` — 3
  - `effort:S` — 3 (all three `status:backlog` issues)
- **Closed issues: 425.** Large closed history, not in scope for this pickup
  (see Decisions below).
- **The 4 open issues:**
  - `#460` — "Revisit cast(Page, ...) vs isinstance(...) in lift resolvers
    after M3 PageRecord lands." Deliberately deferred follow-up from a prior
    fix (`#459`, commit `b66fc19`): production code uses `cast(Page, ...)`
    instead of `isinstance(..., Page)` because test fixtures are duck-typed
    stubs that fail `isinstance`. Explicitly gated on the M3 `PageRecord`
    milestone landing (see `core/page_state.py:116`). This is real,
    well-specified future work, not stale noise — but it cannot start until
    M3 ships, hence `status:blocked`.
  - `#437` — "[F-032] Route/OpenAPI tests check presence, not schema
    quality." `status:backlog`, `effort:S`, `area:tests`. Comes from a
    findings series (`F-0xx` prefix), real pending work.
  - `#433` — "[F-028] OpenAPI drift check compares ignored
    `frontend/openapi.json`." `status:backlog`, `effort:S`, `area:ci`. Same
    findings series.
  - `#430` — "[F-025] GitHub CI is not equivalent to documented `make ci`."
    `status:backlog`, `effort:S`, `area:ci`. Traced to
    `docs/research/2026-05-22-deep-code-review-security-scan.md`: the
    `Makefile` `ci` target runs `pre-commit-check` and `frontend-knip`, but
    `.github/workflows/ci.yml` omits both, so local and remote CI gates can
    disagree.
  - **Read on these four:** all are genuine, specific, still-relevant
    backlog items (three carry concrete file/commit evidence, not vague
    placeholders). None look safe to just delete without carrying the intent
    forward — this is a real, if small, backlog, not tracker cruft.
- `docs/decisions/` already exists in this repo (e.g.
  `docs/decisions/2026-07-13-shared-page-record-boundary.md`), so the
  archive-doc pattern has a home.
- No `docs/roadmap.md` yet.
- `docgraph` is present (`DOCGRAPH.md` at repo root) — treat this as a
  docgraph-governed repo; run `docgraph` checks after writing new docs.
- Admin access on the repo confirmed (`admin:true` via `gh api
  repos/pdomain/pdomain-ocr-labeler-spa`), so `gh issue delete` will work
  when the time comes.

## Decisions

- **Scope: migrate the 4 open issues.** This is the recommended and
  sufficient scope for this pickup. All four are real, well-described
  backlog items, so each should land as a roadmap entry before its issue is
  deleted.
- **Do not touch the 425 closed issues by default.** Archiving and deleting
  the entire closed history is a much bigger, strictly optional job (only
  relevant if someone explicitly wants a full tracker wipe, not just an
  open-backlog cleanup). At this repo's closed-issue volume the archive
  document would be very large and slow to produce and review. Unless a full
  wipe is explicitly requested, leave all closed issues alone and migrate
  only the 4 open ones.
- **Roadmap-first is required, not optional**, because the open issues are
  unfinished backlog (one blocked, three backlog-status). Never delete an
  issue without first carrying its intent into `docs/roadmap.md` — the
  roadmap is the thing that keeps the work alive after the issue is gone.
  With only 4 open issues, a lightweight roadmap document is entirely
  adequate; there's no need for elaborate roadmap machinery here.

## The proven procedure

1. **Pull full issue content before touching anything.** For each in-scope
   issue:

   ```
   gh issue view N --repo pdomain/pdomain-ocr-labeler-spa \
     --json number,title,author,createdAt,closedAt,state,stateReason,labels,body,comments,url
   ```

   Save the output to a scratch file and take a `sha256sum` of it, so the
   archive doc can be checked against the original API response later.

2. **Author `docs/roadmap.md`**, mirroring the structure of
   `../pdomain-ocr-cli/docs/roadmap.md` (now/next/later style sections).
   Give each migrated item a line that cites its original issue number as
   `#NNN` so the provenance is traceable even after the issue is deleted.

3. **Render the archive doc** at
   `docs/decisions/2026-07-DD-closed-issues-archive.md` (pick the actual
   date). It needs:
   - Standard docgraph frontmatter: `kind: decision`, `status: retired`.
   - An `## Agent Index` block (Kind/Status/Read when/Search terms) exactly
     like other docs in this repo.
   - Body sections: `## Context`, `## Decision`, `## Consequences`,
     `## Supersedes`.
   - Then one `## #N — <title>` section per migrated issue, each containing
     its metadata (author, created/closed dates, state, state reason),
     labels, URL, and the **full body plus every comment, verbatim**.
   - Add `<!-- markdownlint-disable -->` immediately after the frontmatter
     block — the raw issue text will not conform to markdownlint rules and
     should not be reformatted or lossy-edited to satisfy them.

4. **Commit in two steps, not one:**
   - Commit the roadmap and the archive doc together first.
   - Then, in a **second, separate commit**, `git rm` the archive doc. Cite
     the first commit's SHA in the removal commit message, along with the
     retrieval command (`git show <sha>:<path>`) so a future reader can
     recover the full text straight from Git history. The roadmap stays live
     in the tree; the archive doc's job is done once it exists in history —
     Git itself becomes the tombstone.

5. **Only after the archive commit exists**, delete the migrated issues from
   GitHub:

   ```
   gh issue delete N --repo pdomain/pdomain-ocr-labeler-spa --yes
   ```

   This is **permanent** — GitHub does not support undeleting an issue.
   Get an explicit human "go" before running any `gh issue delete` command,
   even though the archive already preserves the content in Git history.

## Gotchas

- The `pre-commit-update` hook may bump `.pre-commit-config.yaml` during a
  commit and abort it. If that happens: `git checkout -- .pre-commit-config.yaml`
  to revert the bump, then retry with `SKIP=pre-commit-update git commit ...`.
- Validate new/changed docs with the `markdownlint-cli2` pre-commit hook and
  the docgraph check MCP tool (`docgraph_check` / `mcp__docgraph__docgraph_check`)
  before committing. An "orphan doc" advisory from docgraph on the archive
  doc is expected and fine — it is deliberately short-lived and gets removed
  in the very next commit.

## Pointers

- `docs/roadmap.md` — does not exist yet; this pickup creates it.
- `docs/decisions/` — existing home for the archive doc.
- `DOCGRAPH.md` — repo's docgraph configuration/entry point.
- `../pdomain-ocr-cli/docs/roadmap.md` — reference roadmap structure/style.
- `../pdomain-ocr-simple-gui/docs/roadmap.md` — second reference, also
  roadmap-first.

## Reference worked examples

- `pdomain-ocr-cli` — archive-then-delete pattern, commit `9498407`.
- `pdomain-ocr-simple-gui` — roadmap-first pattern, add commit `ec3979f`
  followed by the archive-removal commit `7f3be6b`.
- Agent memory: `closed-issue-archive-pattern` (see
  `.claude/agent-memory/` conventions in this workspace) documents the
  general procedure distilled from those two runs.

## Resume steps

1. `gh issue view 460 --repo pdomain/pdomain-ocr-labeler-spa --json number,title,author,createdAt,closedAt,state,stateReason,labels,body,comments,url`
2. Repeat step 1 for `437`, `433`, and `430`, saving each to scratch and
   hashing it.
3. Draft `docs/roadmap.md` from the four pulled issues, using
   `../pdomain-ocr-cli/docs/roadmap.md` as the structural template.
