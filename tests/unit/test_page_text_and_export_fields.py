"""PagePayload text fields, and the removed ExportRequest normalize field.

Split out of ``test_text_normalize.py`` when the text-normalization capability
was removed (P2-NORMALIZE-DEAD, 2026-09-18): ``core.text_normalize`` no longer
exists, but ``PagePayload.page_text_ocr`` / ``page_text_gt`` and the
``ExportRequest`` regression coverage below are unrelated to that module and
still apply.

Spec authority: ``docs/architecture/18-text-normalization.md`` (normalization
is not offered).
"""

from __future__ import annotations

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
