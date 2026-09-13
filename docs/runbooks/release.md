---
kind: runbook
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-07-13
---

# Release Runbook

How to build and publish a new `pdomain-ocr-labeler-spa` wheel.

For local development setup see [`docs/runbooks/local-dev.md`](local-dev.md).
For the wheel's deployment contract see [`docs/architecture/15-deployment-dev.md`](../architecture/15-deployment-dev.md).

---

## Prerequisites

- Clean working tree on `master`, in sync with `origin/master`.
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
# From a clean master branch, in sync with origin/master:
make release-patch   # v0.4.2 -> v0.4.3
make release-minor   # v0.4.2 -> v0.5.0
make release-major   # v0.4.2 -> v1.0.0
```

Each target delegates to `scripts/do-release.sh` via `scripts/release-common.sh`.
The script (`scripts/release-common.sh`, verified 2026-06-01):

1. Fetches `origin/master` and checks that the working tree is clean and on `master`.
2. Computes the next three-component version tag from existing `vN.N.N` git tags.
3. Runs `make ci-slow` (the `RELEASE_PREFLIGHT`).
4. Creates an annotated tag `vN.N.N`.
5. Pushes `master` and the exact tag to `origin`.
6. Triggers `.github/workflows/release.yml` via `gh workflow run release.yml --ref master -f tag=vN.N.N`.

### Escape hatches

| Flag | Effect |
|------|--------|
| `FORCE=1` | Skip repo-state guards (dirty tree / wrong branch / origin sync) |
| `SKIP_PUSH=1` | Create tag locally; do not push |

---

## What the release script does after tagging

The GitHub workflows were removed on 2026-09-13. `scripts/release-common.sh`
now does the whole job locally, in this order:

1. Runs the preflight, which is `make ci-slow`, against the working tree.
2. Creates the annotated tag and pushes `master` and the tag.
3. Builds the artifacts with `make build`, overridable through `RELEASE_BUILD`.
4. Creates the GitHub Release with `gh release create --generate-notes
   --verify-tag` and attaches everything matching `dist/*.whl`, `dist/*.tar.gz`
   and `dist/*.tgz`.

If the build fails after the tag is pushed, the script stops and prints the
`gh release create` command to run by hand once the build is fixed. The tag is
already public at that point, so the release is the only missing piece.

**Publishing to the index is a separate, manual step.** Nothing dispatches it
and there is no scheduled fallback any more:

```bash
(cd ../pdomain-index-pip && ./scripts/publish-index.sh)
```

A release that is not followed by that command stays invisible to installers,
because the index is generated from release assets.

---

## Wheel contents check

There is no pre-merge CI gate any more. `make build` refuses to run without a
populated `static/`, and the wheel should contain
`pdomain_ocr_labeler_spa/static/index.html`. Check it before releasing:

```bash
make frontend-build && make build
unzip -l dist/*.whl | grep static/index.html
```

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

## Trigger

Use this runbook when preparing or validating a tagged wheel release.

## Preconditions

Start from a clean release commit with locked backend and frontend dependencies
installed. Confirm the intended version source before tagging.

## Steps

Run the build and release checks above in order. Publish only through the GitHub
Release workflow and the `pdomain-index-pip` target described above.

## Verification

Require the repository CI gate, inspect the wheel for `static/index.html`, and
confirm the release artifact is indexed by the intended package index.

## Rollback

Do not overwrite a bad published artifact. Stop publication, correct the source,
and issue a new version according to the repository release policy.
