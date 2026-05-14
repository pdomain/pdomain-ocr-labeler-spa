# Parity status — pd-ocr-labeler-spa vs pd-ocr-labeler

**Snapshot.** 2026-05-14 (rewritten after the parity audit captured in
[`PARITY_GAPS_2026_05_14.md`](PARITY_GAPS_2026_05_14.md)).
**Audience.** CT, deciding next priorities.
**Scope.** What the SPA replacement covers today vs what the legacy
NiceGUI labeler ships, with explicit columns for **component-built**
vs **wired-into-the-page**.

> **Why the rewrite.** Prior versions of this file claimed the
> frontend was `⛔ Q-A8` blocked while every M1–M9.1 component had
> in fact shipped and is unit-tested. They also claimed M4 was done
> when `PageImageCanvas.tsx` is a DOM stub. The new layout separates
> **component built** (the component exists, has tests, looks right
> in isolation) from **wired** (it actually renders inside the
> running app). Almost every frontend row is `✅ built / ⛔ not wired`.

---

## 1. One-paragraph status

The SPA scaffolding is comprehensive. Backend has M0/M1/M2 fully
shipped (settings, adapters, AppState, project enumeration, session
state, ground-truth persistence, three-lane persistence model,
config.yaml persistence, source-root carrier). Backend rotate and
export job handlers are real (#263/#264/#226). **Every other per-page
endpoint is a 501 or no-op stub** ([`api/pages.py:174`](../src/pd_ocr_labeler_spa/api/pages.py),
[`api/words.py:180-189`](../src/pd_ocr_labeler_spa/api/words.py)).
Frontend has all 15 user-facing components built and unit-tested,
but **only `HeaderBar` and `LineCard` (via `WordMatchView`) are
rendered by the route tree**. `ProjectPage.tsx` is a 76-line stub
that displays "Project: X — Page Y (full UI in progress)". No image
renders. No edit flows function end-to-end. The toolchain works; the
notifications stack works; the project picker works; nothing past
that.

The path forward is captured in three new specs:
[`specs/21-konva-renderer.md`](../specs/21-konva-renderer.md) replaces
the `PageImageCanvas` DOM stub with real Konva (supersedes D-020 via
[D-043](../specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020));
[`specs/22-page-surface-wireup.md`](../specs/22-page-surface-wireup.md)
mounts the existing components into `ProjectPage`;
[`specs/23-page-payload-backend.md`](../specs/23-page-payload-backend.md)
fills in the 501 stubs. Order: 21 → 23 → 22.

---

## 2. Legend

- ✅ **done** — built, tested, in the running tree.
- 🟩 **built** — built and unit-tested but **not wired into the page**.
- 🟡 **partial** — some parts built, others stub.
- ⬜ **not started** — no implementation.
- ⛔ **blocked** — explicitly waiting on a decision or upstream.

The `Wired` column says yes/no for whether the component renders in
the actual running app.

---

## 3. Backend parity table

| Capability | Status | Wired | Notes |
|---|---|---|---|
| CLI entry (`pd-ocr-labeler-ui`) | ✅ done | yes | iter 47 |
| `/healthz` | ✅ done | yes | M0 |
| Lifespan + shutdown clean | ✅ done | yes | iter 48 |
| Settings (env-driven, frozen) | ✅ done | yes | B-63 closed |
| Storage adapter (filesystem) | ✅ done | yes | S3 deferred per D-019/D-042 |
| Auth adapter (none) | ✅ done | yes | B-42 minor signature drift |
| OCR adapter Protocol | 🟡 partial | partial | `LocalDoctrPageLoader` + `PredictorCache` shipped; `modal`/`shared_container` are `NotImplementedYet` per D-042 |
| Request-ID middleware + audit log | ✅ done | yes | |
| Error handler (500 envelope) | ✅ done | yes | D-040 |
| `/env.js` | ✅ done | yes | |
| Static SPA fallback | ✅ done | yes | |
| Image-cache HTTP route | 🟡 partial | yes | Route works; nothing tells it to serve a page image yet |
| Project discovery / enumeration | ✅ done | yes | `GET /api/projects`, `POST /api/projects/load`, `POST /api/projects/discover`, `POST /api/projects/source-root` |
| Session restore (last project, last page) | ✅ done | yes | session_state read+write, D-041 |
| Ground-truth + project envelope read | ✅ done | yes | `core/persistence/ground_truth.py`, `project_envelope.py` |
| Three-lane persistence model (labeled/cached/ocr) | ✅ done | yes | `ensure_page_model` dispatcher + `LaneResolver` |
| `GET /api/projects/{id}/pages/{idx}` payload | ⬜ not started | no | **501 stub** — spec 23-A is P0 |
| `POST .../pages/{idx}/save` | ⬜ not started | no | **501 stub**; `persist_page_to_file` exists, no caller |
| `POST .../pages/{idx}/load` | ⬜ not started | no | 501 stub |
| `POST .../pages/{idx}/reload-ocr` | 🟡 partial | no | 202+`asyncio.sleep(0)` — handler not implemented |
| `POST .../pages/{idx}/rematch-gt` | ⬜ not started | no | 501 stub |
| `POST .../pages/{idx}/rotate` (manual) | ✅ done | no | M9.1 (#263); endpoint live; frontend rotate button not mounted |
| `POST .../auto-rotate-all` | ✅ done | no | M9.2 (#264); endpoint live; OCR config UI not mounted |
| Word mutation endpoints (×11) | 🟡 partial | no | URL shapes + Pydantic validation real; handlers return empty `PagePayload` |
| Line / paragraph mutation endpoints (×8) | 🟡 partial | no | Same |
| Selection endpoint | ⬜ not started | no | Spec 23-E |
| Refine bboxes (page + project) | ✅ done | no | Job handler shipped; frontend launcher missing |
| Save Project (multi-page job) | 🟡 partial | no | 202+sleep-0 handler — spec 23-B |
| Export (per-style `labels.json`) | ✅ done | no | `handle_export` real (#226); frontend `ExportDialog` not mounted |
| Notification SSE | ✅ done | yes | NotificationQueue + `/api/notifications/stream` + `useNotificationStream` |
| OCR config snapshot endpoint | ✅ done | no | `GET /api/ocr-config` etc.; `OCRConfigModal` not mounted |

---

## 4. Frontend parity table — built vs wired

The killer column is **Wired**: a `⛔ no` means the component renders
nowhere in the running tree. A `🟩 built ⛔ no` row means the
component is real, tests pass, and it's invisible to a user.

| Capability | Built | Wired | Notes |
|---|---|---|---|
| Vite + React 19 + Vitest scaffold | ✅ | yes | #246 — toolchain works, MSW + Konva mock + coverage |
| Tailwind | ✅ | yes | B-18 resolved |
| ESLint + tsc + pyright in CI | ✅ | yes | #176 |
| Router (`react-router-dom`) + `QueryClient` | ✅ | yes | #240, #193 |
| Header bar | ✅ | yes | #272 |
| `ProjectLoadControls` (dropdown + LOAD) | ✅ | yes | shipped; powers M2 load flow |
| `EmptyProjectState` + `RootPage` | ✅ | yes | #84, #274 |
| `Toaster` (sonner) | ✅ | yes | #231 |
| `useNotificationStream` (SSE → toasts) | ✅ | yes | #231 |
| **`ProjectPage` (real shell)** | ⬜ | no | **Stub only** — 76-LOC placeholder; spec 22 mounts the real surface |
| `ProjectNavigationControls` (Prev/Next/GoTo) | ⬜ | no | Stub `display:none` block for driver-contract testids only |
| `PageActions` (Reload/Save/Load/Rematch/Rotate) | 🟩 | no | 313 LOC real component, not mounted |
| `ImageTabsHeader` (layer checkboxes + selection mode + Erase) | 🟩 | no | #196; bug: paragraph radio hardcoded `&& false` (line 108); SelectionMode type uses `box` instead of `paragraph` |
| `PageImageCanvas` (Konva) | ⬜ | no | **DOM stub** — imageUrl unused; spec 21 ships real renderer |
| `BBoxOverlay` (Konva rects) | ⬜ | no | **Test-only `<div>` stub** — spec 21 |
| `TextTabs` (Matches / GT / OCR) | 🟩 | no | 181 LOC |
| `WordMatchView` (virtualized) | 🟩 | no | 118 LOC; uses `@tanstack/react-virtual` |
| `LineCard` (per-line GT/OCR + per-word controls) | 🟩 | partial | Imported by `WordMatchView`; rendered only if `WordMatchView` is — which it isn't |
| `WordCell` + GT-input | 🟩 | no | #203 |
| `WordTagRow` + tag chips | 🟩 | no | |
| `FilterToggle` (Unvalidated/Mismatched/All) | ⬜ | no | Not yet built; spec 22 §8 adds it |
| `ToolbarActionGrid` (Page/Paragraph/Line/Word × actions) | 🟩 | no | 332 LOC; #207 |
| `WordEditDialog` (merge/split/erase/nudge/refine) | 🟩 | no | 296 LOC; #209 |
| `WordImageCanvas` (Konva, in dialog) | ✅ | partial | **Real Konva** — only via dialog when launched, which never happens because dialog not mounted |
| `WordActionRows`, `WordRefineNudgeRows` | 🟩 | no | |
| `OCRConfigModal` | 🟩 | no | 398 LOC; #261 normalize section + auto-rotation section |
| `ExportDialog` | 🟩 | no | 431 LOC; backend export shipped |
| `HotkeyHelpModal` | 🟩 | no | #235 |
| `ConfirmDialog` | 🟩 | no | #236 |
| `BusyOverlay` | 🟩 | no | #232 |
| `InlineBanners` (OCR-failed / not-found / image-drift) | 🟩 | no | #233 |
| `Splitter` (horizontal pane resize) | ⬜ | no | Not yet built; spec 22 §9 adds it |
| Hotkey hooks (`useHotkey`, `useGlobalHotkeys`, viewport/matches/dialog) | ✅ | partial | #235/#236/#237/#202 — wired only where their consumer components are mounted |
| Data hooks (`useProject`, `usePage`, `useJobProgress`, mutations) | ✅ | partial | #192/#215/#216/#202 |
| Driver-contract conformance E2E test | ✅ | yes | #241/#242/#247 — passes against stub testids |

---

## 5. Outstanding blockers (user-decision queue)

(2026-05-14 status — Q-A14 closed by D-043 in this commit.)

None. All blocking questions are resolved. The path forward is
described entirely by specs 21 / 22 / 23 and does not require new
input from CT until those specs land.

Q-A7 (per-mark glyph provenance) is open but only blocks M11; not on
the critical path for the audit-driven re-spec.

---

## 6. Open bugs of consequence (medium+)

| ID | Severity | One-line |
|---|---|---|
| **B-42** | low | `IAuth.verify` signature drift; one-line fix |
| **(new) BBL-AUDIT-1** | medium | `ImageTabsHeader.tsx:108` — paragraph radio hardcoded `&& false`; `SelectionMode` type uses `box` not `paragraph` (spec 21 §8) |

Closed since previous snapshot: B-58, B-72, Q-A12. See
[`docs/archive/BUGS_RESOLVED.md`](archive/BUGS_RESOLVED.md).

---

## 7. Recommendation: next priorities

(The audit makes the prior "Bootstrap the frontend toolchain"
recommendation obsolete — that's been done.)

1. **Land spec 21** (Konva renderer). Three sub-issues. P0.
2. **Land spec 23-A + 23-B** (`GET /pages/{idx}` real impl + reload-OCR
   real handler). Without these the wired page renders nothing.
3. **Land spec 22** (page surface wireup). After 21 and 23-A this
   becomes the iter that makes the SPA usable for the first time.
4. **Land spec 23-C/D/E** (mutation handlers + selection endpoint).
   Unblocks edit operations.
5. **Polish** — `ImageTabsHeader` paragraph-radio fix, `FilterToggle`,
   `Splitter`, `OCRConfigModal` launcher, `ExportDialog` launcher,
   banners + busy overlay in tree.

---

## 8. Risk register

1. **pd-book-tools mutation methods may not all exist.** Spec 23-C/D
   assumes `Word.set_ground_truth_text`, `Word.apply_style`,
   `Word.set_validated`, `Word.rebox`, `Page.add_word`,
   `Page.merge_words`, `Line.copy_gt_to_ocr`, `Page.delete_line`,
   etc. Mitigation: per-handler audit during spec 23-C; route any
   missing methods to `pd-book-tools` agent before that issue starts.
2. **`use-image` adds a dep.** Spec 21 §5 commits to it. Mitigation:
   pinned to `^1.1` (small surface, stable); fallback pattern from
   `WordImageCanvas.ImageLayer` documented if we ever need to drop.
3. **Driver-contract sidecar divs.** Spec 21 §6 keeps `data-testid`
   sidecar divs alongside Konva nodes. Mitigation: dev/test-only via
   `import.meta.env.MODE !== "production"`; bundle stays clean.

---

## 9. References

- Audit: [`docs/PARITY_GAPS_2026_05_14.md`](PARITY_GAPS_2026_05_14.md)
- Konva spec: [`specs/21-konva-renderer.md`](../specs/21-konva-renderer.md)
- Wireup spec: [`specs/22-page-surface-wireup.md`](../specs/22-page-surface-wireup.md)
- Backend payload spec: [`specs/23-page-payload-backend.md`](../specs/23-page-payload-backend.md)
- D-043: [`specs/17-decisions.md`](../specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020)
- Legacy UI inventory: [`pd-ocr-labeler/docs/architecture/ui-action-buttons.md`](../../pd-ocr-labeler/docs/architecture/ui-action-buttons.md)
