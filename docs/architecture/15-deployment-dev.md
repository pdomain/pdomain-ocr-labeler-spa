---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# 15 — Deployment + Developer Workflow

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#34

How `pdomain-ocr-labeler-spa` is built, packaged, distributed, and developed.

> Cross-refs:
> Architecture template — `pdomain-prep-for-pgdp/` (justfile, install.sh, Dockerfile)
> CI gates — [`14-testing.md`](14-testing.md) §7
> Drift checks — [`01-data-models.md`](01-data-models.md) §6

---

## 1. End-user install

Single-line GitHub-Release wheel installer, mirroring pgdp-prep's flow.

### Linux / macOS

```sh
curl -fsSL https://raw.githubusercontent.com/pdomain/pdomain-ocr-labeler-spa/master/install.sh | bash
```

`install.sh` does:

1. Verify `uv` is installed; bail with installation hint otherwise.
2. Fetch the latest GitHub Release wheel via the GitHub API.
3. `uv tool install <wheel> --reinstall`.
4. Print "`pdomain-ocr-labeler-ui` is on your PATH; run with `pdomain-ocr-labeler-ui [project_dir]`."

### Windows

```pwsh
iwr -useb https://raw.githubusercontent.com/pdomain/pdomain-ocr-labeler-spa/master/install.ps1 | iex
```

Same flow, PowerShell-flavoured.

End users install **once**; future updates re-run the same script.

---

## 2. Console scripts

`pyproject.toml` installs `pdomain-ocr-labeler-ui`, `pdomain-ocr-labeler-control` and
`pdomain-ocr-labeler-spa-export`. The export entry point is `core.jobs.handlers.export_cli:main`.
There is no installed prefetch console script. Python support is `>=3.13,<3.14`. Current dependency
pins and explicit package-index sources live in the manifest/lock, not copied examples here.

## 3. Boot

`pdomain-ocr-labeler-ui` (no args) runs the server on `127.0.0.1:8080`,
auto-opens the user's browser to `http://localhost:8080`.

```
pdomain-ocr-labeler-ui [project_dir]
  --data-root PATH            Override Settings.data_root (env: PDLABELER_DATA_ROOT)
  --projects-root PATH        Override config.yaml source_projects_root
  --host TEXT                 Default 127.0.0.1
  --port INT                  Default 8080
  --reload                    Enable uvicorn --reload + skip browser
  --no-browser                Don't auto-open browser
  --frontend-dev URL          Vite dev URL (skip static SPA mount)
  --debugpy                   Parsed compatibility flag; listener wiring is absent
  --verbose / -v              Count, 0..3
  --page-timing               Parsed compatibility flag; logger consumer is absent
```

Same flag set as legacy + the `--frontend-dev` flag from pgdp-prep.

### 3.1 Auto-port selection

When no explicit port is provided (neither `--port` nor `PDLABELER_PORT`),
the server scans `8080–8099` and binds the first available port. If all
20 sequential ports are busy, the OS assigns an ephemeral port (bind to
port 0). A notice is printed to stderr whenever the actual port differs
from the default:

```
Port 8080 in use — starting on port 8081
```

When an explicit port is provided and it is already in use, the server
exits immediately with an error:

```
Error: Port 9999 is already in use
```

On every successful start, the actual bound port is written as a plain
integer string to `.pdlabeler-port` in the current working directory.
`vite.config.ts` reads this file at config evaluation time so that
`npm run dev` automatically proxies to the correct backend port, even
when the default shifted. The file falls back to `8080` if absent (e.g.
on a first `npm run dev` before the server has started).

---

## 4. Dev workflow

### 4.1 First-time setup

```sh
git clone <repo>
cd pdomain-ocr-labeler-spa
just setup            # locked Python install, hooks, version refresh
just frontend-install # frozen pnpm install via mise
just setup-e2e        # install Playwright Chromium when needed
```

`just setup` does:

- `uv sync --locked --group dev` — install locked Python dependencies.
- `install-hooks` — install pre-commit hooks for this checkout.
- `refresh-version` — refresh the editable package version.

### 4.2 Two-terminal dev loop

Terminal 1 (backend):
```sh
just dev    # uvicorn --reload --frontend-dev http://localhost:5173
```

Terminal 2 (frontend):
```sh
just frontend-dev   # vite dev server on :5173 with proxy to :8080
```

Browser to `http://localhost:5173`. HMR works for the frontend; uvicorn
reloads on Python changes.

### 4.3 One-terminal dev loop

```sh
just dev            # backend only; run just frontend-dev in a second terminal
```

The backend and frontend use separate terminals.

### 4.4 OpenAPI sync

After backend wire-shape edits, run `just openapi-export` and inspect the generated
`frontend/src/api/types.ts` diff. `frontend/openapi.json` is an ignored intermediate.
`just ci` regenerates types but does not contain a separate git-diff refusal step, and the hook config
does not install the old proposed pre-push openapi-drift hook.

### 4.5 Tests

```sh
just test                # excludes e2e/, slow, and integration markers
just frontend-test       # vitest
just e2e                 # build SPA, then Playwright
just ci e2e              # full CI, then Playwright
```

### 4.6 Lint + format

```sh
just lint                # Python lint fixes
just lint-check          # read-only Python format and lint checks
just format              # Python format only
just frontend-lint       # ESLint fixes
just frontend-format     # Prettier write
just frontend-typecheck  # application and test TypeScript checks
just pre-commit-check    # all configured pre-commit hooks
```

---

## 5. Build + package

### 5.1 Wheel

`just build` runs OpenAPI export/frontend build, then explicit `uv build --sdist` and `uv build --wheel`.
Global Hatch artifacts include `src/pdomain_ocr_labeler_spa/static/**/*` in both artifacts. The manifest
uses hatchling plus hatch-vcs and the configured Python range; there is no git-tag dependency source to
recreate from an old example. See `pyproject.toml` and [repository boundaries](30-repository-boundaries.md).

### 5.2 Build hook (SPA presence assertion)

`build_hooks/spa_check.py` (verbatim port from pgdp-prep
`build_hooks/spa_check.py:31-72`):

```python
class SpaCheckHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            return  # editable installs without static/ are fine
        if os.environ.get("PD_LABELER_SKIP_SPA_CHECK") == "1":
            return
        index = Path("src/pdomain_ocr_labeler_spa/static/index.html")
        if not index.exists():
            raise RuntimeError("SPA bundle not found. Run `just frontend-build` first.")
```

### 5.3 Sdist

The sdist includes the prepared SPA through global build artifacts. A subsequent wheel build from the
sdist therefore retains the bundle. Tests in `tests/test_packaging.py` cover wheel/sdist contents and
the explicit source sdist-then-wheel sequence.

## 6. Container

`Dockerfile` is the authoritative multi-stage build: pinned Node with frozen pnpm frontend installation,
Python 3.13, uv-exported hashed runtime requirements, and a nonroot runtime user. The runtime serves the
bundled SPA without a Node development server. `just docker-build` builds the dev image;
`just docker-run` publishes its port but does not add a data bind mount. Add an explicitly selected volume
when running it for persistent work; the recipe itself does not promise one.

`tests/integration/test_docker_build.py` covers image build, SPA serving, health and runtime contents.
The ordinary backend test selection currently includes those unmarked Docker tests.

## 7. CI

`just ci` is the local gate. It runs locked setup, a single frozen frontend install, pre-commit, Python and
frontend checks/tests, behavior coverage, OpenAPI/frontend build, explicit sdist then wheel, and strict docgraph.
It does not run the optional Playwright e2e suite. `ci-slow` currently delegates to that same gate.

Release recipes call `scripts/do-release.sh` and `release-common.sh`. The script checks clean branch/remote
state, computes the tag, runs `just ci-slow`, creates an annotated tag, pushes master and that exact tag,
then builds locally and creates the GitHub Release with wheel/sdist assets. It does not dispatch a workflow,
publish the package index or restart services. Index publication is a separate owning-repository operation.
See the [release runbook](../runbooks/release.md).

## 8. Pre-commit hooks

`.pre-commit-config.yaml` owns the hook list. External revisions are frozen 40-character commit SHAs,
not movable tag examples. Setup reinstalls hooks in the canonical checkout; worktrees leave canonical
hook ownership alone. The shared version-refresh script calls `just refresh-version` after relevant Git
operations, with nonfatal failure. There is no configured pre-push OpenAPI drift hook.
The external-hook appendix below preserves the freeze policy and dated verification evidence.

## 9. Versioning

`hatch-vcs` derives version from git tags:

- `v0.1.0` tag → version `0.1.0`.
- Any commit between tags → `0.1.0.dev<n>+<sha>`.

Schema versions (envelope, project) are independent — bumped
deliberately. See [`01-data-models.md`](01-data-models.md) §4 for
versioning policy.

---

## 10. Mise / pinned tools

`mise.toml`:

```toml
[tools]
node = "24"
python = "3.13"
```

Node is provided via mise per `mise.toml` (D-036; resolves Q-A8). The
canonical bootstrap is `mise install` then `just frontend-install`
for frozen pnpm dependencies. The `justfile`'s `_pnpm` helper dispatches through `mise exec` when available and falls
back to PATH otherwise, so a
developer with their own Node 24 on PATH also works — but the
workspace-pinned default is mise.

---

## 11. Devcontainer (optional, not required)

D-028: the canonical onboarding is **`just setup`**. The workspace
devcontainer at `/workspaces/ocr-container/` is supported but
**not required**. A developer with their own Python/Node environment
can `just setup` and be productive without ever opening the devcontainer.

`just setup` does:

- `uv sync --locked --group dev` (Python dependencies).
- Hook installation and editable-version refresh.

Run `just frontend-install` for frozen pnpm dependencies and `just setup-e2e`
when Playwright Chromium is needed.

If `mise` is installed, frontend recipes dispatch through `mise exec`
(pulling Node 24 / Python 3.13 from `mise.toml`); else they fall
through to the developer's PATH. Document required versions
prominently in `DEVELOPMENT.md` so PATH-only developers know what
they need.

When the devcontainer is in use, everything just works — `mise` and
all language tools are pre-installed.

---

## 12. Logs

By default: `<data_root>/logs/session_<YYYYMMDD_HHMMSS>.log` per server
boot. Plain text format with `[rid=...]` request-id tags.

`--verbose -vv` enables `pdomain_book_tools` DEBUG; `-vvv` enables
`urllib3`, `engineio`, `socketio` DEBUG.

Logging format comes from Settings.log_format (default plain). The CLI has no `--log-format` flag.
Configure the Settings field rather than invoking the removed example.

There is no log-cleanup recipe in the justfile.

---

## 13. Just recipe index

```sh
just --list          # current recipe index
just setup           # locked Python setup, hooks, version refresh
just frontend-install # frozen frontend dependencies
just test            # selected backend pytest suite
just frontend-test   # Vitest
just e2e             # Playwright
just lint            # Python lint fixes
just format          # Python format only
just frontend-lint   # ESLint fixes
just frontend-format # Prettier
just frontend-typecheck # application and test TypeScript projects
just dev             # backend with reload
just frontend-dev    # Vite
just frontend-build  # OpenAPI export, SPA build, copy to static/
just build           # SPA, sdist, then wheel
just openapi-export  # regenerate types.ts
just docker-build    # runtime container
just docker-run      # local container
just clean           # build artifacts
just release-patch   # manual release; also release-minor and release-major
```

---

## 14. Open issues

- **Mac arm64 / Apple Silicon.** DocTR may need MPS configuration. The
  `local_doctr` adapter should detect MPS and use it; document any
  additional steps in `DEVELOPMENT.md`.
- **GPU container.** A separate `Dockerfile.gpu` for users who want
  CUDA. Out of scope for v1; add in M9 if requested.
- **Auto-update.** No in-app update prompt. Users re-run `install.sh`.
  Acceptable.

---

## 15. Dev-local mode + safe `upgrade-deps` (deferred)

**Historical proposal (2026-05-07).** This section preserves the Make-era proposal. Its Make commands
and deferred milestone labels describe that proposal. Current operation uses the repository
[`justfile`](../../justfile) and [local-dev runbook](../runbooks/local-dev.md).

**Status.** Deferred until the `Makefile` lands
(see [`16-milestones.md`](../../specs/16-milestones.md) M0). Captured here so the
requirement is not lost when the Makefile is authored. Workspace-wide
standard agreed 2026-05-07; mirrored across all `pd-*` repos.

### 15.1 Problem

A workspace developer can opt into **dev-local mode** for the venv:
editable installs of sibling `pd-*` checkouts (notably
`pdomain-book-tools`), GPU/CUDA torch wheels, and
`doctr` from git. None of that state is captured in `uv.lock` — it's
applied imperatively after `uv sync`. So the obvious recipe

```make
upgrade-deps:
    uv lock --upgrade
    uv sync --group dev
```

silently reverts a dev-local venv back to canonical published / CPU
the moment it runs `uv sync`. The developer's editable
`pdomain-book-tools` checkout becomes a published wheel; the GPU torch
becomes CPU torch; and the next `make test` run is testing something
materially different from what the developer thinks they're testing.

The fix below is the workspace-standard pattern; once this repo grows
a Makefile (M0), it must implement this pattern rather than the naive
recipe above.

### 15.2 Required behavior

1. **Detect mode before any `uv sync`.** `make upgrade-deps` (and any
   other target that calls `uv sync`) must probe the current venv to
   determine whether it is in dev-local or canonical mode, before
   running the sync.
2. **Detection probes**, in order:
   1. Run `uv pip show pdomain-book-tools` and look for an
      `Editable project location:` line. `pdomain-book-tools` is the
      cross-repo anchor — every `pd-*` repo depends on it, so its
      editable-vs-wheel state is the load-bearing signal. If editable
      → dev-local.
   2. Fallback marker file inside the venv (e.g.
      `.venv/.pdomain-dev-local`). The companion `upgrade-deps-local`
      target (15.3) writes this after a successful dev-local restore;
      the marker is honored on subsequent runs in case the editable
      probe is unavailable.
   3. Last-resort env var: `PDOMAIN_DEV_LOCAL=1` forces dev-local.
3. **UX — refuse-with-message default.** When dev-local is detected,
   `make upgrade-deps` must **not** run `uv sync`. It must print a
   clear message naming the detected dev-local state, citing the
   probe that fired, and pointing at `make upgrade-deps-local`.
4. **Sibling target — `upgrade-deps-local`.** Performs:
   `uv lock --upgrade`, then `uv sync --group dev`, then re-applies
   the dev-local restore (editable sibling installs, GPU torch index,
   `doctr` from git, etc.), then writes/refreshes the
   `.venv/.pdomain-dev-local` marker.
5. **Canonical-mode behavior unchanged.** When no dev-local state is
   detected, `make upgrade-deps` behaves exactly as the naive recipe:
   `uv lock --upgrade && uv sync --group dev`. No new prompts.
6. **Cross-platform.** Detection and both targets must work on Linux
   (workspace devcontainer) and macOS. Avoid GNU-only `make`
   constructs and bash-only `[[ ]]` tests in shell snippets that run
   in either environment; stick to POSIX-compatible probes.

### 15.3 Spec for the implementation milestone

When this lands (planned M0; see [`16-milestones.md`](../../specs/16-milestones.md)),
the Makefile must include:

- `upgrade-deps` — canonical recipe, gated by the detection above.
- `upgrade-deps-local` — lock + sync + dev-local restore + marker write.
- A small shared shell function (or `mise task`/Make macro) that
  performs the three-probe detection and exports the result; reused
  by any other target that calls `uv sync`.

The dev-local restore step itself (which siblings to install editable,
which torch index to use, which `doctr` ref) is shared workspace
state and should be sourced from a single workspace location rather
than duplicated per-repo. That location is TBD at the workspace
level; this spec only requires that the repo's Makefile honor the
detect-and-refuse contract.

### 15.4 Acceptance criteria

- In a canonical venv: `make upgrade-deps` runs lock + sync to
  completion; `uv pip show pdomain-book-tools` continues to show a
  published wheel; nothing prompts.
- In a dev-local venv (editable `pdomain-book-tools` sibling installed):
  `make upgrade-deps` exits **without** mutating the venv, prints the
  refusal message, and names the probe that fired.
- `make upgrade-deps-local` in either mode produces a dev-local venv
  with editable siblings + GPU torch + `doctr`-from-git intact, and
  leaves `.venv/.pdomain-dev-local` present.
- `PDOMAIN_DEV_LOCAL=1 make upgrade-deps` refuses on a venv that probes as
  canonical.

## External pre-commit hook revisions

External hooks use full 40-character commit SHAs with a `# frozen: <tag>`
comment. The local `require-frozen-hook-revs` check rejects revisions that do
not match that form.

Run `just update-hooks` to update hooks to their latest releases. It runs
`uv run pre-commit autoupdate --freeze` and preserves failures instead of
ignoring them. Review the resulting configuration diff and upstream release
notes. The former pre-commit-update bumper was removed because it rewrote
frozen SHAs back to tags.

Node-based hooks use Node 26.13.0. This avoids nodeenv 1.10.0 choosing a prerelease such as v27.0.0-alpha,
whose version string it cannot parse. Bump that Node pin deliberately.

### Configuration and verification evidence

- Configuration: `.pre-commit-config.yaml`; update command: `justfile`'s
  `update-hooks` target.
- Verification on 2026-11-07: the frozen-revision hook passes on SHA pins.
  It fails when one revision is temporarily changed back to its tag. It passes
  again after restoration.
- Initial freeze preserves existing hook versions; it does not upgrade them.
