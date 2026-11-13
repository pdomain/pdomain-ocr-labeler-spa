"""Reading-order stamps survive membership moves and clear on a structural edit."""

from __future__ import annotations

from types import SimpleNamespace

from pdomain_ocr_labeler_spa.api.lines_paragraphs import _finalize_structural_edit
from pdomain_ocr_labeler_spa.core.word_identity import identity_reading_order


def test_structural_finalize_clears_reading_order_stamps() -> None:
    word = SimpleNamespace(ground_truth_match_keys={"labeler_reading_order": 3, "kept": "yes"})
    blank = SimpleNamespace(ground_truth_match_keys=None)
    page = SimpleNamespace(lines=[SimpleNamespace(words=[word, blank])])
    pstate = SimpleNamespace(generation=1, page_id=None)
    project_state = SimpleNamespace(loaded_project=None)

    _finalize_structural_edit(
        page=page,
        pstate=pstate,
        project_state=project_state,  # type: ignore[arg-type]
        page_index=0,
        store=None,
        changes=[{"type": "line_merge"}],
    )

    assert "labeler_reading_order" not in word.ground_truth_match_keys
    assert word.ground_truth_match_keys["kept"] == "yes"
    assert identity_reading_order(word, 1) == 1
    assert pstate.generation == 2
