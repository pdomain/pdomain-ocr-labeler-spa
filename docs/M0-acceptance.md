# M0 Acceptance Gate

Authoritative milestone definition: [`../specs/16-milestones.md`](../specs/16-milestones.md) §M0.
Implementation tracker: [`ROADMAP.md`](ROADMAP.md).

This document is the single page that says "what does done mean for
M0, and what's still in the way?" Update it whenever an M0 criterion
flips state or a blocking question resolves. The shape-pin test in
`tests/unit/test_m0_acceptance.py` enforces that this doc keeps a
**Status** section and lists every criterion the spec/ROADMAP names.

## Criteria (verbatim from `specs/16-milestones.md` §M0)

The eight clauses below are taken directly from `specs/16-milestones.md`
§"Acceptance tests" plus `specs/16-milestones.md:86` ("Pre-commit
hooks installed and pass"). Each has a status flag.

| # | Criterion | Status |
|---|---|---|
| 1 | `make setup && make test` — green | green (130/130 pytest passing iter 28; backend `make setup` exercised iter 1+) |
| 2 | `make frontend-test` — green (one smoke test) | gated on Q-A8 — file in place since iter 2 (`frontend/src/App.test.tsx`), not runtime-verified |
| 3 | `make frontend-build` — produces `dist/` and copies to `static/` | gated on Q-A8 — Makefile target wired iter 3, never executed |
| 4 | `make build` — wheel contains `pd_ocr_labeler_spa/static/index.html` | gated on Q-A8 — `build_hooks/spa_check.py` correctly fails until SPA is built |
| 5 | `pd-ocr-labeler-ui --no-browser --port 8080 --host 127.0.0.1` answers `/healthz` and serves `index.html` at `/` | partial — `/healthz` green since iter 1; `/` 404s until SPA is built (Q-A8) |
| 6 | `make openapi-export` — produces `frontend/openapi.json` and `frontend/src/api/types.ts` | green for the Python half (export); `types.ts` regen requires `npx openapi-typescript` (Q-A8) |
| 7 | ESLint and ruff pass clean | ruff green (lint+format); ESLint gated on Q-A9 (config shape undecided; `lint` script dropped in iter 8) |
| 8 | Pre-commit hooks installed and pass | green — `.pre-commit-config.yaml` landed iter 4; iter 12/16 added auto-`refresh-version` post-commit/post-rewrite/post-checkout coverage |

## Status

**M0 is in progress.** Backend, repo scaffold, Dockerfile, installers,
and release workflow are complete; the frontend half is gated on
Q-A8 (no Node/npm in the devcontainer). 130/130 pytest are green and
ruff is clean as of iter 28. After iter 29:

- Open BUGS_FOUND items: **0**. (B-18 closed in iter 29.)
- Remaining open questions blocking M0: **Q-A8** (frontend toolchain),
  **Q-A9** (ESLint config + restored `lint` script).
- Remaining open questions NOT blocking M0: Q-A10 (PyPI publishing —
  out of M0 scope per `specs/16-milestones.md`).

## Remaining blockers

### Q-A8 — Frontend toolchain availability

See [`../OPEN_QUESTIONS.md` Q-A8](../OPEN_QUESTIONS.md). The
devcontainer ships without `node`/`npm`/`mise`, so criteria 2-6
above cannot be runtime-verified from inside the /loop. The agent's
edit boundary stops at this repo, so the resolution path is one of:

- **(preferred)** Workspace owner adds
  `ghcr.io/devcontainers/features/node:1` to
  `/workspaces/ocr-container/.devcontainer/devcontainer.json` and
  rebuilds the container. Then `make frontend-install` /
  `frontend-build` / `frontend-test` run end-to-end.
- **(fallback)** Run `make mise-setup && make frontend-install &&
  make frontend-build && make frontend-test` from an interactive shell
  with outbound network. The Makefile's `_npm` macro is already wired
  for the mise-exec path. This commits `frontend/package-lock.json`,
  which closes the bootstrap branch in `Dockerfile` and
  `release.yml` (see B-19/B-28 fixes).

### Q-A9 — ESLint config + restored `lint` script

See [`../OPEN_QUESTIONS.md` Q-A9](../OPEN_QUESTIONS.md). The
`lint` script in `frontend/package.json` was dropped in iter 8 (B-05)
because it referenced `eslint` without it being declared as a
dev-dep. Resolution path (recommended): an iteration that lands
`frontend/eslint.config.ts` (flat-config form, matching the M0 file
list at `specs/16-milestones.md:51`), adds
`@typescript-eslint/eslint-plugin` + `@vitejs/plugin-react` (or the
v9-compatible equivalents) to `devDependencies`, and restores the
`lint` script. The shape-pin test in `tests/unit/test_frontend_config.py`
flips its conditional invariant ("if lint exists then eslint must be
installed") to a hard "lint must exist" assertion. Q-A8 is a
prerequisite (no npm → can't add devDeps).

## Sign-off ritual

When both Q-A8 and Q-A9 are unblocked, follow this sequence to flip
M0 from "in progress" to "done":

1. Run the full M0 acceptance sequence end-to-end on the workstation
   that has Node/npm available:
   ```
   make setup
   make ci
   make frontend-build
   make build
   pd-ocr-labeler-ui --no-browser --port 8080 --host 127.0.0.1 &
   curl -fsS http://127.0.0.1:8080/healthz   # expect {"status":"ok"}
   curl -fsS http://127.0.0.1:8080/ | head -1 # expect <!doctype html>
   make openapi-export
   ```
   Each step must succeed. Capture the wheel filename and the
   `pd-ocr-labeler-ui --version` output for the sign-off note.
2. Verify `frontend/package-lock.json` is committed and
   `frontend/src/api/types.ts` was regenerated by step 1.
3. Update `ROADMAP.md`'s M0 row to `✅ done` with the iter and short
   sha that closed it. Flip every M0 sub-task checkbox.
4. Update the **Status** section of this doc to mirror — every row
   in the criteria table reads "green", and the "Remaining blockers"
   section contracts to a one-line "None — closed in iter N (sha)."
5. Tag `v0.0.1` (or the next available `v*` PEP-440-shaped tag — see
   B-29) on the closing commit so `release.yml` runs and the
   GitHub Release carries the M0-bake-off wheel + sdist.
6. Note in `LOOP_STATE.md` and the iter-N memory that M0 is closed
   and M1 is unblocked.

A reviewer (the next code-review checkpoint) confirms by re-running
the same six commands and inspecting the criteria table here. If any
clause has regressed, the review files a `B-NN` bug and M0 reverts
to "in progress" until it's resolved.
