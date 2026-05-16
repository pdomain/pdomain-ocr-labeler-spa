"""Conformance golden-file tests: ``UserPageEnvelope`` v2.1 legacy round-trip.

Spec authority:
- ``docs/specs/2026-05-12-testing-design.md`` — conformance test rationale.
- ``docs/architecture/09-persistence.md §2`` lines 102–109 — round-trip identity invariant.
- ``docs/architecture/09-persistence.md §12`` — test checklist for golden-fixture tests.
- ``docs/architecture/01-data-models.md §3`` — ``UserPageEnvelope`` v2.1 wire shape.
- D-003 (docs/specs/2026-05-12-persistence-design.md) — byte-compat guarantee.

What these tests guard:

``tests/conformance/fixtures/`` contains frozen copies of ``UserPageEnvelope``
v2.1 JSON files — the canonical format written by the legacy
``pd-ocr-labeler`` and expected by the SPA. Any change to ``parse_envelope``
or ``envelope_to_dict`` that breaks these fixtures means v2.1 compat is broken.

Round-trip contract:

    json.loads(fixture) → parse_envelope → envelope_to_dict == original_dict

The assertion is dict-equal (not bytes-equal): JSON serialisation of identical
dicts is deterministic in Python 3.7+ but whitespace/ordering may differ across
encoder configurations. Structural equivalence is the meaningful invariant.

To add a fixture:
  1. Save the envelope JSON to ``tests/conformance/fixtures/<name>.json``.
  2. The parametrised test picks it up automatically.
  3. Add a note in ``tests/conformance/fixtures/README.md`` about its provenance.

Issue: #245
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    envelope_to_dict,
    is_user_page_envelope,
    parse_envelope,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


# ── conformance: fixtures directory has content ───────────────────────────────


def test_conformance_fixtures_dir_has_at_least_one_file() -> None:
    """Guard against a silently empty fixture directory making the
    parametrised test trivially pass with zero cases."""
    paths = _fixture_paths()
    assert len(paths) >= 1, (
        f"No *.json fixtures in {FIXTURES_DIR}. "
        "Add at least one v2.1 envelope fixture (copy from legacy saved-pages or "
        "export from a running labeler session)."
    )


# ── conformance: round-trip identity ─────────────────────────────────────────


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.name)
def test_legacy_envelope_round_trip(fixture_path: Path) -> None:
    """parse_envelope → envelope_to_dict must reproduce the original dict.

    Any regression here means v2.1 backward-compatibility is broken —
    the SPA can no longer correctly read envelopes that the legacy labeler
    (or a previous SPA version) has written.

    Assertion is dict-equal (structural, not byte-equal) because JSON
    serialisation may use different whitespace depending on encoder
    configuration. Structural equivalence is the meaningful round-trip
    invariant.
    """
    raw_text = fixture_path.read_text(encoding="utf-8")
    original_data = json.loads(raw_text)

    assert is_user_page_envelope(original_data), (
        f"{fixture_path.name} is not recognised as a user_page envelope "
        f"(schema.name mismatch or missing). "
        "Verify the fixture was exported from pd-ocr-labeler or pd-ocr-labeler-spa."
    )

    parsed = parse_envelope(original_data)
    rebuilt = envelope_to_dict(parsed)

    assert rebuilt == original_data, (
        f"Round-trip failed for {fixture_path.name} — v2.1 compat broken.\n"
        f"  Keys missing from rebuilt : {sorted(set(original_data) - set(rebuilt))}\n"
        f"  Keys extra in rebuilt     : {sorted(set(rebuilt) - set(original_data))}"
    )


# ── conformance: schema field preservation ───────────────────────────────────


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.name)
def test_legacy_envelope_schema_version_preserved(fixture_path: Path) -> None:
    """Schema version survives the round-trip unchanged.

    Silently bumping the version in ``envelope_to_dict`` would cause
    the legacy labeler to refuse to open SPA-written files (it validates
    version on read).
    """
    raw_text = fixture_path.read_text(encoding="utf-8")
    original_data = json.loads(raw_text)
    original_version = original_data["schema"]["version"]

    parsed = parse_envelope(original_data)
    rebuilt = envelope_to_dict(parsed)

    assert rebuilt["schema"]["version"] == original_version, (
        f"Schema version changed during round-trip for {fixture_path.name}: "
        f"{original_version!r} → {rebuilt['schema']['version']!r}"
    )


# ── GAP-4: legacy "footnote" → "right_footnote" migration ────────────────────


_MINIMAL_ENVELOPE: dict = {
    "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
    "provenance": {
        "saved_at": "2024-01-01T00:00:00Z",
        "saved_by": "Save Page",
        "source_lane": "labeled",
        "app": {"name": "pd_ocr_labeler", "version": "unknown"},
        "toolchain": {"python": "3.11.0", "pd_book_tools": "unknown"},
        "ocr": {"engine": "unknown", "models": []},
    },
    "source": {
        "project_id": "test_proj",
        "page_index": 0,
        "page_number": 1,
        "image_path": "test_proj_001.png",
    },
    "payload": {"page": {}},
}


def test_load_envelope_migrates_legacy_footnote() -> None:
    """Envelope with "footnote" key in word_attributes is migrated to
    "right_footnote" on load.

    Legacy pd-ocr-labeler stored footnote attributes under the bare
    "footnote" key.  A later refactor split this into "left_footnote"
    and "right_footnote".  The SPA must silently migrate old files so
    that footnote labels are not silently dropped (GAP-4).

    Parity ref: pd-ocr-labeler/pd_ocr_labeler/operations/page_operations.py:1263-1273.
    """
    import copy

    data = copy.deepcopy(_MINIMAL_ENVELOPE)
    data["payload"]["word_attributes"] = {
        "word_1_2": {"italic": False, "footnote": True},
    }

    result = parse_envelope(data)

    assert result.payload.word_attributes is not None
    word_attrs = result.payload.word_attributes["word_1_2"]
    assert "right_footnote" in word_attrs, "Legacy 'footnote' key must be migrated to 'right_footnote'"
    assert word_attrs["right_footnote"] is True
    assert "footnote" not in word_attrs, "Legacy 'footnote' key must be removed after migration"
    # Other attributes must survive the migration unchanged.
    assert "italic" in word_attrs
    assert word_attrs["italic"] is False


def test_load_envelope_keeps_right_footnote_when_both_present() -> None:
    """When both "footnote" and "right_footnote" are present, the existing
    "right_footnote" wins and "footnote" is dropped.

    This guards hand-edited or partially migrated files: the explicit
    "right_footnote" value takes precedence; we do not overwrite it.
    """
    import copy

    data = copy.deepcopy(_MINIMAL_ENVELOPE)
    data["payload"]["word_attributes"] = {
        "word_3_1": {"footnote": True, "right_footnote": False},
    }

    result = parse_envelope(data)

    assert result.payload.word_attributes is not None
    word_attrs = result.payload.word_attributes["word_3_1"]
    # right_footnote was already present — its value is preserved.
    assert word_attrs.get("right_footnote") is False
    assert "footnote" not in word_attrs


def test_load_envelope_no_migration_without_footnote_key() -> None:
    """Envelopes that never had "footnote" (i.e. modern files) are
    unaffected by the migration — "right_footnote" must be present only
    if it was explicitly in the file.
    """
    import copy

    data = copy.deepcopy(_MINIMAL_ENVELOPE)
    data["payload"]["word_attributes"] = {
        "word_2_5": {"bold": True, "right_footnote": True},
    }

    result = parse_envelope(data)

    assert result.payload.word_attributes is not None
    word_attrs = result.payload.word_attributes["word_2_5"]
    assert word_attrs == {"bold": True, "right_footnote": True}
