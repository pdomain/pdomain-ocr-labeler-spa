"""Tests for glyph annotation API endpoints.

Spec: specs/20-glyph-annotations.md §6
Issue: ConcaveTrillion/pd-ocr-labeler-spa#268
"""

from pd_ocr_labeler_spa.core.models import GlyphAnnotationsModel, LigatureMarkModel

# ---------------------------------------------------------------------------
# GlyphAnnotationsModel wire shape
# ---------------------------------------------------------------------------


def test_glyph_annotations_model_serializes_with_source() -> None:
    """GlyphAnnotationsModel.model_dump() includes source field for wire."""
    ga = GlyphAnnotationsModel(
        ligatures=[LigatureMarkModel(kind="ct", char_span=(1, 3))],
        source="human_confirmed",
    )
    d = ga.model_dump()
    assert d["source"] == "human_confirmed"
    assert len(d["ligatures"]) == 1


def test_glyph_annotations_model_accepts_predicted_source() -> None:
    ga = GlyphAnnotationsModel(source="predicted")
    assert ga.source == "predicted"


def test_glyph_annotations_model_accepts_human_confirmed() -> None:
    ga = GlyphAnnotationsModel(source="human_confirmed")
    assert ga.source == "human_confirmed"


# ---------------------------------------------------------------------------
# SetGlyphAnnotationsRequest and AcceptGlyphPredictionRequest model shape
# ---------------------------------------------------------------------------


def test_set_glyph_annotations_request_accepts_none() -> None:
    """annotations=None means 'unset back to not-reviewed'."""
    from pd_ocr_labeler_spa.api.words import SetGlyphAnnotationsRequest

    req = SetGlyphAnnotationsRequest(annotations=None)
    assert req.annotations is None


def test_set_glyph_annotations_request_accepts_model() -> None:
    from pd_ocr_labeler_spa.api.words import SetGlyphAnnotationsRequest

    req = SetGlyphAnnotationsRequest(
        annotations=GlyphAnnotationsModel(
            ligatures=[LigatureMarkModel(kind="ct", char_span=None)],
            source="human",
        )
    )
    assert req.annotations is not None
    assert req.annotations.source == "human"


def test_accept_glyph_prediction_request_has_no_body() -> None:
    """AcceptGlyphPredictionRequest has no required fields."""
    from pd_ocr_labeler_spa.api.words import AcceptGlyphPredictionRequest

    req = AcceptGlyphPredictionRequest()
    assert req is not None


# ---------------------------------------------------------------------------
# GlyphBulkMarkRequest / Response shapes
# ---------------------------------------------------------------------------


def test_glyph_bulk_mark_request_default_fields() -> None:
    from pd_ocr_labeler_spa.api.pages import GlyphBulkMarkRequest

    req = GlyphBulkMarkRequest(recipe="ct_substring")
    assert req.skip_already_annotated is True
    assert req.accept_predictions is False
    assert req.dry_run is False


def test_glyph_bulk_mark_request_valid_recipes() -> None:
    from pd_ocr_labeler_spa.api.pages import GlyphBulkMarkRequest

    for recipe in ("ct_substring", "st_substring", "long_s_typeset_era"):
        req = GlyphBulkMarkRequest(recipe=recipe)
        assert req.recipe == recipe


def test_glyph_bulk_mark_response_shape() -> None:
    from pd_ocr_labeler_spa.api.pages import GlyphBulkMarkResponse

    resp = GlyphBulkMarkResponse(
        affected_word_ids=["w1", "w2"],
        skipped_word_ids=["w3"],
        page=None,
    )
    assert resp.affected_word_ids == ["w1", "w2"]
    assert resp.skipped_word_ids == ["w3"]
    assert resp.page is None
