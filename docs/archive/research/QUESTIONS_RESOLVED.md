# QUESTIONS_RESOLVED — archive of resolved spec questions

Resolved questions from [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md). Each
entry preserves the original **Filed** / **Background** / **Choice** /
**Recommendation** structure plus the user's **Resolution** and a link to the
landing ADR in `specs/17-decisions.md`.

The Resolution-log table at the bottom is the at-a-glance index; full entries
appear above for the questions where the spec authors needed to capture the
trade-off discussion.

Active (unanswered) questions live in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).

---

## Q-A5 — Does the legacy labeler tolerate a v2.2 `UserPageEnvelope` (with `glyph_annotations`)?

**Resolution.** 2026-05-11 — Option **(A)**: SPA writes v2.2 freely. The legacy
labeler uses hand-rolled `from_dict` (pure `data.get` — no Pydantic, no strict
validation). Extra/unknown fields are silently ignored. A v2.2 envelope is
loaded without error; the new fields are simply never accessed. **No
compatibility shim needed** for the read path. The write path would strip new
fields (legacy `to_dict` only emits the five fields it knows), which is
acceptable during the transition window. GitHub:
ConcaveTrillion/pdomain-ocr-labeler-spa#56 (closed).

---

## Q-A6 — Predictions-overlay ghost color on `<PageImageCanvas>`

**Resolution.** 2026-05-11 — Translucent blue (`#3B82F6` / Tailwind `blue-500`)
at 40% opacity, exposed as CSS custom property `--predictions-ghost-color` on
`:root` so operators can theme it without a code change. Spec updated:
`specs/20-glyph-annotations.md` §5.6. GitHub:
ConcaveTrillion/pdomain-ocr-labeler-spa#57 (closed).

---

## Q-A11 — 500 traceback in client `details`: keep verbatim pgdp-prep parity, or redact?

**Resolution.** 2026-05-07 — option **(B)**. Add
`Settings.debug_unhandled_traceback: bool = True` (default-on, env
`PDLABELER_DEBUG_UNHANDLED_TRACEBACK`). When `True` (single-user UX
default, current behaviour preserved) the 500 envelope's `details`
includes the last 3 traceback lines. When `False`, `details` is null /
absent and `message` becomes the redacted form; `logger.exception`
still fires server-side with the X-Request-ID correlation so triage
remains possible from server logs. **Implemented iter 53** (commit
`ef5908d`); B-51 closed. See
[D-040](../specs/17-decisions.md#d-040--unhandled-exception-traceback-disclosure-gated-by-debug_unhandled_traceback-flag).

**Original question for context:**

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

**Blocks.** B-51 — **closed iter 53** (commit `ef5908d`). The
pgdp-prep agent should be polled in parallel — if pgdp-prep adopts
(B), labeler-spa stays parity. If pgdp-prep diverges, labeler-spa
picks independently.

---

## Q-A12 — `session_state.json` extras-tolerance policy under D-003

**Resolution.** 2026-05-07 — option **(A) with WARNING-level drift
signal**. Switch `SessionState.model_config` to
`ConfigDict(extra="ignore")` to match legacy `from_dict` semantics
under D-003. Per the user's framing — "warning in log maybe and
possible *indication of library drift* in a release that shouldn't have
had it" — the dropped-keys log fires at **WARNING** (not `info`,
upgrading the recommendation in option A) with the stable grep-able
substring `session_state_extras_dropped` so a release-time CI gate or
operator can detect unintended SPA-vs-legacy schema drift. Spec §6
gains an explicit reader-tolerance clause; the deliberate asymmetry vs
spec §11 (`UserPageEnvelope` keeps `extra="forbid"`) is documented
because `UserPageEnvelope` has a versioned `schema_version` gate that
session_state.json does not. **Implemented commit `c10e914` (2026-05-07)**;
B-58 closed. See
[D-041](../specs/17-decisions.md#d-041--session_statejson-extras-tolerance-with-warning-level-drift-signal).

**Original question for context:**

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

**Blocks.** B-58 — closed commit `c10e914` (2026-05-07).

---

## Q-A14 — M4 renderer: must Konva be validated by spike before M4 starts?

**Filed.** 2026-05-11 (ConcaveTrillion/pdomain-ocr-labeler-spa#55).

**Background.** `docs/architecture/04-image-viewport.md` is written
against a Konva component tree, but D-020 left the renderer choice
deferred to a research spike "at the start of M4". The spike never
ran; `PageImageCanvas` and `BBoxOverlay` shipped as DOM stubs at
M4, accumulating "shipped" status while the actual implementation
stayed empty. The 2026-05-14 parity audit
([`docs/PARITY_GAPS_2026_05_14.md`](../PARITY_GAPS_2026_05_14.md))
forced the question to a head.

**Choice.**

- (A) Run the spike now — measure 4 K-page perf, commit to a
  renderer, then implement.
- (B) Commit to Konva without the spike — `WordImageCanvas`
  already proves Konva works at our scale; raw-canvas fallback is
  cost without benefit; ship the renderer and revisit only if a
  measured failure surfaces.

**Resolution.** **(B)** — D-043 commits to Konva. The
`use-image@^1.1` dep is added; `specs/21-konva-renderer.md` is the
implementation spec; D-020 is superseded.

**Refs.** [D-043](../../specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020),
[`specs/21-konva-renderer.md`](../../specs/21-konva-renderer.md),
[`docs/PARITY_GAPS_2026_05_14.md`](../PARITY_GAPS_2026_05_14.md).

**Status.** Resolved 2026-05-14.

---

## Q-A7 — Per-mark provenance: is object-level `source` granular enough?
> GitHub: ConcaveTrillion/pdomain-ocr-labeler-spa#58

**Q.** In v1, `GlyphAnnotations.source` is a single `Literal["human",
"predicted", "human_confirmed"]` field on the whole `GlyphAnnotations` object —
not per `LigatureMark`, not per `long_s_positions` entry. Is that granularity
sufficient, or do we need provenance at the individual mark level?

**Context.** `specs/20-glyph-annotations.md` §3 states: "Provenance is
per-`GlyphAnnotations` object in v1 (not per-mark). This keeps the model
simple; if mixed-source granularity is needed later, we bump again." A typical
mixed-source scenario: the classifier predicted 2 ligature marks correctly; the
human then manually added a third ligature mark and corrected a long-s position.
With object-level provenance, the whole `GlyphAnnotations` becomes `"human"`,
losing the fact that 2 marks were originally predicted. This is a schema design
decision that is hard to change post-M11 without a v2.3 envelope bump.

**Options.**

- **(A) Keep object-level provenance.** Accept the simplification for v1; spec
  explicitly plans "bump if needed."
- **(B) Per-mark provenance now.** Add `source` to `LigatureMark`, add
  `long_s_sources: list[Literal[...]]` parallel to `long_s_positions`, and add
  `swash_source`. More complex model, but avoids a future schema bump.
- **(C) Hybrid.** Keep `GlyphAnnotations.source` as the "dominant" signal, plus
  an optional `mark_sources: dict[int, Literal[...]]` escape hatch.

**Recommendation.** **(A)** — object-level is consistent with D-032 (rotation
provenance); the spec explicitly names the trade-off; a v2.3 bump is low-cost if
the need materializes.

**Blocks.** M11 data-model lock-in (`specs/16-milestones.md` §M11 pre-conditions).

**Owner.** CT.

**Resolution:** D-044 — object-level provenance adopted. See `specs/17-decisions.md`.
**Closed:** 2026-05-16

---

## Resolution log

All initial questions resolved by user on 2026-05-06; sub-questions
Q-A1..Q-A4 resolved 2026-05-07; Q-A8..Q-A13 resolved 2026-05-07.
Decisions live in [`../specs/17-decisions.md`](../specs/17-decisions.md).

| Q | Topic | User's answer | ADR |
|---|---|---|---|
| Q1 | Co-existence with legacy data root | (A) during dev; (C) at GA | [D-003](../specs/17-decisions.md) |
| Q2 | Auth seam | (B) `none` only for v1, plan to ship full triplet later | [D-005](../specs/17-decisions.md) |
| Q3 | SSE vs polling for jobs | (C) hybrid sync + SSE | [D-006](../specs/17-decisions.md) |
| Q4 | OCR adapter axis | **(B)** full adapter axis like pgdp-prep | [D-018](../specs/17-decisions.md) |
| Q5 | Image cache HTTP serving | (B) IStorage adapter; S3 NotImplemented | [D-019](../specs/17-decisions.md) |
| Q6 | Konva vs raw canvas | (B) raw canvas, but defer final choice to M4 research | [D-020](../specs/17-decisions.md) |
| Q7 | Word-match virtualisation | (B) virtualise + filter | [D-007 follow-up](../specs/17-decisions.md) |
| Q8 | CodeMirror vs textarea | (B) textarea | [D-008](../specs/17-decisions.md) |
| Q9 | UI prefs persistence | (B) localStorage; per-user later | [D-021](../specs/17-decisions.md) |
| Q10 | Hotkey scope | (B) wishlist + "full keyboard editing" milestone | [D-022](../specs/17-decisions.md) |
| Q11 | Multi-tab races | (A) last-writer-wins; optimistic locking later | [D-023](../specs/17-decisions.md) |
| Q12 | shadcn/ui adoption | (B) adopt; delegate pgdp-prep doc update | [D-004](../specs/17-decisions.md) (delegated 2026-05-06) |
| Q13 | pd-png-optimizer dep | No, not used | [D-024](../specs/17-decisions.md) |
| Q14 | Ligature/long-s normalization | Configurable, default Unicode glyphs; design lives in pdomain-book-tools | [D-025](../specs/17-decisions.md) (delegated 2026-05-06) |
| Q15 | Refine-bbox refactor | (A) for v1, (B) on pdomain-book-tools roadmap | [D-026](../specs/17-decisions.md) (delegated 2026-05-06) |
| Q16 | Export bundling | (C) same wheel + jobs runner | [D-027](../specs/17-decisions.md) |
| Q17 | Devcontainer | Makefile is canonical; devcontainer optional | [D-028](../specs/17-decisions.md) |
| Q18 | Auto-rotation | (B) AND (C) with GT-best-match heuristic | [D-029](../specs/17-decisions.md) |
| Q19 | URL grammar | pgdp-prep style with `index/{idx0}` and `pageno/{n}` sub-routes + 301 redirect from legacy | [D-030](../specs/17-decisions.md) |
| Q20 | Auto-open browser | (C) auto-open with `--no-browser` opt-out | [D-031](../specs/17-decisions.md) |
| Q-A1 | Auto-rotation envelope bump | (A) v2.2 additive (`source.rotation_degrees`/`rotation_source`); fall back to (B) sidecar if legacy `Source` rejects extras (resolved 2026-05-07) | [D-032](../specs/17-decisions.md) |
| Q-A2 | Q14 normalization toggle scope | (A) project-level checkbox in OCR config modal, persisted in `OCRConfig` (resolved 2026-05-07) | [D-033](../specs/17-decisions.md) |
| Q-A3 | Rotation indicator UI placement | (B) separate badge next to source pill + tooltip showing source; manual-rotate button also gets a state tooltip (resolved 2026-05-07) | [D-034](../specs/17-decisions.md) |
| Q-A4 | Legacy URL redirect status | (A) `301 Moved Permanently` — SPA routes are GET, broadest client support (resolved 2026-05-07) | [D-035](../specs/17-decisions.md) |
| Q-A8 | Frontend toolchain | mise installed; Node 24 from `mise.toml`. `mise install` + `npm ci` is canonical. Supersedes ghcr.io devcontainer-feature suggestion (resolved 2026-05-07) | [D-036](../specs/17-decisions.md) |
| Q-A9 | ESLint config shape | (A) flat `eslint.config.ts` + typescript-eslint v8 + `@vitejs/plugin-react` recommended (resolved 2026-05-07) | [D-037](../specs/17-decisions.md) |
| Q-A10 | PyPI publishing | (A) defer; ship via GitHub Releases + future pd-index PEP 503 index; no `PYPI_TOKEN` (resolved 2026-05-07) | [D-038](../specs/17-decisions.md) |
| Q-A13 | `--log-level` CLI flag | (D) drop it; `-v/--verbose` (count) is spec-canonical and matches legacy (resolved 2026-05-07) | [D-039](../specs/17-decisions.md) |
| Q-A11 | 500 traceback `details` redaction | (B) `Settings.debug_unhandled_traceback: bool = True` default; `False` redacts client `details` while `logger.exception` keeps full server log + X-Request-ID correlation (resolved 2026-05-07; impl iter 53) | [D-040](../specs/17-decisions.md) |
| Q-A12 | session_state.json extras tolerance | (A) with WARNING-level drift signal — `extra="ignore"` + `logger.warning("session_state_extras_dropped …")` so library/SPA-legacy drift in a release that shouldn't have had it surfaces as a grep-able log signal (resolved 2026-05-07; impl commit `c10e914`) | [D-041](../specs/17-decisions.md) |
| Q-A14 | M4 renderer Konva spike requirement | (B) commit to Konva without spike; `WordImageCanvas` proves the toolchain works; D-020 superseded; spec 21 is implementation spec (resolved 2026-05-14) | [D-043](../specs/17-decisions.md) |
| Q-A5 | Legacy `UserPageEnvelope` v2.2 tolerance | (A) SPA writes v2.2 freely — legacy `from_dict` silently ignores extras (resolved 2026-05-11) | gh#56 |
| Q-A6 | Predictions-overlay ghost color | Tailwind `blue-500` at 40% opacity, exposed as `--predictions-ghost-color` CSS var (resolved 2026-05-11) | gh#57 + spec 20 §5.6 |
| Q-A7 | Per-mark provenance granularity | (A) object-level — one `source` string per `GlyphAnnotations` dict; per-char deferred to v2.3 (resolved 2026-05-16) | [D-044](../specs/17-decisions.md) |

### Delegations to peer-repo agents (2026-05-06)

- **pgdp-prep:** roadmap entry "Adopt shadcn/ui + Radix" added to
  `pdomain-prep-for-pgdp/docs/08-roadmap.md` (P2 — Frontend polish, item 13a).
- **pdomain-book-tools:** roadmap entries for `bbox.refine_robust(...)` and
  `pd_book_tools.text.normalize` — *delegated, agent running*.
- **pdomain-ocr-cli:** roadmap entry "Output normalization (post-OCR)" added
  to `pdomain-ocr-cli/docs/usage.md` § Text normalization.
