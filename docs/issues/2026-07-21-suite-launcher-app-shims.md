---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# AppShell suite launcher still uses fetchInstalled/postLaunch shims

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — suite launcher never lists or launches siblings from AppShell
- **Affected version:** deep code review 2026-07-21 (`P1-SUITE`); PGDP item 5
- **Read when:** wiring AppShell launcher, suite routes, Export “Send to trainer,” or GAP-3.
- **Search terms:** fetchInstalled, postLaunch, SuiteSiblingsProvider, GAP-3, /api/suite, suite launcher, P1-SUITE.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`docs/plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md),
  [`frontend/src/App.tsx`](../../frontend/src/App.tsx),
  [`frontend/src/components/ExportDialogUtils.ts`](../../frontend/src/components/ExportDialogUtils.ts),
  [`src/pdomain_ocr_labeler_spa/bootstrap.py`](../../src/pdomain_ocr_labeler_spa/bootstrap.py)

## Summary

Bootstrap mounts real `/api/suite/*` routes (installed, launch, prefs, device,
etc.), and `ExportDialogUtils` already calls those endpoints for trainer handoff.
`App.tsx` still supplies **hard-coded shims**: `fetchInstalled` always returns
`[]`, and `postLaunch` always returns `requires-host-config`. AppShell’s suite
launcher therefore never shows siblings or performs a real launch (GAP-3 /
PGDP item 5 / **P1-SUITE**).

## Impact

- Users cannot discover or open installed sibling apps from the AppShell
  launcher, even when the host suite registry and backend routes work.
- Export “Send to trainer” may succeed while the chrome launcher claims
  “requires host config,” which is product-dishonest dual behavior.
- Trainer / suite handoff from the shell remains dead UI chrome.

## Environment / versions

- Source: deep code review Wave 5 item 5;
  `docs/plans/2026-07-21-pgdp-alignment-remaining.md` status table item 5
  (**open**, verified 2026-07-21).
- Finding ID: **P1-SUITE**.
- Backend: `pdomain_ops.suite.routes.mount_routes` via
  `bootstrap.build_app` / `mount_suite_routes`.

## Evidence

1. **Shims in App.tsx** — comments state launcher callbacks remain shimmed even
   though suite compute/settings endpoints are mounted. Implementations:

   ```ts
   async function fetchInstalled(): Promise<InstalledApp[]> {
     return [];
   }
   async function postLaunch(id: string): Promise<LaunchResult> {
     return { kind: "requires-host-config", siblingId: id };
   }
   ```

   Wired through `SuiteSiblingsProvider value={{ fetchInstalled, postLaunch }}`.

1. **Real client already exists for export** —
   `ExportDialogUtils.ts` uses `GET /api/suite/installed` and
   `POST /api/suite/launch?app_id=…` for the trainer path.

1. **Backend mount is live** — `bootstrap.py` calls `mount_suite_routes` and
   documents suite paths including `POST /api/suite/launch` and related prefs /
   device routes.

1. **PGDP plan tasks 5.1–5.3** spell the fix: replace shims, share helpers with
   ExportDialogUtils (or `frontend/src/api/suite.ts`), cover empty/success/failure
   tests, keep graceful degradation when siblings are unavailable.

## Root-cause hypotheses

1. **(Most likely) Stale GAP-3 deferral** — shims were left in place when only
   compute/settings suite routes were needed; launcher wiring was never finished
   after `mount_suite_routes` landed.
2. **Contract mismatch fear** — ExportDialog query-param launch vs pdomain-ui
   JSON `{ id }` body deferred full wiring until someone reconciled shapes
   against the mounted ops router.
3. **Dual clients by accident** — export path grew a real client; AppShell kept
   the original empty shims without a shared suite module.

## Defects to fix

1. `fetchInstalled` ignores `/api/suite/installed` and always returns empty.
2. `postLaunch` never POSTs to `/api/suite/launch`; always synthesizes
   `requires-host-config`.
3. AppShell launcher and Export “Send to trainer” use inconsistent suite clients.
4. Missing unit coverage for launcher success / empty / failure states once real
   fetches land.

## Next steps

1. Confirm backend launch contract (query `app_id` vs JSON body) against mounted
   ops suite routes.
2. Replace App.tsx shims with shared helpers (prefer one `api/suite.ts` used by
   App and ExportDialogUtils).
3. Add App / MSW tests for empty list, successful install list, launch success,
   and error without crash.
4. Manual or e2e check: launcher shows installed siblings when registry reports
   them; launch returns backend result.
5. Track under Wave 5 / PGDP Night-1 item 5; no dependency on Jobs pill contract.

## What is NOT broken

- Backend suite route mounting and compute-device prefs path.
- Export dialog trainer handoff via `ExportDialogUtils` real `/api/suite/*` calls
  (subject to sibling install/runtime).
- Core OCR labeling, save, and in-app export loops.
- Settings/Compute panel warmup that already uses suite device endpoints
  (separate from launcher list/launch).

## Resolution

Open. Wave 5 / PGDP alignment item 5. Disposition: small–medium wiring change
once launch body shape is reconciled with bootstrap-mounted suite routes.
