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

### Q-A1. Auto-rotation envelope schema bump?

**Context.** D-029 (auto-rotation) adds a per-page `rotation_degrees`
field. To persist it across save/load, we need to extend the
`UserPageEnvelope`. v2.1 is byte-shared with the legacy labeler.

**Options.**

- **(A)** Bump to v2.2 (additive: new optional `source.rotation_degrees: int = 0`
  field). Legacy v2.1 readers ignore unknown fields by default but
  `extra="forbid"` on the top-level `UserPageEnvelopeSchema` would
  reject — verify legacy behaviour before bumping.
- **(B)** Keep v2.1, store rotation in a sidecar file
  `<labeled-projects>/<project_id>_<page:03d>.rotation.json`. Doesn't
  break legacy. More files to manage.
- **(C)** Keep v2.1, store rotation only in the cache-lane envelope
  (which is SPA-only). Crash recovery preserves it; explicit Save Page
  resets it to 0. **Bad** — unexpected reset.

**Recommendation.** **(A)** with verification of legacy strictness
first. If legacy rejects v2.2: ship **(B)** with auto-cleanup of the
sidecar on next legacy save.

**Blocks.** M9.x rotation milestone, [`19-auto-rotation.md`](specs/19-auto-rotation.md) §Persistence.

### Q-A2. Q14 normalization toggle scope?

**Context.** D-025 (normalization in pd-book-tools, opt-in everywhere).
The labeler can opt the **comparison** path into normalization-aware
GT matching so `ſhall` matches `shall` as exact. Where does the
toggle live?

**Options.**

- **(A)** Project-level: a checkbox in OCR config modal "Normalize for
  GT matching". Persisted in `OCRConfig`. Applies to the whole project.
- **(B)** Per-page: a toggle near the line filter. Each page can
  differ.
- **(C)** Global setting in `usePrefsStore`. Persisted per-browser.
- **(D)** Off in v1; surface in M9 polish only after we have data.

**Recommendation.** **(A)** project-level. Books are typographically
homogeneous within themselves; per-page toggling is unnecessary
churn.

**Blocks.** [`18-text-normalization.md`](specs/18-text-normalization.md) §Implementation, M9 polish.

### Q-A3. Q18 rotation indicator UI placement?

**Context.** D-029 adds a rotation indicator. Where?

**Options.**

- **(A)** Append to the source badge: "LABELED ↻90". Compact, near
  filename.
- **(B)** Separate badge next to source badge: "[LABELED] [↻90 auto]".
  Two pills.
- **(C)** Tooltip on rotate-button: "Currently rotated 90° (auto)".
  No always-on indicator.

**Recommendation.** **(B)**. Distinct concept from source provenance;
distinct pill. Tooltip provides the "auto" vs "manual" detail.

**Blocks.** [`19-auto-rotation.md`](specs/19-auto-rotation.md) §UI, [`13-driver-contract.md`](specs/13-driver-contract.md).

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

### Delegations to peer-repo agents (2026-05-06)

- **pgdp-prep:** roadmap entry "Adopt shadcn/ui + Radix" added to
  `pd-prep-for-pgdp/docs/08-roadmap.md` (P2 — Frontend polish, item 13a).
- **pd-book-tools:** roadmap entries for `bbox.refine_robust(...)` and
  `pd_book_tools.text.normalize` — *delegated, agent running*.
- **pd-ocr-cli:** roadmap entry "Output normalization (post-OCR)" added
  to `pd-ocr-cli/docs/usage.md` § Text normalization.
