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
FROM node:24-bookworm-slim AS spa
WORKDIR /work
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --include=dev
COPY frontend/ ./
RUN npm run build

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

RUN uv build --wheel -o /dist/

# ──────────────────────────── Stage 3: runtime ──────────────────────────────
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git + ca-certificates needed at install time to resolve pd-book-tools
# from its git source. Stripped after install to keep the image lean.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=wheel /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# Listen on 0.0.0.0:8080 inside the container; users map the port out.
# `--no-browser` because there is no browser to open inside a container.
EXPOSE 8080
ENV PD_LABELER_HOST=0.0.0.0 \
    PD_LABELER_PORT=8080

ENTRYPOINT ["pd-ocr-labeler-ui", "--host", "0.0.0.0", "--no-browser"]
