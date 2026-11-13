---
kind: runbook
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-11-13
---

# Troubleshooting

Common failure modes and fixes, sourced from real code paths.

For local setup see [`docs/runbooks/local-dev.md`](local-dev.md).
For the release build process see [`docs/runbooks/release.md`](release.md).

---

## Missing frontend build

**Symptom:** `just run` exits immediately with "SPA bundle missing".
Or: `GET /` returns `503 Service Unavailable` at runtime.

**Cause:** `src/pdomain_ocr_labeler_spa/static/index.html` is absent. The
FastAPI mount checks for this file at startup.

**Fix:**

```sh
just frontend-build
# then retry:
just run
```

The same symptom on `just build` is caught earlier, by
`build_hooks/spa_check.py`, which raises:

```
pdomain-ocr-labeler-spa: SPA bundle is missing — refusing to build a wheel
without src/pdomain_ocr_labeler_spa/static/index.html.
```

Fix is the same: `just frontend-build`.
(`build_hooks/spa_check.py:65-72`, source-checked 2026-06-01)

---

## OpenAPI types drift

**Symptom:** Generated frontend types differ after an API model change, or frontend typechecks expose a mismatch.

**Cause:** A FastAPI request or response model changed and `just
openapi-export` was not re-run before commit. Local CI regenerates and typechecks; it does not contain
the former workflow/pre-push git-diff gate. Inspect the tracked types diff explicitly.

**Fix:**

```sh
just openapi-export
git add frontend/src/api/types.ts frontend/openapi.json
git commit -m "chore: regenerate openapi types"
```

(`Makefile:280-289`, source-checked 2026-06-01)

---

## Port file (`.pdlabeler-port`) issues

**Symptom:** Vite dev server (`just frontend-dev`) proxies to the wrong port.
API calls in the browser go to `:8080` even though the backend is on a
different port.

**Cause:** `__main__.py` writes the resolved port to `.pdlabeler-port` in the
current working directory every time it starts.
(`src/pdomain_ocr_labeler_spa/__main__.py:346`, source-checked 2026-06-01)
`vite.config.ts` reads this file; if the file is absent it falls back to
`8080`.
(`frontend/vite.config.ts`, source-checked 2026-06-01)

**Fix:** Start the backend before the Vite dev server. If the file is stale
(e.g. a prior run bound to a different port), restart the backend - it
overwrites `.pdlabeler-port` on every startup.

**Port in use:** If `PDLABELER_PORT` or `--port` is set and that port is
already bound, the server prints `Error: Port NNNN is already in use` and
exits. Without an explicit port, the backend auto-selects the next free port
starting from `8080` using `pdomain_ops.suite.bootstrap_spa`.

---

## Sibling-dep resolution / local-dev mode marker

**Symptom:** `just test` or runtime imports resolve the wrong version of
`pdomain-book-tools` (registry instead of your local editable, or vice versa).

**Cause:** Local-dev mode is tracked by the marker file
`${UV_PROJECT_ENVIRONMENT:-.venv}/.pdomain-local-mode`. A plain `uv sync` after a worktree merge can
revert the editable install without removing the marker, leaving an
inconsistent state.

**Check current mode:**

```sh
just local-check
```

**Fix (restore editable mode after `uv sync`):**

```sh
just local-setup-py   # idempotent; re-applies editable Python siblings
```

**Fix (revert to registry):**

```sh
uv sync --locked --group dev && just frontend-install && \
  rm -f "${UV_PROJECT_ENVIRONMENT:-.venv}/.pdomain-local-mode" \
        "${UV_PROJECT_ENVIRONMENT:-.venv}/.pdomain-dev-local"
```

**Symptom:** `ModuleNotFoundError: No module named 'pdomain_ocr_labeler_spa'`
after merging a worktree branch.

**Cause:** An explicitly shared project environment can retain an editable path to a removed worktree.
Ordinary worktrees can have independent environments; local-dev scripts resolve their mode marker against
the canonical checkout. Inspect UV_PROJECT_ENVIRONMENT and `just local-check` before changing resolution.

**Fix:**

```sh
uv sync --locked --group dev && just local-setup-py
```

(`Makefile:118-119`, source-checked 2026-06-01)

---

## pnpm store / install issues

**Symptom:** `pnpm install` fails with permissions or `ENOTDIR` errors.
Or: `just frontend-install` resolves node_modules from an unexpected path.

**Cause:** pnpm 11 requires the store directory to be set explicitly when the
default parent-directory location is on a different filesystem or a
restricted path.

**Fix:** Ensure `.npmrc` in `frontend/` (or the repo root) sets:

```ini
store-dir=~/.local/share/pnpm/store
```

Preserve the lockfile while diagnosing resolution. Run `just frontend-install` for registry mode or
`just local-frontend-install` for the local-link overlay. Dependency upgrades are a separate deliberate action.

(`feedback_pnpm_store_location.md` in agent memory, source-pattern verified
against `frontend/.npmrc`)

---

## mise tool resolution failures

**Symptom:** `just frontend-build` or `just frontend-install` reports
`no pnpm available` even though pnpm is installed.

**Cause:** `just` recipes dispatch through mise for tool version pinning
(`Makefile:218-232`, source-checked 2026-06-01). If `mise` is not installed
or its config is untrusted, the fallback is the `pnpm` on your `PATH`.

**Fix (install mise):**

```sh
just mise-download      # downloads mise binary to ~/.local/bin/mise
just mise-setup         # installs pinned Node 24 + pnpm 11 from mise.toml
```

**Fix (trust config for worktrees):**

```sh
just mise-trust-worktrees
```

(`Makefile:180-194`, source-checked 2026-06-01)

**Bypass:** If you manage Node yourself and mise is unnecessary:

```sh
just frontend-install   # falls back to PATH pnpm if mise not found
```

---

## TypeScript errors after `just openapi-export`

**Symptom:** `just frontend-typecheck` fails with TypeScript errors after
regenerating API types.

**Cause:** The regenerated `frontend/src/api/types.ts` may expose new type
gaps in components that use the changed schemas.

**Fix:** Address the new type errors before committing. Do not suppress them
with a new `// @ts-ignore`. Existing exceptions need their recorded narrow rationale; check
`docs/process/lint-deviations.md` for the project's suppression policy.

---

## `just upgrade-deps` refused

**Symptom:** `just upgrade-deps` exits with
`upgrade-deps refused: editable pdomain-book-tools detected`.

**Cause:** Local-dev mode is active. `just upgrade-deps` refuses to run when
editable siblings are installed to prevent silently reverting them to registry
versions.
(`Makefile:70-88`, source-checked 2026-06-01)

**Fix:** Use the local-dev-aware upgrade target:

```sh
just local-upgrade-deps
```

## Trigger

Use this runbook after a documented development, startup, build, dependency, or
local-mode symptom occurs.

## Preconditions

Capture the failing command and exact message first. Check local-dev resolution
before changing dependencies, and preserve project data and user edits.

## Steps

Match the symptom to the relevant section above, confirm its stated cause, then
apply only that section's fix.

## Verification

Rerun the original failing command. If the fix changes tracked files, also run
the repository-required focused and full gates.

## Rollback

Reverse only the attempted environment or dependency change. Restore locked
resolution with `just setup` and `just frontend-install`; preserve intentional
local-dev overlays and never discard unrelated work or data.
