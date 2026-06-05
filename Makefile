AI ?=
LOG := .ci-ai.log

ifdef AI
_goals := $(or $(MAKECMDGOALS),ci)
.PHONY: $(_goals)
$(_goals):
	@rm -f $(LOG)
	@$(MAKE) --no-print-directory AI= $@ > $(LOG) 2>&1 \
		&& echo "✅ $@ passed (log: $(LOG))" \
		|| (echo "❌ $@ failed:"; uv run scripts/ai_filter_log.py $(LOG); echo "(full log: $(LOG))"; exit 1)

else

.PHONY: help setup refresh-version install uninstall reset remove-venv lint fast-check format \
        pre-commit-check test integration e2e exercise-real build clean ci dev run \
        behavior-coverage \
        frontend-install frontend-build frontend-dev frontend-test frontend-knip \
        frontend-lint frontend-format frontend-format-check \
        openapi-export update-pdomain-deps upgrade-pdomain-book-tools upgrade-deps upgrade-deps-local \
        local-setup local-dev local-check local-upgrade-deps local-run \
        local-setup-py local-frontend-install local-frontend-build local-frontend-test \
        mise-download mise-trust-worktrees mise-setup mise-doctor \
        docker-build docker-run docker-shell \
        release-patch release-minor release-major _do-release ci-slow

# ---------------------------------------------------------------------------
# Help / discovery
# ---------------------------------------------------------------------------

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Backend setup
# ---------------------------------------------------------------------------

setup: ## Sync deps + install pre-commit hooks + refresh version
	@echo "Installing dependencies..."
	uv sync --group dev
	@echo "Setting up pre-commit hooks..."
	uv run pre-commit install || true
	@$(MAKE) --no-print-directory refresh-version
	@echo "Setup complete!"

refresh-version: ## Force hatch-vcs to re-derive version from current git state
	@echo "Reinstalling pdomain-ocr-labeler-spa so hatch-vcs picks up HEAD/tags..."
	@# Hatchling's `force-include` of src/pdomain_ocr_labeler_spa/static refuses to
	@# resolve when the directory is missing (FileNotFoundError during the
	@# editable build), so make sure it exists before the editable install.
	@# The wheel-side SPA check (build_hooks/spa_check.py) still gates real
	@# wheel builds on the bundled index.html being present.
	@mkdir -p src/pdomain_ocr_labeler_spa/static
	@UV_LINK_MODE=copy uv pip install -e . --reinstall-package pdomain-ocr-labeler-spa
	@uv run pdomain-ocr-labeler-ui --version 2>/dev/null || true

install: ## Install pdomain-ocr-labeler-ui as a uv tool from local source
	uv tool install --reinstall .
	@echo "pdomain-ocr-labeler-ui installed. Run: pdomain-ocr-labeler-ui --version"

uninstall: ## Remove the installed pdomain-ocr-labeler-spa uv tool
	@uv tool uninstall pdomain-ocr-labeler-spa || true

remove-venv: ## Remove the virtual environment
	rm -rf .venv

reset: clean remove-venv setup ## Rebuild the virtual environment
	@echo "Environment Reset!"

upgrade-deps: ## Upgrade dependency lockfile (refuses in a dev-local venv)
	@if uv pip show pdomain-book-tools 2>/dev/null | grep -q "Editable project location"; then \
		echo "upgrade-deps refused: editable pdomain-book-tools detected (probe 1)."; \
		echo "  'make upgrade-deps' would silently revert it to the pinned release."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and re-install editable."; \
		exit 1; \
	fi
	@if [ -f .venv/.pdomain-dev-local ]; then \
		echo "upgrade-deps refused: .venv/.pdomain-dev-local marker present (probe 2)."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and preserve dev-local state."; \
		exit 1; \
	fi
	@if [ "$${PDOMAIN_DEV_LOCAL:-0}" = "1" ]; then \
		echo "upgrade-deps refused: PDOMAIN_DEV_LOCAL=1 in environment (probe 3)."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and preserve dev-local state."; \
		exit 1; \
	fi
	@echo "Upgrading dependency lockfile..."
	uv lock --upgrade
	@echo "Syncing upgraded dependencies..."
	uv sync --group dev
	@echo "Dependencies upgraded and environment synced."

upgrade-deps-local: ## [deprecated] Use 'make local-upgrade-deps' instead
	@echo "DEPRECATED: use 'make local-upgrade-deps' (canonical local-dev target)." >&2
	@$(MAKE) --no-print-directory local-upgrade-deps

# ---------------------------------------------------------------------------
# Local-dev mode — editable sibling pd-* deps (pdomain-book-tools + pdomain-ui)
# ---------------------------------------------------------------------------
# 5-script SPA pattern: Python sibling pdomain-book-tools; npm sibling pdomain-ui.
# Scripts live in scripts/local-*.sh (idempotent; safe to re-run).

local-setup: ## Clone any missing sibling pd-* repos (pdomain-book-tools, pdomain-ui)
	@./scripts/local-setup.sh

local-dev: ## Switch to local-dev mode (editable pdomain-book-tools + linked pdomain-ui; writes marker)
	@./scripts/local-dev.sh

local-check: ## Print local-dev mode status (marker + editable / linked state)
	@./scripts/local-check.sh

local-upgrade-deps: ## Upgrade deps then restore editable siblings (requires local-dev mode)
	@./scripts/local-upgrade-deps.sh

local-run: ## Run the SPA against local-dev workspace (requires local-dev mode)
	@./scripts/local-run.sh

local-setup-py: ## Re-apply editable Python siblings (idempotent; safe after uv sync)
	@./scripts/local-setup-py.sh

local-frontend-install: ## pnpm install + restore pnpm link overlays for npm siblings
	@./scripts/local-frontend-install.sh

local-frontend-build: local-frontend-install ## Vite build using local-linked siblings (preserves pnpm link)
	@$(call _npm,run build)
	@mkdir -p src/pdomain_ocr_labeler_spa/static
	@rm -rf src/pdomain_ocr_labeler_spa/static/*
	cp -r frontend/dist/. src/pdomain_ocr_labeler_spa/static/
	@echo "Frontend bundled into src/pdomain_ocr_labeler_spa/static/"

local-frontend-test: ## Vitest using local sibling pdomain-ui with test-time peer resolution
	@./scripts/local-frontend-test.sh

# ---------------------------------------------------------------------------
# Sibling-dep refresh (spec #363) — update-pdomain-deps
# ---------------------------------------------------------------------------
# Queries pdomain-index-pip + pdomain-index-npm for each sibling, bumps minimum-version
# pins in pyproject.toml and frontend/package.json, then leaves the diff for
# human review. Does NOT commit. Idempotent.
# See ../docs/process/update-pdomain-deps.md for full workflow.

update-pdomain-deps: ## Bump all sibling pd-* deps (Python + npm) to registry latest; leaves diff for review
	@./scripts/update-pdomain-deps.sh

upgrade-pdomain-book-tools: ## DEPRECATED: use update-pdomain-deps
	@echo "warning: 'upgrade-pdomain-book-tools' is deprecated; use 'make update-pdomain-deps'"
	@$(MAKE) --no-print-directory update-pdomain-deps

# ---------------------------------------------------------------------------
# Optional: mise-managed tool versions (mirrors pdomain-prep-for-pgdp pattern)
# ---------------------------------------------------------------------------
# `mise.toml` pins node/python. `make mise-setup` downloads the mise binary
# (locally, no .bashrc edit) and pulls the toolchain. Other targets dispatch
# through `$(MISE) exec --` so make is the only place that sees the pinned
# versions; your interactive shell is unchanged.

MISE := $(shell command -v mise 2>/dev/null || echo $$HOME/.local/bin/mise)
WORKSPACE_ROOT := $(abspath $(CURDIR)/..)
HAVE_MISE = [ -x "$(MISE)" ]

# Security (F-017 Option B): pin mise installer to an immutable tagged GitHub
# Release asset URL rather than piping the floating https://mise.run shortlink
# to a shell. GitHub Release assets are immutable once a tag is published; TLS
# to github.com provides transport integrity. To upgrade: bump MISE_INSTALLER_VERSION.
MISE_INSTALLER_VERSION := v2026.5.15
MISE_INSTALLER_URL := https://github.com/jdx/mise/releases/download/$(MISE_INSTALLER_VERSION)/install.sh

mise-download: ## [optional] Download the mise binary only (no shell init, no tools yet)
	@if $(HAVE_MISE); then \
		echo "mise already installed at $(MISE)"; \
	else \
		echo "Downloading mise $(MISE_INSTALLER_VERSION) to $$HOME/.local/bin/mise..."; \
		MISE_TMP=$$(mktemp) && \
		curl -fsSL -o "$$MISE_TMP" "$(MISE_INSTALLER_URL)" && \
		sh "$$MISE_TMP" && \
		rm -f "$$MISE_TMP"; \
		echo "mise downloaded. Run 'make mise-setup' next to install pinned tools."; \
	fi

mise-trust-worktrees: mise-download ## [optional] Trust repo + generated worktree roots for mise
	@echo "Trusting mise config roots for this repo and generated worktrees..."
	@mkdir -p "$$HOME/.config/mise/conf.d"
	@printf '%s\n' \
		'[settings]' \
		'trusted_config_paths = [' \
		'    "$(WORKSPACE_ROOT)",' \
		'    "/srv/bot-workspaces",' \
		']' \
		> "$$HOME/.config/mise/conf.d/ocr-container-worktrees.toml"
	@echo "mise trust roots configured."

mise-setup: mise-download mise-trust-worktrees ## [optional] Download mise + install pinned tools from mise.toml
	@echo "Installing tools from mise.toml..."
	@$(MISE) install
	@echo "mise tools installed."
	@echo "Make targets dispatch through mise automatically — no shell hook needed."

mise-doctor: ## [optional] Show resolved tool versions (mise binary + PATH fallback)
	@echo "-- mise binary --"
	@if $(HAVE_MISE); then \
		echo "  found: $(MISE)"; \
		$(MISE) current 2>/dev/null | sed 's/^/  /' || echo "  (no mise.toml resolved)"; \
	else \
		echo "  not installed (run 'make mise-setup')"; \
	fi
	@echo "-- PATH (your interactive shell) --"
	@command -v node   >/dev/null 2>&1 && echo "  node:   $$(node --version)"   || echo "  node:   not on PATH"
	@command -v pnpm   >/dev/null 2>&1 && echo "  pnpm:   $$(pnpm --version)"   || echo "  pnpm:   not on PATH"
	@command -v uv     >/dev/null 2>&1 && echo "  uv:     $$(uv --version)"     || echo "  uv:     not on PATH"
	@command -v python >/dev/null 2>&1 && echo "  python: $$(python --version)" || echo "  python: not on PATH"

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
# Each target prefers `mise exec` (so node/pnpm version matches mise.toml). Falls
# back to PATH `pnpm` for contributors who manage Node themselves.

define _npm
	if $(HAVE_MISE); then \
		echo "  (via $(MISE) exec)"; \
		( cd frontend && $(MISE) exec -- pnpm $(1) ); \
	elif command -v pnpm >/dev/null 2>&1; then \
		( cd frontend && pnpm $(1) ); \
	else \
		echo "no pnpm available."; \
		echo "   Options:"; \
		echo "     - run 'make mise-setup' (downloads mise locally, no shell edit)"; \
		echo "     - install pnpm yourself: npm install -g pnpm"; \
		echo "     - add the devcontainer node feature in .devcontainer/devcontainer.json"; \
		exit 1; \
	fi
endef

frontend-install: ## Install frontend dependencies
	@echo "Installing frontend deps..."
	@$(call _npm,install --frozen-lockfile)

frontend-build: ## Build the SPA into src/pdomain_ocr_labeler_spa/static/ (so the wheel includes it)
	@echo "Building frontend..."
	@$(call _npm,install)
	@$(call _npm,run build)
	@mkdir -p src/pdomain_ocr_labeler_spa/static
	@rm -rf src/pdomain_ocr_labeler_spa/static/*
	cp -r frontend/dist/. src/pdomain_ocr_labeler_spa/static/
	@echo "Frontend bundled into src/pdomain_ocr_labeler_spa/static/"

frontend-dev: ## Run Vite dev server (frontend only)
	@$(call _npm,install)
	@$(call _npm,run dev)

frontend-test: ## Run the SPA's vitest suite (jsdom)
	@echo "Running frontend (vitest) tests..."
	@$(call _npm,install)
	@$(call _npm,test)

frontend-knip: ## Run knip dead-code/unused-exports scan (blocking; CI gate)
	@echo "Running knip dead-code scan..."
	@if [ -f frontend/node_modules/.bin/knip ]; then \
		$(call _npm,exec -- knip); \
	else \
		echo "  [knip] not installed — run 'make frontend-install' to enable."; \
		exit 1; \
	fi

frontend-lint: ## Run ESLint on the SPA
	@echo "Running frontend ESLint..."
	@$(call _npm,install)
	@$(call _npm,run lint)

frontend-format: ## Apply Prettier formatting to the SPA
	@echo "Applying Prettier to the frontend..."
	@$(call _npm,install)
	@$(call _npm,run format)

frontend-format-check: ## Check SPA formatting with Prettier (blocking; CI gate)
	@echo "Checking frontend formatting (Prettier)..."
	@$(call _npm,install)
	@$(call _npm,run format:check)

openapi-export: ## Regenerate frontend/src/api/types.ts from /openapi.json
	@echo "Exporting OpenAPI schema and regenerating TS types..."
	uv run python -c "import json, logging; logging.disable(logging.CRITICAL); from pdomain_ocr_labeler_spa.bootstrap import build_app; \
print(json.dumps(build_app().openapi(), indent=2))" > frontend/openapi.json
	@if $(HAVE_MISE); then \
		cd frontend && $(MISE) exec -- npx --yes openapi-typescript openapi.json -o src/api/types.ts; \
	else \
		cd frontend && npx --yes openapi-typescript openapi.json -o src/api/types.ts; \
	fi
	@echo "frontend/src/api/types.ts regenerated."

# ---------------------------------------------------------------------------
# Lint / format / test / build
# ---------------------------------------------------------------------------

typecheck: ## Run basedpyright recommended on src/pdomain_ocr_labeler_spa (--level error, warnings suppressed)
	uv run basedpyright src/pdomain_ocr_labeler_spa --level error

lint: ## Run ruff + basedpyright + eslint + tsc --noEmit (backend + frontend)
	uv run ruff check --select I --fix
	uv run ruff check --fix
	uv run basedpyright src/pdomain_ocr_labeler_spa --level error
	@if [ -f frontend/node_modules/.bin/eslint ]; then \
		echo "  Running eslint..."; \
		$(call _npm,run lint); \
		echo "  Running tsc --noEmit..."; \
		$(call _npm,run typecheck); \
	else \
		echo "  [lint] eslint not installed — run 'make frontend-install' to enable frontend lint."; \
	fi

fast-check: lint ## Quick lint check (alias used by style-review-apply.py)

format: ## Format code with ruff
	uv run ruff format
	@$(MAKE) --no-print-directory lint

pre-commit-check: ## Run pre-commit on all files
	uv run pre-commit run --all-files

test: ## Run pytest (excludes e2e/ and slow/integration markers)
	uv run pytest tests/ -v --ignore=tests/e2e -m "not slow and not integration" -n auto

behavior-coverage: ## Regenerate behavior coverage.md + gate (declared vs cited IDs)
	uv run python -m scripts.behavior_coverage

integration: ## Run slow/integration tests (real DocTR OCR pipeline, ~10 min)
	uv run pytest tests/ -v --ignore=tests/e2e -m "slow or integration"

e2e: frontend-build ## Run Playwright E2E tests (requires `playwright install chromium`)
	uv run --group e2e pytest tests/e2e -v -n auto

e2e-browser: frontend-build ## Run Playwright browser verification tests
	uv run --group e2e pytest tests/e2e/test_browser_verification.py -m e2e -v --browser chromium

setup-e2e: ## Install Playwright browser binaries
	uv run --group e2e playwright install chromium

# ---------------------------------------------------------------------------
# Exercise harness — multi-page real-project workflow smoke run
# ---------------------------------------------------------------------------
# Exercises the major UI paths across 8 pages of the exercise-fixture project.
# The fixture ships pre-built envelopes with real OCR block/line/word structure
# so line cards, word edit dialogs, filter modes, etc. all have content to work with.
#
# Prerequisites:
#   1. make frontend-build   (or the SPA bundle must already exist)
#   2. playwright install chromium  (first time only)
#   The fixture at tests/e2e/fixtures/projects/exercise-fixture/ is committed
#   to the repo and ready to use; re-run
#   `uv run python scripts/generate_exercise_fixture.py` to regenerate it.
#
# Run options:
#   make exercise-real            — headless (default)
#   make exercise-real HEADED=1   — headed Chromium, useful for watching it work

EXERCISE_HEADED ?= $(if $(filter 1,$(HEADED)),--headed,)

exercise-real: ## Run Playwright exercise against the 8-page exercise-fixture project
	@echo "Running exercise harness (8 pages, real OCR data)..."
	@if [ ! -f src/pdomain_ocr_labeler_spa/static/index.html ]; then \
		echo "SPA bundle missing — running frontend-build first..."; \
		$(MAKE) --no-print-directory frontend-build; \
	fi
	uv run --group e2e pytest tests/e2e/exercise_real_project.py -v \
		$(if $(EXERCISE_HEADED),--headed,) \
		-p no:timeout \
		--tb=short

dev: ## Run uvicorn with --reload against a Vite dev server on :5173
	uv run pdomain-ocr-labeler-ui --reload --frontend-dev http://localhost:5173

# ---------------------------------------------------------------------------
# `make run` — single-command "just use the labeler" entry point
# ---------------------------------------------------------------------------
# Distinct from `make dev` (which assumes you're hacking on the frontend
# and want HMR via Vite on :5173). `run` serves the bundled SPA from
# src/pdomain_ocr_labeler_spa/static/ directly via FastAPI — no Vite, no
# --reload, browser tab opens automatically. The startup banner
# (printed by __main__.main via core.device_info.describe_device)
# announces whether torch picked up the local GPU.
#
# We rebuild the SPA only if the bundle is missing — operators running
# `make run` repeatedly shouldn't pay the npm-install + vite-build cost
# every invocation. To force a rebuild, run `make frontend-build` first.

run: ## Build SPA if missing, then serve via pdomain-ocr-labeler-ui (production-style; opens browser)
	@if [ ! -f src/pdomain_ocr_labeler_spa/static/index.html ]; then \
		echo "SPA bundle missing; running frontend-build first..."; \
		$(MAKE) --no-print-directory frontend-build; \
	else \
		echo "SPA bundle present at src/pdomain_ocr_labeler_spa/static/index.html (run 'make frontend-build' to refresh)."; \
	fi
	uv run pdomain-ocr-labeler-ui

build: frontend-build ## Build the wheel and sdist (with frontend bundled)
	# Build sdist and wheel as separate explicit commands — NOT bare `uv build`.
	# Bare `uv build` (default) builds the wheel from the sdist in a temporary
	# non-git directory. In that path, hatchling only honours `artifacts` set at
	# the global [tool.hatch.build] table; a wheel-target-only artifacts spec is
	# silently dropped, producing a wheel with 0 frontend files. Explicitly
	# building both from the source tree avoids this failure mode entirely.
	# The sdist also ships the built SPA (via global artifacts) so that
	# downstream pipelines using wheel-from-sdist still work.
	uv build --sdist
	uv build --wheel

clean: ## Clean cache + build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ src/pdomain_ocr_labeler_spa/static/ frontend/dist/ 2>/dev/null || true

# ---------------------------------------------------------------------------
# Security audit (F-021) — pip-audit with non-PyPI manifest
# ---------------------------------------------------------------------------
# pip-audit cannot query advisories for packages served from private registries
# (e.g. pdomain-book-tools from pdomain-index-pip). Passing such packages to pip-audit
# causes it to fail or silently skip them. This target:
#   1. Parses uv.lock to find every non-PyPI source package.
#   2. Prints an explicit manifest of those packages so nothing is invisible.
#   3. Audits the remaining PyPI-resolvable packages via the OSV advisory DB.
#
# NOT included in `make ci` — requires network access and pip-audit install.
# Run manually or from a dedicated security-scan workflow step.
#
# See docs/research/2026-05-22-deep-code-review-security-scan.md F-021.

pip-audit: ## Audit PyPI deps; print manifest of skipped non-PyPI packages (F-021)
	@bash scripts/pip-audit-with-manifest.sh

pip-audit-no-dev: ## Audit runtime-only PyPI deps (excludes dev group)
	@bash scripts/pip-audit-with-manifest.sh --no-dev

ci: setup frontend-install pre-commit-check typecheck openapi-export frontend-build lint test behavior-coverage frontend-format-check frontend-lint frontend-test frontend-knip ## Full CI pipeline

ci-slow: ci build ## Full pre-flight for releases (CI plus wheel build)

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
# Mirrors `pdomain-prep-for-pgdp/Makefile` docker-* shape so cross-repo muscle
# memory works: `docker-build` depends on `frontend-build` (the
# Dockerfile's wheel stage requires a populated `static/` regardless,
# but the wheel-from-source `make build` path needs it locally too, and
# folks frequently run `make docker-build` after editing TS), and
# `docker-run` maps the EXPOSEd port out 1:1.
#
# The image tag and host port are exposed as overridable vars so
# operators can `make docker-run DOCKER_PORT=9000` without editing the
# Makefile, while the in-container port stays pinned to whatever the
# Dockerfile EXPOSEs (and `Settings.port` defaults to). The unit test
# in `tests/unit/test_makefile_docker.py` asserts those three values
# stay in lockstep.

DOCKER_IMAGE ?= pdomain-ocr-labeler-spa
DOCKER_TAG   ?= dev
DOCKER_PORT  ?= 8080

# `_docker` parallels `_npm`: emit a friendly diagnostic if `docker` isn't
# on PATH, instead of letting the recipe fail with bash's terse
# `make: docker: No such file or directory`. M0 contributors who try the
# docker targets without docker installed get a pointer rather than a
# stack trace. Argument is the docker subcommand + flags as a single
# string (e.g. `build -t img:tag .`).
define _docker
	if command -v docker >/dev/null 2>&1; then \
		docker $(1); \
	else \
		echo "docker not on PATH."; \
		echo "   Options:"; \
		echo "     - install Docker Desktop (https://www.docker.com/products/docker-desktop/)"; \
		echo "     - install Colima or another OCI runtime that provides 'docker'"; \
		echo "     - add the docker-in-docker feature in .devcontainer/devcontainer.json"; \
		exit 1; \
	fi
endef

docker-build: frontend-build ## Build the production Docker image
	@$(call _docker,build --build-arg VERSION=$$(git describe --tags --always --dirty) -t $(DOCKER_IMAGE):$(DOCKER_TAG) .)

docker-run: ## Run the built image (host:container port $(DOCKER_PORT):8080)
	@$(call _docker,run --rm -it -p $(DOCKER_PORT):8080 $(DOCKER_IMAGE):$(DOCKER_TAG))

docker-shell: ## Open a debugging shell in the built image
	@$(call _docker,run --rm -it --entrypoint /bin/bash $(DOCKER_IMAGE):$(DOCKER_TAG))

# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------
# Three public targets delegate to `_do-release` with the bump kind.
# `_do-release` calls scripts/do-release.sh, which runs the full `make ci-slow`
# pre-flight, creates an annotated three-component tag, and pushes.
#
# Usage:
#   make release-patch   # v0.4.2 → v0.4.3
#   make release-minor   # v0.4.2 → v0.5.0
#   make release-major   # v0.4.2 → v1.0.0
#
# Escape hatches (passed through to do-release.sh):
#   FORCE=1      skip repo-state guards (dirty tree / branch / origin sync)
#   SKIP_PUSH=1  create tag locally but don't push

release-patch: ## Release: bump patch, run ci-slow, tag, push
	@$(MAKE) --no-print-directory _do-release BUMP=patch

release-minor: ## Release: bump minor, run ci-slow, tag, push
	@$(MAKE) --no-print-directory _do-release BUMP=minor

release-major: ## Release: bump major, run ci-slow, tag, push
	@$(MAKE) --no-print-directory _do-release BUMP=major

_do-release:
	@BUMP=$(or $(BUMP),minor) ./scripts/do-release.sh

endif
