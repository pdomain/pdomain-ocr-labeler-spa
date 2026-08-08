---
last_verified: 2026-08-08
created: 2026-08-08
owner: maintainers
kind: spec
repo: pdomain/pdomain-ocr-labeler-spa
status: draft
date: 2026-08-08
---

# Page-load progress and status

## Agent Index

- **Kind:** spec
- **Status:** draft
- **Read when:** the SPA appears to hang on "Loading project", you are adding
  progress reporting to a slow backend path, or you are coordinating an OCR
  progress hook with `pdomain-book-tools`.
- **Search terms:** loading screen, progress, spinner, cold OCR,
  ensure_page_model, job SSE, update_progress, model load, device resolution,
  stage reporting.

## The problem

Opening a page can block for half a minute with nothing on screen but a spinner. The user cannot
tell whether the app is working, stuck, or broken.

Measured on 2026-08-07 and 2026-08-08 in this repo, on a machine reporting
`device: cuda:0 (NVIDIA GeForce RTX 3070 Ti Laptop GPU)`:

| What | Cost | How often |
|---|---|---|
| Detection model load (`db_resnet50`) | 15s | once per predictor-cache key |
| Recognition model load (`crnn_vgg16_bn`) | 5s | once per predictor-cache key |
| One page's OCR pass | 13s to 30s | once per page, per store miss |

A first page open therefore costs about 33 seconds, and each later page costs 13 to 30 seconds.
Three separate measurements of later pages on a clean store gave 30.18s, 17.06s, and 13.26s.

The app has no way to say any of this. The page request runs OCR synchronously and returns only
when everything is done.

## Why the current design cannot report progress

The blocking work happens inside a single HTTP GET, under a lock. `ensure_page_model` in
`core/page_state.py` holds the project lock for the entire load, OCR included, which its own
docstring states as a deliberate contract. So a second request cannot ask what the first one is
doing. There is no seam to report through.

This is the part worth fixing structurally rather than papering over. A spinner with a better
animation still cannot know what stage it is in.

The machinery already exists but sits on a different path. The job system supports
`update_progress(current, total, message)` with a server-sent-event stream. The `reload_ocr`
handler already reports four progress fractions through it. The explicit "Reload OCR" action is
observable. The implicit first load is not.

## Failures are currently invisible

`api/pages.py` wraps the loader call in `except Exception` and logs the failure at DEBUG only,
then returns an empty page record. In practice the DEBUG line never appears: running the server
with `-v` produced zero DEBUG lines in a reproduction on 2026-08-08.

The result is that a genuine OCR failure and a page with no text render identically. Both show an
empty page and neither reports anything. Any loading screen built on top of this inherits that
blindness. The error path has to be fixed as part of this work, not after it.

## What the loading screen should report

Name the stage, not a percentage. The user needs to know which slow thing is happening and whether
it is progressing.

1. **Opening the project** — enumerating images, reading the page manifest, probing for
   ground truth, opening the event store. This stage belongs to `POST /api/projects/load`, not to
   the page endpoint, so it needs the same treatment applied there. See the note under the
   recommendation.
2. **Preparing the OCR engine** — resolving the compute device, fetching or verifying model
   weights, loading the detection model, loading the recognition model. Report this only when it
   runs. The predictor cache is keyed on detection model, recognition model, and revision, so the
   cost is paid once per key, not once per process. Changing the OCR config mid-session loads a
   fresh predictor and pays the cost again.
3. **Reading stored results** — the store lookup, and whether it hit or missed. A miss is what
   triggers the expensive path, so it belongs on screen.
4. **Running OCR** — which page, and its position in any queued set.
5. **Failed** — the stage that failed and the error, never a silent empty page.

Stage 3 matters more than it looks. A user who sees "stored results not found, running OCR" learns
that the wait is expected. A user who sees a bare spinner learns nothing.

## Move page loading onto the job system

Move the implicit first load onto the existing job system rather than building a second progress
channel.

The page request keeps its existing synchronous check. It looks in the in-memory page state, then
the store. When either hits, it returns the page as it does today, with no job and no added
latency. Only a genuine miss, the case that would have blocked for 13 to 30 seconds, creates a job
and returns a pending record with a job id. The SPA then subscribes to the stream it already
consumes and renders the stages above.

`reload_ocr` is the working reference. It runs OCR on a worker thread through `asyncio.to_thread`,
reports progress as it goes, and takes the project lock only afterwards to apply the outcome.

The alternative is to keep the request synchronous and stream progress from a side channel. Reject
it for consistency, not feasibility: it would build a second progress path next to the job stream
that already works, forcing the SPA to consume both.

Both options need the same underlying change. `ensure_page_model` currently holds the project lock
across the whole load, including OCR, so neither approach can report progress until that lock
discipline changes. The lock is not what decides between them.

This does change the page endpoint's contract on the miss path, so the shape needs agreement before
implementation. It is also adjacent to the Wave 3 job SSE work already tracked between frontend and
backend.

Stage 1 sits on a different endpoint. `POST /api/projects/load` does the project-open work and needs
the same treatment. It should report through the same stream, so the SPA renders one continuous
sequence rather than two disconnected waits. Doing the page endpoint alone would leave the first
half of the delay unexplained, so both belong in the same piece of work.

## Coordination with the sibling libraries

Only one stage needs something this repo does not already have. The device information turned out to
be available; the OCR progress hook is not.

### pdomain-book-tools

`Document.from_image_ocr_via_doctr` takes no progress callback today, and neither does the default
predictor construction behind `get_default_doctr_predictor`. Stage 2 and stage 4 both need a hook
there.

The minimum useful addition is an optional callback invoked at stage boundaries: weights resolved,
detection model ready, recognition model ready, OCR pass starting, OCR pass complete. Without it,
the labeler can only report "preparing the OCR engine" as one opaque 20-second block, because the
only signal available is doctr's own root-logger lines.

This repo passes `auto_rotate=False` explicitly, so a page is one OCR pass. The cost does not
include hidden rotation probes.

### pdomain-ops needs no change

Stage 2 should name the device it selected, because a user who expected the GPU and sees CPU has
found their explanation for the wait. That needs no ops work.

Ops already resolves the preference through `resolve_effective_device` and serves it at
`GET /api/suite/device`, which the SPA already calls on load. The human-readable string also already
exists here, as `describe_device()`.

The gap is local and small. `__main__.py` prints `describe_device()` once as a CLI boot banner and
nothing exposes it over HTTP. Surfacing it is labeler work, not a coordination item.

## Acceptance criteria

- Opening a page that needs OCR shows a named stage within one second, not a bare spinner.
- The stage text changes as the work moves between model load, store lookup, and OCR.
- A store miss is visible as its own stage, so the wait is explained rather than mysterious.
- An OCR failure reaches the screen with its error, and is distinguishable from a page with no text.
- A page served from a warm store still returns immediately, with no added latency from the
  progress machinery, and creates no job.
- Opening a project reports its stages through the same stream as the page load, so the two waits
  read as one sequence.

## Non-goals

Making OCR faster is out of scope. The measured costs are the cost of the models on this hardware,
and this spec only makes them legible.

Replacing the job system or the event stream is out of scope. The recommendation is to use both.

Redesigning the empty-page rendering is out of scope beyond the failure case, which has to change
because it currently hides errors.

## Open questions

Whether the OCR engine should warm up eagerly at server start is unresolved. Doing so moves the
20-second model load off the first page open and into startup. That is better if the user always
opens a page, and worse if they do not.

Whether `pdomain-book-tools` should take a callback or emit structured events is also unresolved.
That is the first thing to settle with that repo, since the stage granularity here depends on it.
