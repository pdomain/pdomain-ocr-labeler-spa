# Lint-rule Deviations — pdomain-ocr-labeler-spa

Standing suppressions and per-file rule overrides in this repo.
Each entry records: the rule, the tool, the file(s) affected, and
the justification. Update this file whenever a new suppression is added.

---

## Python — ruff

### 1. `B008` — ruff (function-call-in-default-argument)

**Config:** `pyproject.toml` `[tool.ruff.lint] ignore = ["B008"]` (project-wide)

**Justification.** FastAPI's canonical dependency-injection pattern uses
`Depends(...)` as a default argument value. This is idiomatic FastAPI and
has no actionable alternative; suppressing the rule globally avoids
false positives across all route handlers.

---

### 2. `UP042` — ruff (use-StrEnum)

**Config:** project-wide ignore.

**Justification.** `Foo(str, Enum)` is used widely in the spec and Pydantic
model layer. `StrEnum` is the newer alternative but is semantically
equivalent; switching would be pure churn.

---

### 3. `RUF002` — ruff (ambiguous-unicode-character-docstring)

**Config:** project-wide ignore.

**Justification.** En-dashes (–) appear in spec citations in docstrings
(e.g., "spec §3 — overview"). These are intentional typography, not
accidental Unicode confusion.

---

### 4. `D203`, `D212` — ruff (docstring style conflicts)

**Config:** project-wide ignore.

**Justification.** `D203` (1-blank-before-class-docstring) conflicts with
`D211` (no-blank-before-class-docstring). `D212`
(multi-line-summary-first-line) conflicts with `D213`
(multi-line-summary-second-line). ruff requires picking one of each pair;
the selected alternatives (`D211`, `D213`) are what the Google convention
implies.

---

### 5. `D100`, `D104`, `D107` — ruff (missing docstrings)

**Config:** project-wide ignore.

**Justification.** Missing docstrings on public modules, packages, and
magic methods. Large existing codebase; docstrings are being added
incrementally — a single global enforcement sweep would be invasive.

---

### 6. `PLR0913` — ruff (too-many-arguments)

**Config:** project-wide ignore.

**Justification.** FastAPI route handlers and core domain functions
legitimately need many parameters. Enforcing this rule would require
invasive config-object refactors not warranted by the linting rollout.

---

### 7. `PLR2004` — ruff (magic-value-comparison)

**Config:** project-wide ignore.

**Justification.** Common in OCR geometry and image-threshold code where
literal values (pixel intensities, coordinate offsets) are semantically
clear from context.

---

### 8. `TRY003` — ruff (long-message-outside-exception-class)

**Config:** project-wide ignore.

**Justification.** The service uses f-string error messages everywhere;
requiring a custom exception class per message would be invasive without
readability gain.

---

### 9. `COM812` — ruff (missing-trailing-comma)

**Config:** project-wide ignore.

**Justification.** Conflicts with the ruff formatter's auto-style. Both
cannot be on simultaneously; the formatter wins.

---

### 10. `ANN401` — ruff (dynamically-typed-expressions)

**Config:** project-wide ignore.

**Justification.** Some functions legitimately accept or return `Any` —
JSON deserialisers, generic dispatch helpers, FastAPI `app.state` accessors.
The specific sites are documented in the inline comments where they occur.

---

### 11. `T201` — ruff (print)

**Suppression form:** `# noqa: T201` inline.

**Files:** `src/pdomain_ocr_labeler_spa/__main__.py` — five call sites:

- line 297: `--version` flag; version output goes to stdout by convention.
- line 326: CLI error notice to stderr.
- line 335: CLI error notice to stderr.
- line 360: startup device banner; intentionally goes to stdout.
- line 363: `Listening on <url>` startup notice; intentionally goes to stdout.

**Justification.** These are user-facing CLI messages. Using a logger would
route them through the structured logging pipeline and away from stdout,
breaking the convention for version flags and startup notices.

Also suppressed project-wide for `scripts/*.py` and
`src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py` via
`per-file-ignores` — developer scripts and the headless export CLI where
print() is the output mechanism.

---

### 12. `N818` — ruff (exception-name-should-be-Error)

**Suppression form:** `# noqa: N818` inline.

**Files:** `src/pdomain_ocr_labeler_spa/core/exceptions.py:37` —
`NotImplementedYet(NotImplementedError)`.

**Justification.** `NotImplementedYet` is intentionally non-`Error`-suffixed:
it signals "feature not yet wired" (a development sentinel), not a runtime
error condition. The name is more descriptive than `NotImplementedYetError`.

---

### 13. `F401` — ruff (unused-import)

**Suppression form:** `# noqa: F401` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/api/jobs.py:13` — `Job, JobProgress, JobType`
  re-exported from the public API surface so callers can import them from
  the `api.jobs` namespace.
- `src/pdomain_ocr_labeler_spa/api/projects.py:766` — lazy import of
  `detect_best_rotation` inside a `try` block to check availability;
  the import itself is the probe, not the return value.

**Justification.** Re-export modules and optional-feature availability probes.

---

### 14. `PLW0603` — ruff (use-of-global)

**Suppression form:** `# noqa: PLW0603` inline.

**Files:** `src/pdomain_ocr_labeler_spa/core/persistence/user_page_envelope.py:698`
— `global _v22_warn_emitted`.

**Justification.** Emit-once warning flag — module-level boolean that flips
from `False` to `True` on the first call. The `global` keyword is the
standard pattern for this; `PLW0603` is suppressed with an inline comment.

---

### 15. Per-file rule bundles — ruff

**Config:** `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`.

| File(s) | Rules suppressed | Reason |
|---------|-----------------|--------|
| `tests/**/*.py` | `S101, S105, S106, S311, S603, S607, S108, S104, ANN, D, PLR2004, PLR0133, PLW2901, PLR0911, PLR0912, PLR0913, PT011, PT006, TC001–TC003, PLC0415, BLE001, PERF401, TRY003/300/301, RET504, PLW1510, PT018, PLR1714, PLW0108, PLC0414, C408, E402, E741` | Test idioms: assert, magic numbers, no annotation/docstring requirement; coordinate names (E741); security rules relaxed; TC deferred in test scope |
| `tests/*` | `E741` | Spec-aligned coordinate names (L/R/T/B) in tests |
| `scripts/*.py` | `T201, S603, S607, ANN, D` | Developer helper scripts; print() is the output mechanism; no docstrings/annotations required |
| `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py` | `T201` | Headless export CLI; print() for user-facing output |
| `src/pdomain_ocr_labeler_spa/api/*.py` | `ANN, D, BLE001, TRY, TID252, S101, TC001–TC003, PLC0415, RET504, PT018, PLR0911, PLR0912, PLR0915` | API router annotation/docstring debt; assert-narrowing in FastAPI dependencies; deferred TC/PLC0415 |
| `src/pdomain_ocr_labeler_spa/core/*.py` and `core/**/*.py` | `ANN, D, TID252, TC001–TC003, PLC0415, BLE001, TRY, RET504` | Core domain annotation/docstring debt; TC/PLC0415 deferred; implicit-return-in-try is project style |
| `src/pdomain_ocr_labeler_spa/adapters/**/*.py` | `ANN, D, TRY, BLE001, TID252, S101, TC001–TC003, PLC0415` | Adapter layer annotation/docstring debt; S101 asserts used as invariant guards |
| `src/pdomain_ocr_labeler_spa/*.py` | `ANN, D, TC001–TC003, PLC0415, PLR0911, PLR0912, PLR0915, S101` | Top-level module files (`__main__`, bootstrap, settings, `__init__`); PLC0415 deferred imports are intentional in `__main__`; PLR09xx complexity in bootstrap/main |

---

### 16. `TC` — ruff (type-checking imports)

**Config:** suppressed on all `src/pdomain_ocr_labeler_spa/**/*.py` in the
api/core/adapters layers.

**Justification.** ruff's `TC` auto-fix moves runtime imports into
`TYPE_CHECKING` blocks. When `from __future__ import annotations` is active,
Pydantic v2 evaluates annotations lazily as strings, and type-checking-only
imports are not present at runtime — this breaks model validation. The
correct fix is to use `model_rebuild()` or remove `from __future__ import
annotations`, neither of which is done globally yet. `TC` is suppressed
until the Pydantic models are migrated.

---

## Python — basedpyright

### 17. `reportReturnType` — basedpyright

**Suppression form:** `# type: ignore[return-value]  # pyright: ignore[reportReturnType]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/api/dependencies.py:93` — `get_storage` returns `storage`
  typed as the narrow adapter concrete type rather than the protocol.
- `src/pdomain_ocr_labeler_spa/api/dependencies.py:99` — `get_auth` same pattern.
- `src/pdomain_ocr_labeler_spa/api/dependencies.py:105` — `get_ocr` same pattern.
- `src/pdomain_ocr_labeler_spa/api/jobs.py:95` — `JSONResponse` short-circuit path
  in a route typed as returning a Pydantic model.
- `src/pdomain_ocr_labeler_spa/api/pages.py:1168` and `:1179` — same `JSONResponse`
  short-circuit pattern.

**Justification.** FastAPI dependency injectors retrieve adapters from
`app.state` via the protocol but the stored object's concrete type is
narrower than the declared return. At runtime the types are correct.
The `JSONResponse` short-circuits carry the same payload shape as the
declared model return type.

---

### 18. `reportAttributeAccessIssue` — basedpyright

**Suppression form:** `# type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/adapters/storage/filesystem.py:78, :94, :123` —
  `anyio.to_thread.run_sync` call attribute.
- `src/pdomain_ocr_labeler_spa/core/jobs/handlers/save_project.py:108` —
  `settings.data_root` dynamic attribute on `app.state`.
- `src/pdomain_ocr_labeler_spa/core/logging_config.py:149` —
  `handler._pdlabeler_managed = True`.

**Justification.**

- `anyio` stubs do not fully model `to_thread.run_sync` as a callable
  attribute in the installed version; at runtime it works correctly.
- `settings.data_root` is set on `app.state` during bootstrap; basedpyright
  cannot narrow through the dynamic attribute pattern.
- `_pdlabeler_managed` is a dynamic attribute injected onto `StreamHandler`
  to mark it as managed by this logging config (for idempotent removal on
  reconfigure). `StreamHandler` has no such slot in the stubs; the injection
  is intentional and narrowly scoped.

---

### 19. `reportArgumentType` — basedpyright

**Suppression form:** `# pyright: ignore[reportArgumentType]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/api/projects.py:297` — `config_source` argument
  typed wider than the callee expects.
- `src/pdomain_ocr_labeler_spa/api/static_mounts.py:258` —
  `resources.as_file(traversable)` context-manager entry typed as `Path`
  by importlib.resources stubs but the stack expects `str | Path`.
- `src/pdomain_ocr_labeler_spa/api/pages.py:586, :587` — `char_bboxes_map` /
  `char_ranges_map` conditional expressions: `x if x else None` produces a
  wider type than the callee expects; guarded at runtime.

**Justification.** Narrowing gaps between importlib.resources stubs and the
runtime types, and between conditional-expression result types and callee
expectations. The runtime types are compatible.

---

### 20. `reportMissingImports` — basedpyright

**Suppression form:** `# type: ignore[import-untyped]  # pyright: ignore[reportMissingImports]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/core/text_normalize.py:21` —
  `pdomain_book_tools.text.normalize`.
- `src/pdomain_ocr_labeler_spa/core/persistence/config_yaml.py:92, :128` —
  `import yaml`.

**Justification.** `pdomain_book_tools` is not installed in the basedpyright dev
venv (stubs absent during type-checking only; works at runtime). `yaml`
(`PyYAML`) is an optional dependency; its stubs are absent in the dev venv.

---

### 21. `reportConstantRedefinition` — basedpyright

**Suppression form:** `# pyright: ignore[reportConstantRedefinition]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/core/text_normalize.py:27` —
  `_AVAILABLE = False` reassigned in a `try/except` block.
- `src/pdomain_ocr_labeler_spa/api/ocr_config.py:89` —
  `_AUTO_ROTATE_AVAILABLE = False` reassigned in a `try/except` block.

**Justification.** Module-level booleans are initialised as `False` then
reassigned to `True` if the optional import succeeds. This is the standard
optional-feature probe pattern; the name looks like a constant but is
intentionally reassigned once.

---

### 22. `reportGeneralTypeIssues` / `type: ignore[assignment]` — basedpyright

**Suppression form:** `# type: ignore[assignment]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/core/text_normalize.py:28` —
  `_pd_normalize = None` assigned to a callable-typed module-level name.

**Justification.** `_pd_normalize` is `None` initially and replaced by the
real function if the optional import succeeds. The `None` sentinel type
widens the declared type; the assignment suppression covers the initialisation.

---

### 23. `type: ignore[union-attr]` — basedpyright / mypy-compat

**Suppression form:** `# type: ignore[union-attr]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/core/model_selection.py:83` —
  `_selection_reason_annotation.__args__`.

**Justification.** `__args__` exists on `Union` types at runtime but is
typed as optional (`None` for non-generic types). The access is guarded by
the annotation structure; the suppression covers the union-member access.

---

### 24. `type: ignore[no-untyped-def]` — annotation backlog (mypy-compat codes)

**Suppression form:** `# type: ignore[no-untyped-def]` inline.

**Files:**

- `src/pdomain_ocr_labeler_spa/api/normalize.py:45` — `install_normalize_router(app)`
- `src/pdomain_ocr_labeler_spa/api/export.py:138` — `install_export_router(app)`
- `src/pdomain_ocr_labeler_spa/api/projects.py:793` — `install_projects_router(app)`
- `src/pdomain_ocr_labeler_spa/api/jobs.py:149` — `install_jobs_router(app)`
- `src/pdomain_ocr_labeler_spa/api/env_js.py:48` — `install_env_js(app)`
- `src/pdomain_ocr_labeler_spa/api/notifications.py:82` — `install_notifications_router(app)`
- `src/pdomain_ocr_labeler_spa/api/pages.py:1191` — `install_pages_router(app)`
- `src/pdomain_ocr_labeler_spa/api/ocr_config.py:532` — `install_ocr_config_router(app)`
- `src/pdomain_ocr_labeler_spa/api/lines_paragraphs.py:1395` — `install_lines_paragraphs_router(app)`
- `src/pdomain_ocr_labeler_spa/api/session_state.py:77` — `install_session_state_router(app)`
- `src/pdomain_ocr_labeler_spa/api/healthz.py:32` — `install_healthz(app)`
- `src/pdomain_ocr_labeler_spa/api/refine.py:162` — `install_refine_router(app)`
- `src/pdomain_ocr_labeler_spa/api/words.py:1341` — `install_words_router(app)`

**Status — needs review / annotation backlog.** These are mypy-style
suppressions (`# type: ignore[no-untyped-def]`). basedpyright uses
`# pyright: ignore[...]` with its own diagnostic names; the mypy codes are
not recognized by basedpyright and are therefore silencing nothing in CI.
These suppressions should be replaced with proper annotations (`app:
FastAPI`) in a future annotation pass.

---

### 25. `type: ignore[return-value]` (without pyright form)

**Suppression form:** `# type: ignore[return-value]` inline only (no pyright form).

**Files:**

- `src/pdomain_ocr_labeler_spa/api/pages.py:225` — `return loader` in a route
  typed to return a specific Pydantic model.
- `src/pdomain_ocr_labeler_spa/api/pages.py:856` — `loader=loader` argument.
- `src/pdomain_ocr_labeler_spa/api/pages.py:1146` — `return err`.
- `src/pdomain_ocr_labeler_spa/api/jobs.py:95` — `JSONResponse` short-circuit (see §17).
- `src/pdomain_ocr_labeler_spa/core/envelope_lift.py:54` — `return payload`.
- `src/pdomain_ocr_labeler_spa/core/jobs/handlers/reload_ocr.py:134` — `return loader`.

**Status — needs review.** These use only the mypy-compat code form;
basedpyright ignores them. They should be audited and converted to
`# pyright: ignore[reportReturnType]` (or the underlying type fixed) in
a future annotation pass.

---

## TypeScript/ESLint (frontend)

### 26. `react-hooks/exhaustive-deps` — ESLint

**Suppression form:** `// eslint-disable-next-line react-hooks/exhaustive-deps` inline.

**Files:**

- `frontend/src/hooks/useJobCompletionInvalidation.ts:114` — dep omitted to
  avoid infinite invalidation loop; callback reference is stable.
- `frontend/src/pages/RootPage.tsx:485` — intentional one-shot effect;
  dep would trigger on every render.
- `frontend/src/components/right-panel/sections/ReboxSection.tsx:76` —
  dep omitted; callback identity is guaranteed stable by the calling context.

**Justification.** These hooks intentionally omit certain dependencies to
avoid infinite re-render loops. Each site carries an inline note explaining
which dep is omitted.

---

### 27. `jsx-a11y/click-events-have-key-events`, `jsx-a11y/no-noninteractive-element-interactions`, `jsx-a11y/no-static-element-interactions` — ESLint

**Suppression form:** `// eslint-disable-next-line` inline.

**Files:**

- `frontend/src/components/ConfirmDialog.tsx:47` — dialog backdrop click-to-dismiss.
- `frontend/src/components/ExportDialog.tsx:219, :230` — dialog backdrop and inner-panel.
- `frontend/src/components/HotkeyHelpModal.tsx:100` — dialog backdrop.
- `frontend/src/components/OCRConfigModal.tsx:160` — dialog backdrop.
- `frontend/src/components/SourceFolderDialog.tsx:186, :197` — dialog backdrop and inner-panel.
- `frontend/src/components/WordEditDialog.tsx:150, :161` — dialog backdrop and inner-panel.
- `frontend/src/components/Splitter.tsx:113` — separator element captures mouse drag events.
- `frontend/src/components/shell/QuickSearch.tsx:45` — cosmetic click-to-focus wrapper.

**Justification.**

- Dialog backdrops: Escape close is handled by `useHotkey` / `onKeyDown`
  at the component level; ARIA requirements are satisfied by the
  `role=dialog` assignment. Backdrop click-to-dismiss is a UX convenience.
- Inner-panel `stopPropagation` elements: not interactive themselves;
  suppression is on the inner panel only to prevent event bubbling to the backdrop.
- Splitter separator: `role=separator` captures mouse events for resize;
  keyboard resize handled via parent-level hotkeys.
- QuickSearch wrapper: the inner `<input>` is the real interactive element
  with full keyboard support.

---

### 28. `jsx-a11y/no-autofocus` — ESLint

**Suppression form:** `{/* eslint-disable jsx-a11y/no-autofocus */}` block inline.

**Files:**

- `frontend/src/components/ConfirmDialog.tsx:69` — confirm button auto-focus.
- `frontend/src/components/SourceFolderDialog.tsx:278` — path input auto-focus.

**Justification.** Auto-focus in destructive-confirmation dialogs improves
keyboard UX: the user can press Enter/Escape immediately without tabbing.
For the source-folder dialog, auto-focusing the path input enables immediate
keyboard navigation on open.

---

### 29. `@typescript-eslint/no-explicit-any` — ESLint

**Suppression form:** `// eslint-disable-next-line @typescript-eslint/no-explicit-any` inline.

**Files:**

- `frontend/src/components/right-panel/LineDetail.tsx:214, :228` —
  `any` used on a JSON round-trip comparison path where the types are not
  exported by the consuming library.

**Justification.** The suppressed code handles a JSON comparison case where
the type is structurally `any` from the library boundary. A typed alternative
would require a custom interface that mirrors an undocumented internal.

---

### 30. `@typescript-eslint/no-non-null-assertion` — ESLint

**Suppression form:** `// eslint-disable-next-line @typescript-eslint/no-non-null-assertion` inline.

**Files:**

- `frontend/src/stores/ui-prefs.ts:56` — non-null assertion on a Zustand
  store selector result.

**Justification.** The value is guaranteed non-null by the store's initial
state contract; the selector path cannot return `null` for this key.
A defensive check would add noise without catching a real bug.
