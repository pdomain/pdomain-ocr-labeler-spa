"""Golden round-trip tests for ``UserPageEnvelope`` v2.1.

Spec authority:

- ``specs/09-persistence.md §2`` lines 102–109 — round-trip identity
  invariant: ``parse → rebuild`` must equal the original data.
- ``specs/09-persistence.md §11`` lines 343–357 — incompatible_envelope:
  schema versions the SPA doesn't understand raise an error with code
  ``incompatible_envelope`` that maps to ``422``.
- ``specs/09-persistence.md §12`` lines 362–373 — test checklist naming
  ``test_envelope_round_trip.py`` as the golden-fixture test.
- ``specs/01-data-models.md §3`` lines 503–576 — ``UserPageEnvelope``
  v2.1 wire shape.
- ``docs/specs/2026-05-12-persistence-design.md`` — D-003 byte-compat
  guarantee.

Issue #220 acceptance:

- ``build_envelope`` / ``parse_envelope`` implemented — validated by
  importing and calling them below.
- Unknown schema version returns ``incompatible_envelope`` — validated by
  ``test_parse_envelope_rejects_incompatible_version``.
- Round-trip golden test passes against fixture envelopes — validated by
  the parametrised ``test_fixture_round_trip`` below.

Fixtures live in ``tests/fixtures/envelopes/``.  They are
byte-compatible v2.1 envelopes that represent saved pages from the
``browser-test-project`` project (mirroring what the legacy labeler
would write). The test loads each from disk, parses it, serialises back,
and asserts the output equals the original parsed dict — modulo JSON
whitespace (we compare dict-to-dict, not bytes-to-bytes, because JSON
serialisation of identical dicts is deterministic in Python 3.7+ but
whitespace may differ).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.exceptions import IncompatibleEnvelopeError
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    envelope_to_dict,
    is_user_page_envelope,
    parse_envelope,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "envelopes"


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


# ── golden round-trip against fixture files ──────────────────────────────


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.name)
def test_fixture_round_trip(fixture_path: Path) -> None:
    """parse → write yields the same dict as the original JSON.

    This is the D-003 byte-compat guard: every fixture that represents a
    legacy-written envelope must survive a SPA parse+write cycle
    unchanged. The test is parametrised over all ``*.json`` files in
    ``tests/fixtures/envelopes/`` so adding a new fixture automatically
    exercises it.
    """
    raw_text = fixture_path.read_text(encoding="utf-8")
    original_data = json.loads(raw_text)

    # Type guard confirms the fixture is a user_page envelope.
    assert is_user_page_envelope(original_data), (
        f"{fixture_path.name} is not a user_page envelope — check its schema.name"
    )

    parsed = parse_envelope(original_data)
    rebuilt = envelope_to_dict(parsed)

    assert rebuilt == original_data, (
        f"Round-trip failed for {fixture_path.name}:\n"
        f"  diff keys missing from rebuilt: {set(original_data) - set(rebuilt)}\n"
        f"  diff keys extra in rebuilt: {set(rebuilt) - set(original_data)}"
    )


def test_fixture_dir_has_at_least_one_file() -> None:
    """Guard against a silent empty-fixture directory that would make
    the parametrised test trivially pass with zero cases."""
    paths = _fixture_paths()
    assert len(paths) >= 1, (
        f"No *.json files found in {FIXTURES_DIR}. Add at least one v2.1 envelope fixture."
    )


# ── incompatible_envelope: unknown schema version → IncompatibleEnvelopeError ──


def test_parse_envelope_accepts_v2_1() -> None:
    """v2.1 is the canonical supported version — must not raise."""
    data = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "provenance": {"saved_at": ""},
        "source": {"project_id": "p", "page_index": 0, "page_number": 1, "image_path": "0.png"},
        "payload": {"page": {}},
    }
    env = parse_envelope(data)
    assert env.schema.version == "2.1"


def test_parse_envelope_accepts_v2_2() -> None:
    """v2.2 is the additive rotation bump (D-032 / Q-A1) — spec says
    readers MUST accept both 2.1 and 2.2."""
    data = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.2"},
        "provenance": {"saved_at": ""},
        "source": {"project_id": "p", "page_index": 0, "page_number": 1, "image_path": "0.png"},
        "payload": {"page": {}},
    }
    env = parse_envelope(data)
    assert env.schema.version == "2.2"


def test_parse_envelope_rejects_incompatible_version() -> None:
    """spec §11: unknown / incompatible schema version raises
    ``IncompatibleEnvelopeError``.  The error handler maps this to 422
    ``incompatible_envelope``.

    A major version bump (3.0, 10.0, …) is the clearest incompatible
    case — the SPA was built against v2.x and cannot safely read v3.x.
    """
    data = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "3.0"},
        "provenance": {"saved_at": ""},
        "source": {"project_id": "p", "page_index": 0, "page_number": 1, "image_path": "0.png"},
        "payload": {"page": {}},
    }
    with pytest.raises(IncompatibleEnvelopeError) as exc_info:
        parse_envelope(data)

    err = exc_info.value
    # The error message must include the offending version and something
    # about the supported range so the SPA toast is informative.
    assert "3.0" in str(err)
    assert err.version == "3.0"


def test_parse_envelope_rejects_major_version_1() -> None:
    """v1.x predates the schema — not a valid UserPageEnvelope version."""
    data = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "1.0"},
        "provenance": {"saved_at": ""},
        "source": {},
        "payload": {"page": {}},
    }
    with pytest.raises(IncompatibleEnvelopeError):
        parse_envelope(data)


def test_incompatible_envelope_error_has_version_attribute() -> None:
    """``IncompatibleEnvelopeError.version`` carries the encountered
    version string so the API handler can embed it in the response body
    without string-parsing the message."""
    err = IncompatibleEnvelopeError(version="9.9", supported=["2.1", "2.2"])
    assert err.version == "9.9"
    assert "9.9" in str(err)


def test_incompatible_envelope_error_supported_list() -> None:
    """``IncompatibleEnvelopeError.supported`` is the list of versions
    the SPA can read — embedded in the error so the route/handler can
    format the toast: "Upgrade to read v{version}; this binary supports
    {supported}."
    """
    err = IncompatibleEnvelopeError(version="3.0", supported=["2.1", "2.2"])
    assert err.supported == ["2.1", "2.2"]
    assert "2.1" in str(err)
    assert "2.2" in str(err)
