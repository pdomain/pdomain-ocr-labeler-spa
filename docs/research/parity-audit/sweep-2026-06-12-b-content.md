# Parity sweep 2026-06-12 — Dimension B (OCR content actions)

**Auditor:** dimension-B agent (1 of 3 parallel). **Tree:** worktree
`agent-a2bf727009facfe3a` rebased onto local main `d0ba846`. **Bundle:** fresh
`make frontend-build AI=1` this session. **Method:** live browser drive of a
seeded event-store fixture (`/tmp/audit-b/serve.py`, 2 blocks / 3 paras /
6 lines / 24 words, 2 GT mismatches) + API persistence re-fetch after every
mutating op. Acceptance = VISIBLE + ENABLED + real EFFECT (persisted).

> Status legend: PASS / PARTIAL / FAIL / N-A (superseded or out of dimension).

## Architectural deltas since PARITY-GAP.md (2026-06-06)

- **WordEditDialog deleted entirely** (`c5ddd35`, 2026-06-10): all
  `dialog-*` capabilities are superseded by WordDetail right-panel sections
  (Structure / BBox / Rebox / Erase / CharFixer / CharRanges). Legacy
  dialog rows are judged against the WordDetail equivalent.
- **MultiWordDetail + MultiLineDetail** routed in RightPanel (specs
  2026-06-05 + 2026-06-10).
- **Matches pane (WordMatchView/TextTabs) still `display:none`**
  (ProjectPage.tsx:956 `canvas-hidden-stubs`) — retained for driver-contract
  testids only; S2 decision shipped a visible Text drawer tab
  (PlaintextGtOcrView) instead.

## Verdict table

| # | Capability (legacy ref) | SPA surface | Verdict | Evidence |
|---|---|---|---|---|

(rows appended as verified)

## New findings (not in inventories)

(appended as found)
