# Konva + Parity Execution Plan — 2026-05-14

Decomposition of the three P0 specs (21 / 22 / 23) into 26 child issues
sized for the `ship-issue` bot lane. Generated after the 2026-05-14
parity audit; macro phases align with the audit's "21 → 23-A/B → 22 →
23-C/D/E" guidance.

Parent spec issues: #289 (Konva), #290 (wireup), #291 (backend).
Milestones: **M12** (Konva), **M13** (ProjectPage wireup), **M14**
(Backend page payload + mutations).

---

## Macro phases

1. **Phase A — Konva renderer** (spec 21, milestone M12) — issues
   #296, #297, #298, #299, #300, #301, #302, #303, #304, #305.
2. **Phase B — Backend page load + reload_ocr** (spec 23-A/B,
   milestone M14) — issues #306, #307, #308.
3. **Phase C — ProjectPage wireup** (spec 22, milestone M13) — issues
   #309, #310, #311, #312, #313, #314.
4. **Phase D — Backend mutations + selection + autosave** (spec
   23-C/D/E/F/G, milestone M14) — issues #315, #316, #317, #318,
   #319, #320, #321.

Phases A and B can run completely concurrently — they share no files
and no dependencies. Phase C depends on both. Phase D depends on
spec-23-A (#306) only and can therefore start the moment #306 ships,
parallel with the rest of Phases A and B.

---

## Phase A — Konva renderer (M12)

Spec: `specs/21-konva-renderer.md`. Parent: #289.

| Issue | Title | Effort | Blocked by | Wave |
|---|---|---|---|---|
| #296 | spec-21-A1: add `use-image` dep + `<PageImage>` wrapper | S | — | 1 |
| #299 | spec-21-A4: selection-expand helper + SelectionMode type fix | S | — | 1 |
| #300 | spec-21-C1: rafSchedule rAF-batching helper | S | — | 1 |
| #297 | spec-21-A2: PageImageCanvas real Konva Stage scaffold | M | #296 | 2 |
| #298 | spec-21-A3: BBoxOverlay Konva-rect rendering + sidecar | M | #297 | 3 |
| #302 | spec-21-A6: select-mode drag + drag-preview rect + cursor | M | #297, #300 | 3 |
| #301 | spec-21-A5: selection layer rendering wired | S | #298, #299 | 4 |
| #303 | spec-21-A7: rebox/add-word/erase mode drag callbacks | M | #302 | 4 |
| #304 | spec-21-A8: focus wrapper + viewport hotkeys | S | #298, #302 | 4 |
| #305 | spec-21-C2: perf pinning + viewport perf E2E benchmark | M | #298, #302, #303 | 5 |

---

## Phase B — Backend page load + reload_ocr (M14, partial)

Spec: `specs/23-page-payload-backend.md` §3–§6. Parent: #291.

| Issue | Title | Effort | Blocked by | Wave |
|---|---|---|---|---|
| #306 | spec-23-A: GET /pages/{idx} real PagePayload assembler | M | — | 1 |
| #307 | spec-23-B1: reload_ocr job handler — real loader + progress | M | #306 | 2 |
| #308 | spec-23-B2: POST /save + /load + save_project job handler | M | #306 | 2 |

---

## Phase C — ProjectPage wireup (M13)

Spec: `specs/22-page-surface-wireup.md`. Parent: #290.

| Issue | Title | Effort | Blocked by | Wave |
|---|---|---|---|---|
| #309 | spec-22-A: useDialogStore + HeaderBar triggers + AppShell dialogs | M | — | 1 |
| #310 | spec-22-B1: Splitter + usePrefsStore.splitterRatio | S | — | 1 |
| #311 | spec-22-B2: ProjectNavigationControls — real Prev/Next/GoTo | S | — | 1 |
| #312 | spec-22-B3: FilterToggle + WordMatchView filter plumbing | S | — | 1 |
| #313 | spec-22-B4: PlaintextEditor — read-only textarea | S | — | 1 |
| #314 | spec-22-C: ProjectPage real shell — full assembly | L | #309, #310, #311, #312, #313, plus Phase A (#297/#298/#302) + Phase B (#306) | terminal |

Phase C's wave-1 issues (#309–#313) are independent UI primitives. They
can dispatch in parallel the moment subagent-driven-development starts
— they do not depend on Phase A or B. Only #314 (the integration slice)
needs Phase A + Phase B to be at least partially complete.

---

## Phase D — Backend mutations + selection + autosave (M14, remainder)

Spec: `specs/23-page-payload-backend.md` §7–§13. Parent: #291.

| Issue | Title | Effort | Blocked by | Wave |
|---|---|---|---|---|
| #315 | spec-23-C1: word mutations — GT/style/component/validated/batch | M | #306 | 2 |
| #316 | spec-23-C2: word mutations — add/rebox/nudge/split/merge/erase-pixels | M | #306 | 2 |
| #317 | spec-23-D1: line mutations — copy/validate/delete/merge/split/refine | M | #306 | 2 |
| #318 | spec-23-D2: paragraph mutations — copy/validate/delete/merge/split | M | #306 | 2 |
| #319 | spec-23-E: selection endpoint + core/selection.py set ops | M | #306 | 2 |
| #320 | spec-23-F: rematch-gt endpoint — real ground_truth_matcher | S | #306 | 2 |
| #321 | spec-23-G: integration test — concurrent mutations + per-page lock | S | #315 | 3 |

Wave 2 inside Phase D is six issues touching different router files
(`api/words.py`, `api/lines_paragraphs.py`, `core/selection.py`,
`api/refine.py`) — fully parallel-safe.

---

## Parallel-safe waves (cross-phase)

The bot scheduler can dispatch the following waves concurrently. Each
wave waits on its predecessors to fully ship before the next one begins,
but every issue inside a wave is parallel-safe.

### Wave 1 — kick-off (8 issues, all `status:ready`)

- Phase A: #296, #299, #300
- Phase B: #306
- Phase C: #309, #310, #311, #312, #313

(Yes, that is 9 issues — the wave-1 count is 9, not 8.)

### Wave 2 — after Phase A wave 1 + #306 ship

- Phase A: #297 (needs #296)
- Phase B: #307, #308 (need #306)
- Phase D: #315, #316, #317, #318, #319, #320 (need #306)

### Wave 3 — after Phase A wave 2 ships

- Phase A: #298, #302 (need #297; #302 also needs #300 from wave 1)
- Phase D: #321 (needs #315 from wave 2)

### Wave 4 — after #298 + #302 ship

- Phase A: #301, #303, #304

### Wave 5 — after #303 ships

- Phase A: #305

### Wave 6 — terminal integration

- Phase C: #314 (waits on every preceding wave)

---

## Total effort estimate

- **26 child issues** across three milestones.
- Effort breakdown: **L** × 1 (#314), **M** × 14, **S** × 11.
- Assuming the ship-issue bot lane delivers ~3 issues per agent session
  on M slices and ~5 per session on S slices, this is roughly **6–8
  sessions** of bot time before a demoable SPA exists.
- Critical path runs Phase A → wave 4 → wave 5, which is 5 sequential
  waves of Konva work; with parallel dispatch most waves contain ≥3
  independent issues, so wall-clock time is dominated by the critical
  path, not the issue count.

---

## Items that need CT judgement before subagent-driven-development starts

None blocking.  Notes for the dispatcher:

- **pdomain-book-tools method audit.** Phase D issues each call out that
  any missing pdomain-book-tools method (per spec 23 §9) must be filed as a
  tracking issue against `pdomain-book-tools` rather than no-op'd. The
  child bot lane should route those through the `pdomain-book-tools` agent.
- **#305 perf benchmark flakiness.** The 60-fps benchmark may fail on
  shared CI hardware. The issue body asks the reviewer to bump
  tolerance to 45 frames and file a follow-up rather than block-merge.
- **#295 (ImageTabs sub-tabs).** Confirmed parity gap, queued
  `status:backlog` — picks up after the P0 wireup lands; not included
  in this execution plan.

---

## References

- Parity audit: `docs/PARITY_GAPS_2026_05_14.md`
- Spec 21 (Konva): `specs/21-konva-renderer.md`
- Spec 22 (Wireup): `specs/22-page-surface-wireup.md`
- Spec 23 (Backend): `specs/23-page-payload-backend.md`
- ADR D-043 (Konva commitment): `specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020`
