---
last_verified: 2026-07-13
created: 2026-06-10
owner: maintainers
kind: plan
status: draft
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
---

# Compute Settings Panel Backlog

`pdomain-ocr-labeler-spa` needs the shared pdomain ops Compute settings panel now.
The app performs local OCR/refinement work where CUDA availability directly affects
runtime behavior, so users need the same compute-state visibility and CUDA setup
guidance available in `pdomain-ocr-simple-gui`.

## Scope

- Mount the pdomain-ops suite device route if it is not already available in the
  FastAPI app.
- Add a Compute settings entry backed by `createApiDeviceConfig()` and
  `useDeviceInfo()`.
- Start a background `GET /api/suite/device` warmup task at SPA startup when the
  Compute panel is exposed.
- Render in-app CUDA setup guidance near the Compute panel, including
  `nvidia-smi`, `torch.cuda.is_available()`, and a PyTorch selector link.
- Keep app-specific OCR settings separate from compute-device selection.

## Acceptance

- Opening the app triggers one background `/api/suite/device` fetch before the
  user opens settings.
- Settings exposes a Compute panel listing CPU, usable CUDA devices, and detected
  but unusable NVIDIA hardware.
- The panel shows a reset path for app-forced CPU overrides.
- CUDA setup guidance is readable inside the app, not only as an external docs
  link.
- Focused frontend tests cover panel registration, startup warmup, and guidance
  rendering.

## Goal

Expose the shared compute-device state and CUDA guidance without merging
app-specific OCR settings into device selection.

## Architecture

Mount the suite device route in FastAPI, warm it at startup, and present it
through the shared `pdomain-ui` compute panel.

## Tech Stack

FastAPI and the pdomain ops suite device API back a React/TypeScript panel using
`createApiDeviceConfig()` and `useDeviceInfo()`.

## Global Constraints

Keep OCR configuration separate, preserve generated OpenAPI types, and test the
startup warmup without requiring CUDA hardware.
