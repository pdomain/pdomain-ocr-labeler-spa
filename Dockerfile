# pdomain-ocr-labeler-spa runtime container.
#
# Two-stage build: Node compiles the SPA, Python builds and installs the
# wheel that bundles it. End image is CPU-only and does not require Node
# at runtime — the wheel ships the prebuilt SPA under
# `pdomain_ocr_labeler_spa/static/`.
#
# Spec: `specs/15-deployment-dev.md` §6.
# Mirrors `pdomain-prep-for-pgdp/Dockerfile` for cross-repo consistency.

# syntax=docker/dockerfile:1.7

# ──────────────────────────── Stage 1: build SPA ────────────────────────────
# Node 24 matches `mise.toml` so dev and image builds share a toolchain.
# pnpm is used exclusively (tracks `frontend/pnpm-lock.yaml`).
FROM node:24.15.0-bookworm-slim AS spa
# Install pnpm via corepack (ships with Node 24).
# pnpm 11 reads overrides from pnpm-workspace.yaml. That file has to be
# present for a frozen install, and 11.28 is the pnpm 11 that wrote the lockfile.
RUN corepack enable && corepack prepare pnpm@11.28.11 --activate
WORKDIR /work
# Copy lockfile + manifest first so pnpm store layer is cached.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc* ./
# --frozen-lockfile: fail fast on lockfile drift (no mutations in image builds).
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# ──────────────────────────── Stage 2: build wheel ──────────────────────────
# Python 3.13 matches `mise.toml` and `pyproject.toml requires-python`.
FROM python:3.13.13-slim-bookworm AS wheel

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_PROGRESS=1 \
    UV_LINK_MODE=copy

# git for `uv` to resolve the pdomain-book-tools git source; ca-certificates so
# the HTTPS clone works.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pull `uv` from Astral's official image — `python:3.13-slim` ships
# without curl/wget, so the install.sh path doesn't work here.
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

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
# `src/pdomain_ocr_labeler_spa/static` → `pdomain_ocr_labeler_spa/static`, and
# `build_hooks/spa_check.py` requires
# `src/pdomain_ocr_labeler_spa/static/index.html` to exist before it lets
# `uv build --wheel` proceed.
COPY --from=spa /work/dist/ ./src/pdomain_ocr_labeler_spa/static/

# Replace `dynamic = ["version"]` with a literal version line so
# hatch-vcs is bypassed (no `.git/` in the context).
RUN sed -i 's|^dynamic = \["version"\]|version = "'"${VERSION}"'"|' pyproject.toml \
    && grep -E '^(version|dynamic)' pyproject.toml

# Build the wheel itself.
RUN uv build --wheel -o /dist/

# B-20: Export `uv.lock` to a hash-pinned `requirements.lock` for the
# runtime stage. `pip install <wheel>` alone re-resolves transitive deps
# from PyPI; consuming this file with `--require-hashes` pins every
# transitive dep to its exact wheel hash, preventing substitution attacks
# and drift from what `uv lock` resolved at author time.
# `--no-emit-project` excludes `pdomain-ocr-labeler-spa` itself (the wheel
# installs that). `--no-dev` strips dev/test extras.
# NOTE: `--no-hashes` is intentionally absent — hashes are required.
# The uv pinned above (0.11.16) has no `--emit-index-url`. The runtime
# pip install passes the pdomain index itself.
RUN uv export --frozen --no-emit-project --no-dev \
    -o /dist/requirements.lock

# ──────────────────────────── Stage 3: runtime ──────────────────────────────
FROM python:3.13.13-slim-bookworm AS runtime

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
COPY --from=wheel /dist/*.whl /dist/requirements.lock /tmp/

# B-21: install-time deps (`git` for pip to clone the pdomain-book-tools git
# source; `ca-certificates` for HTTPS) live only inside this single RUN.
# `apt-get purge --autoremove` strips both packages out of the final
# image layer so the runtime carries no git binary and no cert bundle
# beyond what Python wheels need at import time. (Python's `ssl` module
# uses the certs baked into `certifi` once the wheels are installed.)
#
# B-20: install in two passes against the hash-pinned lockfile so
# neither pass triggers a fresh PyPI resolution and every wheel is
# verified against its recorded hash:
#   1. `pip install --require-hashes -r requirements.lock` pulls every
#      transitive dep at the exact version uv locked AND verifies each
#      wheel against its sha256 hash, closing the supply-chain gap that
#      --no-hashes introduced (F-016). The pdomain index is required:
#      those packages are not on PyPI.
#   2. `pip install --no-deps <wheel>` adds `pdomain-ocr-labeler-spa` itself
#      without re-resolving — its declared deps were already satisfied
#      by step 1.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --require-hashes --extra-index-url https://pdomain.github.io/pdomain-index-pip/simple/ -r /tmp/requirements.lock \
    && pip install --no-cache-dir --no-deps /tmp/*.whl \
    && rm /tmp/*.whl /tmp/requirements.lock \
    && apt-get purge --autoremove -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# opencv-python links these and does not bundle them. python:slim has none
# of them, so `import cv2` dies before the server can listen.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libgl1 \
        libglib2.0-0 \
        libice6 \
        libsm6 \
        libx11-6 \
        libxext6 \
        libxcb1 \
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
# `src/pdomain_ocr_labeler_spa/settings.py` env_prefix). Hardcoding an
# `ENV PDLABELER_HOST=…` here would just duplicate the argv default and
# also fight any user override of `--host`. Users can still override
# the port at runtime by passing `-e PDLABELER_PORT=…` to `docker run`,
# which Settings will pick up automatically.
# Port 8080 is non-privileged; no extra capabilities are needed.
EXPOSE 8080

ENTRYPOINT ["pdomain-ocr-labeler-ui", "--host", "0.0.0.0", "--no-browser"]
