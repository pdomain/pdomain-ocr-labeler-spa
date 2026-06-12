# Parity sweep 2026-06-12 — Dimension A (screens / nav / chrome / global hotkeys)

Live-verified browser audit at commit `d0ba846` (includes SEL-3 rail↔radio fix).
Server: standalone uvicorn seeded via `_ingest_ocr_result` event-store pattern
(exercise-fixture, 8 pages, real line_matches). Fresh `make frontend-build`
confirmed (`/healthz` → `0.2.1.dev63+gd0ba846d6`).

Verdict key: PASS = visible + enabled + real effect observed.
PARTIAL = reachable but degraded/incomplete. FAIL = no working reachable path.
N-A = not applicable (capability retired/moved by design with CT sign-off).

| # | Capability | Verdict | Evidence |
|---|---|---|---|

(rows appended as verified)
