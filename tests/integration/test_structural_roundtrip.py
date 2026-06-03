"""M0 parity gate: structural edits survive save → reload through a FRESH store.

Companion to ``test_label_roundtrip.py``. Splitting a word, merging two lines, and
deleting a word must all be durable: a fresh ``LabelerPageStore`` opened over the same
on-disk ``events.db`` must replay the *edited structure*, not the original OCR layout.

The structure is asserted by line count and per-line word counts, captured from the
edited in-memory page (book-tools ``split_word`` reorders words within a line by bbox,
so the test fixes the contract to the genuine post-edit shape rather than a hand-coded
expectation).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord, ProvenanceGraph, ProvenanceNode

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore

# ── Real book-tools Page builders ──────────────────────────────────────────────


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(0, 0, 10, 10),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "Block", "child_type": "WORDS", "items": words, "bounding_box": _bbox(0, 0, 100, 20)}


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "Block", "child_type": "BLOCKS", "items": lines, "bounding_box": _bbox(0, 0, 100, 40)}


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            _para(
                [
                    _line([_word("teh"), _word("cat")]),
                    _line([_word("sat")]),
                    _line([_word("mat")]),
                ]
            )
        ],
    }
    return Page.from_dict(page_dict)


def _shape(page: Page) -> list[int]:
    """Structural fingerprint: per-line word counts (length == line count)."""
    return [len(line.words) for line in page.lines]


def _seed_ocr_page(store: LabelerPageStore, page: Page) -> UUID:
    page_id = uuid4()
    content_hash = store.blobs.write(json.dumps(page.to_dict()).encode("utf-8"))
    node = ProvenanceNode(id=f"ocr-{page_id}", source="ocr", tool="doctr", blob_refs=[content_hash])
    graph = ProvenanceGraph(nodes={node.id: node}, head_id=node.id, history=[node.id])
    record = PageRecord(page_id=page_id, page_index=0, source="ocr", provenance=graph)
    store.save_page(PageAggregate(record))
    return page_id


# ── Acceptance test (M0.3) ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_structural_edits_survive_reload(tmp_path: Path) -> None:
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    store = LabelerPageStore(project_dir=project_dir)
    try:
        page = _make_page()
        page_id = _seed_ocr_page(store, page)
        loaded = load_page_from_store(store, page_id)
        assert loaded is not None
        assert _shape(loaded) == [2, 1, 1]

        # Structural edits: split a word, merge two lines, delete a word.
        assert loaded.split_word(0, 0, 0.5) is True
        assert loaded.merge_lines([0, 1]) is True
        assert loaded.delete_words([(0, 0)]) is True
        expected_shape = _shape(loaded)

        save_page_content_to_store(page_id=page_id, page=loaded, store=store)
    finally:
        store.close()

    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        reloaded = load_page_from_store(reopened, page_id)
        assert reloaded is not None, "fresh store returned no page content"
        assert _shape(reloaded) == expected_shape, (
            f"structure drifted across reload: expected {expected_shape}, got {_shape(reloaded)}"
        )
    finally:
        reopened.close()
