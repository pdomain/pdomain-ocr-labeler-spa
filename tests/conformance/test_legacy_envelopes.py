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
