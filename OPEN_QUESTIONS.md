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
| Q-A4 | Legacy URL redirect status | (A) `301 Moved Permanently` — SPA routes are GET, broadest client support (resolved 2026-05-07) | [D-035](specs/17-decisions.md) |
| Q-A8 | Frontend toolchain | mise installed; Node 24 from `mise.toml`. `mise install` + `npm ci` is canonical. Supersedes ghcr.io devcontainer-feature suggestion (resolved 2026-05-07) | [D-036](specs/17-decisions.md) |
| Q-A9 | ESLint config shape | (A) flat `eslint.config.ts` + typescript-eslint v8 + `@vitejs/plugin-react` recommended (resolved 2026-05-07) | [D-037](specs/17-decisions.md) |
| Q-A10 | PyPI publishing | (A) defer; ship via GitHub Releases + future pd-index PEP 503 index; no `PYPI_TOKEN` (resolved 2026-05-07) | [D-038](specs/17-decisions.md) |

### Delegations to peer-repo agents (2026-05-06)

- **pgdp-prep:** roadmap entry "Adopt shadcn/ui + Radix" added to
  `pd-prep-for-pgdp/docs/08-roadmap.md` (P2 — Frontend polish, item 13a).
- **pd-book-tools:** roadmap entries for `bbox.refine_robust(...)` and
  `pd_book_tools.text.normalize` — *delegated, agent running*.
- **pd-ocr-cli:** roadmap entry "Output normalization (post-OCR)" added
  to `pd-ocr-cli/docs/usage.md` § Text normalization.
