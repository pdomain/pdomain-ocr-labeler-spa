"""v2.2 envelope round-trips with tri-state glyph_annotations preserved."""

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    parse_envelope,
    serialize_envelope,
)


def test_v22_round_trip_preserves_tri_state(v22_envelope_str: str) -> None:
    env = parse_envelope(v22_envelope_str)
    s = serialize_envelope(env)
    env2 = parse_envelope(s)
    orig_words = [w for line in env.payload.page["lines"] for w in line["words"]]
    round_words = [w for line in env2.payload.page["lines"] for w in line["words"]]
    for w_orig, w_rt in zip(orig_words, round_words, strict=True):
        assert w_orig.get("glyph_annotations") == w_rt.get("glyph_annotations")
