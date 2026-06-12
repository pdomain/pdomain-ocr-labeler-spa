# Sweep 2026-06-12 — Dimension C (document / project / system actions)

Live-verified refresh of the dimension-C parity rows. Method: seeded
exercise-fixture server (event-store seed via `_ingest_ocr_result` +
`_register_page_in_project`, same as `tests/e2e/exercise_real_project.py`),
driven in a real Chromium via Playwright MCP; durability checked via API
re-fetch and files on disk.

Acceptance per row = **VISIBLE + ENABLED + real EFFECT** (durable where
applicable). A testid existing is not parity.

Server: worktree `agent-ae30520f4d388f99c` @ `d0ba846` (rebased onto local
main), fresh `make frontend-build`, `http://127.0.0.1:8931`,
data roots under `/tmp/c-audit/run/`.

## Verdict table

| Row | Capability | Verdict | Evidence |
|---|---|---|---|

## Notes

(populated as the sweep progresses)
