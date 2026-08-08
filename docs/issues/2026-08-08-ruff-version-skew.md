---
kind: issue
status: active
owner: maintainers
created: 2026-08-08
last_verified: 2026-08-08
level: I1
---

# The lint gate runs a different ruff than the project does, and rewrites source

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-08-08
- **Resolution:** Open
- **Severity:** Medium — the full gate fails on a clean tree and edits a source file as a side effect
- **Affected version:** pdomain-ocr-labeler-spa @ f4ae475
- **Read when:** the lint gate fails but `uv run ruff check` passes, or `bootstrap.py` changes on its own
- **Search terms:** ruff version skew, PLR0917, RUF100, LOG004, pre-commit ruff, unused noqa, lint gate red
- **Relates to:** [issues index](README.md)

## Summary

Two different ruff versions run against this repository. The pre-commit hook is
pinned to v0.16.2, while the project's own environment resolves ruff 0.15.21.
The newer one finds 53 errors that the older one does not implement, so
`uv run ruff check` reports a clean tree and the full pre-commit pass fails on
that same tree.

One of those findings makes the gate mutate source. The `ruff-check` hook runs
with `--fix`, and ruff 0.16.2 considers a `# noqa: BLE001` in
`src/pdomain_ocr_labeler_spa/bootstrap.py` unnecessary, so an all-files run
deletes it. The file changes without anyone editing it.

## Impact

- The full pre-commit pass fails on a clean tree, and any CI path calling it
  fails with it.
- Running the gate modifies `bootstrap.py`. Anyone who runs it and then commits
  without reading `git status` carries an unintended source edit.
- The 53 findings are invisible to `uv run ruff check`, so a developer sees a
  green local check and a red gate with no obvious cause.

## Environment / versions

```text
pdomain-ocr-labeler-spa @ f4ae475
.pre-commit-config.yaml  ruff-pre-commit  rev: v0.16.2
pyproject.toml           dev group        "ruff>=0.15.13"
uv.lock                  ruff             version = "0.15.21"
```

## Evidence

### 1. The two versions disagree completely

```text
$ uv run ruff --version
ruff 0.15.21
$ uv run ruff check
All checks passed!

$ uvx ruff@0.16.2 check --no-fix
Found 53 errors.
```

### 2. The findings are rules 0.15.21 does not enforce

```text
$ uvx ruff@0.16.2 check --no-fix --output-format=concise | ...
     51 PLR0917
      1 RUF100
      1 LOG004
```

`PLR0917` (too-many-positional-arguments) was promoted from preview to stable in
ruff 0.16, which is why it appears all at once rather than gradually.

### 3. The RUF100 finding makes the gate write to the tree

The `ruff-check` hook is configured with `--fix`. `RUF100` reports an
unnecessary `# noqa`, and the fix deletes it, so `pre-commit run --all-files`
leaves `src/pdomain_ocr_labeler_spa/bootstrap.py` modified. This was observed
during the 2026-08-08 CI-gate work and reverted by hand both times it happened.

### 4. The dependency floor permits the drift

`pyproject.toml` asks for `ruff>=0.15.13`, and `uv.lock` resolved 0.15.21. The
pre-commit hook does not read either one. It builds its own isolated environment
at whatever `rev:` the config names, so the two can move independently and
nothing reconciles them.

## Root-cause hypotheses

1. **(Most likely) The hook pin was bumped without a matching lockfile bump.**
   The `rev:` moved to v0.16.2 while `uv.lock` stayed at 0.15.21. Nothing checks
   that the two agree, so the skew was silent until the new version started
   reporting findings. The same `pre-commit-update` hook that auto-rewrites pins
   would produce exactly this state.
2. **The floor constraint was never raised.** Even with a fresh `uv lock`,
   `ruff>=0.15.13` allows any newer release, so re-resolving is not guaranteed to
   land on the hook's version. This does not explain the current gap on its own,
   but it means fixing the lockfile once will not prevent a recurrence.

## Defects to fix

1. **The gate and the project run different linters.** One of the two versions
   has to become authoritative. (Primary)
2. **The gate edits source.** A read-only check should never leave the tree
   dirty. This resolves once the `RUF100` finding is addressed under an agreed
   ruff version.
3. **Nothing detects the skew.** No check compares the pre-commit `rev:` against
   the resolved ruff version, so the next drift is also silent.
4. **53 findings are unaddressed.** They are real under the version the gate
   enforces.

## Next steps

1. Raise the project's ruff to 0.16.2 so both sides match, rather than
   downgrading the hook. That aligns this repo with `pdomain-book-tools`,
   `pdomain-ocr-cli`, and `pdomain-ops`, which already run 0.16.2.
2. Fix the 51 `PLR0917` findings by making excess parameters keyword-only, not by
   suppressing the rule. `pdomain-book-tools` did this in commit 790ea84 and the
   approach transfers directly: keep the identifying arguments positional and
   move the rest behind `*`. Check every call site before choosing cut points.
3. Resolve the `RUF100` in `bootstrap.py` deliberately, by removing the stale
   `# noqa: BLE001` in a reviewed commit rather than letting the gate do it.
4. Fix the single `LOG004` finding on its own merits.
5. Consider raising the `ruff>=` floor to the adopted version so a future
   re-resolve cannot silently fall behind the hook.

## What is NOT broken

- `uv run ruff check`, `uv run ruff format --check`, and `basedpyright` all pass.
- The Python test suite passes; this is a lint-configuration problem, not a code
  defect.
- The frozen SHA pins in `.pre-commit-config.yaml` are intact and unrelated.
- The frontend lint and format tooling is separate and not affected.

## Resolution

*Open.* When fixed: set frontmatter and Agent Index `status: retired`, add the
resolving commit link here, and move the README pointer out of the open list.
