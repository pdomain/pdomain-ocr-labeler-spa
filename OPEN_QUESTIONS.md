# Open Questions for `pd-ocr-labeler-spa`

Questions the spec authors could not resolve from the source material
alone. Each entry: **Q** (the question), **Context** (why it matters),
**Options** (with trade-offs), **Recommendation** (spec author's bet),
**Blocks** (which milestones can't start until resolved), and once
the user has answered, a **Resolution** line linking the resulting ADR.

> **2026-05-06:** All initial Q1–Q20 resolved by user. New sub-blockers
> Q-A1 through Q-A4 surfaced and listed below; the rest is in the
> Resolution log at the bottom.

---

## Open — needs user input

### Q-A4. Q19 redirect status code?

**Context.** D-030 introduces 301 redirects from `/project/{id}` to
`/projects/{id}`. Should it be `301 Moved Permanently` or
`308 Permanent Redirect`?

**Options.**

- **(A)** `301`. Browsers fully understand. Older clients may
  downgrade method to GET on POST redirects (irrelevant — these
  routes are GET-only SPA paths).
- **(B)** `308`. Preserves method strictly. Modern; some older
  clients don't honour.

**Recommendation.** **(A)**. SPA routes are always GET; method
preservation isn't a concern; `301` has the broadest support.

**Blocks.** [`13-driver-contract.md`](specs/13-driver-contract.md) §1.

---

### Q-A8. Frontend toolchain availability in dev shell

**Context.** Iteration 2 of the dev /loop scaffolded
`frontend/` (package.json, tsconfig, vite/vitest configs, App.tsx,
smoke test) but could not run `npm install` or `npx vitest` — neither
`node` nor `npm` is on PATH in the current devcontainer. mise (which
the spec/`mise.toml` plan would pin Node 24 via) is also not installed.

This blocks the M0 acceptance gate clause "frontend `make
frontend-install` and `make frontend-test` succeed" — the files are
in place but unverified end-to-end.

**Options.**

- **(A)** Install Node 24 + mise into the devcontainer image (modify
  `.devcontainer/Dockerfile` upstream of this repo) and re-run
  `npm install` + `vitest run` from a follow-up iteration.
- **(B)** Add a one-shot bootstrap script (e.g. `make
  frontend-install` calls `corepack enable && corepack prepare
  pnpm@latest --activate` after a manual node install) and document
  the prerequisite in `DEVELOPMENT.md`.
- **(C)** Defer to whichever iteration first lands `mise.toml` +
  Makefile (planned M0 sub-task) and verify there.

**Recommendation.** **(C)** — the next iteration that authors
`mise.toml` + Makefile is the natural place to also `mise install`
and verify `vitest run`. Until then the scaffold compiles by
inspection (mirrors pgdp-prep's working setup) but is not
runtime-verified.

**Iter 3 update (2026-05-06).** `mise.toml` (Node 24, Python 3.13)
and `Makefile` (mirrors pd-prep-for-pgdp targets) are now in place.
The Makefile's `_npm` macro tries `mise exec` then PATH `npm`, and
fails with a clear error otherwise — so `make frontend-install`
gives an actionable message in the current devcontainer rather than
an opaque shell error. **Still unverified end-to-end:** the
devcontainer has neither `node`/`npm` nor a pre-installed `mise`
binary (`/home/vscode/.local/bin/mise` does not exist), and
`make mise-setup` (which downloads mise) requires outbound network
that may not be available from /loop iterations. Resolution path:
either (1) run `make mise-setup && make frontend-install` from an
interactive shell where network is allowed, or (2) add the
`ghcr.io/devcontainers/features/node:1` feature to
`/workspaces/ocr-container/.devcontainer/devcontainer.json` (which
is **outside this repo's edit boundary** — must be done by the
workspace owner, not this agent).

**Blocks.** M0 acceptance gate clause for frontend tests. (Numbered
Q-A8 to avoid colliding with reserved Q-A5/A6/A7 in the M11 glyph
annotations milestone.)

---

### Q-A9. ESLint flavor + config shape for the SPA frontend

**Filed.** 2026-05-06 (iter 8, in conjunction with B-05 fix).

**Context.** B-05 (iter 5 review) flagged the dangling
`"lint": "eslint . --ext .ts,.tsx"` script in
`frontend/package.json` — the script was declared but `eslint` was
not in `devDependencies`. Iter 8 fixed B-05 by **dropping the
script entirely** rather than picking an ESLint configuration
unilaterally. `specs/16-milestones.md:51` lists `eslint.config.ts`
as an M0 file (still pending) and `specs/16-milestones.md:85`
includes "ESLint and ruff pass clean" in the M0 acceptance gate, so
the script must come back before M0 closes. The peer
`pd-prep-for-pgdp/frontend/package.json` has the **same dangling
script** and no eslint installed — i.e. the peer doesn't resolve
this question for us.

**Question.** When ESLint lands, which config shape do we adopt?
- (A) Flat config (`eslint.config.ts`) with the
  `typescript-eslint` v8 + `@vitejs/plugin-react` recommended
  presets and Vite/React 19 defaults. (Spec wording matches.)
- (B) Legacy `.eslintrc.cjs` for parity with whatever the
  workspace owner runs in other projects (pgdp-prep doesn't have
  one, so this is a guess).
- (C) Skip ESLint entirely; rely on `tsc -b` + Prettier-via-ruff
  parity. Would require updating `specs/16-milestones.md:85` to
  drop the ESLint clause.

**Resolution path.** Pick (A) by default — spec already names
`eslint.config.ts`. Land the config + devDeps + restore the `lint`
script in a single iteration so the regression test in
`tests/unit/test_frontend_config.py` can flip from "if lint exists
then eslint must be installed" to "lint must exist".

**Blocks.** M0 acceptance gate clause "ESLint passes clean".

### Q-A10. PyPI publishing for `pd-ocr-labeler-spa`?

**Context.** Iter 24 landed `.github/workflows/release.yml`, which on
`v*` tag push builds the wheel + sdist and attaches both to the
GitHub Release. `install.sh`/`install.ps1` already download from
that Release, so publish-to-Release is sufficient for the install
flow. PyPI publishing is intentionally **not** wired — it would
either require a `PYPI_TOKEN` repo secret (footgun: long-lived
credential, easy to leak) or an OIDC trusted-publisher setup on
PyPI (one-time configuration on the user's PyPI account).

**Options.**

- **(A)** Skip PyPI entirely. Ship from GitHub Releases only.
  Mirrors current peer pd-prep-for-pgdp behaviour. Zero secrets.
- **(B)** Add OIDC trusted publishing via
  `pypa/gh-action-pypi-publish` (requires the user to register the
  workflow on PyPI as a trusted publisher; no token in repo). Adds
  `permissions: id-token: write` to the workflow.
- **(C)** Token-based PyPI publish. **Rejected** — the release-
  workflow tests in `test_release_workflow.py` actively forbid
  `PYPI_TOKEN` / `secrets.PYPI*` references.

**Recommendation.** **(A)** for now. Defer **(B)** until the
project has a tagged 0.1.0 release worth publishing.

**Blocks.** Nothing in M0–M9. Pure distribution-channel question.

---

### Q-A11 — 500 traceback in client `details`: keep verbatim pgdp-prep parity, or redact?

**Filed.** 2026-05-06 (iter-40 review checkpoint, B-51).

**Background.** Spec §8 says the `Exception` catch-all returns `{error:
"internal_error", message: str(exc), details: <last 3 traceback lines>}`.
The labeler's M1.c `error_handler.py` ports this verbatim from
pgdp-prep. The iter-40 review confirmed by live `TestClient` probe that
`raise RuntimeError('boom-secret')` lands `'boom-secret'` (a string
literal embedded in the source line) verbatim in the client's
`details`. The spec contains no security guidance; the iter-38 commit
message simultaneously claims the design is "security: don't help a
probe map our internals" — contradictory with the implementation.

**Choice.**

- **(A) Keep verbatim parity with pgdp-prep.** The labeler is single-
  user-on-laptop in v1; pgdp-prep itself ships this behaviour
  unchanged; debug-from-browser-console is the explicit operator UX.
  Update the iter-38 commit-message claim to match (drop the security
  framing).
- **(B) Redact in v1, debug-flag in dev.** Add
  `Settings.debug_unhandled_traceback: bool = True` (default on for
  local labeler). When `False`, emit `{error: "internal_error",
  message: "internal server error", details: null}` to the client
  while still logging the full traceback server-side via
  `logger.exception`. Spec §8 grows a security clause referencing this
  flag.
- **(C) Always redact.** Drop the `details` traceback entirely; trust
  the server-side log + `X-Request-ID` correlation as the operator
  triage path.

**Recommendation.** **(B)**. Keeps v1 ergonomics for the labeler's
single-user case, gives a knob deployments can flip, and aligns spec
§8 with explicit guidance instead of leaving security implicit.

**Blocks.** B-51 closeout. The pgdp-prep agent should be polled in
parallel — if pgdp-prep adopts (B), labeler-spa stays parity. If
pgdp-prep diverges, labeler-spa picks independently.

---

### Q-A12 — `session_state.json` extras-tolerance policy under D-003

**Filed.** 2026-05-07 (iter-45 review checkpoint, B-58).

**Background.** `core/persistence/session_state.py` (iter 44) sets
`SessionState.model_config = ConfigDict(extra="forbid")`, citing
`specs/09-persistence.md §11`. But §11 specifically discusses
`UserPageEnvelope` (a versioned envelope where `extra="forbid"` plus
the schema-version gate is the deliberate forward-compat circuit-
breaker). Spec §6 (`session_state.json`) does NOT specify forbid; it
just lists the three keys. The legacy
`pd-ocr-labeler/operations/persistence/session_state_operations.py:30-37`
uses `from_dict` with `data.get(...)` for each known key — i.e.
**silently ignores** any extra fields. Under D-003 (shared data root),
both binaries read+write the same file. If the legacy ever adds an
additive field (`last_window_geometry`, etc.), the SPA's strict
`extra="forbid"` envelope would reject it, `load_session_state` would
return `None`, and the user's last session would silently disappear.

**Choice.**

- **(A) Switch to `extra="ignore"`.** Match legacy `from_dict`'s
  silent-drop behaviour. Log dropped keys at `info` so a legacy
  schema bump is at least visible to the operator. Amend spec §6 to
  state explicitly: "Readers MUST tolerate unknown keys per the
  D-003 forward-compat contract." This is the recommended default
  for shared-file scenarios; `UserPageEnvelope`'s strict policy is
  the exception, justified by its versioned schema.
- **(B) Keep `extra="forbid"`.** Strictness matches the spec §11
  envelope policy. Trade-off: schema drift is loud (good for
  catching legacy bugs early), but the user-visible cost is "lost
  session on first run after legacy adds a field." Would need spec
  §6 to add an explicit "MUST forbid extras" clause and a D-003
  caveat that legacy upgrades require a coordinated SPA upgrade.
- **(C) Per-binary version negotiation via `schema_version`.**
  Heavyweight. Treat extras as forbid but accept any
  `schema_version` ≤ the SPA's known maximum, dropping fields
  introduced after that version. Doesn't fit a single-string-version
  schema and would require coordinating with legacy to bump the
  version on every additive field.

**Recommendation.** **(A)**. The legacy already does silent-drop;
matching it under D-003 is the path of least surprise. The "drift
catcher" argument behind (B) is better served by the optional `info`
log when extras are dropped — that's still visible without breaking
the user.

**Blocks.** B-58 closeout. Iter 46 should pick this and pair the spec
amendment with the one-line code change.

---

### Q-A13 — `--log-level` CLI flag: which Settings field does it touch?

**Filed.** 2026-05-07 (iter-47, M1.g `__main__` CLI wiring).

**Background.** Iter 47's M1.g task (per the user's directive) called for
`--log-level` alongside `--host`, `--port`, `--reload`, `--data-root`.
Spec `02-backend.md §3` only declares `log_format: Literal["plain",
"json"]` and `request_id_header: str` — there is no `log_level` field.
Legacy `pd-ocr-labeler/cli.py:50-56` uses `-v/--verbose` (count) and
maps that to root/dependency log levels in `get_logging_configuration`
— it doesn't have a `--log-level` either. pgdp-prep's `__main__.py`
also doesn't have `--log-level`.

The spec-aligned legacy-parity flag is **`-v/--verbose`** (count, 0–3),
which iter 47 wired. But the user named `--log-level` directly, which
suggests one of three possible intents:

**Choice.**

- **(A) Add a new `Settings.log_level: Literal["debug", "info",
  "warning", "error", "critical"]` field**, mappable from `--log-level`
  in `__main__`. Pro: explicit, matches `uvicorn --log-level`'s shape.
  Con: redundant with `-v/--verbose`'s legacy mapping; would need spec
  §3 to grow a new field; opens "is this the python `logging` module
  level or the uvicorn access-log level?" ambiguity.
- **(B) Treat `--log-level` as an alias for `-v` count.** `--log-level
  debug` → `verbose=1`, `info` → `0`, etc. Pro: no new Settings field;
  preserves the legacy verbosity-count mapping. Con: surprising —
  `--log-level critical` mapping to `verbose=-1` doesn't make sense.
- **(C) Treat `--log-level` as a uvicorn-only knob.** Threaded into
  `uvicorn.run(log_level=...)` directly, never touching Settings. Pro:
  matches uvicorn's CLI surface 1:1; doesn't pollute Settings. Con:
  doesn't drive the application logger (only uvicorn's), so a user
  passing `--log-level debug` wouldn't see app-level DEBUG logs.
- **(D) Drop `--log-level` from the M1.g surface.** Iter 47 wired `-v`
  per spec §15 §3 and that's the spec-canonical knob. The user's ask
  for `--log-level` was a generic flag-set sketch, not a binding spec
  requirement. Document the alias rationale in `__main__.py`'s
  docstring and call it done.

**Recommendation.** **(D)**. The spec already names `-v/--verbose`
(count) as the verbosity knob; adding `--log-level` would either
duplicate that surface or grow Settings without a clear consumer.
Deferral keeps the flag set spec-aligned. If a real consumer surfaces
later (e.g. a deployment doc that specifies `--log-level` literally),
revisit then with a concrete shape.

**Status as of iter 47.** Q-A13 filed; `--log-level` NOT wired in
M1.g. The `-v/--verbose` flag IS wired in the parser (consumer not
yet routed; lands in a future iter that wires the verbosity →
logging-level mapping per legacy `cli.py:65-170`).

**Blocks.** Nothing today (M1.g shipped without `--log-level`).
Resolving Q-A13 in any direction other than (D) would re-open a one-
line patch to the M1.g `__main__.py` flag set.

---

## Resolution log

All initial questions resolved by user on 2026-05-06. Decisions live
in [`specs/17-decisions.md`](specs/17-decisions.md).

| Q | Topic | User's answer | ADR |
|---|---|---|---|
| Q1 | Co-existence with legacy data root | (A) during dev; (C) at GA | [D-003](specs/17-decisions.md) |
| Q2 | Auth seam | (B) `none` only for v1, plan to ship full triplet later | [D-005](specs/17-decisions.md) |
| Q3 | SSE vs polling for jobs | (C) hybrid sync + SSE | [D-006](specs/17-decisions.md) |
| Q4 | OCR adapter axis | **(B)** full adapter axis like pgdp-prep | [D-018](specs/17-decisions.md) |
| Q5 | Image cache HTTP serving | (B) IStorage adapter; S3 NotImplemented | [D-019](specs/17-decisions.md) |
| Q6 | Konva vs raw canvas | (B) raw canvas, but defer final choice to M4 research | [D-020](specs/17-decisions.md) |
| Q7 | Word-match virtualisation | (B) virtualise + filter | [D-007 follow-up](specs/17-decisions.md) |
| Q8 | CodeMirror vs textarea | (B) textarea | [D-008](specs/17-decisions.md) |
| Q9 | UI prefs persistence | (B) localStorage; per-user later | [D-021](specs/17-decisions.md) |
| Q10 | Hotkey scope | (B) wishlist + "full keyboard editing" milestone | [D-022](specs/17-decisions.md) |
| Q11 | Multi-tab races | (A) last-writer-wins; optimistic locking later | [D-023](specs/17-decisions.md) |
| Q12 | shadcn/ui adoption | (B) adopt; delegate pgdp-prep doc update | [D-004](specs/17-decisions.md) (delegated 2026-05-06) |
| Q13 | pd-png-optimizer dep | No, not used | [D-024](specs/17-decisions.md) |
| Q14 | Ligature/long-s normalization | Configurable, default Unicode glyphs; design lives in pd-book-tools | [D-025](specs/17-decisions.md) (delegated 2026-05-06) |
| Q15 | Refine-bbox refactor | (A) for v1, (B) on pd-book-tools roadmap | [D-026](specs/17-decisions.md) (delegated 2026-05-06) |
| Q16 | Export bundling | (C) same wheel + jobs runner | [D-027](specs/17-decisions.md) |
| Q17 | Devcontainer | Makefile is canonical; devcontainer optional | [D-028](specs/17-decisions.md) |
| Q18 | Auto-rotation | (B) AND (C) with GT-best-match heuristic | [D-029](specs/17-decisions.md) |
| Q19 | URL grammar | pgdp-prep style with `index/{idx0}` and `pageno/{n}` sub-routes + 301 redirect from legacy | [D-030](specs/17-decisions.md) |
| Q20 | Auto-open browser | (C) auto-open with `--no-browser` opt-out | [D-031](specs/17-decisions.md) |
| Q-A1 | Auto-rotation envelope bump | (A) v2.2 additive (`source.rotation_degrees`/`rotation_source`); fall back to (B) sidecar if legacy `Source` rejects extras (resolved 2026-05-07) | [D-032](specs/17-decisions.md) |
| Q-A2 | Q14 normalization toggle scope | (A) project-level checkbox in OCR config modal, persisted in `OCRConfig` (resolved 2026-05-07) | [D-033](specs/17-decisions.md) |
| Q-A3 | Rotation indicator UI placement | (B) separate badge next to source pill + tooltip showing source; manual-rotate button also gets a state tooltip (resolved 2026-05-07) | [D-034](specs/17-decisions.md) |

### Delegations to peer-repo agents (2026-05-06)

- **pgdp-prep:** roadmap entry "Adopt shadcn/ui + Radix" added to
  `pd-prep-for-pgdp/docs/08-roadmap.md` (P2 — Frontend polish, item 13a).
- **pd-book-tools:** roadmap entries for `bbox.refine_robust(...)` and
  `pd_book_tools.text.normalize` — *delegated, agent running*.
- **pd-ocr-cli:** roadmap entry "Output normalization (post-OCR)" added
  to `pd-ocr-cli/docs/usage.md` § Text normalization.
