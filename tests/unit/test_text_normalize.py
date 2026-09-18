"""Unit tests for core.text_normalize — issue #260.

Tests:
- is_available() returns bool without raising
- normalize_string returns input unchanged when module absent (mocked)
- normalize_string delegates to pdomain_book_tools when available (mocked)
- normalize_string never raises (error path)
- PagePayload has page_text_ocr, page_text_gt fields

Spec: docs/specs/2026-05-12-text-normalization-design.md
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


def test_is_available_returns_bool() -> None:
    """is_available must return a bool (either True or False — both are OK)."""
    from pdomain_ocr_labeler_spa.core.text_normalize import is_available

    result = is_available()
    assert isinstance(result, bool)


def test_normalize_string_returns_str() -> None:
    """normalize_string must always return a str."""
    from pdomain_ocr_labeler_spa.core.text_normalize import normalize_string

    result = normalize_string("hello")
    assert isinstance(result, str)


def test_normalize_string_fallback_when_unavailable() -> None:
    """When _AVAILABLE is False, normalize_string returns input unchanged."""
    # Use chr() to avoid RUF001 ambiguous-unicode-character warning
    long_s_hall = chr(0x017F) + "hall"  # U+017F + "hall" = long-s hall
    import pdomain_ocr_labeler_spa.core.text_normalize as mod

    with (
        patch.object(mod, "_AVAILABLE", False),
        patch.object(mod, "_pd_normalize", None),
    ):
        result = mod.normalize_string(long_s_hall)
        assert result == long_s_hall


def test_normalize_string_delegates_when_available() -> None:
    """When _AVAILABLE is True, normalize_string calls _pd_normalize."""
    long_s = chr(0x017F)  # U+017F LATIN SMALL LETTER LONG S
    fi_lig = chr(0xFB01)  # U+FB01 LATIN SMALL LIGATURE FI

    def fake_normalize(text: str, profile: str = "ascii") -> str:
        return text.replace(long_s, "s").replace(fi_lig, "fi")

    import pdomain_ocr_labeler_spa.core.text_normalize as mod

    with (
        patch.object(mod, "_AVAILABLE", True),
        patch.object(mod, "_pd_normalize", fake_normalize),
    ):
        assert mod.normalize_string(long_s + "hall") == "shall"
        assert mod.normalize_string("shall") == "shall"  # idempotent


def test_normalize_string_never_raises_on_exception() -> None:
    """Even if _pd_normalize raises, normalize_string returns input unchanged."""
    long_s_hall = chr(0x017F) + "hall"  # U+017F + "hall"

    def always_raise(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("boom")

    import pdomain_ocr_labeler_spa.core.text_normalize as mod

    with (
        patch.object(mod, "_AVAILABLE", True),
        patch.object(mod, "_pd_normalize", always_raise),
    ):
        result = mod.normalize_string(long_s_hall)
        assert result == long_s_hall


# ── PagePayload fields ────────────────────────────────────────────────


def test_page_payload_has_page_text_ocr_field() -> None:
    """PagePayload must have page_text_ocr: str | None = None."""
    from pdomain_ocr_labeler_spa.api.pages import PagePayload

    p = PagePayload(project_id="x", page_index=0)
    assert p.page_text_ocr is None


def test_page_payload_has_page_text_gt_field() -> None:
    """PagePayload must have page_text_gt: str | None = None."""
    from pdomain_ocr_labeler_spa.api.pages import PagePayload

    p = PagePayload(project_id="x", page_index=0)
    assert p.page_text_gt is None


def test_page_payload_accepts_text_fields() -> None:
    """PagePayload must accept string values for page_text_ocr and page_text_gt."""
    from pdomain_ocr_labeler_spa.api.pages import PagePayload

    long_s_text = chr(0x017F) + "hall not"  # U+017F + "hall not" = long-s hall
    p = PagePayload(
        project_id="x",
        page_index=0,
        page_text_ocr=long_s_text,
        page_text_gt="shall not",
    )
    assert p.page_text_ocr == long_s_text
    assert p.page_text_gt == "shall not"


# ── ExportRequest — normalize_recognition_labels removed (P1-NORMALIZE) ────
#
# No long-s/ligature ASCII normalizer exists anywhere in pdomain-book-tools,
# pdomain-pgdp-measure, or this repo (verified 2026-09-18): the field was
# dead from the API model through the UI, so it was removed rather than
# wired to a normalizer that does not exist. See
# docs/issues/2026-07-21-export-normalize-flag-dead.md.


def test_export_request_has_no_normalize_labels_field() -> None:
    """ExportRequest no longer has a normalize_recognition_labels field."""
    from pdomain_ocr_labeler_spa.api.export import ExportRequest, ExportScope

    req = ExportRequest(scope=ExportScope.CURRENT, page_index=0)
    assert not hasattr(req, "normalize_recognition_labels")


def test_export_request_ignores_unknown_normalize_field_from_old_clients() -> None:
    """A client still sending the removed field gets it silently ignored.

    ``ExportRequest`` has no ``model_config`` override, so Pydantic v2's
    default ``extra="ignore"`` applies: the field is dropped during
    validation rather than raising or reappearing on the model.
    """
    from pdomain_ocr_labeler_spa.api.export import ExportRequest, ExportScope

    req = ExportRequest.model_validate(
        {"scope": ExportScope.CURRENT.value, "page_index": 0, "normalize_recognition_labels": True}
    )
    assert not hasattr(req, "normalize_recognition_labels")
