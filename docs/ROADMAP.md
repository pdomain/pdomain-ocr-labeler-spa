# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M0** Repo scaffold | 🟡 in progress | Iter 1 (2026-05-06): backend skeleton + tests landed; frontend / Makefile / Dockerfile / install scripts pending. |
| M1 Settings + adapters + AppState | ⬜ not started | Pre-conditions: M0. |
| M2 Project discovery + load | ⬜ not started | Pre-conditions: M0, M1. |
| M3 OCR config modal + first-page OCR | ⬜ not started | |
| M4 Image viewport + overlays + drag selection | ⬜ not started | |
| M5 Word matches view (right pane) | ⬜ not started | |
| M6 Toolbar action grid + style/component apply + add-word | ⬜ not started | |
| M7 Word edit dialog + word-image canvas + bbox edit | ⬜ not started | |
| M8 Save / Load page + Save Project + Rematch GT + driver compat | ⬜ not started | |
| M9 Export + cleanup + cut-over | ⬜ not started | |
| M9.1 Manual rotation buttons | ⬜ blocked | Pre: M9. |
| M9.2 Auto-rotation pass | ⬜ blocked | Pre: M9.1 + pd-book-tools `rotation` module. |
| M9.5 Full keyboard-driven editing audit | ⬜ blocked | Pre: M9. |
| M10 Text normalization | ⬜ blocked | Pre: pd-book-tools `text.normalize`. |
| M11 Glyph-level annotations | ⬜ blocked | Pre: M9 + pd-book-tools/pd-ocr-trainer upstreams + Q-A5/A6/A7. |

## M0 sub-tasks

- [x] **Iter 1.** Backend skeleton: `pyproject.toml`, `__init__`,
  `settings.py`, `bootstrap.py`, `__main__.py`, `api/healthz.py`,
  `api/env_js.py`, `static/.gitkeep`, `build_hooks/spa_check.py`,
  unit tests for `/healthz`, `/env.js`, settings, `build_app`.
- [ ] **Iter 2 (next).** Frontend scaffold: `frontend/` with
  Vite + React + TS + Tailwind + Vitest stub, plus a Vitest smoke
  test. `frontend/src/api/{client,types}.ts` placeholder.
- [ ] Makefile mirroring pd-prep-for-pgdp targets (`setup`, `test`,
  `frontend-*`, `openapi-export`, `build`, `ci`).
- [ ] `mise.toml` pinning Node 24 / Python 3.13.
- [ ] `.pre-commit-config.yaml` (ruff + ruff-format).
- [ ] `Dockerfile` (two-stage Node → Python wheel).
- [ ] `install.sh` / `install.ps1` (uv tool installer).
- [ ] `.github/workflows/release.yml` (CI gate including SPA-bundle
  presence check).
- [ ] `DEVELOPMENT.md`.
- [ ] M0 acceptance gate: `make ci` green, `make build` produces a
  wheel that contains `pd_ocr_labeler_spa/static/index.html`,
  `pd-ocr-labeler-ui --no-browser --port 8080` answers `/healthz`,
  `make openapi-export` regenerates `frontend/src/api/types.ts`.

## Iteration index (this repo)

See `/workspaces/ocr-container/docs/LOOP_STATE.md` for the full per-
iteration log driven by the dev /loop.
