# pd-ocr-labeler-spa runtime container.
#
# Two-stage build: Node compiles the SPA, Python builds and installs the
# wheel that bundles it. End image is CPU-only and does not require Node
# at runtime — the wheel ships the prebuilt SPA under
# `pd_ocr_labeler_spa/static/`.
#
# Spec: `specs/15-deployment-dev.md` §6.
# Mirrors `pd-prep-for-pgdp/Dockerfile` for cross-repo consistency.

# syntax=docker/dockerfile:1.7

# ──────────────────────────── Stage 1: build SPA ────────────────────────────
# Node 24 matches `mise.toml` so dev and image builds share a toolchain.
# pnpm is used exclusively (tracks `frontend/pnpm-lock.yaml`).
FROM node:24-bookworm-slim AS spa
# Install pnpm via corepack (ships with Node 24).
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /work
# Copy lockfile + manifest first so pnpm store layer is cached.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/.npmrc* ./
# --frozen-lockfile: fail fast on lockfile drift (no mutations in image builds).
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# ──────────────────────────── Stage 2: build wheel ──────────────────────────
# Python 3.13 matches `mise.toml` and `pyproject.toml requires-python`.
FROM python:3.13-slim-bookworm AS wheel

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_PROGRESS=1 \
    UV_LINK_MODE=copy

# git for `uv` to resolve the pd-book-tools git source; ca-certificates so
# the HTTPS clone works.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pull `uv` from Astral's official image — `python:3.13-slim` ships
# without curl/wget, so the install.sh path doesn't work here.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# `hatch-vcs` derives the version from git tags. The build context does
# not (and should not) ship `.git/`, so we statically pin the version
# into pyproject.toml at build time. CI passes the real tag via
# `--build-arg VERSION=…`; ad-hoc builds default to 0.0.0+docker.
ARG VERSION=0.0.0+docker

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY build_hooks/ ./build_hooks/

# Bring in the built SPA. `pyproject.toml`'s
# `[tool.hatch.build.targets.wheel.force-include]` maps
# `src/pd_ocr_labeler_spa/static` → `pd_ocr_labeler_spa/static`, and
# `build_hooks/spa_check.py` requires
# `src/pd_ocr_labeler_spa/static/index.html` to exist before it lets
# `uv build --wheel` proceed.
COPY --from=spa /work/dist/ ./src/pd_ocr_labeler_spa/static/

# Replace `dynamic = ["version"]` with a literal version line so
# hatch-vcs is bypassed (no `.git/` in the context).
RUN sed -i 's|^dynamic = \["version"\]|version = "'"${VERSION}"'"|' pyproject.toml \
    && grep -E '^(version|dynamic)' pyproject.toml

# Build the wheel itself.
RUN uv build --wheel -o /dist/

# B-20: Export `uv.lock` to a frozen `requirements.txt` for the runtime
# stage. `pip install <wheel>` alone re-resolves transitive deps from
# PyPI; consuming this file with `--no-deps` (per dep) keeps the
# transitive tree bit-for-bit identical to what `uv lock` resolved at
# author time. `--no-emit-project` excludes `pd-ocr-labeler-spa` itself
# (the wheel installs that). `--no-dev` strips dev/test extras that
# the runtime doesn't need.
RUN uv export --frozen --no-emit-project --no-dev --no-hashes \
    -o /dist/requirements.txt

# ──────────────────────────── Stage 3: runtime ──────────────────────────────
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Non-root user for runtime security. UID/GID 1000 matches the default user
# on most Linux distros; override at build time if the host bind-mount UID
# differs (e.g. --build-arg APP_UID=1001).
#
# Bind-mount caveat: in local mode the source root is mounted into the
# container. The host directory must be owned by UID 1000 (or the overridden
# UID). In future managed-storage mode no local bind-mounts are needed.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} app \
    && useradd -m -u ${APP_UID} -g app -s /bin/bash app

WORKDIR /app
COPY --from=wheel /dist/*.whl /dist/requirements.txt /tmp/

# B-21: install-time deps (`git` for pip to clone the pd-book-tools git
# source; `ca-certificates` for HTTPS) live only inside this single RUN.
# `apt-get purge --autoremove` strips both packages out of the final
# image layer so the runtime carries no git binary and no cert bundle
# beyond what Python wheels need at import time. (Python's `ssl` module
# uses the certs baked into `certifi` once the wheels are installed.)
#
# B-20: install in two passes against the frozen lockfile so neither
# pass triggers a fresh PyPI resolution:
#   1. `pip install -r requirements.txt` pulls every transitive dep at
#      the exact version uv locked. Each line in requirements.txt is a
#      `==`-pinned spec or a `pkg @ git+…@<sha>` URL, so pip cannot
#      drift.
#   2. `pip install --no-deps <wheel>` adds `pd-ocr-labeler-spa` itself
#      without re-resolving — its declared deps were already satisfied
#      by step 1.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps /tmp/*.whl \
    && rm /tmp/*.whl /tmp/requirements.txt \
    && apt-get purge --autoremove -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Transfer ownership of /app to the non-root user so the app can write any
# local temp files it needs.
RUN chown -R app:app /app

# Drop privileges — all subsequent RUN/CMD/ENTRYPOINT run as app (UID 1000).
USER app

# Listen on 0.0.0.0:8080 inside the container; users map the port out.
# `--no-browser` because there is no browser to open inside a container.
#
# Bind host is set via argv (`--host 0.0.0.0`) rather than via ENV because
# `Settings` reads the `PDLABELER_` prefix (no underscore — see
# `src/pd_ocr_labeler_spa/settings.py` env_prefix). Hardcoding an
# `ENV PDLABELER_HOST=…` here would just duplicate the argv default and
# also fight any user override of `--host`. Users can still override
# the port at runtime by passing `-e PDLABELER_PORT=…` to `docker run`,
# which Settings will pick up automatically.
# Port 8080 is non-privileged; no extra capabilities are needed.
EXPOSE 8080

ENTRYPOINT ["pd-ocr-labeler-ui", "--host", "0.0.0.0", "--no-browser"]
