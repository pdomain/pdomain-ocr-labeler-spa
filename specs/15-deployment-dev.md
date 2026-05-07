# 15 — Deployment + Developer Workflow

How `pd-ocr-labeler-spa` is built, packaged, distributed, and developed.

> Cross-refs:
> Architecture template — `pd-prep-for-pgdp/` (Makefile, install.sh, Dockerfile)
> CI gates — [`14-testing.md`](14-testing.md) §7
> Drift checks — [`01-data-models.md`](01-data-models.md) §6

---

## 1. End-user install

Single-line GitHub-Release wheel installer, mirroring pgdp-prep's flow.

### Linux / macOS

```sh
curl -fsSL https://raw.githubusercontent.com/<org>/pd-ocr-labeler-spa/main/install.sh | bash
```

`install.sh` does:
1. Verify `uv` is installed; bail with installation hint otherwise.
2. Fetch the latest GitHub Release wheel via the GitHub API.
3. `uv tool install <wheel> --reinstall`.
4. Print "`pd-ocr-labeler-ui` is on your PATH; run with `pd-ocr-labeler-ui [project_dir]`."

### Windows

```pwsh
iwr -useb https://raw.githubusercontent.com/<org>/pd-ocr-labeler-spa/main/install.ps1 | iex
```

Same flow, PowerShell-flavoured.

End users install **once**; future updates re-run the same script.

---

## 2. Console scripts

Declared in `pyproject.toml`:

```toml
[project.scripts]
pd-ocr-labeler-ui = "pd_ocr_labeler_spa.__main__:main"
pd-ocr-labeler-spa-export = "pd_ocr_labeler_spa.operations.export.cli:main"
pd-ocr-labeler-spa-prefetch = "pd_ocr_labeler_spa.prefetch:main"
```

The legacy `pd-ocr-labeler-ui` console script name is preserved so
end users can swap binaries without re-learning the command. The
other two scripts get the `-spa-` suffix to avoid collision with
legacy when both are installed.

(Decision flag: if [Q1](../OPEN_QUESTIONS.md) resolves "no transition
period — hard cut", we drop the suffix and shadow the legacy.)

---

## 3. Boot

`pd-ocr-labeler-ui` (no args) runs the server on `127.0.0.1:8080`,
auto-opens the user's browser to `http://localhost:8080`.

```
pd-ocr-labeler-ui [project_dir]
  --data-root PATH            Override Settings.data_root (env: PDLABELER_DATA_ROOT)
  --projects-root PATH        Override config.yaml source_projects_root
  --host TEXT                 Default 127.0.0.1
  --port INT                  Default 8080
  --reload                    Enable uvicorn --reload + skip browser
  --no-browser                Don't auto-open browser
  --frontend-dev URL          Vite dev URL (skip static SPA mount)
  --debugpy                   Listen on 0.0.0.0:5678
  --verbose / -v              Count, 0..3
  --page-timing               Enable page-timing logger
```

Same flag set as legacy + the `--frontend-dev` flag from pgdp-prep.

---

## 4. Dev workflow

### 4.1 First-time setup

```sh
git clone <repo>
cd pd-ocr-labeler-spa
make setup            # uv sync + npm install + pre-commit + playwright install
```

`make setup` does:
- `uv sync` — Python deps + dev group.
- `cd frontend && npm install`.
- `pre-commit install`.
- `playwright install chromium`.

### 4.2 Two-terminal dev loop

Terminal 1 (backend):
```sh
make dev-backend    # uvicorn --reload --frontend-dev http://localhost:5173
```

Terminal 2 (frontend):
```sh
make dev-frontend   # vite dev server on :5173 with proxy to :8080
```

Browser to `http://localhost:5173`. HMR works for the frontend; uvicorn
reloads on Python changes.

### 4.3 One-terminal dev loop

```sh
make dev            # Tmux split: backend left, frontend right
```

Optional convenience target.

### 4.4 OpenAPI sync

After any backend wire-shape change:

```sh
make openapi-export   # writes frontend/openapi.json + frontend/src/api/types.ts
```

CI gate (closes pgdp-prep drift gap):

```yaml
- run: make openapi-export
- run: git diff --exit-code frontend/src/api/types.ts frontend/openapi.json
```

If the diff is non-empty, CI fails with "regenerate openapi types
before merging".

### 4.5 Tests

```sh
make test                # backend unit + integration + conformance
make frontend-test       # vitest
make e2e                 # build SPA, then Playwright
make test-all            # all of the above
```

### 4.6 Lint + format

```sh
make lint                # ruff check + ruff format --check + eslint + tsc --noEmit
make format              # ruff format + prettier write
pre-commit run --all     # everything
```

---

## 5. Build + package

### 5.1 Wheel

```sh
make build               # frontend-build + uv build --wheel
```

Produces `dist/pd_ocr_labeler_spa-<version>-py3-none-any.whl` containing
the built SPA under `pd_ocr_labeler_spa/static/`.

`pyproject.toml` highlights:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "pd-ocr-labeler-spa"
dynamic = ["version"]
requires-python = ">=3.13,<4.0"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "pydantic>=2.7",
    "pydantic-settings",
    "python-multipart",
    "anyio",
    "sse-starlette",
    "huggingface_hub>=0.24",
    "pd-book-tools>=0.1.0",
    "PyYAML",
    "numpy",
    "opencv-python",
    "torch",
    "torchvision",
]

[project.optional-dependencies]
cuda = []                # placeholder

[tool.uv.sources]
pd-book-tools = { git = "https://github.com/<org>/pd-book-tools.git", tag = "v0.10.0" }

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.targets.wheel.force-include]
"src/pd_ocr_labeler_spa/static" = "pd_ocr_labeler_spa/static"

[tool.hatch.build.hooks.custom]
path = "build_hooks/spa_check.py"
```

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
        index = Path("src/pd_ocr_labeler_spa/static/index.html")
        if not index.exists():
            raise RuntimeError(
                "SPA bundle not found. Run `make frontend-build` first."
            )
```

### 5.3 Sdist

Wheel-only is the supported install path. `pyproject.toml` declares
sdist-omits via `.gitignore` (`static/` is gitignored). Building an
sdist drops the SPA; building a wheel from the sdist trips the hook.
This is intentional — same as pgdp-prep.

---

## 6. Container

`Dockerfile` (multi-stage):

```dockerfile
# 1) Build SPA
FROM node:24 AS spa
WORKDIR /work
COPY frontend/package.json frontend/package-lock.json /work/
RUN npm ci
COPY frontend/ /work/
RUN npm run build

# 2) Build wheel
FROM python:3.13-slim AS wheel
WORKDIR /work
COPY pyproject.toml uv.lock README.md /work/
COPY src/ /work/src/
COPY --from=spa /work/dist/ /work/src/pd_ocr_labeler_spa/static/
RUN pip install uv && uv build --wheel -o /dist/

# 3) Runtime
FROM python:3.13-slim
COPY --from=wheel /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl
EXPOSE 8080
ENTRYPOINT ["pd-ocr-labeler-ui", "--host", "0.0.0.0", "--no-browser"]
```

For local Docker dev:
```sh
make docker-build        # docker build -t pd-ocr-labeler-spa .
make docker-run          # docker run -p 8080:8080 -v ~/data:/data pd-ocr-labeler-spa
```

---

## 7. CI

`.github/workflows/release.yml` mirrors pgdp-prep (`release.yml:24-145`):

| Job | Trigger | Required for green PR? |
|---|---|---|
| `lint` | every push + PR | Yes |
| `test-backend` | every push + PR | Yes |
| `test-frontend` | every push + PR | Yes |
| `test-e2e` | every push + PR | Yes |
| `openapi-drift` | every push + PR | Yes |
| `build-wheel` | every push + PR | Yes (asserts static/index.html in wheel) |
| `build-container` | tag push only | No |
| `release` | tag push only | No (uploads wheel + container to GitHub Release) |

`UV_PYTHON: "3.13"` is pinned because uv-discovered 3.14 has a known
anyio/SQLite teardown segfault (same fix as pgdp-prep `release.yml:33`).

---

## 8. Pre-commit hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: meta
    hooks:
      - id: check-hooks-apply
      - id: check-useless-excludes
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.13.0
    hooks:
      - id: ruff-check
        args: ["--select", "I", "--fix"]
      - id: ruff-check
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v9.x
    hooks:
      - id: eslint
        files: ^frontend/src/.*\.(ts|tsx)$
        args: ["--fix"]
  - repo: local
    hooks:
      - id: openapi-drift
        name: OpenAPI types in sync
        language: system
        entry: bash -c 'make openapi-export && git diff --exit-code frontend/src/api/types.ts frontend/openapi.json'
        pass_filenames: false
        stages: [pre-push]
```

`openapi-drift` runs only on `pre-push` so the inner-loop dev cycle
isn't slowed by openapi regen.

---

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

`mise install` is optional. `Makefile` dispatches through
`mise exec` when available, else falls back to PATH (matches pgdp-prep
`Makefile:104-135`).

---

## 11. Devcontainer (optional, not required)

D-028: the canonical onboarding is **`make setup`**. The workspace
devcontainer at `/workspaces/ocr-container/` is supported but
**not required**. A developer with their own Python/Node environment
can `make setup` and be productive without ever opening the devcontainer.

`make setup` does:
- `uv sync` (Python deps + dev group).
- `cd frontend && npm install`.
- `pre-commit install`.
- `playwright install chromium`.

If `mise` is installed, Make targets dispatch through `mise exec`
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

`--verbose -vv` enables `pd_book_tools` DEBUG; `-vvv` enables
`urllib3`, `engineio`, `socketio` DEBUG.

`--log-format json` switches to NDJSON for log aggregators.

`make clean-logs` purges old logs (offset by 7 days).

---

## 13. Make targets index

```
make setup           First-time dev setup
make test            Backend pytest
make frontend-test   Vitest
make e2e             Playwright e2e (requires built SPA)
make test-all        All of the above
make lint            ruff + eslint + tsc
make format          ruff format + prettier
make dev-backend     uvicorn --reload --frontend-dev …
make dev-frontend    vite dev
make frontend-build  npm run build + cp to static/
make build           Wheel build (with SPA)
make openapi-export  Regenerate types.ts
make docker-build    Build the runtime container
make docker-run      Run the container locally
make clean           Remove build artefacts
make clean-logs      Remove old session logs
make clean-cache     Remove image cache
make release         Tag + push (manual; CI handles wheel/container)
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
