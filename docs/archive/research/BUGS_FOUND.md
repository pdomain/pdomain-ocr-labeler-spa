# BUGS_FOUND — open code-review findings

> **Resolved bugs are archived in [`archive/BUGS_RESOLVED.md`](archive/BUGS_RESOLVED.md).**
> Only currently-open findings live below. When a bug is closed, move its full entry
> to the archive in the same commit that closes it (see
> [`DEVELOPMENT.md` § Archive on close](DEVELOPMENT.md#archive-on-close)).

Severity legend: blocker > high > medium > low > nit.

New findings are filed at code-review checkpoints driven by the dev `/loop`. Each
entry includes **Status / Severity / Where / Issue / Why-it-matters / Suggested-fix**.
The closing-commit hash and iter number are recorded on the **Status** line at
close time, then the entry moves to the archive.

---

## M9.1/M9.2 rotate handlers are stubs (not shipped)

- **Status:** open
- **Severity:** medium
- **Found:** 2026-05-16
- **Where:** `core/jobs/handlers/rotate.py` and `core/jobs/handlers/auto_rotate_all.py`
- **Issue:** Both handlers do `await asyncio.sleep(0)` and emit `complete`. Steps 2–4
  (rotate image via pd-book-tools, re-run OCR, update `PageRecord.rotation_degrees`) are
  not implemented. CLAUDE.md and `specs/16-milestones.md` previously listed M9.1 and M9.2
  as ✅ shipped — corrected 2026-05-16.
- **Why it matters:** User clicks Rotate, gets a success toast, image is unchanged.
- **Suggested fix:** Wire `pd_book_tools.ocr.rotation.rotate_image` in
  `handle_rotate_page`, then call the reload-ocr machinery, then update
  `existing.page_record.payload.rotation_degrees`.

---

## BUG-KBD-1 — `Mod+,` not registered — OCR Config modal unreachable by keyboard

- **Status:** open
- **Severity:** high
- **Where:** `frontend/src/hooks/useGlobalHotkeys.ts` / `frontend/src/App.tsx`
- **Issue:** `HOTKEY_MAP` lists `{ combo: "mod+,", scope: "global", description: "OCR Config" }` but
  no `useHotkey("mod+,", ...)` call exists anywhere in the codebase. `useGlobalHotkeys` does not
  include it, and `App.tsx` has no separate binding. The only way to open `OCRConfigModal` is
  clicking a button.
- **Why it matters:** The hotkey is advertised in the `?` help modal (via the bridge) but pressing
  it does nothing. Users who rely on keyboard-only workflows cannot reach OCR config.
- **Suggested fix:** Add `useHotkey("mod+,", () => dialogStore.open("ocrConfig"))` inside
  `useGlobalHotkeys` (or directly in `AppShell`) alongside the `?` binding.

## BUG-KBD-4 — `ConfirmDialog` has no keyboard bindings — Escape and Enter do nothing

- **Status:** open
- **Severity:** medium
- **Where:** `frontend/src/components/ConfirmDialog.tsx`
- **Issue:** `ConfirmDialog` renders Confirm and Cancel buttons but has no `onKeyDown` handler and
  no `useHotkey` registration. The global `escape` listener in `HotkeyHelpModal` only closes the
  help modal. When `ConfirmDialog` is open, pressing Escape or Enter does not dismiss it.
  Clicking backdrop (`e.target === e.currentTarget`) does call `onCancel`, but this requires a
  mouse.
- **Why it matters:** Destructive-action flows (Mod+L, Mod+G, line Delete) require confirmation;
  if the confirm dialog ignores keyboard, the workflow is broken for keyboard-only users.
- **Suggested fix:** Add `useHotkey("escape", () => onCancel(), { enabled: open })` and
  `useHotkey("enter", () => onConfirm(), { enabled: open })` inside `ConfirmDialog`, or add an
  `onKeyDown` on the outer div. The Confirm button already has `autoFocus`, so Enter naturally
  fires on the focused button — verify this is enough in browser (may resolve without extra code).

## BUG-KBD-5 — `Mod+J` jump-to-page not registered — no `useHotkey` call exists

- **Status:** open
- **Severity:** low
- **Where:** `frontend/src/hooks/useGlobalHotkeys.ts` (missing) and `HOTKEY_MAP` line 37
- **Issue:** `HOTKEY_MAP` lists `{ combo: "mod+j", scope: "global", description: "Jump to page…" }`.
  No `useHotkey("mod+j", ...)` call exists anywhere. The jump-to-page dialog / inline page-input
  is not wired to this key.
- **Why it matters:** Users expect to jump to an arbitrary page number from keyboard; it's
  advertised in the help modal but silently inert.
- **Suggested fix:** Add `onJumpToPage` to `GlobalHotkeyHandlers` and register `mod+j` in
  `useGlobalHotkeys`. Wire it to the page-number input focus / jump dialog.

---

## BUG-SMOKE-3 — data_root default mismatches legacy labeler's XDG path on Linux

- **Status:** open
- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/settings.py` — `data_root` default factory
- **Issue:** The SPA defaults `data_root` to `~/pd-ocr-labeler/`. The legacy
  NiceGUI labeler uses XDG-aware `~/.local/share/pd-ocr-labeler/` on Linux.
  Labeled envelopes live under `~/.local/share/pd-ocr-labeler/labeled-projects/`;
  the SPA looks in `~/pd-ocr-labeler/labeled-projects/` by default and finds
  nothing. Users must set `PDLABELER_DATA_ROOT=~/.local/share/pd-ocr-labeler`
  explicitly to access legacy-labeled pages.
- **Why it matters:** Upgrading users see all previously-labeled pages as blank
  (falls through to OCR re-run) without the env var. Breaks continuity with
  existing labeled work.
- **Suggested fix:** Mirror `PersistencePathsOperations.get_data_root()` from the
  legacy codebase: on Linux use `$XDG_DATA_HOME/pd-ocr-labeler` (default
  `~/.local/share/pd-ocr-labeler`); on macOS `~/Library/Application Support/…`;
  on Windows `%APPDATA%/…`.

---

## BUG-RELOAD-1 — GET /api/projects/{id}/pages/{n} returns zero-bbox words after Reload OCR

- **Status:** open (investigation complete — root cause isolated, not a backend bug)
- **Severity:** low (expected shape; UI must tolerate it)
- **Where:** `src/pd_ocr_labeler_spa/core/page_to_line_matches.py:382` and frontend `BBoxOverlay`
- **Issue:** After `POST .../reload-ocr` completes and `GET .../pages/{n}` is called, the
  response may contain `WordMatch` entries with `{"ocr": null, "gt": null, "bbox": {"x":0,"y":0,"width":0,"height":0}}`.
  These are intentional **UNMATCHED_GT placeholders** — words in the ground-truth that DocTR did
  not match to any OCR word. They are synthesized with `BBox(x=0, y=0, width=0, height=0)` at
  `page_to_line_matches.py:382` because they have no bounding box in the image.
- **Actual concern:** If the *entire* page returns only zero-bbox words (i.e., DocTR ran but found
  no text), the root cause may be one of: (a) image path mismatch — `LocalDoctrPageLoader` loads
  the wrong image, (b) DocTR confidence threshold filtering out all words, or (c) a model that
  hasn't been initialized. This is distinct from the UNMATCHED_GT case and would appear as
  `line_matches` being empty after OCR, not as zero-bbox words.
- **Why it matters:** If the frontend renders all UNMATCHED_GT words on the canvas with zero-size
  boxes, the BBoxOverlay may show invisible or stacked 0x0 boxes at origin. `BBoxOverlay` should
  skip or visually suppress words with zero-area bboxes.
- **Suggested fix:**
  1. In `BBoxOverlay`, add a guard: skip items where `bbox.width === 0 && bbox.height === 0`.
  2. If DocTR genuinely returns no text, surface the `ocr_failed` notification banner rather than
     a misleading empty-but-complete state.
  3. To investigate empty-page OCR: check `LocalDoctrPageLoader` logs for the image path it
     actually reads and the raw DocTR word count before `page_to_line_matches` filtering.
