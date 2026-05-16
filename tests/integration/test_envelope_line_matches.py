"""Regression tests for envelope→Page lift in ``_page_payload``.

Bug: ``GET /api/projects/{id}/pages/{idx}`` always returned
``line_matches: []`` for labeled and cached lanes, even after OCR had run.

Root cause (two layers):

1. The labeled-lane ``load_labeled`` stores ``payload=UserPageEnvelope``
   (not a ``Page`` object).  The lift in ``_page_payload`` tries
   ``Page.from_dict(envelope.payload.page)`` — but some legacy files
   (produced by older pd-ocr-labeler saves) store ``payload.page`` as
   *another full UserPageEnvelope dict* rather than a bare
   ``Page.to_dict()`` output.  ``Page.from_dict`` raises
   ``KeyError: 'items'`` on those files; the exception was previously
   swallowed by ``log.debug``, leaving ``payload_obj`` as the raw
   ``UserPageEnvelope`` which has no ``.lines``, so
   ``page_to_line_matches`` returned ``[]``.

2. Fix: detect the double-nested case (``page_dict`` has
   ``schema.name == "pd_ocr_labeler.user_page"``) and unwrap one more
   level before calling ``Page.from_dict``.  Also promote the
   exception log from ``debug`` → ``warning`` so future failures are
   visible.

These tests do NOT run real OCR (no DocTR import needed).  They inject
a pre-built ``PageLoadOutcome`` directly onto ``PageState.page_record``
so the route's ``_page_payload`` exercises the lift path.

The two fixture shapes tested:

- ``page_dict_normal`` — a ``Page.to_dict()``-compatible dict (the
  correct cached-lane shape).  Should lift cleanly in both before and
  after the fix.
- ``page_dict_double_nested`` — ``Page.to_dict()`` wrapped inside a
  full ``UserPageEnvelope`` dict (the broken labeled-lane shape).  Was
  returning ``line_matches: []`` before the fix.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    USER_PAGE_SCHEMA_NAME,
    UserPageEnvelope,
    UserPagePayload,
    UserPageProvenance,
    UserPageSchema,
    UserPageSource,
)
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings

# ── helpers ──────────────────────────────────────────────────────────────


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


def _minimal_page_dict(page_index: int = 0) -> dict[str, Any]:
    """Build a ``Page.to_dict()``-compatible dict with one line containing one word.

    Uses the nested Block → Paragraph → Line → Word structure that
    ``Page.from_dict`` and ``Page.lines`` expect.
    """
    bb = {
        "top_left": {"x": 0, "y": 0, "is_normalized": False},
        "bottom_right": {"x": 10, "y": 10, "is_normalized": False},
        "is_normalized": False,
    }
    word_dict = {
        "type": "Word",
        "text": "hello",
        "bounding_box": bb,
        "ocr_confidence": None,
        "word_labels": [],
        "text_style_labels": ["regular"],
        "text_style_label_scopes": {"regular": "whole"},
        "word_components": [],
        "baseline": None,
        "ground_truth_text": None,
        "ground_truth_bounding_box": None,
        "ground_truth_match_keys": {},
    }
    line_block = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "block_role_labels": [],
        "block_position_labels": [],
        "line_role_labels": [],
        "line_position_labels": [],
        "baseline": None,
        "bounding_box": bb,
        "items": [word_dict],
        "override_page_sort_order": None,
        "unmatched_ground_truth_words": [],
        "additional_block_attributes": {},
        "base_ground_truth_text": "",
    }
    para_block = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "block_role_labels": [],
        "block_position_labels": [],
        "line_role_labels": [],
        "line_position_labels": [],
        "baseline": None,
        "bounding_box": bb,
        "items": [line_block],
        "override_page_sort_order": None,
        "unmatched_ground_truth_words": [],
        "additional_block_attributes": {},
        "base_ground_truth_text": "",
    }
    top_block = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "block_role_labels": [],
        "block_position_labels": [],
        "line_role_labels": [],
        "line_position_labels": [],
        "baseline": None,
        "bounding_box": bb,
        "items": [para_block],
        "override_page_sort_order": None,
        "unmatched_ground_truth_words": [],
        "additional_block_attributes": {},
        "base_ground_truth_text": "",
    }
    return {
        "type": "Page",
        "width": 100,
        "height": 100,
        "page_index": page_index,
        "bounding_box": bb,
        "items": [top_block],
        "ocr_provenance": None,
    }


def _make_double_nested_envelope_dict(page_index: int = 0) -> dict[str, Any]:
    """Build the *broken* legacy shape: a ``Page.to_dict()`` dict wrapped inside
    a full ``UserPageEnvelope`` dict, which is then stored as ``payload.page``.

    This is what some older pd-ocr-labeler saves produced.  Reading such a
    file gives ``envelope.payload.page == { "schema": ..., "provenance": ...,
    "source": ..., "payload": { "page": <actual Page dict> } }``.
    """
    page_dict = _minimal_page_dict(page_index)
    # The inner UserPageEnvelope dict (the double-nesting layer).
    inner_envelope_dict: dict[str, Any] = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "provenance": {"app": {}, "toolchain": {}},
        "source": {"lane": "labeled"},
        "payload": {"page": page_dict},
    }
    return inner_envelope_dict


def _make_envelope(page_dict: dict[str, Any]) -> UserPageEnvelope:
    """Wrap *page_dict* in a ``UserPageEnvelope`` as the labeled/cached lane does."""
    return UserPageEnvelope(
        schema=UserPageSchema(),
        provenance=UserPageProvenance(),
        source=UserPageSource(),
        payload=UserPagePayload(page=page_dict),
    )


def _seed_page_state(
    client: TestClient,
    *,
    page_index: int,
    envelope: UserPageEnvelope,
    source: PageSource = PageSource.FILESYSTEM,
) -> None:
    """Inject a ``PageLoadOutcome`` directly onto the in-memory ``PageState``."""
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=source,
        payload=envelope,
    )
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    existing = project_state._page_states.get(page_index)
    if existing is None:
        existing = PageState(page_index=page_index)
        project_state._page_states[page_index] = existing
    existing.page_record = outcome


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    # Minimal stub images — just need to exist (PIL reads dims; 1x1 PNG)
    _tiny_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (proj / "001.png").write_bytes(_tiny_png)
    (proj / "002.png").write_bytes(_tiny_png)
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project already loaded (book1, 2 pages)."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


# ── tests ─────────────────────────────────────────────────────────────────


def test_cached_lane_normal_page_dict_yields_line_matches(
    loaded_client: TestClient,
) -> None:
    """Cached-lane ``payload.page`` is a proper ``Page.to_dict()`` dict.

    The lift path succeeds: ``Page.from_dict(page_dict)`` → ``Page`` object
    → ``page_to_line_matches`` returns non-empty ``line_matches``.

    This lane was already working before the fix; this test is a
    non-regression guard.
    """
    page_dict = _minimal_page_dict(page_index=0)
    envelope = _make_envelope(page_dict)
    _seed_page_state(loaded_client, page_index=0, envelope=envelope, source=PageSource.CACHED_OCR)

    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    page_record = body.get("page_record") or {}
    assert page_record.get("page_source") == "cached_ocr"
    assert len(body["line_matches"]) > 0, (
        "cached_ocr lane with a valid Page dict should produce non-empty line_matches"
    )


def test_labeled_lane_double_nested_envelope_yields_line_matches(
    loaded_client: TestClient,
) -> None:
    """Labeled-lane ``payload.page`` is a *double-nested* UserPageEnvelope dict.

    Before the fix, ``Page.from_dict(page_dict)`` raised ``KeyError: 'items'``
    (swallowed silently), leaving ``payload_obj`` as the raw
    ``UserPageEnvelope`` → ``line_matches: []``.

    After the fix, the lift code detects the double-nesting (``schema.name``
    matches ``USER_PAGE_SCHEMA_NAME``), unwraps one level, and
    ``Page.from_dict`` succeeds → non-empty ``line_matches``.
    """
    double_nested = _make_double_nested_envelope_dict(page_index=0)
    envelope = _make_envelope(double_nested)
    _seed_page_state(loaded_client, page_index=0, envelope=envelope, source=PageSource.FILESYSTEM)

    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    page_record = body.get("page_record") or {}
    assert page_record.get("page_source") == "filesystem"
    assert len(body["line_matches"]) > 0, (
        "labeled lane with double-nested envelope should produce non-empty line_matches after fix"
    )


def test_no_line_matches_when_envelope_page_is_empty_dict(
    loaded_client: TestClient,
) -> None:
    """When ``payload.page`` is an empty dict (malformed), ``line_matches`` is
    empty but the endpoint still returns 200 (graceful degradation).
    """
    envelope = _make_envelope({})
    _seed_page_state(loaded_client, page_index=0, envelope=envelope, source=PageSource.FILESYSTEM)

    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["line_matches"] == [], "empty page dict should produce empty line_matches gracefully"


def test_labeled_lane_with_real_fixture_envelope() -> None:
    """Smoke-test against the real on-disk exercise-fixture labeled-lane file.

    Reads the actual ``projectID629292e7559a8_001.json`` from the e2e test
    fixtures, parses it as ``UserPageEnvelope``, confirms it is double-nested,
    then calls ``Page.from_dict`` on the correctly unwrapped inner page dict.

    This test validates the fix logic in isolation (no HTTP stack needed).
    Does NOT require DocTR — uses only ``Page.from_dict`` from pd_book_tools.
    """
    fixture_path = (
        Path(__file__).parent.parent
        / "e2e"
        / "fixtures"
        / "projects"
        / "exercise-fixture"
        / "labeled-projects"
        / "projectID629292e7559a8"
        / "projectID629292e7559a8_001.json"
    )
    assert fixture_path.exists(), f"fixture not found: {fixture_path}"

    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload_page = raw["payload"]["page"]

    # Confirm it is double-nested.
    assert isinstance(payload_page.get("schema"), dict), (
        "expected double-nested envelope dict with 'schema' key"
    )
    assert payload_page["schema"]["name"] == USER_PAGE_SCHEMA_NAME, (
        "inner dict schema name should match USER_PAGE_SCHEMA_NAME"
    )

    # Unwrap one level (mirrors the fix in _page_payload).
    inner_page_dict = payload_page["payload"]["page"]
    assert "items" in inner_page_dict, "unwrapped dict should have 'items' key"

    # Page.from_dict must succeed on the unwrapped dict.
    import importlib

    page_mod = importlib.import_module("pd_book_tools.ocr.page")
    page_obj = page_mod.Page.from_dict(inner_page_dict)
    lines = page_obj.lines
    assert len(lines) > 0, f"real fixture page should have at least one line after unwrapping; got {lines}"
