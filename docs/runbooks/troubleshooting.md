# Troubleshooting

Common failure modes and fixes, sourced from real code paths.

For local setup see [`docs/runbooks/local-dev.md`](local-dev.md).
For the release build process see [`docs/runbooks/release.md`](release.md).

---

## Missing frontend build

**Symptom:** `make run` exits immediately with "SPA bundle missing".
Or: `GET /` returns `503 Service Unavailable` at runtime.

**Cause:** `src/pdomain_ocr_labeler_spa/static/index.html` is absent. The
FastAPI mount checks for this file at startup.

**Fix:**

```sh
make frontend-build
# then retry:
make run
```

The same symptom on `make build` is caught earlier, by
`build_hooks/spa_check.py`, which raises:

```
pdomain-ocr-labeler-spa: SPA bundle is missing — refusing to build a wheel
without src/pdomain_ocr_labeler_spa/static/index.html.
```

Fix is the same: `make frontend-build`.
(`build_hooks/spa_check.py:65-72`, source-checked 2026-06-01)

---

## OpenAPI types drift

**Symptom:** CI `openapi-drift` job fails with a diff in
`frontend/src/api/types.ts` or `frontend/openapi.json`.

**Cause:** A FastAPI request or response model changed and `make
openapi-export` was not re-run before commit. CI re-runs the export and
compares via `git diff --exit-code`.

**Fix:**

```sh
make openapi-export
git add frontend/src/api/types.ts frontend/openapi.json
git commit -m "chore: regenerate openapi types"
```

(`Makefile:280-289`, source-checked 2026-06-01)

---

## Port file (`.pdlabeler-port`) issues

**Symptom:** Vite dev server (`make frontend-dev`) proxies to the wrong port.
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

**Symptom:** `make test` or runtime imports resolve the wrong version of
`pdomain-book-tools` (registry instead of your local editable, or vice versa).

**Cause:** Local-dev mode is tracked by the marker file
`.venv/.pdomain-dev-local`. A plain `uv sync` after a worktree merge can
revert the editable install without removing the marker, leaving an
inconsistent state.

**Check current mode:**

```sh
make local-check
```

**Fix (restore editable mode after `uv sync`):**

```sh
make local-setup-py   # idempotent; re-applies editable Python siblings
```

**Fix (revert to registry):**

```sh
uv sync --group dev   # drops the editable install
rm -f .venv/.pdomain-dev-local
```

**Symptom:** `ModuleNotFoundError: No module named 'pdomain_ocr_labeler_spa'`
after merging a worktree branch.

**Cause:** Worktrees share the canonical `.venv`. When a worktree is removed,
the editable install path it was registered at no longer exists.

**Fix:**

```sh
uv sync && make local-setup-py
```

(`Makefile:118-119`, source-checked 2026-06-01)

---

## pnpm store / install issues

**Symptom:** `pnpm install` fails with permissions or `ENOTDIR` errors.
Or: `make frontend-install` resolves node_modules from an unexpected path.

**Cause:** pnpm 11 requires the store directory to be set explicitly when the
default parent-directory location is on a different filesystem or a
restricted path.

**Fix:** Ensure `.npmrc` in `frontend/` (or the repo root) sets:

```ini
store-dir=~/.local/share/pnpm/store
```

If a stale lockfile is preventing correct resolution:

```sh
cd frontend && rm -rf node_modules pnpm-lock.yaml && pnpm install
```

(`feedback_pnpm_store_location.md` in agent memory, source-pattern verified
against `frontend/.npmrc`)

---

## mise tool resolution failures

**Symptom:** `make frontend-build` or `make frontend-install` reports
`no pnpm available` even though pnpm is installed.

**Cause:** `make` targets dispatch through mise for tool version pinning
(`Makefile:218-232`, source-checked 2026-06-01). If `mise` is not installed
or its config is untrusted, the fallback is the `pnpm` on your `PATH`.

**Fix (install mise):**

```sh
make mise-download      # downloads mise binary to ~/.local/bin/mise
make mise-setup         # installs pinned Node 24 + pnpm 11 from mise.toml
```

**Fix (trust config for worktrees):**

```sh
make mise-trust-worktrees
```

(`Makefile:180-194`, source-checked 2026-06-01)

**Bypass:** If you manage Node yourself and mise is unnecessary:

```sh
make frontend-install   # falls back to PATH pnpm if mise not found
```

---

## basedpyright errors after `make openapi-export`

**Symptom:** `make lint` fails with basedpyright errors after regenerating TS
types.

**Cause:** The regenerated `frontend/src/api/types.ts` may expose new type
gaps in components that use the changed schemas.

**Fix:** Address the new type errors before committing. Do not suppress them
with `// @ts-ignore` unless they are pre-existing; check
`docs/process/lint-deviations.md` for the project's suppression policy.

---

## `make upgrade-deps` refused

**Symptom:** `make upgrade-deps` exits with
`upgrade-deps refused: editable pdomain-book-tools detected`.

**Cause:** Local-dev mode is active. `make upgrade-deps` refuses to run when
editable siblings are installed to prevent silently reverting them to registry
versions.
(`Makefile:70-88`, source-checked 2026-06-01)

**Fix:** Use the local-dev-aware upgrade target:

```sh
make local-upgrade-deps
```
