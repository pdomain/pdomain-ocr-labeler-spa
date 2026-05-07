"""Reader/writer pins for ``core/persistence/user_page_envelope.py``.

Spec authority:

- ``specs/01-data-models.md §3`` lines 503–576 — ``UserPageEnvelope``
  v2.1 / v2.2 wire shape.
- ``specs/09-persistence.md §2`` lines 44–110 — schema details, reader
  surface (``is_user_page_envelope``, ``parse_envelope``,
  ``build_envelope``), round-trip identity invariant.

Byte-compat reference: legacy
``pd-ocr-labeler/pd_ocr_labeler/models/user_page_persistence.py``
(``UserPageEnvelope.from_dict`` / ``to_dict``). The SPA and legacy
share the on-disk file under D-003, so the reader MUST accept every
shape legacy writes and the writer MUST produce a dict legacy reads
without changes.

Slice 8b-iii ships:

- ``UserPageEnvelope`` + nested dataclasses (``UserPageSchema``,
  ``UserPageProvenance``, ``ProvenanceApp``, ``ProvenanceToolchain``,
  ``OCRProvenance``, ``OCRModelProvenance``, ``UserPageSource``,
  ``SourceImageFingerprint``, ``UserPagePayload``).
- ``is_user_page_envelope(data) -> bool`` type guard.
- ``parse_envelope(data) -> UserPageEnvelope`` permissive reader
  matching legacy ``from_dict`` semantics (tolerates missing keys,
  coerces types where legacy did).
- ``envelope_to_dict(envelope) -> dict`` writer mirroring legacy
  ``to_dict`` (omits empty ``cached_images``; omits optional
  ``original_page`` / ``word_attributes`` when ``None``).
- Round-trip identity on a "legacy golden" dict (full envelope as
  written by the legacy labeler).

Deferred to later slices:

- ``build_envelope(...)`` (the high-level constructor that takes a
  ``Page`` object + ``Project`` + ``OCRProvenance`` and produces the
  envelope) — needs ``pd_book_tools.Page`` in scope. Slice 8b-iii
  ships only the dict-in/dict-out layer so the reader can drive
  ``LocalDoctrPageLoader.load_labeled`` / ``load_cached`` without
  pulling in pd_book_tools.
- v2.2 rotation fields (``source.rotation_degrees`` /
  ``source.rotation_source``). The reader tolerates these via
  legacy parity (``UserPageSource.from_dict`` ignores unknown keys
  silently — same as legacy), but no explicit field on the dataclass
  yet; M9 milestone wires them.
"""

from __future__ import annotations

import json
from typing import Any

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    USER_PAGE_SCHEMA_NAME,
    USER_PAGE_SCHEMA_VERSION,
    OCRModelProvenance,
    OCRProvenance,
    ProvenanceApp,
    ProvenanceToolchain,
    SourceImageFingerprint,
    UserPageEnvelope,
    UserPagePayload,
    UserPageProvenance,
    UserPageSchema,
    UserPageSource,
    envelope_to_dict,
    is_user_page_envelope,
    parse_envelope,
)

# ── module-level constants (legacy parity pin) ───────────────────────────


def test_schema_constants_match_legacy() -> None:
    """Schema name + version verbatim from legacy
    ``user_page_persistence.py:83-86``.
    """
    assert USER_PAGE_SCHEMA_NAME == "pd_ocr_labeler.user_page"
    assert USER_PAGE_SCHEMA_VERSION == "2.1"
    assert isinstance(USER_PAGE_SCHEMA_VERSION, str)


# ── is_user_page_envelope type guard ─────────────────────────────────────


def test_is_user_page_envelope_true_on_match() -> None:
    data = {"schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"}}
    assert is_user_page_envelope(data) is True


def test_is_user_page_envelope_false_on_wrong_name() -> None:
    data = {"schema": {"name": "pd_ocr_labeler.project", "version": "1.0"}}
    assert is_user_page_envelope(data) is False


def test_is_user_page_envelope_false_on_missing_schema() -> None:
    assert is_user_page_envelope({}) is False


def test_is_user_page_envelope_false_on_non_dict_schema() -> None:
    """Legacy returns False for non-dict ``schema`` (parity with
    ``user_page_persistence.py:355``)."""
    assert is_user_page_envelope({"schema": "v2.1"}) is False


def test_is_user_page_envelope_accepts_unknown_version() -> None:
    """Spec §3: readers MUST accept v2.1 AND v2.2. Future SPA-only
    versions like v2.3 would still pass the name check; version
    rejection is the parser's job, not the type guard's."""
    data = {"schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.99"}}
    assert is_user_page_envelope(data) is True


# ── golden legacy round-trip ─────────────────────────────────────────────


# A representative envelope as written by legacy ``save_page``:
# - all top-level keys present
# - non-empty ``cached_images``
# - non-None ``original_page`` and ``word_attributes``
# - full provenance (saved_at, app, toolchain, ocr.models)
# - full ``source.image_fingerprint``
LEGACY_GOLDEN_ENVELOPE: dict[str, Any] = {
    "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
    "provenance": {
        "saved_at": "2026-05-06T12:34:56.789Z",
        "saved_by": "Save Page",
        "source_lane": "labeled",
        "app": {
            "name": "pd_ocr_labeler",
            "version": "0.1.0",
            "git_commit": "abc1234",
        },
        "toolchain": {
            "python": "3.13.1",
            "pd_book_tools": "0.5.0",
            "opencv_python": "4.10.0",
        },
        "ocr": {
            "engine": "doctr",
            "engine_version": "0.7.0",
            "models": [
                {
                    "name": "detection",
                    "version": "stock",
                    "weights_id": "db_resnet50",
                },
                {
                    "name": "recognition",
                    "version": "stock",
                    "weights_id": "crnn_vgg16_bn",
                },
            ],
            "config_fingerprint": "f" * 64,
        },
    },
    "source": {
        "project_id": "the_four_men",
        "page_index": 0,
        "page_number": 1,
        "image_path": "001.png",
        "project_root": "/abs/path/to/the_four_men",
        "image_fingerprint": {
            "size": 12345,
            "mtime_ns": 1700000000000000000,
            "sha256": "a" * 64,
        },
    },
    "payload": {
        "page": {"index": 0, "name": "001.png", "items": []},
        "original_page": {"index": 0, "name": "001.png", "items": []},
        "word_attributes": {
            "word-0001": {"italic": True, "small_caps": False},
            "word-0002": {"italic": False, "small_caps": True},
        },
    },
    "cached_images": {
        "original": "the_four_men_001_original_aaaaaaaaaaaaaaaa.jpg",
        "lines": "the_four_men_001_lines_bbbbbbbbbbbbbbbb.jpg",
    },
}


def test_parse_envelope_full_legacy_round_trip() -> None:
    """parse → write yields the same dict (Python 3.7+ key order
    preserved). This is the core D-003 byte-compat guard."""
    env = parse_envelope(LEGACY_GOLDEN_ENVELOPE)
    out = envelope_to_dict(env)
    assert out == LEGACY_GOLDEN_ENVELOPE


def test_parse_envelope_full_round_trip_via_json_text() -> None:
    """Same as above but goes through JSON serialization to catch
    e.g. tuple-vs-list drift."""
    text = json.dumps(LEGACY_GOLDEN_ENVELOPE, indent=2, ensure_ascii=False)
    data = json.loads(text)
    env = parse_envelope(data)
    out = envelope_to_dict(env)
    assert out == data


# ── parse_envelope: schema defaults + minimal-input behavior ─────────────


def test_parse_envelope_defaults_when_keys_missing() -> None:
    """Legacy ``from_dict`` is permissive — missing keys → defaults.
    Required for reading older legacy saves that predate v2.1."""
    env = parse_envelope({})
    # Schema falls back to current name+version.
    assert env.schema.name == USER_PAGE_SCHEMA_NAME
    assert env.schema.version == USER_PAGE_SCHEMA_VERSION
    # Provenance defaults: empty saved_at, "Save Page", "labeled".
    assert env.provenance.saved_at == ""
    assert env.provenance.saved_by == "Save Page"
    assert env.provenance.source_lane == "labeled"
    # Source defaults to empty/zero.
    assert env.source.project_id == ""
    assert env.source.page_index == 0
    assert env.source.page_number == 0
    assert env.source.image_path == ""
    assert env.source.project_root is None
    assert env.source.image_fingerprint is None
    # Payload defaults to empty dicts / None.
    assert env.payload.page == {}
    assert env.payload.original_page is None
    assert env.payload.word_attributes is None
    # cached_images empty by default.
    assert env.cached_images == {}


def test_parse_envelope_omits_empty_cached_images_on_write() -> None:
    """Legacy ``to_dict`` omits ``cached_images`` when empty
    (``user_page_persistence.py:330-331``). Parity required so
    re-writes don't accidentally bloat the file with ``"cached_images": {}``.
    """
    minimal = {"schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"}}
    out = envelope_to_dict(parse_envelope(minimal))
    assert "cached_images" not in out


def test_parse_envelope_omits_none_original_page_on_write() -> None:
    """Legacy ``UserPagePayload.to_dict`` omits ``original_page`` when
    ``None`` (``user_page_persistence.py:277-278``)."""
    data = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "payload": {"page": {"index": 0}},
    }
    out = envelope_to_dict(parse_envelope(data))
    assert "original_page" not in out["payload"]


def test_parse_envelope_omits_none_word_attributes_on_write() -> None:
    """Legacy parity — omit ``word_attributes`` when None
    (``user_page_persistence.py:279-280``)."""
    data = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "payload": {"page": {"index": 0}},
    }
    out = envelope_to_dict(parse_envelope(data))
    assert "word_attributes" not in out["payload"]


# ── word_attributes filtering parity (legacy lines 291-303) ──────────────


def test_word_attributes_skips_non_string_keys() -> None:
    """Legacy filters out entries whose key is not a string."""
    data = {
        "payload": {
            "page": {},
            "word_attributes": {
                "word-0001": {"italic": True},
                42: {"italic": True},  # non-string key — dropped
            },
        }
    }
    env = parse_envelope(data)
    assert env.payload.word_attributes == {"word-0001": {"italic": True}}


def test_word_attributes_skips_non_dict_values() -> None:
    """Legacy filters out entries whose value is not a dict."""
    data = {
        "payload": {
            "page": {},
            "word_attributes": {
                "word-0001": {"italic": True},
                "word-0002": "not a dict",  # dropped
            },
        }
    }
    env = parse_envelope(data)
    assert env.payload.word_attributes == {"word-0001": {"italic": True}}


def test_word_attributes_coerces_values_to_bool() -> None:
    """Legacy ``user_page_persistence.py:298-302`` coerces each attr
    value to ``bool``."""
    data = {
        "payload": {
            "page": {},
            "word_attributes": {
                "word-0001": {"italic": 1, "small_caps": 0},
            },
        }
    }
    env = parse_envelope(data)
    assert env.payload.word_attributes == {"word-0001": {"italic": True, "small_caps": False}}


def test_word_attributes_none_when_not_dict() -> None:
    """A non-dict ``word_attributes`` field becomes ``None`` (legacy
    line 293)."""
    data = {
        "payload": {"page": {}, "word_attributes": "garbage"},
    }
    env = parse_envelope(data)
    assert env.payload.word_attributes is None


# ── cached_images filtering parity (legacy lines 336-343) ────────────────


def test_cached_images_filters_empty_keys_and_values() -> None:
    """Legacy drops entries with empty key or empty value."""
    data = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "cached_images": {
            "original": "img.jpg",
            "": "should-drop.jpg",
            "lines": "",
            "paragraphs": "para.jpg",
        },
    }
    env = parse_envelope(data)
    assert env.cached_images == {"original": "img.jpg", "paragraphs": "para.jpg"}


def test_cached_images_filters_non_string_types() -> None:
    """Legacy drops entries whose key or value is not a string."""
    data = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "cached_images": {
            "original": "img.jpg",
            123: "num-key.jpg",
            "lines": 456,
        },
    }
    env = parse_envelope(data)
    assert env.cached_images == {"original": "img.jpg"}


def test_cached_images_non_dict_yields_empty() -> None:
    """A non-dict ``cached_images`` is silently treated as empty
    (legacy lines 336-337)."""
    data = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "cached_images": "garbage",
    }
    env = parse_envelope(data)
    assert env.cached_images == {}


# ── ocr provenance parity (legacy lines 56-80) ───────────────────────────


def test_ocr_provenance_models_accept_string_legacy_form() -> None:
    """Legacy line 64-65: a model entry that's a non-empty string is
    coerced into ``OCRModelProvenance(name=...)`` for backward compat
    with very old saves that stored model names as strings."""
    data = {
        "provenance": {
            "ocr": {
                "engine": "doctr",
                "models": ["legacy_detector_name", "legacy_recognizer_name"],
            }
        }
    }
    env = parse_envelope(data)
    assert env.provenance.ocr.models == [
        OCRModelProvenance(name="legacy_detector_name"),
        OCRModelProvenance(name="legacy_recognizer_name"),
    ]


def test_ocr_provenance_models_skips_garbage_entries() -> None:
    """Legacy line 60-65 silently skips non-dict, non-string entries
    in the models list."""
    data = {
        "provenance": {
            "ocr": {
                "engine": "doctr",
                "models": [
                    {"name": "detection"},
                    None,  # dropped
                    42,  # dropped
                    "",  # dropped (empty string)
                    {"name": "recognition", "weights_id": "crnn"},
                ],
            }
        }
    }
    env = parse_envelope(data)
    assert env.provenance.ocr.models == [
        OCRModelProvenance(name="detection"),
        OCRModelProvenance(name="recognition", weights_id="crnn"),
    ]


def test_ocr_provenance_to_dict_omits_optional_fields() -> None:
    """Legacy ``OCRProvenance.to_dict`` only emits non-None
    ``engine_version`` and ``config_fingerprint`` (lines 50-53)."""
    prov = OCRProvenance(engine="doctr", models=[])
    out = prov.to_dict()
    assert out == {"engine": "doctr", "models": []}
    assert "engine_version" not in out
    assert "config_fingerprint" not in out


def test_ocr_provenance_default_engine_unknown() -> None:
    """Empty ``ocr`` block parses to ``engine="unknown"`` per legacy
    line 40 + 68."""
    data = {"provenance": {"ocr": {}}}
    env = parse_envelope(data)
    assert env.provenance.ocr.engine == "unknown"


# ── source.image_fingerprint parity (legacy lines 215-222) ───────────────


def test_image_fingerprint_omits_none_fields() -> None:
    """Legacy ``SourceImageFingerprint.to_dict`` (lines 204-212) omits
    None fields."""
    fp = SourceImageFingerprint(size=42)
    assert fp.to_dict() == {"size": 42}


def test_image_fingerprint_skipped_when_not_dict() -> None:
    """Legacy ``UserPageSource.from_dict`` (lines 249-254) ignores a
    non-dict ``image_fingerprint`` value."""
    data = {"source": {"image_fingerprint": "garbage"}}
    env = parse_envelope(data)
    assert env.source.image_fingerprint is None


# ── source.* required-field coercion ─────────────────────────────────────


def test_source_coerces_indices_to_int() -> None:
    """Legacy line 257-258 coerces page_index/page_number through
    int(). String numbers are still accepted (legacy parity)."""
    data = {
        "source": {
            "project_id": "p1",
            "page_index": "5",
            "page_number": "6",
            "image_path": "p.png",
        }
    }
    env = parse_envelope(data)
    assert env.source.page_index == 5
    assert env.source.page_number == 6


# ── provenance defaults ──────────────────────────────────────────────────


def test_provenance_app_default_when_block_missing() -> None:
    env = parse_envelope({})
    assert env.provenance.app == ProvenanceApp()


def test_provenance_toolchain_default_when_block_missing() -> None:
    env = parse_envelope({})
    assert env.provenance.toolchain == ProvenanceToolchain()


def test_provenance_app_omits_none_git_commit() -> None:
    """Legacy line 120-121 omits ``git_commit`` when ``None``."""
    app = ProvenanceApp(name="x", version="y", git_commit=None)
    assert "git_commit" not in app.to_dict()


def test_provenance_toolchain_omits_none_opencv() -> None:
    """Legacy line 146-147 omits ``opencv_python`` when ``None``."""
    tc = ProvenanceToolchain(python="3.13", pd_book_tools="0.5")
    assert "opencv_python" not in tc.to_dict()


# ── envelope_to_dict integration with full UserPageEnvelope ──────────────


def test_build_envelope_from_dataclasses() -> None:
    """Constructing the envelope dataclasses by hand and serialising
    yields a dict shape that matches a fresh parse of the same dict —
    the writer is the inverse of the reader for valid full input."""
    env = UserPageEnvelope(
        schema=UserPageSchema(),
        provenance=UserPageProvenance(saved_at="2026-01-01T00:00:00Z"),
        source=UserPageSource(project_id="p", page_index=0, page_number=1, image_path="0.png"),
        payload=UserPagePayload(page={"index": 0}),
    )
    out = envelope_to_dict(env)
    assert out["schema"] == {
        "name": USER_PAGE_SCHEMA_NAME,
        "version": USER_PAGE_SCHEMA_VERSION,
    }
    assert out["provenance"]["saved_at"] == "2026-01-01T00:00:00Z"
    assert out["source"]["project_id"] == "p"
    assert out["payload"]["page"] == {"index": 0}
    assert "cached_images" not in out


# ── module export surface ────────────────────────────────────────────────


def test_public_api_exports() -> None:
    """The slice promises a stable surface: type guard, parser, writer,
    + the dataclasses needed to read the result."""
    from pd_ocr_labeler_spa.core.persistence import user_page_envelope as m

    public = set(m.__all__)
    expected_min = {
        "USER_PAGE_SCHEMA_NAME",
        "USER_PAGE_SCHEMA_VERSION",
        "UserPageEnvelope",
        "UserPageSchema",
        "UserPageProvenance",
        "UserPageSource",
        "UserPagePayload",
        "ProvenanceApp",
        "ProvenanceToolchain",
        "OCRProvenance",
        "OCRModelProvenance",
        "SourceImageFingerprint",
        "is_user_page_envelope",
        "parse_envelope",
        "envelope_to_dict",
    }
    assert expected_min.issubset(public)


def test_pytest_module_imports_clean() -> None:
    """Sanity: importing the module mid-test session doesn't raise."""
    import importlib

    importlib.import_module("pd_ocr_labeler_spa.core.persistence.user_page_envelope")
