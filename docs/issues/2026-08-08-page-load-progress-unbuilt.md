---
kind: issue
status: active
owner: maintainers
created: 2026-08-08
last_verified: 2026-08-08
level: I1
---

# Page load blocks for up to half a minute with no status and no way to report one

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-08-08
- **Resolution:** Open
- **Severity:** High — the app is indistinguishable from hung on every cold page open
- **Affected version:** 0.2.1.dev175+g8227a8c43
- **Read when:** implementing the page-load loading screen, moving OCR onto the
  job system, or touching the `ensure_page_model` lock contract.
- **Search terms:** loading project, spinner, cold OCR, ensure_page_model, job
  SSE, update_progress, BusyOverlay, ProjectRouteGate, predictor build, page
  region status.
- **Relates to:**
  [`docs/specs/2026-08-08-page-load-progress-design.md`](../specs/2026-08-08-page-load-progress-design.md)

## Summary

Opening a page that is not already in the store blocks for seconds to half a
minute behind a spinner that says "Loading project". The message is wrong, the
wait is unexplained, and the app looks hung.

The design is settled in the spec. This issue is the work item: build it. The
spec's recommendation is to create a job on a store miss and report named
stages through the stream the SPA already consumes.

## Impact

- Every cold page open looks like a hang. A first open costs about 33 seconds.
- The whole view is blocked, so the rail, page list, and panels are unusable
  during a wait where only one page's words are actually missing.
- The message names the wrong stage. Project open finishes in milliseconds and
  the SPA keeps showing "Loading project" through the page fetch.
- OCR failures are invisible on this path, tracked separately in
  [`2026-08-08-get-page-hides-ocr-failures.md`](2026-08-08-get-page-hides-ocr-failures.md).

## Environment / versions

```
pdomain-ocr-labeler-spa 0.2.1.dev175+g8227a8c43
pdomain-book-tools 0.21.0
device: cuda:0 (NVIDIA GeForce RTX 3070 Ti Laptop GPU)
launch: uv run pdomain-ocr-labeler-ui --no-browser --port 8080
```

## Evidence — reproduction & diagnosis

### 1. The wait is real and the label is wrong

Server log from one page open. The project load returns inside its own second;
the following 33 seconds are the page request:

```
10:02:59  POST /api/projects/load        200 OK      (returns immediately)
10:02:59  WARNING store reload failed for index=0 — falling through to re-OCR
10:03:14  Using downloaded & verified file: db_resnet50-79bd7d70.pt
10:03:19  Using downloaded & verified file: crnn_vgg16_bn-0417f351.pt
10:03:32  GET /api/projects/demo-book/pages/0   request_end
```

The SPA shows "Loading project" for that whole window, from `BusyOverlay` and
`ProjectRouteGate`.

### 2. Project open is not the slow part

```
POST /api/projects/load, 8-page book:            12ms – 76ms
POST /api/projects/load, synthetic 500-page book: 14ms – 81ms
```

It does not scale with page count in any way a user notices, so it needs a
correct label rather than a job.

### 3. The cost is the predictor build and the OCR pass

Building the predictor with both weight files already on disk, 102 MB and
63 MB under `~/.cache/doctr/models`:

```
import torch          3.59s
CUDA context init     0.28s
build predictor      26.22s   <- no network; deserialise, build graph, move to device
```

Warm per-page OCR, five consecutive uncached pages (the first includes the
predictor build):

```
22.17s  3.08s  3.76s  9.98s  9.91s
```

An earlier run on the same machine and book gave 30.18s, 17.06s, 13.26s.

### 4. Nothing can report on the work today

`ensure_page_model` in `core/page_state.py` holds the project lock for the
entire load, OCR included, as a documented contract. A second request cannot
ask what the first is doing.

## What is NOT broken (to scope the fix)

- OCR itself works. Pages complete with `source: 'ocr'` on their records.
- Project enumeration and load are fast, including at 500 pages.
- The job system is fine and already does this correctly elsewhere.
  `reload_ocr` runs OCR through `asyncio.to_thread`, reports four progress
  fractions through `update_progress(current, total, message)`, and takes the
  project lock only afterwards to apply the outcome.
- `pdomain-ops` needs no change. It already serves the device at
  `GET /api/suite/device`, and `describe_device()` already exists here.
- `auto_rotate` is not implicated. This repo passes `auto_rotate=False`, so a
  page is a single OCR pass.

## Defects to fix

1. **No progress channel on the implicit first load.** (Primary) Create a job on
   a store miss only; return a pending record and a job id. A hit stays
   synchronous and creates no job.
2. **`ensure_page_model` holds the lock across OCR.** Follow `reload_ocr`: run
   OCR off-lock, take the lock to apply the outcome.
3. **The wait is labelled "Loading project".** Name the real stage. Clear the
   project-open overlay when the project data arrives.
4. **The whole view blocks.** Move the OCR status into the page region and keep
   the rest of the shell interactive.
5. **The effective device is not exposed.** `__main__.py` prints
   `describe_device()` as a CLI boot banner and nothing serves it over HTTP.

## Dependencies

- Stage granularity for the predictor build depends on
  `pdomain-book-tools`, which has no progress hook on
  `from_image_ocr_via_doctr` or the default predictor path. Filed there as
  `docs/issues/2026-08-08-ocr-progress-hook.md`. Without it, "preparing the OCR
  engine" is one opaque 26-second block, which is still better than today.
- The failure stage depends on
  [`2026-08-08-get-page-hides-ocr-failures.md`](2026-08-08-get-page-hides-ocr-failures.md).
  Do not build the loading screen on top of the current silent degrade.
- Adjacent to the Wave 3 job SSE frontend-to-backend shape work.

## Next steps

1. Agree the page endpoint's miss-path contract, since it changes the response
   shape. This is the one blocking decision.
2. Move the loader call off the project lock, following `reload_ocr`.
3. Emit the stages from the handler and render them in the page region.
4. Fix the "Loading project" label and clear the overlay on project data.
5. Expose the effective device and show it in the engine stage.

## Resolution

_Open._
