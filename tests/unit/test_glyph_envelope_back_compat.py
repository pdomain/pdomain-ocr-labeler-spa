"""v2.1 envelopes must parse with every word's glyph_annotations == None."""

from pathlib import Path

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import parse_envelope


def test_v21_envelope_loads_with_glyph_annotations_none() -> None:
    fixture = Path(__file__).parent / "fixtures" / "v21_minimal.json"
    envelope = parse_envelope(fixture.read_text())
    assert envelope.schema_minor == 1
    # Every word in the page must have glyph_annotations == None.
    for line in envelope.payload.page["lines"]:
        for word in line["words"]:
            assert word.get("glyph_annotations") is None
