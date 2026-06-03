# Release Runbook

How to build and publish a new `pdomain-ocr-labeler-spa` wheel.

For local development setup see [`docs/runbooks/local-dev.md`](local-dev.md).
For the wheel's deployment contract see [`docs/architecture/15-deployment-dev.md`](../architecture/15-deployment-dev.md).

---

## Prerequisites

- Clean working tree on `main`, in sync with `origin/main`.
- `make ci AI=1` green (the release script runs this as a pre-flight).
- `gh` CLI authenticated with write access to the repository.

---

## How the wheel works

The wheel ships the pre-built React SPA inside the Python package. Three
pieces enforce this:

**`frontend/dist/` to `static/` copy**
`make frontend-build` runs `pnpm run build` inside `frontend/`, then copies
`frontend/dist/` to `src/pdomain_ocr_labeler_spa/static/`.
(`Makefile:238-245`, verified 2026-06-01)

**`force-include` in `pyproject.toml`**

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/pdomain_ocr_labeler_spa/static" = "pdomain_ocr_labeler_spa/static"
```

(`pyproject.toml:89-90`, verified 2026-06-01)
This ensures the `static/` directory is bundled even though it is `.gitignore`d.

**`build_hooks/spa_check.py` guard**
A Hatchling custom hook runs before wheel assembly and raises `RuntimeError`
if `src/pdomain_ocr_labeler_spa/static/index.html` is absent or empty.
(`build_hooks/spa_check.py:43-72`, verified 2026-06-01)
The hook is skipped for editable installs (`version == "editable"`) and can be
bypassed with `PD_LABELER_SKIP_SPA_CHECK=1` (undocumented escape hatch).

---

## Version source

Version is derived from the most recent `vN.N.N` git tag via `hatch-vcs`.
(`pyproject.toml:83-85`, verified 2026-06-01)
There is no version field in `pyproject.toml`; the tag is authoritative.

```toml
[tool.hatch.version]
source = "vcs"
```

`make refresh-version` forces `hatch-vcs` to re-derive the version from the
current git state after a checkout or cherry-pick.
(`Makefile:46-55`, verified 2026-06-01)

---

## Build commands

| Command | Does |
|---------|------|
| `make frontend-build` | Runs `pnpm run build`; copies `frontend/dist/` to `src/.../static/` |
| `make build` | Chains `frontend-build` then `uv build --wheel`; output under `dist/` |
| `make ci-slow AI=1` | Full CI (`make ci`) plus `make build`; the release pre-flight |

`make build` calls `uv build --wheel` (not the default `uv build` which also
produces an sdist). The sdist path fails because the unpacked sdist has no
`static/`; wheel-only is the supported release path.
(`Makefile:386-393`, verified 2026-06-01)

---

## Release workflow

### Standard release (patch / minor / major)

```sh
# From a clean main branch, in sync with origin/main:
make release-patch   # v0.4.2 -> v0.4.3
make release-minor   # v0.4.2 -> v0.5.0
make release-major   # v0.4.2 -> v1.0.0
```

Each target delegates to `scripts/do-release.sh` via `scripts/release-common.sh`.
The script (`scripts/release-common.sh`, verified 2026-06-01):

1. Fetches `origin/main` and checks that the working tree is clean and on `main`.
2. Computes the next three-component version tag from existing `vN.N.N` git tags.
3. Runs `make ci-slow` (the `RELEASE_PREFLIGHT`).
4. Creates an annotated tag `vN.N.N`.
5. Pushes `main` and the exact tag to `origin`.
6. Triggers `.github/workflows/release.yml` via `gh workflow run release.yml --ref main -f tag=vN.N.N`.

### Escape hatches

| Flag | Effect |
|------|--------|
| `FORCE=1` | Skip repo-state guards (dirty tree / wrong branch / origin sync) |
| `SKIP_PUSH=1` | Create tag locally; do not push or trigger CI |

---

## CI release workflow (`.github/workflows/release.yml`)

Triggered by `gh workflow run` with `inputs.tag`.
Runs two jobs:

1. **`release-ci`** - checks out the exact tag, runs `make ci-slow` on
   `ubuntu-latest`. This re-verifies the build including wheel assembly.
   (`.github/workflows/release.yml`, verified 2026-06-01)

2. **`publish`** - builds release artifacts via `make build` and creates a
   GitHub Release with auto-generated notes.

The release workflow builds a wheel with `make build` and attaches `dist/*.whl` to the
GitHub Release. It does not attach an sdist unless `make build` is changed to produce one.
After release creation, the workflow dispatches `pdomain-index-pip`; if dispatch fails,
the index scheduled regen is the fallback.

---

## CI pre-merge wheel check (`.github/workflows/ci.yml`)

The `build-wheel` job in the PR CI gate also builds a wheel and asserts that
`pdomain_ocr_labeler_spa/static/index.html` is present inside the zip.
(`ci.yml: build-wheel job`, verified 2026-06-01)
This catches a missing `static/` on every PR, not just at release time.

---

## Verifying a built wheel

```sh
uv run python -m zipfile -l dist/pdomain_ocr_labeler_spa-*.whl | grep static/index.html
```

Expected output: one line containing `pdomain_ocr_labeler_spa/static/index.html`.

---

## Publication target

Wheels are published to GitHub Releases and indexed by
`pdomain/pdomain-index-pip` (self-hosted PEP 503 index on GitHub
Pages). Do not use `pip`/`twine` to push to PyPI - the release pipeline does
not target PyPI.
