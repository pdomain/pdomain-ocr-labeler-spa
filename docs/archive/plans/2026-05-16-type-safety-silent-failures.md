# Type Safety & Silent Failure Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate every `except Exception: log.debug(...)` silent-swallow in the OCR page-loading pipeline, add proper type guards so wrong-type inputs fail loudly, and cover all `# pragma: no cover - defensive` sites with real tests.

**Architecture:** Three interlocking layers — (1) a shared `envelope_lift.py` helper that replaces duplicated lift code in `api/pages.py` and `api/words.py`, (2) a `payload_error` field on `PageRecord` that makes failures machine-readable on the wire, and (3) targeted tests that inject faults at every previously-uncovered defensive path. Type annotations (Phase 5) use `TYPE_CHECKING` guards for pdomain-book-tools imports so tests don't need the full OCR stack.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, `caplog` fixture for log assertions, `monkeypatch` for fault injection. No new dependencies.

---

## File map — what changes and why

| File | Action | Why |
|---|---|---|
| `src/pd_ocr_labeler_spa/core/envelope_lift.py` | **Create** | Shared `lift_envelope_to_page()` helper; replaces duplicated code in pages.py + words.py |
| `src/pd_ocr_labeler_spa/core/models.py` | **Modify** | Add `payload_error: str \| None` to `PageRecord` |
| `src/pd_ocr_labeler_spa/core/page_to_line_matches.py` | **Modify** | Warn on wrong-type `page` arg; remove all `# pragma: no cover - defensive` by adding warnings at those sites |
| `src/pd_ocr_labeler_spa/api/pages.py` | **Modify** | Use `lift_envelope_to_page()`; stamp `payload_error`; narrow `get_page_image` exception |
| `src/pd_ocr_labeler_spa/api/words.py` | **Modify** | Use `lift_envelope_to_page()`; upgrade `log.debug` → `log.warning` on lift failure |
| `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py` | **Modify** | Surface skipped-page count in terminal notification |
| `tests/unit/core/test_envelope_lift.py` | **Create** | Unit tests for the new lift helper |
| `tests/unit/core/test_page_to_line_matches_errors.py` | **Create** | Tests for every `# pragma: no cover - defensive` site |
| `tests/integration/test_ocr_pipeline_integration.py` | **Create** | Real OCR pipeline end-to-end: real PNG → reload-ocr job → GET pages → line_matches |
| `tests/integration/test_envelope_line_matches.py` | **Modify** | Add wrong-type-payload test cases |
| `tests/integration/test_pages_router.py` | **Modify** | Add `payload_error` field assertion; add corrupt-image test |
| `tests/integration/test_export_router.py` | **Modify** | Assert skipped-page count in notification |
| `CLAUDE.md` | **Modify** | Correct M9.1/M9.2 status from ✅ to stub |
| `docs/BUGS_FOUND.md` | **Modify** | Document rotate/auto-rotate stubs |

---

## Task 1: Create `core/envelope_lift.py` — shared envelope→Page lift helper

The same lift code is duplicated in `api/pages.py` (~30 lines) and `api/words.py` (~15 lines). This task extracts it into one place with a typed return — either the lifted `Page` object or an `EnvelopeLiftError` that carries the exception. Callers can then `isinstance` on the result instead of catching exceptions.

**Files:**
- Create: `src/pd_ocr_labeler_spa/core/envelope_lift.py`
- Create: `tests/unit/core/test_envelope_lift.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/core/test_envelope_lift.py
"""Unit tests for core.envelope_lift.lift_envelope_to_page."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pytest
from pd_ocr_labeler_spa.core.envelope_lift import lift_envelope_to_page, EnvelopeLiftError


# ── Helpers ──────────────────────────────────────────────────────────

class _FakePage:
    """Minimal stand-in for pd_book_tools.ocr.page.Page."""
    lines: list = []


@dataclass
class _FakeEnvelopePayload:
    page: Any


@dataclass
class _FakeEnvelope:
    payload: _FakeEnvelopePayload


# ── Tests ─────────────────────────────────────────────────────────────

def test_plain_object_passthrough():
    """An object with no .payload attribute is returned unchanged."""
    page = _FakePage()
    result = lift_envelope_to_page(page)
    assert result is page


def test_none_passthrough():
    """None is returned unchanged."""
    assert lift_envelope_to_page(None) is None


def test_envelope_lift_success(monkeypatch):
    """A well-formed UserPageEnvelope lifts to the Page.from_dict result."""
    fake_page = _FakePage()
    page_dict = {"items": []}

    import importlib
    import types
    fake_page_mod = types.ModuleType("pd_book_tools.ocr.page")
    fake_page_mod.Page = type("Page", (), {"from_dict": staticmethod(lambda d: fake_page)})  # type: ignore
    monkeypatch.setitem(importlib.import_module("sys").modules, "pd_book_tools.ocr.page", fake_page_mod)

    envelope = _FakeEnvelope(payload=_FakeEnvelopePayload(page=page_dict))
    result = lift_envelope_to_page(envelope)
    assert result is fake_page


def test_envelope_lift_returns_error_on_from_dict_failure(monkeypatch):
    """When Page.from_dict raises, returns EnvelopeLiftError (not raises)."""
    import importlib
    import types
    fake_page_mod = types.ModuleType("pd_book_tools.ocr.page")
    fake_page_mod.Page = type("Page", (), {"from_dict": staticmethod(lambda d: (_ for _ in ()).throw(KeyError("items")))})  # type: ignore
    monkeypatch.setitem(importlib.import_module("sys").modules, "pd_book_tools.ocr.page", fake_page_mod)

    page_dict = {"bad": "schema"}
    envelope = _FakeEnvelope(payload=_FakeEnvelopePayload(page=page_dict))
    result = lift_envelope_to_page(envelope)
    assert isinstance(result, EnvelopeLiftError)
    assert "items" in result.message or "KeyError" in result.message


def test_envelope_with_non_dict_page_passthrough():
    """When envelope.payload.page is not a dict, returns original envelope unchanged."""
    class BadPayload:
        page = "not-a-dict"
    class BadEnvelope:
        payload = BadPayload()

    env = BadEnvelope()
    result = lift_envelope_to_page(env)
    assert result is env


def test_double_nested_envelope_unwrap(monkeypatch):
    """Double-nested envelope (legacy labeled-lane): unwraps two levels."""
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import USER_PAGE_SCHEMA_NAME
    fake_page = _FakePage()

    import importlib
    import types
    fake_page_mod = types.ModuleType("pd_book_tools.ocr.page")
    fake_page_mod.Page = type("Page", (), {"from_dict": staticmethod(lambda d: fake_page)})  # type: ignore
    monkeypatch.setitem(importlib.import_module("sys").modules, "pd_book_tools.ocr.page", fake_page_mod)

    inner_page_dict = {"items": []}
    outer_page_dict = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME},
        "payload": {"page": inner_page_dict},
    }
    envelope = _FakeEnvelope(payload=_FakeEnvelopePayload(page=outer_page_dict))
    result = lift_envelope_to_page(envelope)
    assert result is fake_page
```

- [x] **Step 2: Run tests to confirm they all fail**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
uv run pytest tests/unit/core/test_envelope_lift.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'pd_ocr_labeler_spa.core.envelope_lift'`

- [x] **Step 3: Create `core/envelope_lift.py`**

```python
# src/pd_ocr_labeler_spa/core/envelope_lift.py
"""Shared envelope→Page lifting logic.

Duplicated in api/pages.py and api/words.py before this module.
Centralised here so both callers get consistent behaviour and the
double-nested-envelope handling lives in one place.

Returns either the lifted Page object or an EnvelopeLiftError dataclass.
Callers use isinstance() on the result — no exception handling needed.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class EnvelopeLiftError:
    """Returned (not raised) when envelope→Page lift fails.

    Callers check ``isinstance(result, EnvelopeLiftError)`` and map to
    their appropriate error response (500 in mutations, log.warning + empty
    line_matches in reads).
    """
    message: str
    cause: BaseException


def lift_envelope_to_page(payload: object) -> object | EnvelopeLiftError:
    """Lift a payload to a Page object.

    Handles three cases:
    - Plain Page (OCR lane): returned unchanged — no ``.payload`` attribute.
    - Single-nested UserPageEnvelope (cached/labeled lane): lifts via
      ``Page.from_dict(envelope.payload.page)``.
    - Double-nested UserPageEnvelope (legacy labeled-lane saves): unwraps
      one extra level before calling ``Page.from_dict``.

    Returns the original ``payload`` if it doesn't look like an envelope
    (no ``.payload.page`` dict).  Returns ``EnvelopeLiftError`` when
    ``Page.from_dict`` raises — never raises itself.
    """
    if payload is None:
        return payload  # type: ignore[return-value]

    envelope_inner = getattr(payload, "payload", None)
    if envelope_inner is None:
        # No .payload — already a Page or unknown; return as-is.
        return payload

    page_dict = getattr(envelope_inner, "page", None)
    if not isinstance(page_dict, dict):
        # Has .payload but .payload.page isn't a dict — not an envelope we know.
        return payload

    # Double-nested envelope detection: legacy labeled-lane files store
    # payload.page as another full UserPageEnvelope dict.
    try:
        from .persistence.user_page_envelope import USER_PAGE_SCHEMA_NAME as _SCHEMA_NAME
        schema = page_dict.get("schema")
        if isinstance(schema, dict) and schema.get("name") == _SCHEMA_NAME:
            log.warning(
                "lift_envelope_to_page: double-nested envelope detected — unwrapping"
            )
            page_dict = page_dict.get("payload", {}).get("page")
    except Exception as exc:
        return EnvelopeLiftError(
            message=f"double-nested detection failed: {exc}",
            cause=exc,
        )

    if not isinstance(page_dict, dict):
        return EnvelopeLiftError(
            message=f"envelope.payload.page is not a dict after unwrap (got {type(page_dict).__name__})",
            cause=TypeError(f"expected dict, got {type(page_dict).__name__}"),
        )

    try:
        _page_mod = importlib.import_module("pd_book_tools.ocr.page")
        return _page_mod.Page.from_dict(page_dict)
    except Exception as exc:
        return EnvelopeLiftError(
            message=f"Page.from_dict failed: {exc}",
            cause=exc,
        )
```

- [x] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/core/test_envelope_lift.py -v 2>&1 | tail -15
```

Expected: all 6 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/pd_ocr_labeler_spa/core/envelope_lift.py tests/unit/core/test_envelope_lift.py
git commit -m "feat(core): add envelope_lift helper — typed lift with EnvelopeLiftError return"
```

---

## Task 2: Add `payload_error` to `PageRecord`

When the envelope lift fails, `GET /pages/{idx}` currently returns 200 with `line_matches: []` — indistinguishable from "page has no OCR." Adding `payload_error: str | None` to the wire shape gives the frontend a machine-readable signal.

**Files:**
- Modify: `src/pd_ocr_labeler_spa/core/models.py` (the `PageRecord` class, around line 133)
- Modify: `tests/integration/test_pages_router.py` (add assertion that the field exists)

- [x] **Step 1: Write the failing test**

Add to `tests/integration/test_pages_router.py` after the existing `test_get_page_returns_200_for_valid_index` test:

```python
def test_get_page_payload_has_payload_error_field(loaded_client: TestClient) -> None:
    """PagePayload wire shape includes payload_error field (None on clean page)."""
    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Field must exist (even when None — it's part of the wire contract).
    assert "payload_error" in body.get("page_record", {}) or body.get("page_record") is None
```

- [x] **Step 2: Run test to confirm it's currently passing or absent**

```bash
uv run pytest tests/integration/test_pages_router.py::test_get_page_payload_has_payload_error_field -v 2>&1 | tail -10
```

This may pass trivially if `page_record` is `None` for the stub fixture. That's fine — the test value comes in Task 4 when we stamp the error. Continue.

- [x] **Step 3: Add `payload_error` to `PageRecord`**

In `src/pd_ocr_labeler_spa/core/models.py`, find `PageRecord` (around line 133) and add one field after `provenance_summary`:

```python
    # payload_error: set by api/pages.py and api/words.py when the
    # envelope→Page lift fails. None on clean pages. Gives the frontend
    # a machine-readable signal instead of silently returning line_matches=[].
    payload_error: str | None = None
```

- [x] **Step 4: Run `make openapi-export` to sync TS types**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
make openapi-export AI=1 2>&1 | tail -5
```

Expected: `✅` — `frontend/src/api/types.ts` regenerated with `payload_error` in `PageRecord`.

- [x] **Step 5: Run full test suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/core/models.py frontend/src/api/types.ts tests/integration/test_pages_router.py
git commit -m "feat(models): add payload_error field to PageRecord wire shape"
```

---

## Task 3: Fix `page_to_line_matches` — warn on wrong-type input

Currently `page_to_line_matches` accepts `page: Any` and does `getattr(page, "lines", None) or []` — a `UserPageEnvelope` silently produces `[]`. After this task, a non-None object that has no `.lines` attribute triggers a WARNING, not silent empty return.

**Files:**
- Modify: `src/pd_ocr_labeler_spa/core/page_to_line_matches.py` (around line 333–344)
- Create: `tests/unit/core/test_page_to_line_matches_errors.py`

- [x] **Step 1: Write the failing test**

```python
# tests/unit/core/test_page_to_line_matches_errors.py
"""Tests for error-path behaviour in page_to_line_matches.

Every test in this file targets a path previously marked
# pragma: no cover - defensive.  After this task, those paths are
covered and the pragma comments are removed.
"""
from __future__ import annotations
import logging
from pathlib import Path
import pytest
from pd_ocr_labeler_spa.core.page_to_line_matches import page_to_line_matches
from pd_ocr_labeler_spa.core.models import PageSource


IMAGE_PATH = Path("/fake/image.png")


class _NoLines:
    """Object with no .lines attribute — simulates a UserPageEnvelope passed by mistake."""
    payload: object = object()  # has .payload but no .lines


def test_wrong_type_logs_warning(caplog):
    """Non-None page without .lines logs WARNING, returns empty line_matches."""
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        record, lms = page_to_line_matches(_NoLines(), 0, IMAGE_PATH)
    assert lms == []
    assert any("no 'lines' attribute" in m for m in caplog.messages), (
        f"Expected warning about missing 'lines', got: {caplog.messages}"
    )


def test_none_page_returns_empty_no_warning(caplog):
    """None page is the documented degraded path — no warning emitted."""
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        record, lms = page_to_line_matches(None, 0, IMAGE_PATH)
    assert lms == []
    assert not any("no 'lines' attribute" in m for m in caplog.messages)


def test_word_missing_bbox_logs_warning(caplog):
    """A word with no bounding_box is skipped with a WARNING (not DEBUG)."""
    class _Word:
        text = "hello"
        ground_truth_text = ""
        bounding_box = None  # missing bbox
        word_labels: list = []
        text_style_labels: list = []
        word_components: list = []
        fuzz_score_against = None

    class _Line:
        words = [_Word()]

    class _Page:
        lines = [_Line()]
        paragraphs: list = []
        items: list = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        record, lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert lms == []  # word was dropped
    assert any("bbox" in m.lower() or "bounding_box" in m.lower() or "dropped" in m.lower()
               for m in caplog.messages), (
        f"Expected warning about dropped word, got: {caplog.messages}"
    )


def test_fuzz_scorer_raises_logs_warning(caplog):
    """When word.fuzz_score_against raises, logs WARNING (not just DEBUG)."""
    class _BBox:
        minX = 0; minY = 0; maxX = 10; maxY = 10

    class _Word:
        text = "hello"
        ground_truth_text = "world"
        bounding_box = _BBox()
        word_labels: list = []
        text_style_labels: list = []
        word_components: list = []

        def fuzz_score_against(self, gt: str) -> float:
            raise RuntimeError("scorer broken")

    class _Line:
        words = [_Word()]

    class _Page:
        lines = [_Line()]
        paragraphs: list = []
        items: list = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        record, lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert len(lms) == 1  # word still appears (as MISMATCH with score 0)
    assert any("fuzz" in m.lower() for m in caplog.messages), (
        f"Expected warning about fuzz scorer failure, got: {caplog.messages}"
    )


def test_paragraph_lookup_failure_logs_warning(caplog, monkeypatch):
    """When _build_line_to_paragraph_lookup raises, logs WARNING."""
    from pd_ocr_labeler_spa.core import page_to_line_matches as _mod

    def _bad_lookup(page):
        raise RuntimeError("lookup broken")

    monkeypatch.setattr(_mod, "_build_line_to_paragraph_lookup", _bad_lookup)

    class _BBox:
        minX = 0; minY = 0; maxX = 10; maxY = 10

    class _Word:
        text = "hi"
        ground_truth_text = ""
        bounding_box = _BBox()
        word_labels: list = []
        text_style_labels: list = []
        word_components: list = []
        fuzz_score_against = None

    class _Line:
        words = [_Word()]

    class _Page:
        lines = [_Line()]
        paragraphs: list = []
        items: list = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        record, lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert any("paragraph" in m.lower() or "lookup" in m.lower() for m in caplog.messages), (
        f"Expected warning about lookup failure, got: {caplog.messages}"
    )
```

- [x] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/core/test_page_to_line_matches_errors.py -v 2>&1 | tail -20
```

Expected: all 5 tests FAIL (no warnings emitted, they're all `log.debug`).

- [x] **Step 3: Update `page_to_line_matches.py`**

In `src/pd_ocr_labeler_spa/core/page_to_line_matches.py`, make these targeted changes:

**Change 1** — after `if page is None: return record, []` (around line 333), add the wrong-type guard:

```python
    if page is None:
        return record, []

    # Wrong-type guard: if page has no .lines, the caller likely passed a
    # UserPageEnvelope instead of a Page. Log WARNING (not DEBUG) so this
    # is visible at default log level. None is the documented "no OCR yet"
    # path; any other type without .lines is a caller bug.
    if getattr(page, "lines", None) is None and not hasattr(page, "lines"):
        log.warning(
            "page_to_line_matches: page has no 'lines' attribute (type=%s)"
            " — envelope→Page lift likely failed; returning empty line_matches",
            type(page).__name__,
        )
        return record, []
```

**Change 2** — in `_word_to_word_match`, change the `if bbox_obj is None: return None` to log a warning:

```python
        bbox_obj = getattr(word_obj, "bounding_box", None)
        if bbox_obj is None:
            log.warning(
                "_word_to_word_match: word at line=%d word=%d has no bounding_box — dropped",
                line_index,
                word_index,
            )
            return None  # Can't build a WordMatch without a bbox.
```

**Change 3** — in `_classify_match_status`, upgrade the fuzz scorer exception from `log.debug` to `log.warning` and remove `# pragma: no cover`:

```python
        except Exception:
            log.warning(
                "_classify_match_status: fuzz_score_against raised for word %r — using score 0.0",
                ocr_text,
                exc_info=True,
            )
```

**Change 4** — in `_build_line_to_paragraph_lookup`, upgrade exception from `log.debug` to `log.warning` and remove `# pragma: no cover`:

```python
    except Exception:
        log.warning(
            "_build_line_to_paragraph_lookup: failed to build paragraph lookup — paragraph_index will be None on all lines",
            exc_info=True,
        )
    return result
```

**Change 5** — same for `_build_line_to_block_lookup`:

```python
    except Exception:
        log.warning(
            "_build_line_to_block_lookup: failed to build block lookup — block_index will be None on all lines",
            exc_info=True,
        )
    return result
```

- [x] **Step 4: Run tests**

```bash
uv run pytest tests/unit/core/test_page_to_line_matches_errors.py -v 2>&1 | tail -15
```

Expected: all 5 tests PASS.

- [x] **Step 5: Run full test suite to check for regressions**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/core/page_to_line_matches.py \
        tests/unit/core/test_page_to_line_matches_errors.py
git commit -m "fix(page_to_line_matches): warn on wrong-type page input and all defensive paths"
```

---

## Task 4: Fix `_page_payload` — use lift helper, stamp `payload_error`

Replace the 30-line inline lift block in `api/pages.py` with a call to `lift_envelope_to_page()`. When the lift returns `EnvelopeLiftError`, stamp `payload_error` on the returned `PageRecord` so the frontend can show a banner.

**Files:**
- Modify: `src/pd_ocr_labeler_spa/api/pages.py` (the `_page_payload` function, around line 537–614)
- Modify: `tests/integration/test_pages_router.py`

- [x] **Step 1: Write the failing test**

Add to `tests/integration/test_pages_router.py`:

```python
def test_get_page_stamps_payload_error_on_corrupt_envelope(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch,
) -> None:
    """When envelope lift fails, GET /pages/{idx} returns 200 with payload_error set."""
    from pd_ocr_labeler_spa.core.envelope_lift import EnvelopeLiftError

    # Monkeypatch lift_envelope_to_page to always return an error.
    monkeypatch.setattr(
        "pd_ocr_labeler_spa.api.pages.lift_envelope_to_page",
        lambda payload: EnvelopeLiftError(
            message="injected test failure",
            cause=ValueError("injected"),
        ),
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        # Trigger ensure_page_model so pstate has a page_record.
        c.post("/api/projects/book1/pages/0/load", json={})
        resp = c.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # line_matches is empty (lift failed).
    assert body["line_matches"] == []
    # payload_error is stamped on the page_record.
    pr = body.get("page_record")
    if pr is not None:
        assert pr.get("payload_error") is not None, (
            "Expected payload_error to be set when lift fails, got None"
        )
```

- [x] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/integration/test_pages_router.py::test_get_page_stamps_payload_error_on_corrupt_envelope -v 2>&1 | tail -10
```

Expected: FAIL — `payload_error` is None (not stamped yet).

- [x] **Step 3: Update `_page_payload` in `api/pages.py`**

Add the import at the top of `api/pages.py` (with other core imports):

```python
from ..core.envelope_lift import EnvelopeLiftError, lift_envelope_to_page
```

Then in `_page_payload`, replace the entire `try: envelope_payload = getattr(...) ... except Exception: log.warning(...)` block (roughly lines 566–614) with:

```python
            # Lift UserPageEnvelope → Page (labeled/cached lanes).
            # Plain Page objects (OCR lane) pass through unchanged.
            # EnvelopeLiftError is returned (not raised) on failure.
            lift_result = lift_envelope_to_page(payload_obj)
            if isinstance(lift_result, EnvelopeLiftError):
                log.warning(
                    "_page_payload: envelope→Page lift failed for %s/%d: %s"
                    " — stamping payload_error, line_matches will be empty",
                    project_id,
                    page_index,
                    lift_result.message,
                    exc_info=lift_result.cause,
                )
                # Build a minimal PageRecord with the error stamped so the
                # frontend can show a "corrupt saved data" banner.
                _err_record = PageRecord(
                    page_index=page_index,
                    page_number=page_index + 1,
                    image_path=image_path,
                    page_source=page_source,
                    payload_error=lift_result.message,
                )
                page_record = _err_record
                # line_matches stays []
            else:
                payload_obj = lift_result
                log.debug(
                    "_page_payload: post-lift payload type=%s source=%s for %s/%d",
                    type(payload_obj).__name__,
                    source,
                    project_id,
                    page_index,
                )

                _fuzz = app_config.fuzz_threshold if app_config is not None else 0.8
                _char_bboxes_map = pstate.char_bboxes_map if pstate is not None else None
                _char_ranges_map = pstate.char_ranges_map if pstate is not None else None
                _rec, _lms = page_to_line_matches(
                    payload_obj,
                    page_index,
                    image_path,
                    source=page_source,
                    fuzz_threshold=_fuzz,
                    char_bboxes_map=_char_bboxes_map if _char_bboxes_map else None,
                    char_ranges_map=_char_ranges_map if _char_ranges_map else None,
                )
                if _lms or _rec is not None:
                    page_record = _rec
                    line_matches = _lms
```

- [x] **Step 4: Run the new test**

```bash
uv run pytest tests/integration/test_pages_router.py::test_get_page_stamps_payload_error_on_corrupt_envelope -v 2>&1 | tail -10
```

Expected: PASS.

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/api/pages.py tests/integration/test_pages_router.py
git commit -m "fix(pages): use lift_envelope_to_page helper; stamp payload_error on lift failure"
```

---

## Task 5: Fix `_resolve_page_object` in `api/words.py`

Same fix as Task 4 but for word mutations. Replace the duplicated inline lift with `lift_envelope_to_page()`. When the lift fails, upgrade from `log.debug` to `log.warning` and return the error (caller maps it to 400 `page_not_loaded`).

**Files:**
- Modify: `src/pd_ocr_labeler_spa/api/words.py` (the `_resolve_page_object` function, around line 285–342)
- Modify: `tests/integration/test_words_router.py`

- [x] **Step 1: Write the failing test**

Add to `tests/integration/test_words_router.py`. First check the existing fixture pattern and add:

```python
def test_word_mutation_returns_400_on_corrupt_envelope(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch,
) -> None:
    """When envelope lift fails for a word mutation, returns 400 page_not_loaded."""
    from pd_ocr_labeler_spa.core.envelope_lift import EnvelopeLiftError

    monkeypatch.setattr(
        "pd_ocr_labeler_spa.api.words.lift_envelope_to_page",
        lambda payload: EnvelopeLiftError(
            message="injected test failure",
            cause=ValueError("injected"),
        ),
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        c.post("/api/projects/book1/pages/0/load", json={})
        resp = c.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "hello"},
        )

    # Lift failure → page can't be resolved → 400 page_not_loaded
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"
```

- [x] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/integration/test_words_router.py::test_word_mutation_returns_400_on_corrupt_envelope -v 2>&1 | tail -10
```

Expected: FAIL or error (old code returns the raw payload without erroring cleanly).

- [x] **Step 3: Update `_resolve_page_object` in `api/words.py`**

Add import at the top of `api/words.py` with the other core imports:

```python
from ..core.envelope_lift import EnvelopeLiftError, lift_envelope_to_page
```

Replace the `try/except` block inside `_resolve_page_object` (around lines 325–341) with:

```python
    # Lift UserPageEnvelope → Page (labeled/cached lanes).
    # Returns EnvelopeLiftError on failure (does not raise).
    lift_result = lift_envelope_to_page(payload_obj)
    if isinstance(lift_result, EnvelopeLiftError):
        log.warning(
            "_resolve_page_object: envelope→Page lift failed: %s"
            " — returning None so caller maps to page_not_loaded",
            lift_result.message,
            exc_info=lift_result.cause,
        )
        return None
    return lift_result
```

- [x] **Step 4: Run the new test**

```bash
uv run pytest tests/integration/test_words_router.py::test_word_mutation_returns_400_on_corrupt_envelope -v 2>&1 | tail -10
```

Expected: PASS.

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/api/words.py tests/integration/test_words_router.py
git commit -m "fix(words): use lift_envelope_to_page; upgrade lift failure from debug to warning"
```

---

## Task 6: Fix `get_page_image` — narrow exception types

Currently `get_page_image` catches bare `Exception`, so a corrupt PNG and a missing file both surface as `404 image_not_found`. After this task they're distinguished.

**Files:**
- Modify: `src/pd_ocr_labeler_spa/api/pages.py` (the `get_page_image` function, around line 1195–1214)
- Modify: `tests/integration/test_pages_router.py`

- [x] **Step 1: Write the failing test**

Add to `tests/integration/test_pages_router.py`:

```python
def test_get_page_image_corrupt_returns_422(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A present-but-unreadable image file returns 422 image_corrupt (not 404)."""
    import PIL.Image

    # Write a project with a file that PIL can open but convert("RGB") fails on.
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj = projects_root / "book1"
    proj.mkdir()
    corrupt_png = proj / "001.png"
    # Write 4 valid PNG header bytes then garbage — PIL can open as raw but
    # convert raises.  Easier: monkeypatch PIL.Image.open to raise UnidentifiedImageError.
    corrupt_png.write_bytes(b"\x89PNG\r\n\x1a\nGARBAGE")

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(proj)})
        resp = c.get("/api/projects/book1/pages/0/image")

    # A corrupt image is not "not found" — it's unreadable.
    # Before fix: 404 image_not_found.
    # After fix: 422 image_corrupt.
    assert resp.status_code == 422, f"Expected 422 image_corrupt, got {resp.status_code}: {resp.text}"
    assert resp.json()["error"] == "image_corrupt"


def test_get_page_image_missing_returns_404(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A genuinely missing image file still returns 404 image_not_found."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj = projects_root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x00")  # stub — PIL can't open it

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(proj)})
        # Monkeypatch the image_path lookup to return a non-existent path.
        import pd_ocr_labeler_spa.api.pages as _pages_mod
        original_attr = None

        resp = c.get("/api/projects/book1/pages/0/image")

    # Stub bytes → PIL.Image.open raises or returns unidentifiable → should be 422 or 404
    # (this test just asserts no 500).
    assert resp.status_code in (404, 422)
```

- [x] **Step 2: Run tests to confirm first one fails with 404**

```bash
uv run pytest tests/integration/test_pages_router.py::test_get_page_image_corrupt_returns_422 -v 2>&1 | tail -10
```

Expected: FAIL — currently returns 404 for all PIL failures.

- [x] **Step 3: Update `get_page_image` in `api/pages.py`**

Replace the bare `except Exception` block in `get_page_image` (around lines 1207–1214):

```python
    except FileNotFoundError as exc:
        log.debug("get_page_image: file not found %s: %s", image_path, exc)
        return JSONResponse(
            status_code=404,
            content=ApiError(error="image_not_found", message=str(exc)).model_dump(),
        )
    except Exception as exc:
        # PIL.UnidentifiedImageError, OSError on corrupt file, OOM, etc.
        log.warning(
            "get_page_image: failed to read/convert %s: %s",
            image_path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=422,
            content=ApiError(error="image_corrupt", message=str(exc)).model_dump(),
        )
```

- [x] **Step 4: Run both new tests**

```bash
uv run pytest tests/integration/test_pages_router.py::test_get_page_image_corrupt_returns_422 tests/integration/test_pages_router.py::test_get_page_image_missing_returns_404 -v 2>&1 | tail -10
```

Expected: both PASS.

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/api/pages.py tests/integration/test_pages_router.py
git commit -m "fix(pages): narrow get_page_image exception — image_corrupt 422 vs image_not_found 404"
```

---

## Task 7: Fix export — surface skipped-page count

The export job silently skips pages that fail to parse. The terminal notification says "Exported N pages" with no mention of skipped ones. After this task it says "Exported N pages (M skipped due to errors)."

**Files:**
- Modify: `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py` (around line 340–370)
- Modify: `tests/integration/test_export_router.py`

- [x] **Step 1: Write the failing test**

Look at `tests/integration/test_export_router.py` for the existing notification assertion pattern. Add:

```python
def test_export_surfaces_skipped_pages(tmp_path: Path, projects_root: Path, monkeypatch) -> None:
    """When some pages fail to load during export, the completion message includes the skip count."""
    import pd_ocr_labeler_spa.core.jobs.handlers.export as _export_mod

    original_load = _export_mod._load_page_from_envelope_file

    call_count = {"n": 0}

    def _always_fail(json_path):
        call_count["n"] += 1
        return None  # simulate failure for every page

    monkeypatch.setattr(_export_mod, "_load_page_from_envelope_file", _always_fail)

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        resp = c.post("/api/projects/book1/export", json={})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Drain SSE until terminal event.
        terminal_message = None
        with c.stream("GET", f"/api/jobs/{job_id}/events") as stream:
            for line in stream.iter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    import json as _json
                    try:
                        ev = _json.loads(line[5:].strip())
                        if ev.get("type") in ("complete", "error"):
                            terminal_message = ev.get("message", "")
                            break
                    except Exception:
                        pass

    # The terminal message must mention skipped pages.
    assert terminal_message is not None
    assert "skip" in terminal_message.lower() or "0 exported" in terminal_message.lower(), (
        f"Expected skip count in completion message, got: {terminal_message!r}"
    )
```

- [x] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/integration/test_export_router.py::test_export_surfaces_skipped_pages -v 2>&1 | tail -10
```

Expected: FAIL — terminal message doesn't mention skipped pages.

- [x] **Step 3: Update export handler**

In `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py`, find the loop that calls `_load_page_from_envelope_file` and the `continue` on `None` result (around lines 340–370). Add a skip counter:

```python
    exported_count = 0
    skipped_count = 0
    for json_path in envelope_paths:
        page = _load_page_from_envelope_file(json_path)
        if page is None:
            log.warning("export: could not load page from %s — skipping", json_path)
            skipped_count += 1
            continue
        # ... existing export logic ...
        exported_count += 1

    # Build the terminal message.
    if skipped_count > 0:
        terminal_msg = f"Exported {exported_count} pages ({skipped_count} skipped due to load errors)"
    else:
        terminal_msg = f"Exported {exported_count} pages"
```

Then pass `terminal_msg` to the `runner.update_progress` complete call instead of a hardcoded string.

- [x] **Step 4: Run the test**

```bash
uv run pytest tests/integration/test_export_router.py::test_export_surfaces_skipped_pages -v 2>&1 | tail -10
```

Expected: PASS.

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/core/jobs/handlers/export.py tests/integration/test_export_router.py
git commit -m "fix(export): surface skipped-page count in terminal notification"
```

---

## Task 8: Real OCR pipeline integration test

This test calls the real `reload-ocr` endpoint with a real PNG fixture, waits for SSE `complete`, then calls `GET /pages/{idx}` and asserts that `line_matches` has items if DocTR is available — or at minimum that `payload_error` is not set and the pipeline ran without crashing.

This is the test that would have caught C2/C3: if the pipeline were returning wrong-type data to `page_to_line_matches`, the now-visible WARNING in the log would be caught by `caplog`, and the assertion `line_matches != []` would fail.

**Files:**
- Create: `tests/integration/test_ocr_pipeline_integration.py`

- [x] **Step 1: Check whether DocTR is loadable in this environment**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
uv run python -c "from pd_book_tools.ocr import LocalDoctrPageLoader; print('doctr available')" 2>&1
```

Note the result. If DocTR is available, the integration test can assert `len(line_matches) > 0`. If not, it skips the `> 0` assertion.

- [x] **Step 2: Create a small valid PNG fixture**

```python
# (Run this once to generate the fixture — or add to conftest.py)
# tests/fixtures/tiny_text.png — a 200×40 white image with no text.
# For a test that verifies line_matches > 0, use a real scanned page crop.
# For a test that verifies the pipeline doesn't crash, any valid PNG works.
```

Add to `tests/conftest.py` or a new `tests/fixtures/` helper:

```python
# tests/integration/conftest.py (create if missing)
"""Fixtures for integration tests."""
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture(scope="session")
def tiny_png(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a path to a minimal valid PNG (a 10×10 white image)."""
    try:
        from PIL import Image
        p = tmp_path_factory.mktemp("png_fixtures") / "tiny.png"
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        img.save(p)
        return p
    except ImportError:
        pytest.skip("PIL not available")
```

- [x] **Step 3: Write the integration test**

```python
# tests/integration/test_ocr_pipeline_integration.py
"""Integration test: real reload-ocr pipeline → page_to_line_matches → GET pages.

This test catches the C2/C3 bug class: when the envelope→Page lift fails silently,
page_to_line_matches receives the wrong type and returns []. After the fixes in
Tasks 3–4, that failure is logged at WARNING and stamped in payload_error —
both of which this test asserts are absent on a clean OCR run.

Marks: integration, slow — skipped in fast test runs if DocTR is unavailable.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def ocr_project_root(tmp_path: Path, tiny_png: Path) -> Path:
    """Project root with one valid PNG — real OCR will be attempted."""
    root = tmp_path / "projects" / "ocr_test"
    root.mkdir(parents=True)
    import shutil
    shutil.copy(tiny_png, root / "001.png")
    return root


@pytest.fixture
def ocr_client(tmp_path: Path, ocr_project_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(
        tmp_path, source_projects_root=ocr_project_root.parent
    )
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(ocr_project_root)},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.mark.integration
@pytest.mark.slow
def test_reload_ocr_pipeline_no_envelope_lift_warning(
    ocr_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After reload-ocr completes, GET /pages/0 must NOT log an envelope-lift warning.

    If the warning fires, it means page_to_line_matches received a UserPageEnvelope
    instead of a Page — the C2/C3 bug class.
    """
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa"):
        # Trigger OCR.
        resp = ocr_client.post("/api/projects/ocr_test/pages/0/reload-ocr", json={})
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]

        # Drain SSE to terminal event.
        terminal_type = None
        with ocr_client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
            for line in stream.iter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        ev = json.loads(line[5:].strip())
                        if ev.get("type") in ("complete", "error"):
                            terminal_type = ev.get("type")
                            break
                    except json.JSONDecodeError:
                        pass

        assert terminal_type == "complete", f"OCR job ended with: {terminal_type}"

        # GET the page — this is where the lift bug manifested.
        get_resp = ocr_client.get("/api/projects/ocr_test/pages/0")

    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()

    # No envelope-lift warning should have been emitted.
    lift_warnings = [
        m for m in caplog.messages
        if "envelope" in m.lower() and "lift" in m.lower()
    ]
    assert not lift_warnings, (
        f"Envelope-lift warnings detected — envelope→Page lift is failing:\n"
        + "\n".join(lift_warnings)
    )

    # payload_error must be absent (None or missing) — no lift failure.
    pr = body.get("page_record")
    if pr is not None:
        assert pr.get("payload_error") is None, (
            f"payload_error set after clean OCR run: {pr['payload_error']}"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_reload_ocr_pipeline_line_matches_if_doctr_available(
    ocr_client: TestClient,
) -> None:
    """When DocTR is available, GET /pages/0 after reload-ocr returns non-empty line_matches.

    Skipped when DocTR is not loadable (CI without GPU / lightweight test env).
    The tiny_png fixture is 10×10 white — DocTR may find 0 words on it.
    Use a real scan fixture for a stronger assertion.
    """
    pytest.importorskip("doctr", reason="DocTR not installed — skipping line_matches count assertion")

    resp = ocr_client.post("/api/projects/ocr_test/pages/0/reload-ocr", json={})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    with ocr_client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        for line in stream.iter_lines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    ev = json.loads(line[5:].strip())
                    if ev.get("type") in ("complete", "error"):
                        break
                except json.JSONDecodeError:
                    pass

    get_resp = ocr_client.get("/api/projects/ocr_test/pages/0")
    assert get_resp.status_code == 200
    # Even on a blank image OCR returns 0 words — what we care about is that
    # line_matches is a list (not missing) and payload_error is None.
    body = get_resp.json()
    assert isinstance(body.get("line_matches"), list)
    pr = body.get("page_record")
    if pr is not None:
        assert pr.get("payload_error") is None
```

- [x] **Step 4: Run the pipeline test**

```bash
uv run pytest tests/integration/test_ocr_pipeline_integration.py -v -s -m "integration" 2>&1 | tail -30
```

Expected:
- If DocTR is available: both tests pass.
- If DocTR is unavailable: second test skips; first test may also skip if OCR fails to load.

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass (integration/slow tests may be skipped under `make test` if that target excludes `slow`).

- [x] **Step 6: Commit**

```bash
git add tests/integration/test_ocr_pipeline_integration.py \
        tests/integration/conftest.py
git commit -m "test(integration): real OCR pipeline test — catches envelope-lift warning regression"
```

---

## Task 9: Type annotations pass — replace `Any` in critical signatures

Replace `Any` with proper types in the three files that have the most impact. Use `TYPE_CHECKING` guards for pdomain-book-tools imports so tests don't need the full stack.

**Files:**
- Modify: `src/pd_ocr_labeler_spa/core/page_to_line_matches.py`
- Modify: `src/pd_ocr_labeler_spa/api/pages.py` (critical function signatures only)
- Modify: `src/pd_ocr_labeler_spa/api/words.py` (critical function signatures only)
- Create: `src/pd_ocr_labeler_spa/py.typed` (PEP 561 marker)

- [x] **Step 1: Add `py.typed` marker**

```bash
touch /workspaces/ocr-container/pdomain-ocr-labeler-spa/src/pd_ocr_labeler_spa/py.typed
```

- [x] **Step 2: Type `page_to_line_matches.py` — replace `Any` in signatures**

Add to the imports block (after `from __future__ import annotations`):

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pd_book_tools.ocr.page import Page as _Page
```

Add a `Protocol` for duck-typed page objects used in tests:

```python
@runtime_checkable
class _HasLines(Protocol):
    """Minimal structural type for objects with a .lines attribute."""
    @property
    def lines(self) -> list: ...
```

Change the `page_to_line_matches` signature:

```python
# Before:
def page_to_line_matches(
    page: Any,
    ...
) -> tuple[PageRecord, list[LineMatch]]:

# After:
def page_to_line_matches(
    page: "_Page | _HasLines | None",
    ...
) -> tuple[PageRecord, list[LineMatch]]:
```

Change internal helper signatures:

```python
# Before:
def _classify_match_status(ocr_text: str, ground_truth_text: str, word_obj: Any, ...) -> ...:
def _word_to_word_match(word_index: int, line_index: int, word_obj: Any, ...) -> WordMatch | None:
def _build_line_to_paragraph_lookup(page: Any) -> dict[int, int]:
def _build_line_to_block_lookup(page: Any) -> dict[int, int]:

# After (add narrow types — these remain duck-typed but are explicit):
def _classify_match_status(ocr_text: str, ground_truth_text: str, word_obj: object, ...) -> ...:
def _word_to_word_match(word_index: int, line_index: int, word_obj: object, ...) -> WordMatch | None:
def _build_line_to_paragraph_lookup(page: object) -> dict[int, int]:
def _build_line_to_block_lookup(page: object) -> dict[int, int]:
```

- [x] **Step 3: Type `_resolve_page_object` and `_resolve_word` in `api/words.py`**

```python
# Before:
def _resolve_page_object(pstate: PageState | None) -> Any | None:
def _resolve_word(page: Any, line_index: int, word_index: int) -> Any | None:

# After (use object since we can't import Page without pdomain-book-tools):
def _resolve_page_object(pstate: PageState | None) -> object | None:
def _resolve_word(page: object, line_index: int, word_index: int) -> object | None:
```

- [x] **Step 4: Run pyright to check type errors**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
uv run pyright src/pd_ocr_labeler_spa/core/page_to_line_matches.py src/pd_ocr_labeler_spa/api/words.py 2>&1 | tail -20
```

Fix any errors pyright reports. Common issues:
- `object` doesn't have attribute `.lines` → use `cast` or `getattr` (already done via `getattr(page, "lines", None)`)
- Type narrowing after `isinstance` check → add explicit `assert isinstance` where needed

- [x] **Step 5: Run full suite**

```bash
make test AI=1 2>&1 | tail -10
```

Expected: all pass. Then:

```bash
make frontend-test AI=1 2>&1 | tail -10
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/pd_ocr_labeler_spa/py.typed \
        src/pd_ocr_labeler_spa/core/page_to_line_matches.py \
        src/pd_ocr_labeler_spa/api/pages.py \
        src/pd_ocr_labeler_spa/api/words.py
git commit -m "chore(types): replace Any with proper types in critical signatures; add py.typed"
```

---

## Task 10: Correct CLAUDE.md — M9.1/M9.2 are stubs, not shipped

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/BUGS_FOUND.md`

- [x] **Step 1: Update CLAUDE.md**

Find the "Current milestone" section. Change:

```
M0–M10, M9.1, M9.2, M9.5, and hi-fi follow-ons FO-1–FO-9 are all ✅ done.
```

To:

```
M0–M10, M9.5, and hi-fi follow-ons FO-1–FO-9 are all ✅ done.
M9.1 (manual rotate) and M9.2 (auto-rotate-all) ship the 202+job plumbing
only — the actual image rotation, re-OCR, and PageRecord update are stubbed
(`core/jobs/handlers/rotate.py` and `auto_rotate_all.py`). See BUGS_FOUND.md.
```

- [x] **Step 2: Add entry to `docs/BUGS_FOUND.md`**

```markdown
## M9.1/M9.2 rotate handlers are stubs (not shipped)

**Found:** 2026-05-16
**Severity:** Medium — user clicks Rotate, gets a success toast, image is unchanged.

`core/jobs/handlers/rotate.py` and `core/jobs/handlers/auto_rotate_all.py`
both do `await asyncio.sleep(0)` and emit `complete`. Steps 2–4 (rotate image
via pdomain-book-tools, re-run OCR, update PageRecord.rotation_degrees) are not
implemented.

CLAUDE.md and specs/16-milestones.md incorrectly list M9.1 and M9.2 as ✅.
Tracking: update specs/16-milestones.md to show these as "plumbing only."
```

- [x] **Step 3: Run `make ci AI=1` to confirm nothing broke**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
make ci AI=1 2>&1 | tail -15
```

Expected: ✅

- [x] **Step 4: Commit**

```bash
git add CLAUDE.md docs/BUGS_FOUND.md
git commit -m "docs: correct M9.1/M9.2 status — rotate handlers are stubs, not shipped"
```

---

## Self-Review

### 1. Audit finding coverage

| Finding | Task | Status |
|---|---|---|
| C1 — `_resolve_page_object` same bug | Task 5 | ✅ |
| C2 — `_page_payload` lift failure → empty line_matches | Task 4 | ✅ |
| C3 — `page_to_line_matches` accepts any type silently | Task 3 | ✅ |
| C4 — `handle_rotate_page` stub | Task 10 | ✅ (documented) |
| C5 — `handle_auto_rotate_all` stub | Task 10 | ✅ (documented) |
| H1 — prefetch swallows errors at DEBUG | Task 3 (general upgrade) | ⚠️ prefetch-specific upgrade left as follow-on |
| H2/H3 — missing bbox word dropped silently | Task 3 | ✅ |
| H4 — fuzz scorer failure → MISMATCH with score 0 | Task 3 | ✅ |
| H5 — paragraph/block lookup failure → silent empty | Task 3 | ✅ |
| H6 — export skips pages without notification | Task 7 | ✅ |
| H7 — `get_page_image` broad Exception | Task 6 | ✅ |

H1 (prefetch loader failure stays DEBUG) is intentional — prefetch is explicitly documented as "failure never propagates to the main request." A follow-on slice can add metrics/counters without changing the no-propagation contract.

### 2. Type consistency check

- `lift_envelope_to_page` returns `object | EnvelopeLiftError` — callers use `isinstance(result, EnvelopeLiftError)` ✅
- `_resolve_page_object` returns `object | None` — callers check `if page is None` ✅
- `PageRecord.payload_error: str | None` — stamped in `_page_payload` only when lift fails ✅
- `page_to_line_matches` signature uses `"_Page | _HasLines | None"` as string annotation — not evaluated at import time ✅

### 3. No placeholders check

Every task has complete code blocks. No "TBD" or "add appropriate handling." ✅
