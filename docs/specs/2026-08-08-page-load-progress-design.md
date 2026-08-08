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
| Building the doctr predictor | 26.22s | once per predictor-cache key |
| One page's OCR pass, predictor warm | 3s to 17s | once per page, per store miss |

A first page open therefore costs about 33 seconds. Later pages vary widely. One run of five
consecutive uncached pages gave 22.17s, 3.08s, 3.76s, 9.98s, and 9.91s, where the first figure
includes the predictor build. An earlier run on the same machine gave 30.18s, 17.06s, and 13.26s.
That spread matters for the design: the cost of a single warm page is not predictable in advance.

The predictor build is not a download. Measured in isolation with both weight files already on
disk, at 102 MB for `db_resnet50` and 63 MB for `crnn_vgg16_bn` under `~/.cache/doctr/models`, the
build still took 26.22s. Importing torch accounted for 3.59s and initialising the CUDA context for
0.28s. The remaining time is deserialising the weights, constructing the model graph, and moving it
to the device. A first-ever run pays a download on top of this, but a warm cache does not avoid the
cost.

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
   ground truth, opening the event store. This one needs a label, not a job. Measured on
   2026-08-08, `POST /api/projects/load` took 12ms to 76ms on an 8-page book and 14ms to 81ms on a
   synthetic 500-page book, so it does not scale with page count in any way a user notices.
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
latency. Only a genuine miss, the case that would have blocked for seconds to half a minute, creates
a job and returns a pending record with a job id. The SPA then subscribes to the stream it already
consumes and renders the stages above.

A job here does not mean the work moves to the background and the user carries on elsewhere. The
page view still waits, because there is nothing to show until the words arrive. The job exists so
the wait can be described, not so it can be dismissed. What changes is that the waiting is confined
to the page region instead of the whole app.

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

Create a job only when the work is known to be slow. That rule has a reliable trigger here, which is
why the design works: a store miss means OCR must run, and OCR is the multi-second cost. A hit means
the answer is already in hand. Nothing has to guess or predict a duration.

Do not branch further than that. It is tempting to skip the job when the predictor is already warm
and the device is a GPU, on the theory that one page is then fast enough to just block. The
measurements do not support it. Warm GPU pages ranged from 3.08s to 17.06s on the same machine and
the same book, so the fast case is neither fast enough to hide nor predictable enough to bet on. A
job costs milliseconds against a floor of three seconds, and a second code path costs a permanent
maintenance burden plus a class of bug that only appears on slow hardware.

The device and predictor state still matter, but as content rather than control flow. Report them.
"Loading the OCR model, about 25 seconds" and "Running OCR on page 4" are different messages, and
"Running on CPU" explains a wait that "Running OCR" does not. That is a display decision the SPA
makes from the reported stage, not a branch the backend takes.

Project open does not meet that bar and should not get a job. `POST /api/projects/load` measured
12ms to 76ms on an 8-page book and 14ms to 81ms on a synthetic 500-page book. Wrapping that in a job
would add machinery, a round trip, and a stream subscription to work that finishes faster than the
subscription is set up.

The mislabelling is the actual defect for stage 1. The SPA shows "Loading project" from
`BusyOverlay` and `ProjectRouteGate` while the page fetch is what blocks. In the reproduction on
2026-08-08 the load call returned in the same second it started, and the following 33 seconds were
the page request. So a user watching "Loading project" for half a minute is reading a message about
a step that finished immediately. Naming the real stage fixes most of the confusion before any job
work lands.

## Coordination with the sibling libraries

Only one stage needs something this repo does not already have. The device information turned out to
be available; the OCR progress hook is not.

### pdomain-book-tools

`Document.from_image_ocr_via_doctr` takes no progress callback today, and neither does the default
predictor construction behind `get_default_doctr_predictor`. Stage 2 and stage 4 both need a hook
there.

The minimum useful addition is an optional callback invoked at stage boundaries: weights resolved,
detection model ready, recognition model ready, OCR pass starting, OCR pass complete. Without it,
the labeler can only report "preparing the OCR engine" as one opaque 26-second block, because the
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

## Where each status appears

These are two different waits and they belong in two different places.

Project open is a whole-view wait, and it is over in milliseconds. It keeps the existing overlay
treatment. Nothing about it needs to change except that it should stop claiming the page-load time
as its own.

First-page OCR is a region wait. The project is open by then, so the shell should render and be
usable: the rail, header, page list, and panels are all backed by data that has already arrived.
Only the page view is waiting. Put the OCR status there, in the canvas region, and leave the rest
of the app interactive.

That distinction is not only cosmetic. During a 13-to-30-second OCR pass a user can reasonably want
to scan the page list, change the OCR config, or switch to a page whose results are already stored.
A full-view overlay blocks all of it for no reason, since the only thing actually unavailable is one
page's words.

## Acceptance criteria

- Opening a page that needs OCR shows a named stage within one second, not a bare spinner.
- The stage text changes as the work moves between model load, store lookup, and OCR.
- A store miss is visible as its own stage, so the wait is explained rather than mysterious.
- An OCR failure reaches the screen with its error, and is distinguishable from a page with no text.
- A page served from a warm store still returns immediately, with no added latency from the
  progress machinery, and creates no job.
- Project open creates no job, and its overlay clears as soon as the project data arrives rather
  than persisting through the page fetch.
- While a page is being OCR'd, the OCR status sits in the page region and the rest of the shell
  stays interactive.

## Non-goals

Making OCR faster is out of scope. The measured costs are the cost of the models on this hardware,
and this spec only makes them legible.

Replacing the job system or the event stream is out of scope. The recommendation is to use both.

Redesigning the empty-page rendering is out of scope beyond the failure case, which has to change
because it currently hides errors.

## Open questions

Whether the OCR engine should warm up eagerly at server start is unresolved. Doing so moves the
26-second predictor build off the first page open and into startup. That is better if the user always
opens a page, and worse if they do not.

Whether `pdomain-book-tools` should take a callback or emit structured events is also unresolved.
That is the first thing to settle with that repo, since the stage granularity here depends on it.
