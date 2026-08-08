---
kind: issue
status: active
owner: maintainers
created: 2026-08-08
last_verified: 2026-08-08
level: I1
---

# The weekly dep-refresh has a structural accumulate-and-stick design, unproven only because it has never fired here

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-08-08
- **Resolution:** Open
- **Severity:** Medium — latent design gap; not yet observed to have caused
  harm in this repo, but this repo carries the workspace's most demanding
  merge gate
- **Affected version:** pdomain-ocr-labeler-spa @ 5a555e8
- **Read when:** deciding whether to pre-emptively fix `dep-refresh.yml`, or
  investigating why weekly dependency refreshes have not landed
- **Search terms:** dep-refresh, dated branch, delete_branch_on_merge, auto-merge,
  required status checks, branch protection, stray branch, dependency refresh
- **Relates to:** [issues index](README.md)

## Summary

`.github/workflows/dep-refresh.yml` creates a fresh dated branch
(`dep-refresh/$(date +%Y-%m-%d)-$GITHUB_RUN_ID`) on every run, the repository has
`delete_branch_on_merge: false`, and nothing reconciles a red week's leftover
branch with the next week's run. That is the same structural shape that produced
four consecutive stuck pull requests in `pdomain-ui` before a human batch-closed
them (see the cited spec). This repo shows **zero** dep-refresh branches and
**zero** dep-refresh pull requests today, but that is not evidence the design is
safe here — the workflow has **never run**, so the failure mode has simply never
had a chance to occur. This report is preventive, not a report of observed
accumulation.

## Impact

- If the schedule ever starts firing, red or unreachable refreshes will pile up
  branch by branch exactly as they did in `pdomain-ui`, because nothing here
  differs from that repo's pre-fix design (dated branch name,
  `delete_branch_on_merge: false`, no PR-reuse logic).
- This repo's `master` branch protection requires six status contexts — more
  than the four in the `pdomain-ui` case that failed — so a refresh has more
  ways to go red and get stuck once it starts running.
- Separately, and outside this issue's design scope: the dependency refresh
  itself is not happening. No automated dep-refresh commit has ever landed
  here, so Python/npm/Action-pin drift is accumulating silently regardless of
  which branch strategy is used.

## Environment / versions

```text
pdomain-ocr-labeler-spa @ 5a555e8
.github/workflows/dep-refresh.yml   added 2026-05-31 (574a679), schedule: '0 2 * * 0' (weekly, Sunday 02:00 UTC)
repo setting                        delete_branch_on_merge: false
master branch protection            required_status_checks.contexts:
                                       lint, test-backend, test-frontend,
                                       test-e2e, build-wheel, openapi-drift
```

## Evidence

### 1. The dep-refresh workflow has never run

```text
$ gh run list --repo pdomain/pdomain-ocr-labeler-spa --workflow dep-refresh.yml --limit 10
(empty)

$ gh workflow view dep-refresh.yml --repo pdomain/pdomain-ocr-labeler-spa
dep-refresh - dep-refresh.yml
ID: 286365132
Total runs 0
```

The workflow has been on `master` since commit `574a679` (2026-05-31) with a
weekly Sunday cron — roughly ten scheduled windows have passed — yet the Actions
API reports zero runs of it, ever. A repo-wide check of all 129 recorded workflow
runs confirms only `ci`, `release`, and the Dependency-Graph auto-workflow have
ever executed; `dep-refresh` is absent from that list entirely. The workflow is
listed as `active` (not disabled), so the schedule is simply not firing for a
reason this investigation could not determine from repo-level data (no access to
org-level Actions/schedule settings).

### 2. No dep-refresh pull request or branch has ever existed

```text
$ gh pr list --repo pdomain/pdomain-ocr-labeler-spa --state all --search "dep refresh" --limit 20
(empty)

$ gh api repos/pdomain/pdomain-ocr-labeler-spa/branches --jq '.[].name'
master
```

The 30 most recent PRs (back to 2026-05-11) contain no `dep-refresh/*`
head ref and no "dep refresh" title. `master` is the only branch in the
repository. This directly explains the "0 stray branches, 0 open PRs" starting
observation: there is nothing to accumulate because nothing has run, not
because the design already avoids accumulation.

### 3. One direct commit touched dependencies, but it is not evidence the automation ran

```text
$ git log -1 --format='%an <%ae>%n%cI%n%B' 6795a15
ConcaveTrillion <concavetrillion@gmail.com>
2026-07-12T10:28:45Z
chore: refresh dependencies for master branch
```

This commit landed directly on `master` on 2026-07-12, authored by the human
maintainer (not `github-actions[bot]`), with no corresponding PR. It updated
`uv.lock`, `frontend/pnpm-lock.yaml`, and workflow/script files by hand. It is a
manual catch-up refresh, not a run of `dep-refresh.yml` — the workflow's commit
message template (`"chore: weekly dep refresh (actions pins + all deps)"`)
does not match, and no PR record exists for it.

### 4. Required status checks all map to real jobs — no silent-block mismatch here

```text
$ gh api repos/pdomain/pdomain-ocr-labeler-spa/branches/master/protection --jq '.required_status_checks.contexts'
["lint","test-backend","test-frontend","test-e2e","build-wheel","openapi-drift"]
```

`.github/workflows/ci.yml` defines exactly these six jobs, each with a job-level
`name:` matching its job id (`lint`, `test-backend`, `test-frontend`,
`test-e2e`, `build-wheel`, `openapi-drift`), all triggered on `pull_request`.
Every required context is produced by a real job — **this repo does not have the
silently-blocking mismatch found in `pdomain-ops` and `pdomain-ocr-training`**
(where a required context names a check nothing in `.github/workflows/`
produces). This was the most load-bearing check in this investigation and it
came back clean.

### 5. `delete_branch_on_merge` is `false`, matching the pre-fix `pdomain-ui` state

```text
$ gh api repos/pdomain/pdomain-ocr-labeler-spa --jq '.delete_branch_on_merge'
false
```

### 6. GitHub Actions is disabled for the entire repository — this is the confirmed root cause

```text
$ gh api repos/pdomain/pdomain-ocr-labeler-spa/actions/permissions --jq '.enabled'
false

$ gh run list --repo pdomain/pdomain-ocr-labeler-spa --limit 1 --json createdAt,workflowName
[{"createdAt":"2026-07-12T10:08:58Z","workflowName":"Dependency Graph"}]

$ gh api repos/pdomain/pdomain-book-tools/actions/permissions --jq '.enabled'
true
```

Actions is disabled at the repository level, not per-workflow, so the block
applies to every workflow — `dep-refresh` included — not to dep-refresh
specifically. The repository's last recorded run of any kind, of any
workflow, is the `Dependency Graph` auto-workflow on 2026-07-12; nothing has
run since. For contrast, the peer repo `pdomain-book-tools` has Actions
enabled (`.enabled` = `true`) and its own `dep-refresh` has run on schedule
through 2026-08-02.

The consequence is larger than this report's original design-gap scope: this
repository has had no CI of any kind for nearly a month. Every pull request
merged here since 2026-07-12 was merged without a single status check
running.

## Root-cause hypotheses

1. **(Confirmed) GitHub Actions is disabled for the entire repository, which
   blocks every workflow including `dep-refresh`.** See Evidence item 6.
   `actions/permissions.enabled` is `false`; the last workflow run of any kind
   was 2026-07-12. This fully accounts for the "zero runs" observation in
   items 1 and 3 — no token or permissions-gap investigation is needed. The
   cron in `dep-refresh.yml` (`0 2 * * 0`) is unchanged and identical to the
   seven repos still running weekly, so no workflow-file edit is needed to
   restore the schedule; re-enabling Actions is sufficient.

   Five repos went dark on the same date, 2026-07-12: this repo,
   `pdomain-ocr-synth`, `pdomain-ocr-trainer-spa`, `pdomain-ocr-training`, and
   `pdomain-prep-for-pgdp`. The other seven repos in the workspace have run
   weekly through 2026-08-02. One date across five repos points at a single
   deliberate action rather than five coincidences. 2026-07-12 is also the
   date of the main-to-master default-branch rename and of a batch closure of
   stale dependency pull requests across several repos — but a causal link
   between either of those events and the Actions-disable has not been
   established from repo-scoped data.

   Whether disabling Actions was intentional and temporary, or a side effect
   of that day's other work, cannot be answered from this repo's data alone.
   If it was deliberate, the resolution to this issue should say so, and the
   remaining recommendations become dormant pending that decision rather than
   wrong.

2. **(Demoted — cause now confirmed as #1) The schedule trigger has not fired
   since the workflow was added.** Zero runs across ~10 possible Sunday
   windows, combined with zero PRs or branches of any dep-refresh shape, is
   consistent only with "never invoked," not with "ran and cleaned up
   correctly." At the time this was first written, why the schedule had not
   fired could not be confirmed from repo-scoped data — candidates included an
   org-level Actions/schedule restriction or a `DEP_REFRESH_TOKEN` /
   permissions gap. Evidence item 6 resolves this: Actions is disabled
   repository-wide, which blocks the schedule (and every other trigger)
   outright, so no token or permissions investigation is needed.
3. **The accumulate-and-stick design defect is present independent of #1.**
   Independent of why Actions was disabled, the workflow as written (dated
   branch name, `delete_branch_on_merge: false`, no PR-reuse or re-arm logic)
   is structurally identical to the pre-fix `pdomain-ui` workflow that
   produced four stuck PRs. If Actions is re-enabled without also fixing this
   design gap, the same failure mode would appear on the first red or
   unmerged week.

## Defects to fix

1. **Dated per-run branch name accumulates stray branches on every red or
   unmerged week.** `BRANCH="dep-refresh/$(date +%Y-%m-%d)-$GITHUB_RUN_ID"` in
   `.github/workflows/dep-refresh.yml` creates a new branch every run instead
   of reusing one. (Primary)
2. **No open-PR check before creating a new one.** The workflow always runs
   `gh pr create`, so a still-open prior refresh PR would collide with — or be
   orphaned by — the next run once the schedule does start firing.
3. **`delete_branch_on_merge: false` leaves a merged refresh's branch behind**
   instead of clearing it automatically.
4. **(Separate from the design gap, flagged for owner follow-up, not fixed by
   this report) The schedule itself has not produced a single run in over two
   months.** This is outside the scope of the `pdomain-ui` spec's fix and needs
   its own investigation (Actions schedule settings, `DEP_REFRESH_TOKEN`
   validity) before the design fix below can be observed working end to end.

## Next steps

0. **Decide whether to re-enable GitHub Actions — before anything else.** This
   is a workspace-level decision, not a per-repo one: the same disable event
   affects five repos (this one, `pdomain-ocr-synth`, `pdomain-ocr-trainer-spa`,
   `pdomain-ocr-training`, and `pdomain-prep-for-pgdp`), so it should be
   answered for all five together, not piecemeal. Nothing else in this report
   is testable until this decision is made — steps 1 and 2 below both require
   Actions to be running before their effects can be observed. If the disable
   is confirmed deliberate and meant to stay, steps 1 and 2 become dormant
   rather than wrong.
1. Apply the `pdomain-ui` design fix ahead of the first real failure, per the
   design spec at `pdomain-ui/docs/specs/2026-07-16-dep-refresh-auto-land-design.md`
   (a different repo; read-only reference, not adopted by this repo). Its
   relevant parts (B and C) apply directly here:
   - **One reusable branch.** Replace the dated branch name with a stable
     `dep-refresh` branch, force-pushed from a fresh `master` checkout each
     run.
   - **Open a PR only when none is open.** Check
     `gh pr list --head dep-refresh --state open` before `gh pr create`, then
     re-arm `gh pr merge --auto --rebase` every run so a still-open PR picks up
     the latest push.
   - **`delete_branch_on_merge: true`** on the repository setting, so a green
     auto-merge clears the branch and the next run starts clean.
   The spec's part A (an aggregated `unit-test` check) and its section 5
   rollout caveat about an admin-bypass first merge **do not apply to this
   repo** — Evidence item 4 above found no required-context mismatch here, so
   there is no equivalent gate-can-never-pass bug to work around before landing
   the fix.
2. Separately, investigate why `dep-refresh.yml` has produced zero runs since
   2026-05-31 (Evidence items 1 and 3) — check `DEP_REFRESH_TOKEN` validity and
   any org-level restriction on scheduled workflows — since the design fix
   above cannot be observed working until the workflow actually executes.

## What is NOT broken

- `master` branch protection's required status checks all map to real
  `ci.yml` jobs; there is no silent permanent-block bug like the one found in
  `pdomain-ops` / `pdomain-ocr-training`.
- No dep-refresh branches or pull requests currently exist to clean up — the
  repo is not in a stuck or degraded state today.
- `ci.yml` and `release.yml` both have run history and are not implicated.

## Resolution

_Open._ When fixed: set frontmatter and Agent Index `status: retired`, add the
resolving commit link here, and move the README pointer out of the open list.
