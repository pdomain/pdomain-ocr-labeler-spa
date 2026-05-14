# Conventions — pd-ocr-labeler-spa

<!-- workspace-conventions:start -->

## Rule: No comments explaining what code does

**The rule.** Don't add comments that restate what the code does;
well-named identifiers already do that. Only add a comment when the
WHY is non-obvious: a hidden constraint, a subtle invariant, or a
workaround for a specific bug.

**Why.** Comments rot when code changes and become misleading. The rule
also applies to docstrings — one short line max; no multi-paragraph
docstrings and no multi-line comment blocks.

**Common high-confidence violations** (bot auto-fix candidates)

- One-line summary comment immediately above a function that restates its name.
- `# returns the X` or `# sets the Y` before a return/assignment statement.
- Multi-line docstrings that explain every parameter with no non-obvious WHY.
- Section divider blocks: `# ---…---` / `# ===…===` multi-line banners used as
  navigation headers in test files — class names and blank lines already
  provide structure; remove the banner, keep the blank lines.
- Multi-paragraph module or class docstrings with a "Focus on:" / "Covers:"
  section — collapse to a single-line summary.

**Common judgment-call violations** (bot flags, CT decides)

- Comments that reference the PR, issue, or task that introduced the code — belongs in commit message, not source.
- Multi-line preamble that mixes WHY (worth keeping) with WHAT (worth removing).

## Rule: Unicode escape sequences for ruff-flagged ambiguous characters

**The rule.** Characters ruff flags under RUF001/002/003 (ambiguous Unicode —
curly quotes, en-dashes, em-dashes, multiplication signs, non-breaking spaces,
etc.) must be written as `\uXXXX` escape sequences in string and docstring
literals. In comments, replace with the plain ASCII equivalent. In every case
include a short inline comment naming the character, e.g.
`"""  # LEFT DOUBLE QUOTATION MARK`.

**Why.** Literal curly quotes and dashes are visually indistinguishable from
ASCII equivalents in most editors and diff views, making string comparisons and
grep silently fragile. Escape sequences make intent explicit and are safe across
all encodings. `# noqa: RUF00x` masks the problem instead of fixing it.

**Common high-confidence violations** (bot auto-fix candidates)

- A string literal containing `"hello – world"` written with the literal
  `–` character instead of the escape sequence.
- `# noqa: RUF001`, `# noqa: RUF002`, or `# noqa: RUF003` suppressions instead
  of escape sequences.
- `RUF002` or `RUF003` added to `[tool.ruff.lint] ignore` in `pyproject.toml`
  to paper over ambiguous characters.

**Common judgment-call violations** (bot flags, CT decides)

- Test strings that intentionally exercise curly-quote round-trip through the
  OCR pipeline and must contain the literal character — keep the literal with an
  explicit `# noqa: RUF001  # intentional: testing curly-quote round-trip`
  comment that names the character and states the reason.

## Rule: Use `uv run` for all Python and tool invocation

**The rule.** Invoke Python, pytest, ruff, mypy/pyright, and any project-local
CLI through `uv run`. Never call bare `python`, `python3`, `pytest`, or
`pre-commit` from a Makefile target, CI step, or hook.

**Why.** Direct invocation skips the project's `.venv` and the lockfile-pinned
toolchain; tests pass locally and fail in CI (or vice versa) because the bare
interpreter sees different installed package versions. `uv run` is uniformly
fast (<200 ms warm) and always selects the project venv.

**Common high-confidence violations** (bot auto-fix candidates)

- `python -m pytest` or `python3 script.py` in any `Makefile`, `*.sh`,
  `.github/workflows/*.yml`, or `.pre-commit-config.yaml` hook.
- `pre-commit run` (bare) instead of `uv run pre-commit run` in CI or scripts.
- `ruff check` or `pyright` (bare) in scripts that don't activate a venv first.

**Common judgment-call violations** (bot flags, CT decides)

- One-off REPL commands typed in CT's interactive shell — out of scope for this rule.

## Rule: Design spec files live in `docs/specs/` until the milestone ships

**The rule.** A design spec file produced by `/spec-from-issue` lives at
`docs/specs/<date>-<topic>-design.md` while the milestone's chore issues are open.
When the milestone's last chore closes and the implementation lands, move the file to
`docs/architecture/` in a housekeeping commit:

```bash
git mv docs/specs/<date>-<topic>-design.md docs/architecture/
git commit -m "docs: promote <topic> spec to architecture/ (milestone shipped)"
```

Update any `Spec: docs/specs/...` pointers in still-open issues after the move.

**Why.** `docs/specs/` is the active working area — implementing agents follow `Spec:`
pointers to find their instructions. `docs/architecture/` is the permanent design record
for shipped features. Mixing shipped and in-progress specs in one directory makes it
unclear which specs are still authoritative for ongoing work.

**Common high-confidence violations** (bot auto-fix candidates)

- A spec file remaining in `docs/specs/` after its milestone's last chore issue closes.

**Common judgment-call violations** (bot flags, CT decides)

- A milestone with one chore still open but all substantive work done — CT decides
  whether to move the spec early or wait for the final chore to close.

<!-- workspace-conventions:end -->

---

## Rule: OpenAPI types are generated, never hand-edited

**The rule.** `frontend/src/api/types.ts` is machine-generated from the
FastAPI OpenAPI schema. Run `make openapi-export` to regenerate it after
any change to a FastAPI request or response model. Never edit
`types.ts` by hand.

**Why.** Hand edits drift silently from the backend schema and produce
type errors that only surface at runtime. The generation step is the
contract; the file is its artifact.

**Common high-confidence violations** (bot auto-fix candidates)

- A commit that modifies a `src/pd_ocr_labeler_spa/api/` model but does not
  include a matching change to `frontend/src/api/types.ts`.
- A PR description that says "updated response model" without mentioning
  `make openapi-export`.

**Common judgment-call violations** (bot flags, CT decides)

- A temporary local edit to `types.ts` made while the backend shape was still
  in flux — flag if the PR reaches review without reverting to generated output.

---

## Rule: data-testid values must match specs/13-driver-contract.md exactly

**The rule.** Every interactive element visible to the Playwright driver
must carry the exact `data-testid` string listed in
`specs/13-driver-contract.md`. Do not invent new testids without first
adding them to that spec; do not rename or remove existing ones without
explicit approval (see spec §9 versioning).

**Why.** The `pd-ocr-labeler-driver` agent selects elements exclusively
by `data-testid`. Any mismatch silently breaks the driver pre-pass with
no compile-time signal.

**Common high-confidence violations** (bot auto-fix candidates)

- A `data-testid` string in a React component that differs from the
  catalogue by case, spelling, or trailing/leading characters.
- An interactive button or input rendered without any `data-testid` when
  the spec catalogue lists one for that element.

**Common judgment-call violations** (bot flags, CT decides)

- A new component that has no catalogue entry yet — flag for spec update
  before merge, don't auto-assign a testid.
- A per-index testid (e.g. `line-card-{n}`) that uses a different index
  variable than the spec specifies.

---

## Rule: FastAPI route handlers must declare an explicit response_model

**The rule.** Every `@router.get`, `@router.post`, etc. handler must
include a `response_model=` keyword argument pointing to a concrete
Pydantic model. Returning `dict`, `Any`, or `JSONResponse` without a
model is not permitted.

**Why.** Without a `response_model`, FastAPI cannot validate the outgoing
shape, `make openapi-export` generates an untyped schema, and the
generated `types.ts` degrades to `unknown`. The entire typed-REST surface
depends on this discipline.

**Common high-confidence violations** (bot auto-fix candidates)

- A route decorator with no `response_model=` argument.
- `response_model=dict` or `response_model=Any`.
- A return type annotation of `-> dict` or `-> Any` on a route handler
  (use this as a secondary signal; the decorator attribute is canonical).

**Common judgment-call violations** (bot flags, CT decides)

- A streaming endpoint (`StreamingResponse` for SSE) that intentionally
  cannot declare a Pydantic model — document with an inline comment
  explaining why and reference the spec section.
- A `204 No Content` route: use `@router.delete(..., status_code=204, response_model=None)`
  and return `None` (or a `Response` with no body) — `response_model=None` is the
  explicit FastAPI idiom for "no response body"; it is NOT the same as omitting
  `response_model=` entirely, and must be stated explicitly.

---

## Rule: New stateful React components require a Vitest test file

**The rule.** Any new React component that manages interactive state
(controlled inputs, local `useState`/`useReducer`, react-query mutations,
or Konva canvas interactions) must ship with a corresponding Vitest test
file under `frontend/src/` beside the component. The test file name is
`<ComponentName>.test.tsx`.

**Why.** Stateful components are where bugs live. A component delivered
without tests forces the next developer to reverse-engineer intent before
they can safely change it. The rule does not apply to pure presentational
components with no local state.

**Common high-confidence violations** (bot auto-fix candidates)

- A new `*.tsx` file containing `useState` or `useMutation` with no
  sibling `*.test.tsx` file in the same directory.

**Common judgment-call violations** (bot flags, CT decides)

- A component that is stateful but whose behaviour is already fully
  covered by an E2E test in `tests/e2e/` — flag; CT decides whether
  unit coverage is still needed.
- Wrapper components that delegate all state to a child already under
  test — flag; they may not need their own test file.
