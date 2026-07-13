---
kind: usage
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-07-13
---

# Quickstart

How to install and run `pdomain-ocr-labeler-spa`.

---

## Install

The app ships as a single Python wheel. Install it with `uv` or `pip`:

```sh
# From the self-hosted index
uv tool install pdomain-ocr-labeler-spa \
  --index https://pdomain.github.io/pdomain-index-pip/simple/ \
  --index-strategy unsafe-best-match
```

Or, from a locally built wheel:

```sh
uv tool install dist/pdomain_ocr_labeler_spa-*.whl
```

The wheel includes the pre-built React SPA; no Node or npm is needed at
install time.

---

## Run

```sh
pdomain-ocr-labeler-ui
```

The server starts, prints its listen address, and opens a browser tab.

**Default:** `http://127.0.0.1:8080`

If port 8080 is in use the server auto-selects the next free port and prints
a notice (`Port 8080 in use - starting on port NNNN`).
(`src/pdomain_ocr_labeler_spa/__main__.py:314-326`, source-checked 2026-06-01)

---

## Point at a book directory

From the browser, use the project picker to select the directory that contains
your book's page images and OCR data. The book directory is the one that holds
subfolders like `page-images/` or an existing `session_state.json`.

Alternatively, pass the directory on the command line:

```sh
pdomain-ocr-labeler-ui /path/to/your/book
```

This loads the book immediately, bypassing the project picker.

---

## Key flags

| Flag | Effect |
|------|--------|
| `--port PORT` | Bind to a specific port instead of auto-selecting from 8080 |
| `--host HOST` | Bind to a specific interface (default `127.0.0.1`) |
| `--no-browser` | Suppress automatic browser tab |
| `--data-root PATH` | Override the default data root |

All flags are also readable from environment variables with the `PDLABELER_`
prefix.

---

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PDLABELER_HOST` | `127.0.0.1` | Bind host |
| `PDLABELER_PORT` | next free from 8080 | Bind port |
| `PDLABELER_DATA_ROOT` | `~/pdomain-ocr-labeler-spa` | Data root for projects |
| `PDLABELER_SOURCE_PROJECTS_ROOT` | (none) | Root whose subdirectories appear as selectable projects |

(`src/pdomain_ocr_labeler_spa/settings.py:47-78`, source-checked 2026-06-01)

---

## Console entry points

The wheel installs two commands:
(`pyproject.toml:46-48`, source-checked 2026-06-01)

- `pdomain-ocr-labeler-ui` - starts the server (described above).
- `pdomain-ocr-labeler-spa-export` - headless export CLI; run with `--help` for
  usage.

---

## Developer setup

For local development (editable install, HMR, tests) see
[`docs/runbooks/local-dev.md`](../runbooks/local-dev.md).
