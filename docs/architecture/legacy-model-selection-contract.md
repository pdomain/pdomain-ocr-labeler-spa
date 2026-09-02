---
Status: active
Owner: CT
Created: 2026-09-02
Last verified: 2026-09-02
Kind: architecture
---

# Legacy model-selection behaviour, captured

## Agent Index

- **Kind:** architecture
- **Status:** active
- **Owner:** CT
- **Last verified:** 2026-09-02
- **Read when:** changing model discovery, the Hugging Face probe, or the trainer weights root.
- **Search terms:** model selection, hf probe, last modified, model store dirname, pd-ml-models.

## Why this exists

Several modules here cite `pd_ocr_labeler/operations/ocr/model_selection_operations.py` by line
number as their source of truth. That repository is being retired, so the behaviour they depend on
is recorded here.

Captured from `pd-ocr-labeler` at commit `ce4d8ef` on 2026-09-02, from
`pd_ocr_labeler/operations/ocr/model_selection_operations.py`.

## The weights root is a rename, not a mirror

The legacy directory name was `pd-ml-models`. This repository uses `pdomain-ml-models`.

That difference is deliberate and it matters. Anything describing the current constant as a mirror
of the legacy one is wrong, and acting on that description would point discovery at a directory the
trainer does not write.

The path construction is otherwise unchanged and is OS-aware. On Linux it is `XDG_DATA_HOME` when
set, else `~/.local/share`. On macOS it is `~/Library/Application Support`. On Windows it is
`APPDATA` when set, else `~/AppData/Roaming`. Anything else falls back to `~/.local/share`. The
directory name is appended to that base.

## The Hugging Face probe never raises

`fetch_hf_last_modified` returns the published model's last-modified timestamp, or `None`. It
returns `None` in three cases: `huggingface_hub` is not installed, the call to `model_info` fails
for any reason including an unreachable network, or the repository carries no `last_modified`
metadata. It logs and swallows every exception rather than propagating one.

A naive timestamp is treated as UTC. When `last_modified` is a `datetime` with no `tzinfo`, the
legacy code stamps `UTC` onto it before returning. A caller comparing this value against an
aware timestamp depends on that.

The default timeout is 5 seconds and the revision defaults to the repository's main branch.

## Keys and labels

The legacy selection keys were `default` for the built-in DocTR fallback, `huggingface` for the
latest published model, and `huggingface@` as the prefix for a pinned revision.

The built-in option was labelled `Built-in DocTR (stock Mindee fallback)`, and the latest Hugging
Face option `Hugging Face: {repo} (latest)`.

Profiles named `all` or `base-ocr` were both treated as the preferred profile, which is the same
pair of names `pd-ocr-trainer` used for its base profile before and after its own migration.

A trailing ten-digit run of characters in a name was recognised as a timestamp suffix.
