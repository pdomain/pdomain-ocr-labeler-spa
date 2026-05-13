.PHONY: help setup refresh-version install uninstall reset remove-venv lint fast-check format \
        pre-commit-check test e2e build clean ci dev run \
        frontend-install frontend-build frontend-dev frontend-test \
        openapi-export upgrade-pd-book-tools upgrade-deps upgrade-deps-local \
        mise-download mise-setup mise-doctor \
        docker-build docker-run docker-shell \
        release-patch release-minor release-major _do-release

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
	@echo "Reinstalling pd-ocr-labeler-spa so hatch-vcs picks up HEAD/tags..."
	@# Hatchling's `force-include` of src/pd_ocr_labeler_spa/static refuses to
	@# resolve when the directory is missing (FileNotFoundError during the
	@# editable build), so make sure it exists before the editable install.
	@# The wheel-side SPA check (build_hooks/spa_check.py) still gates real
	@# wheel builds on the bundled index.html being present.
	@mkdir -p src/pd_ocr_labeler_spa/static
	@UV_LINK_MODE=copy uv pip install -e . --reinstall-package pd-ocr-labeler-spa
	@uv run pd-ocr-labeler-ui --version 2>/dev/null || true

install: ## Install pd-ocr-labeler-ui as a uv tool from local source
	uv tool install --reinstall .
	@echo "pd-ocr-labeler-ui installed. Run: pd-ocr-labeler-ui --version"

uninstall: ## Remove the installed pd-ocr-labeler-spa uv tool
	@uv tool uninstall pd-ocr-labeler-spa || true

remove-venv: ## Remove the virtual environment
	rm -rf .venv

reset: clean remove-venv setup ## Rebuild the virtual environment
	@echo "Environment Reset!"

upgrade-deps: ## Upgrade dependency lockfile (refuses in a dev-local venv)
	@if uv pip show pd-book-tools 2>/dev/null | grep -q "Editable project location"; then \
		echo "upgrade-deps refused: editable pd-book-tools detected (probe 1)."; \
		echo "  'make upgrade-deps' would silently revert it to the pinned release."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and re-install editable."; \
		exit 1; \
	fi
	@if [ -f .venv/.pd-dev-local ]; then \
		echo "upgrade-deps refused: .venv/.pd-dev-local marker present (probe 2)."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and preserve dev-local state."; \
		exit 1; \
	fi
	@if [ "$${PD_DEV_LOCAL:-0}" = "1" ]; then \
		echo "upgrade-deps refused: PD_DEV_LOCAL=1 in environment (probe 3)."; \
		echo "  Use 'make upgrade-deps-local' to upgrade and preserve dev-local state."; \
		exit 1; \
	fi
	@echo "Upgrading dependency lockfile..."
	uv lock --upgrade
	@echo "Syncing upgraded dependencies..."
	uv sync --group dev
	@echo "Dependencies upgraded and environment synced."

upgrade-deps-local: ## [dev-local] Upgrade deps then restore dev-local state (editable siblings)
	@echo "Upgrading dependency lockfile..."
	uv lock --upgrade
	@echo "Syncing upgraded dependencies..."
	uv sync --group dev
	@echo "Restoring dev-local environment..."
	@RESTORE_SCRIPT="../scripts/pd-dev-local-restore.sh"; \
	if [ -f "$$RESTORE_SCRIPT" ]; then \
		bash "$$RESTORE_SCRIPT"; \
	else \
		echo "  workspace script not found at $$RESTORE_SCRIPT — skipping dev-local restore."; \
	fi
	@echo "Writing .venv/.pd-dev-local marker..."
	@touch .venv/.pd-dev-local
	@echo "Dependencies upgraded; .venv/.pd-dev-local marker written."

# ---------------------------------------------------------------------------
# Optional: mise-managed tool versions (mirrors pd-prep-for-pgdp pattern)
# ---------------------------------------------------------------------------
# `mise.toml` pins node/python. `make mise-setup` downloads the mise binary
# (locally, no .bashrc edit) and pulls the toolchain. Other targets dispatch
# through `$(MISE) exec --` so make is the only place that sees the pinned
# versions; your interactive shell is unchanged.

MISE := $(shell command -v mise 2>/dev/null || echo $$HOME/.local/bin/mise)
HAVE_MISE = [ -x "$(MISE)" ]

mise-download: ## [optional] Download the mise binary only (no shell init, no tools yet)
	@if $(HAVE_MISE); then \
		echo "mise already installed at $(MISE)"; \
	else \
		echo "Downloading mise to $$HOME/.local/bin/mise..."; \
		curl -fsSL https://mise.run | sh; \
		echo "mise downloaded. Run 'make mise-setup' next to install pinned tools."; \
	fi

mise-setup: mise-download ## [optional] Download mise + install pinned tools from mise.toml
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
	@command -v npm    >/dev/null 2>&1 && echo "  npm:    $$(npm --version)"    || echo "  npm:    not on PATH"
	@command -v uv     >/dev/null 2>&1 && echo "  uv:     $$(uv --version)"     || echo "  uv:     not on PATH"
	@command -v python >/dev/null 2>&1 && echo "  python: $$(python --version)" || echo "  python: not on PATH"

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
# Each target prefers `mise exec` (so node version matches mise.toml). Falls
# back to PATH `npm` for contributors who manage Node themselves.

define _npm
	if $(HAVE_MISE); then \
		echo "  (via $(MISE) exec)"; \
		( cd frontend && $(MISE) exec -- npm $(1) ); \
	elif command -v npm >/dev/null 2>&1; then \
		( cd frontend && npm $(1) ); \
	else \
		echo "no npm available."; \
		echo "   Options:"; \
		echo "     - run 'make mise-setup' (downloads mise locally, no shell edit)"; \
		echo "     - install Node 24 yourself"; \
		echo "     - add the devcontainer node feature in .devcontainer/devcontainer.json"; \
		exit 1; \
	fi
endef

frontend-install: ## Install frontend dependencies
	@echo "Installing frontend deps..."
	@$(call _npm,install)

frontend-build: ## Build the SPA into src/pd_ocr_labeler_spa/static/ (so the wheel includes it)
	@echo "Building frontend..."
	@$(call _npm,install)
	@$(call _npm,run build)
	@mkdir -p src/pd_ocr_labeler_spa/static
	@rm -rf src/pd_ocr_labeler_spa/static/*
	cp -r frontend/dist/. src/pd_ocr_labeler_spa/static/
	@echo "Frontend bundled into src/pd_ocr_labeler_spa/static/"

frontend-dev: ## Run Vite dev server (frontend only)
	@$(call _npm,install)
	@$(call _npm,run dev)

frontend-test: ## Run the SPA's vitest suite (jsdom)
	@echo "Running frontend (vitest) tests..."
	@$(call _npm,install)
	@$(call _npm,test)

openapi-export: ## Regenerate frontend/src/api/types.ts from /openapi.json
	@echo "Exporting OpenAPI schema and regenerating TS types..."
	uv run python -c "import json, sys; from pd_ocr_labeler_spa.bootstrap import build_app; \
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

lint: ## Run ruff + eslint + tsc --noEmit (backend + frontend)
	uv run ruff check --select I --fix
	uv run ruff check --fix
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

test: ## Run pytest (excludes e2e/)
	uv run pytest tests/ -v --ignore=tests/e2e

e2e: frontend-build ## Run Playwright E2E tests (requires `playwright install chromium`)
	uv run --group e2e pytest tests/e2e -v

dev: ## Run uvicorn with --reload against a Vite dev server on :5173
	uv run pd-ocr-labeler-ui --reload --frontend-dev http://localhost:5173

# ---------------------------------------------------------------------------
# `make run` — single-command "just use the labeler" entry point
# ---------------------------------------------------------------------------
# Distinct from `make dev` (which assumes you're hacking on the frontend
# and want HMR via Vite on :5173). `run` serves the bundled SPA from
# src/pd_ocr_labeler_spa/static/ directly via FastAPI — no Vite, no
# --reload, browser tab opens automatically. The startup banner
# (printed by __main__.main via core.device_info.describe_device)
# announces whether torch picked up the local GPU.
#
# We rebuild the SPA only if the bundle is missing — operators running
# `make run` repeatedly shouldn't pay the npm-install + vite-build cost
# every invocation. To force a rebuild, run `make frontend-build` first.

run: ## Build SPA if missing, then serve via pd-ocr-labeler-ui (production-style; opens browser)
	@if [ ! -f src/pd_ocr_labeler_spa/static/index.html ]; then \
		echo "SPA bundle missing; running frontend-build first..."; \
		$(MAKE) --no-print-directory frontend-build; \
	else \
		echo "SPA bundle present at src/pd_ocr_labeler_spa/static/index.html (run 'make frontend-build' to refresh)."; \
	fi
	uv run pd-ocr-labeler-ui

build: frontend-build ## Build the wheel (with frontend bundled)
	# `--wheel` skips the sdist step. The build hook in
	# build_hooks/spa_check.py refuses to build a wheel without
	# src/pd_ocr_labeler_spa/static/index.html, and that directory is
	# .gitignore'd — so the default `uv build` (sdist -> wheel-from-sdist)
	# fails because the unpacked sdist has no SPA. Wheel-only is supported.
	uv build --wheel

clean: ## Clean cache + build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ src/pd_ocr_labeler_spa/static/ frontend/dist/ 2>/dev/null || true

ci: setup frontend-build lint test frontend-test ## Full CI pipeline

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
# Mirrors `pd-prep-for-pgdp/Makefile` docker-* shape so cross-repo muscle
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

DOCKER_IMAGE ?= pd-ocr-labeler-spa
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
	@$(call _docker,build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .)

docker-run: ## Run the built image (host:container port $(DOCKER_PORT):8080)
	@$(call _docker,run --rm -it -p $(DOCKER_PORT):8080 $(DOCKER_IMAGE):$(DOCKER_TAG))

docker-shell: ## Open a debugging shell in the built image
	@$(call _docker,run --rm -it --entrypoint /bin/bash $(DOCKER_IMAGE):$(DOCKER_TAG))

# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------
# Three public targets delegate to `_do-release` with the bump kind.
# `_do-release` calls scripts/do-release.sh, which runs the full `make ci`
# pre-flight, creates an annotated three-component tag, and pushes.
#
# Usage:
#   make release-patch   # v0.4.2 → v0.4.3
#   make release-minor   # v0.4.2 → v0.5.0
#   make release-major   # v0.4.2 → v1.0.0
#
# Escape hatches (passed through to do-release.sh):
#   FORCE=1      skip repo-state guards (dirty tree / branch / origin sync)
#   SKIP_PUSH=1  create tag locally but don't push or trigger the workflow

release-patch: ## Tag + push a patch release (vX.Y.Z+1)
	@$(MAKE) --no-print-directory _do-release BUMP=patch

release-minor: ## Tag + push a minor release (vX.Y+1.0)
	@$(MAKE) --no-print-directory _do-release BUMP=minor

release-major: ## Tag + push a major release (vX+1.0.0)
	@$(MAKE) --no-print-directory _do-release BUMP=major

_do-release:
	BUMP=$(or $(BUMP),minor) ./scripts/do-release.sh
