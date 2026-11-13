---
kind: usage
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-11-13
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

When no port is explicitly set, a busy 8080 triggers the next-free-port scan and a notice.
A busy port explicitly supplied by CLI or PDLABELER_PORT is an error. Valid explicit ports are 1–65535.
(`src/pdomain_ocr_labeler_spa/__main__.py:314-326`, source-checked 2026-06-01)

---

## Point at a book directory

Set the parent source folder with `--projects-root /path/to/books`, then select one of its book
subdirectories in the browser. A filesystem-image book has its `.png`, `.jpg` or `.jpeg` files directly
in that directory. A supported immutable book source has `book-labeling-manifest.json` or
`labeling-bundle.json`. `session_state.json` belongs under the application data root, not inside a book.

The optional positional directory sets startup carrier state; it does not establish a verified bypass
of the browser's project picker. Use the source-root setting and explicit project selection for the
documented path. Loads outside the effective source root are rejected.

## Key flags

| Flag | Effect |
|------|--------|
| `--port PORT` | Bind to a specific port instead of auto-selecting from 8080 |
| `--host HOST` | Bind to a specific interface (default `127.0.0.1`) |
| `--no-browser` | Suppress automatic browser tab |
| `--data-root PATH` | Override the default data root |
| `--projects-root PATH` | Parent directory whose subdirectories are selectable books |

Only Settings fields have environment counterparts. For example, `--projects-root` maps to
`PDLABELER_SOURCE_PROJECTS_ROOT`. `--no-browser` and `--reload` are CLI-only switches.

---

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PDLABELER_HOST` | `127.0.0.1` | Bind host |
| `PDLABELER_PORT` | next free from 8080 | Bind port |
| `PDLABELER_DATA_ROOT` | `${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa` (macOS: `~/Library/Application Support/pdomain-ocr-labeler-spa`; Windows: `%LOCALAPPDATA%/pdomain-ocr-labeler-spa`) | Data root for projects |
| `PDLABELER_SOURCE_PROJECTS_ROOT` | `<data_root>/labeler-books` | Books folder. When set, this overrides `config.yaml`. When unset, an absolute `source_projects_root` in `config.yaml` is used; otherwise `<data_root>/labeler-books`, created at startup if missing. The project menu lists the directories inside that folder. |

If you have an existing `~/pdomain-ocr-labeler-spa` from before this app adopted
OS-aware paths and the new default location doesn't exist yet, the SPA keeps using
that directory instead of starting empty, and says so at startup. See
`docs/architecture/01-data-models.md §5` and `docs/context/decisions.md` (BUG-SMOKE-3).

(`src/pdomain_ocr_labeler_spa/settings.py`, source-checked 2026-09-18)

---

## Console entry points

The wheel installs the UI, control CLI and export CLI:
(`pyproject.toml:46-48`, source-checked 2026-06-01)

- `pdomain-ocr-labeler-ui` - starts the server (described above).
- `pdomain-ocr-labeler-control` - control CLI; run with `--help` for usage.
- `pdomain-ocr-labeler-spa-export` - headless export CLI; run with `--help` for
  usage.

---

## Developer setup

For local development (editable install, HMR, tests) see
[`docs/runbooks/local-dev.md`](../runbooks/local-dev.md).
