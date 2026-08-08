---
kind: issue
status: active
owner: maintainers
created: 2026-08-08
last_verified: 2026-08-08
level: I2
---

# `get_page` swallows loader failures and renders them as an empty page

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-08-08
- **Resolution:** Open
- **Severity:** Medium — a failed OCR run and a page with no text are indistinguishable on screen and in the log
- **Affected version:** 0.2.1.dev173+gf01249948
- **Read when:** a page renders empty for no apparent reason, or you are adding status reporting to the page-load path.
- **Search terms:** degrading to empty page_record, ensure_page_model, get_page,
  except Exception, silent failure, DEBUG log, empty page.
- **Relates to:**
  [`docs/specs/2026-08-08-page-load-progress-design.md`](../specs/2026-08-08-page-load-progress-design.md)

## Summary

`get_page` wraps its `ensure_page_model` call in a bare `except Exception`, logs at DEBUG,
and returns an empty page record. The comment says this degrades gracefully so the SPA can
still show the image and let the user trigger Reload OCR by hand.

In practice the DEBUG line never reaches an operator, so the degrade is silent. A genuine
OCR failure and a page that legitimately has no text produce the same screen and the same
log output.

## Outcome / acceptance criteria

- A loader failure is visible at a level an operator sees by default, without needing to
  reproduce under a debug flag.
- The response distinguishes "OCR failed" from "OCR ran and found no text", so the SPA can
  tell the user which happened.
- A page that genuinely has no text still renders without an error.

## Evidence — reproduction & diagnosis

### 1. The handler catches everything and logs below the default level

`src/pdomain_ocr_labeler_spa/api/pages.py:822-838` catches `Exception`, calls `log.debug`
with `exc_info=True`, and falls through to build a payload from the empty page record.

### 2. The DEBUG line does not appear in practice

Running the server with `-v`, which the CLI documents as "DEBUG app", produced zero DEBUG
lines:

```
$ pdomain-ocr-labeler-ui --no-browser --port 8081 -v --data-root <tmp>
$ grep -c '\[DEBUG\]' dbg.log
0
```

So the one record of the failure is not emitted at the verbosity an operator would
reasonably use to investigate.

### 3. The two outcomes are already indistinguishable downstream

A page whose OCR produced nothing returns `page_text_ocr: ''` with zero line matches. The
degrade path returns the same shape. Nothing in the payload separates them.

## What is NOT broken (to scope the fix)

- OCR itself runs and completes. Later-page loads on a clean store measured 30.18s, 17.06s,
  and 13.26s, with `source: 'ocr'` on the resulting record.
- Empty text on the exercise fixtures is correct output. Those images are near-blank, so
  zero words is the right answer for them.
- `auto_rotate` is not implicated. This repo passes `auto_rotate=False` explicitly at
  `adapters/ocr/local_doctr.py:454`, so a page is a single OCR pass.

## Root-cause hypotheses (ranked)

1. **(Most likely) The log level is wrong for the event.** A loader failure is not routine.
   The comment's stated reason for DEBUG is keeping test noise low, which is a test concern
   solved better by a fixture than by hiding a production signal.
2. **The payload has no field for the distinction.** Even at the right log level, the SPA
   cannot show the user anything, because the response shape carries no failure marker.
   Both probably need fixing.

## Dependencies

Shares surface with [`docs/specs/2026-08-08-page-load-progress-design.md`](../specs/2026-08-08-page-load-progress-design.md),
whose failure stage depends on this being fixed. That spec should not be implemented on top
of the current silent degrade.

## Next steps

1. Raise the log level for a genuine loader failure, and keep test noise down with a fixture
   rather than the level.
2. Add a failure marker to the page payload so the SPA can distinguish the two cases.
3. Cover both paths with a test: a loader that raises, and a loader that returns no words.

## Resolution

_Open._
