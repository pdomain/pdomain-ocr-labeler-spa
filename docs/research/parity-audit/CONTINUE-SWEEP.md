# Handoff: continue the full legacy→new parity sweep

Paste the prompt below into a fresh Claude Code session opened in the
`ocr-container` workspace.

---

Continue the comprehensive **legacy → new parity sweep** for the OCR labeler.

**Repos**
- New (replacement, current): `/workspaces/ocr-container/pdomain-ocr-labeler-spa` — FastAPI + React/Vite/TS, now at **v0.2.0**.
- Legacy (being replaced): `/workspaces/ocr-container/pd-ocr-labeler` — NiceGUI.

**What's already done**
- A prior session closed the **selection + operations** parity gap and shipped **v0.2.0** (multi-block multi-select view, visible ToolbarActionGrid, wired stub buttons, selection feedback; browser-verified).
- Six dimensional inventories exist and are committed at `pdomain-ocr-labeler-spa/docs/research/parity-audit/`:
  - `legacy-a-screens.md`, `legacy-b-content.md`, `legacy-c-system.md`
  - `new-a-screens.md`, `new-b-content.md`, `new-c-system.md`
  - Dimensions: **A** = screens/nav/chrome · **B** = OCR content actions · **C** = document/project/system actions.
- The capability-matrix spec format + the selection/ops worked example: `docs/specs/2026-06-05-selection-operations-parity.md`.
- The synthesis (`PARITY-GAP.md`) was **never produced** — that's the main deliverable of this session.

**Goal**: produce the master parity-gap matrix across **all** dimensions (not just selection/operations) and turn the gaps into an actionable, prioritized slice plan.

**Critical framing (hard-won lessons — do not skip)**
- **Raw action counts lie.** The new SPA has *more* actions in code than legacy yet was far from parity, because operations were real-but-unreachable: mounted under `display:none` to satisfy `data-testid` checks, or rendered as unwired stubs. For every legacy capability classify **PRESENT&WIRED / PARTIAL-STUBBED / MISSING** by *capability*, not code presence. A `data-testid` existing is **not** parity.
- **Account for reorganization.** Actions may have moved dimension/surface in the new app; match by capability, use each inventory's "Cross-dimension spillover" section, don't false-flag a moved action as missing.
- **User paths are the real test.** For each legacy end-to-end journey, determine whether it's achievable in the new app *today*.
- **Acceptance = observable behavior** (visible + enabled + performs effect), verified by **running** (Playwright), not unit tests with spies. (The prior sweep's unit tests were green while a backend bug made per-word validate silently not persist — caught only in a browser.)

**Method (fan out subagents; set `model: sonnet` on workers)**
1. Read all six inventories as the map. Re-verify against current code where a claim is load-bearing (code has changed; selection/operations already shipped).
2. For each dimension A/B/C, dispatch a synthesizer in parallel that diffs legacy vs new and emits a per-dimension gap table: `legacy capability | legacy ref (file:line) | status (✅/⚠️/❌) | new ref/evidence | why it matters`.
3. Merge into `docs/research/parity-audit/PARITY-GAP.md`: executive summary (counts ✅/⚠️/❌, true-parity %, *why*), Missing-actions table, Partial/stubbed table, Missing/broken user paths, Present&wired (condensed), New-only additions, and a **prioritized slice plan**.
4. Spot-check the top gaps **live**. The repo has a Playwright e2e harness at `tests/e2e/` (`test_image_click_selection.py`, `helpers.py`, `fixtures/`, and a `_seed_event_store` / `_ingest_ocr_result` seeding pattern; run with `CI=true`). Confirm a sample of "present" capabilities actually work and "missing" ones truly aren't reachable.
5. For each coherent gap cluster, write a capability-matrix spec (same format as `docs/specs/2026-06-05-selection-operations-parity.md`) with observable-behavior acceptance + a mandatory Playwright browser-verification milestone.

**Workspace rules (must follow)**
- Delegate code changes to the `pdomain-ocr-labeler-spa` repo agent in an isolated worktree under `.claude/worktrees/<slug>`; the orchestrator creates the worktree and passes the absolute path (don't rely on `isolation:"worktree"` alone for parallel writers). TDD (failing test first).
- Before committing run `CI=true make ci AI=1` (release uses `CI=true make ci-slow` via `make release-minor`). **`CI=true` is required** — pnpm aborts the `node_modules` purge in non-TTY runs otherwise.
- No GitHub PRs. Commit locally; push only when CT authorizes. Git identity `ConcaveTrillion <concavetrillion@gmail.com>`.
- Read-only doc agents for cheap cross-repo lookups: `pd-ocr-labeler-docs` (legacy), `pdomain-ocr-labeler-spa-docs` (new). Full-power agents: `pd-ocr-labeler`, `pdomain-ocr-labeler-spa`.
- `main` gets concurrent commits from CT in parallel — re-check `git log main -1` before merging and rebase as needed. A side branch `recover/crash-wip` holds salvaged WIP; leave it unless asked.

**Deliverable for THIS session**: `docs/research/parity-audit/PARITY-GAP.md` (the full matrix) + a prioritized next-slices list. **Do NOT start implementing fixes** until CT reviews the gap matrix and picks slices.

---
