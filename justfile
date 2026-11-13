set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set positional-arguments

# Copy this wrapper and install-hooks with the shell setting to sibling justfiles.
[private]
_ai +args:
    #!/usr/bin/env bash
    set -euo pipefail
    if env AI= just --quiet "$@" > .ci-ai.log 2>&1; then
        printf 'PASS: %s\n' "$*"
    else
        result=$?
        printf 'FAIL: %s (exit %s)\n' "$*" "$result"
        if [[ -f scripts/ai_filter_log.py ]]; then
            uv run python scripts/ai_filter_log.py .ci-ai.log
        else
            tail -50 .ci-ai.log
        fi
        exit "$result"
    fi

install-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai install-hooks; fi
    if [[ -f .git ]]; then
        echo "hooks: worktree checkout - the canonical repo owns them, skipping"
    elif [[ -n "$(git config --get core.hooksPath || true)" ]]; then
        echo "hooks: core.hooksPath is set - leaving it alone, skipping"
    else
        uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
    fi

[private]
_pnpm +args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd frontend
    if command -v mise >/dev/null 2>&1; then
        exec mise exec -- pnpm "$@"
    fi
    exec pnpm "$@"

[private]
_docker +args:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v docker >/dev/null 2>&1; then
        echo "docker not on PATH. Install Docker Desktop, Colima, or the devcontainer docker-in-docker feature." >&2
        exit 1
    fi
    exec docker "$@"

help:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai help; fi
    just --list

setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai setup; fi
    uv sync --locked --group dev
    just --quiet install-hooks refresh-version

refresh-version:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai refresh-version; fi
    mkdir -p src/pdomain_ocr_labeler_spa/static
    uv sync --locked --reinstall-package pdomain-ocr-labeler-spa
    uv run pdomain-ocr-labeler-ui --version 2>/dev/null || true

install:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai install; fi
    uv tool install --reinstall .
    echo "pdomain-ocr-labeler-ui installed. Run: pdomain-ocr-labeler-ui --version"

uninstall:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai uninstall; fi
    uv tool uninstall pdomain-ocr-labeler-spa || true

remove-venv:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai remove-venv; fi
    rm -rf "${UV_PROJECT_ENVIRONMENT:-.venv}"

reset:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai reset; fi
    just --quiet clean remove-venv setup
    echo "Environment Reset!"

upgrade-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai upgrade-deps; fi
    if uv pip show pdomain-book-tools 2>/dev/null | grep -q "Editable project location"; then \
        echo "upgrade-deps refused: editable pdomain-book-tools detected (probe 1)."; \
        echo "  'just upgrade-deps' would silently revert it to the pinned release."; \
        echo "  Use 'just upgrade-deps-local' to upgrade and re-install editable."; \
        exit 1; \
    fi
    if [ -f "${UV_PROJECT_ENVIRONMENT:-.venv}"/.pdomain-dev-local ] || [ -f "${UV_PROJECT_ENVIRONMENT:-.venv}"/.pdomain-local-mode ]; then \
        echo "upgrade-deps refused: "${UV_PROJECT_ENVIRONMENT:-.venv}"/.pdomain-dev-local marker present (probe 2)."; \
        echo "  Use 'just upgrade-deps-local' to upgrade and preserve dev-local state."; \
        exit 1; \
    fi
    if [ "${PDOMAIN_DEV_LOCAL:-0}" = "1" ]; then \
        echo "upgrade-deps refused: PDOMAIN_DEV_LOCAL=1 in environment (probe 3)."; \
        echo "  Use 'just upgrade-deps-local' to upgrade and preserve dev-local state."; \
        exit 1; \
    fi
    echo "Upgrading dependency lockfile..."
    uv lock --upgrade
    echo "Syncing upgraded dependencies..."
    uv sync --group dev
    just --quiet update-hooks
    echo "Dependencies upgraded and environment synced."

upgrade-deps-local:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai upgrade-deps-local; fi
    echo "DEPRECATED: use 'just local-upgrade-deps' (canonical local-dev target)." >&2
    just --quiet local-upgrade-deps

local-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-setup; fi
    ./scripts/local-setup.sh

local-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-dev; fi
    ./scripts/local-dev.sh

local-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-check; fi
    ./scripts/local-check.sh

local-upgrade-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-upgrade-deps; fi
    ./scripts/local-upgrade-deps.sh

local-run:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-run; fi
    ./scripts/local-run.sh

local-setup-py:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-setup-py; fi
    ./scripts/local-setup-py.sh

local-frontend-install:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-frontend-install; fi
    ./scripts/local-frontend-install.sh

local-frontend-build:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-frontend-build; fi
    just --quiet local-frontend-install
    PDOMAIN_FRONTEND_INSTALLED=1 just --quiet openapi-export
    just --quiet _pnpm run build
    mkdir -p src/pdomain_ocr_labeler_spa/static
    rm -rf src/pdomain_ocr_labeler_spa/static/*
    cp -r frontend/dist/. src/pdomain_ocr_labeler_spa/static/
    echo "Frontend bundled into src/pdomain_ocr_labeler_spa/static/"

local-frontend-test:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai local-frontend-test; fi
    ./scripts/local-frontend-test.sh

update-pdomain-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai update-pdomain-deps; fi
    ./scripts/update-pdomain-deps.sh

upgrade-pdomain-book-tools:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai upgrade-pdomain-book-tools; fi
    echo "warning: 'upgrade-pdomain-book-tools' is deprecated; use 'just update-pdomain-deps'"
    just --quiet update-pdomain-deps

mise-download:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai mise-download; fi
    if command -v mise >/dev/null 2>&1; then \
        echo "mise already installed at "${MISE:-$(command -v mise || echo "$HOME/.local/bin/mise")}""; \
    else \
        echo "Downloading mise v2026.5.15 to $HOME/.local/bin/mise..."; \
        MISE_TMP=$(mktemp) && \
        curl -fsSL -o "$MISE_TMP" "https://github.com/jdx/mise/releases/download/v2026.5.15/install.sh" && \
        sh "$MISE_TMP" && \
        rm -f "$MISE_TMP"; \
        echo "mise downloaded. Run 'just mise-setup' next to install pinned tools."; \
    fi

mise-trust-worktrees:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai mise-trust-worktrees; fi
    just --quiet mise-download
    echo "Trusting mise config roots for this repo and generated worktrees..."
    mkdir -p "$HOME/.config/mise/conf.d"
    printf '%s\n' \
        '[settings]' \
        'trusted_config_paths = [' \
        "    \"$(realpath ..)\"," \
        '    "/srv/bot-workspaces",' \
        ']' \
        > "$HOME/.config/mise/conf.d/ocr-container-worktrees.toml"
    echo "mise trust roots configured."

mise-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai mise-setup; fi
    just --quiet mise-download mise-trust-worktrees
    echo "Installing tools from mise.toml..."
    "${MISE:-$(command -v mise || echo "$HOME/.local/bin/mise")}" install
    echo "mise tools installed."
    echo "Make targets dispatch through mise automatically — no shell hook needed."

mise-doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai mise-doctor; fi
    echo "-- mise binary --"
    if command -v mise >/dev/null 2>&1; then \
        echo "  found: "${MISE:-$(command -v mise || echo "$HOME/.local/bin/mise")}""; \
        "${MISE:-$(command -v mise || echo "$HOME/.local/bin/mise")}" current 2>/dev/null | sed 's/^/  /' || echo "  (no mise.toml resolved)"; \
    else \
        echo "  not installed (run 'just mise-setup')"; \
    fi
    echo "-- PATH (your interactive shell) --"
    command -v node   >/dev/null 2>&1 && echo "  node:   $(node --version)"   || echo "  node:   not on PATH"
    command -v pnpm   >/dev/null 2>&1 && echo "  pnpm:   $(pnpm --version)"   || echo "  pnpm:   not on PATH"
    command -v uv     >/dev/null 2>&1 && echo "  uv:     $(uv --version)"     || echo "  uv:     not on PATH"
    command -v python >/dev/null 2>&1 && echo "  python: $(python --version)" || echo "  python: not on PATH"

frontend-install:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-install; fi
    just --quiet _pnpm install --frozen-lockfile

frontend-build:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-build; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    if [[ "${PDOMAIN_OPENAPI_EXPORTED:-}" != 1 ]]; then just --quiet openapi-export; fi
    echo "Building frontend..."
    just --quiet _pnpm run build
    mkdir -p src/pdomain_ocr_labeler_spa/static
    rm -rf src/pdomain_ocr_labeler_spa/static/*
    cp -r frontend/dist/. src/pdomain_ocr_labeler_spa/static/
    echo "Frontend bundled into src/pdomain_ocr_labeler_spa/static/"

frontend-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-dev; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm run dev

frontend-test:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-test; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm exec vitest run

frontend-knip:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-knip; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm exec knip

frontend-lint:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-lint; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm exec eslint . --fix

frontend-format:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-format; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    echo "Applying Prettier to the frontend..."
    just --quiet _pnpm run format

frontend-format-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-format-check; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    echo "Checking frontend formatting (Prettier)..."
    just --quiet _pnpm run format:check

openapi-export:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai openapi-export; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    uv run python -c "import json, logging; logging.disable(logging.CRITICAL); from pdomain_ocr_labeler_spa.bootstrap import build_app; print(json.dumps(build_app().openapi(), indent=2))" > frontend/openapi.json
    just --quiet _pnpm exec openapi-typescript openapi.json -o src/api/types.ts

typecheck:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai typecheck; fi
    uv run basedpyright src/pdomain_ocr_labeler_spa --level error

lint:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai lint; fi
    uv run ruff check --select I --fix
    uv run ruff check --fix

fast-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai fast-check; fi
    just --quiet lint

format:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai format; fi
    uv run ruff format

pre-commit-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai pre-commit-check; fi
    uv run pre-commit run --all-files

update-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai update-hooks; fi
    echo "⬆️  Updating pre-commit hook revisions (frozen to commit SHAs)..."
    uv run pre-commit autoupdate --freeze
    echo "✅ Hook revisions updated — review upstream release notes and the .pre-commit-config.yaml diff."

test:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai test; fi
    uv run pytest tests/ -v --ignore=tests/e2e -m "not slow and not integration" -n auto

behavior-coverage:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai behavior-coverage; fi
    uv run python -m scripts.behavior_coverage

integration:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai integration; fi
    uv run pytest tests/ -v --ignore=tests/e2e -m "slow or integration"

e2e:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai e2e; fi
    just --quiet frontend-build
    uv run --group e2e pytest tests/e2e -v -n ${PYTEST_N:-2}

e2e-browser:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai e2e-browser; fi
    just --quiet frontend-build
    uv run --group e2e pytest tests/e2e/test_browser_verification.py -m e2e -v --browser chromium

setup-e2e:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai setup-e2e; fi
    uv run --group e2e playwright install chromium

exercise-real:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai exercise-real; fi
    echo "Running exercise harness (8 pages, real OCR data)..."
    if [ ! -f src/pdomain_ocr_labeler_spa/static/index.html ] || [ -n "$(find frontend/src frontend/index.html frontend/package.json frontend/vite.config.ts frontend/tailwind.config.js frontend/postcss.config.js frontend/tsconfig.json -newer src/pdomain_ocr_labeler_spa/static/index.html 2>/dev/null)" ]; then \
        echo "SPA bundle stale or missing — running frontend-build first..."; \
        just --quiet frontend-build; \
    else \
        echo "SPA bundle up to date."; \
    fi
    uv run --group e2e pytest tests/e2e/exercise_real_project.py -v \
        ${EXERCISE_HEADED:-$(if [[ "${HEADED:-}" == 1 ]]; then echo --headed; fi)} \
        -p no:timeout \
        --tb=short

dev:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai dev; fi
    uv run pdomain-ocr-labeler-ui --reload --frontend-dev http://localhost:5173

run:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai run; fi
    if [ ! -f src/pdomain_ocr_labeler_spa/static/index.html ] || [ -n "$(find frontend/src frontend/index.html frontend/package.json frontend/vite.config.ts frontend/tailwind.config.js frontend/postcss.config.js frontend/tsconfig.json -newer src/pdomain_ocr_labeler_spa/static/index.html 2>/dev/null)" ]; then \
        echo "SPA bundle stale or missing; running frontend-build first..."; \
        just --quiet frontend-build; \
    else \
        echo "SPA bundle up to date."; \
    fi
    uv run pdomain-ocr-labeler-ui

build:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai build; fi
    just --quiet frontend-build
    uv build --sdist
    uv build --wheel

clean:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai clean; fi
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    rm -rf dist/ src/pdomain_ocr_labeler_spa/static/ frontend/dist/ 2>/dev/null || true

pip-audit:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai pip-audit; fi
    bash scripts/pip-audit-with-manifest.sh

pip-audit-no-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai pip-audit-no-dev; fi
    bash scripts/pip-audit-with-manifest.sh --no-dev

[default]
ci:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai ci; fi
    just --quiet setup frontend-install
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet pre-commit-check typecheck openapi-export
    export PDOMAIN_OPENAPI_EXPORTED=1
    just --quiet lint-check frontend-typecheck test behavior-coverage frontend-format-check frontend-lint-check frontend-test frontend-knip build
    docgraph check --strict

ci-slow:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai ci-slow; fi
    just --quiet ci

ci-against-master:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai ci-against-master; fi
    ./scripts/ci-against-master.sh

docker-build:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai docker-build; fi
    just --quiet frontend-build
    DOCKER_IMAGE=${DOCKER_IMAGE:-pdomain-ocr-labeler-spa}
    DOCKER_TAG=${DOCKER_TAG:-dev}
    version=$(git describe --tags --always --dirty | sed -E \
        -e 's/^v//' \
        -e 's/^(.*)-([0-9]+)-g([0-9a-f]+)-dirty$/\1.post\2+g\3.dirty/' \
        -e 's/^(.*)-([0-9]+)-g([0-9a-f]+)$/\1.post\2+g\3/' \
        -e 's/^([0-9a-f]+)-dirty$/0.0.0+g\1.dirty/' \
        -e 's/^([0-9a-f]+)$/0.0.0+g\1/' \
        -e 's/-dirty$/+dirty/'); \
    just --quiet _docker build --build-arg VERSION="$version" -t "${DOCKER_IMAGE:-pdomain-ocr-labeler-spa}:${DOCKER_TAG:-dev}" .

docker-run:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai docker-run; fi
    just --quiet _docker run --rm -it -p "${DOCKER_PORT:-8080}:8080" "${DOCKER_IMAGE:-pdomain-ocr-labeler-spa}:${DOCKER_TAG:-dev}"

docker-shell:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai docker-shell; fi
    just --quiet _docker run --rm -it --entrypoint /bin/bash "${DOCKER_IMAGE:-pdomain-ocr-labeler-spa}:${DOCKER_TAG:-dev}"

release-patch:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai release-patch; fi
    BUMP=patch ./scripts/do-release.sh

release-minor:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai release-minor; fi
    BUMP=minor ./scripts/do-release.sh

release-major:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai release-major; fi
    BUMP=major ./scripts/do-release.sh

lint-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai lint-check; fi
    uv run ruff format --check
    uv run ruff check

format-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai format-check; fi
    uv run ruff format --check

frontend-typecheck:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-typecheck; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm exec tsc --noEmit
    just --quiet _pnpm exec tsc -p tsconfig.test.json --noEmit

frontend-lint-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${AI:-}" ]]; then exec just --quiet _ai frontend-lint-check; fi
    if [[ "${PDOMAIN_FRONTEND_INSTALLED:-}" != 1 ]]; then just --quiet frontend-install; fi
    export PDOMAIN_FRONTEND_INSTALLED=1
    just --quiet _pnpm exec eslint . --max-warnings 0
