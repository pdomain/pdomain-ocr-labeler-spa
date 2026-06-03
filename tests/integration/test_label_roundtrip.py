"""M0 parity gate: word labels + ground-truth survive save → reload through a FRESH store.

This guards the #1 audit finding: the legacy code hard-stubbed the labeled/cached
load lanes to ``None`` and never serialized labels, so edits were silently lost on
reload. The event-store adoption must persist edited *content* (not just a changelog
of diffs) so a fresh ``LabelerPageStore`` opened over the same on-disk ``events.db``
returns the edited page.

Behavioral contract (names adapted to the real book-tools / ops API):
- ``Word.ground_truth_text`` round-trips.
- ``Word.word_labels`` round-trips (the labeler stores ``"validated"`` and style
  tokens like ``"italic"`` here).
- A fresh ``LabelerPageStore`` over the same project dir replays the saved content.
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
        "items": [_para([_line([_word("teh"), _word("cat")]), _line([_word("sat")])])],
    }
    return Page.from_dict(page_dict)


def _seed_ocr_page(store: LabelerPageStore, page: Page) -> UUID:
    """Persist ``page`` as a fresh OCR aggregate (content blob + head provenance)."""
    page_id = uuid4()
    content_hash = store.blobs.write(json.dumps(page.to_dict()).encode("utf-8"))
    node = ProvenanceNode(id=f"ocr-{page_id}", source="ocr", tool="doctr", blob_refs=[content_hash])
    graph = ProvenanceGraph(nodes={node.id: node}, head_id=node.id, history=[node.id])
    record = PageRecord(page_id=page_id, page_index=0, source="ocr", provenance=graph)
    store.save_page(PageAggregate(record))
    return page_id


# ── Acceptance test (M0.2) ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_labels_survive_save_reload(tmp_path: Path) -> None:
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    store = LabelerPageStore(project_dir=project_dir)
    try:
        # Seed the page as it would land after OCR.
        page = _seed_load(store, project_dir)
        page_id = page[0]

        # Edit: GT correction + a "validated" label + an "italic" style label.
        word = page[1].lines[0].words[0]
        word.ground_truth_text = "Hello"
        word.word_labels.append("validated")
        word.word_labels.append("italic")

        # Save the edited *content* through the store.
        save_page_content_to_store(page_id=page_id, page=page[1], store=store)
    finally:
        store.close()

    # Reopen a FRESH store over the same on-disk events.db + blobs.
    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        reloaded = load_page_from_store(reopened, page_id)
        assert reloaded is not None, "fresh store returned no page content"
        w = reloaded.lines[0].words[0]
        assert w.ground_truth_text == "Hello"
        assert "validated" in w.word_labels
        assert "italic" in w.word_labels
    finally:
        reopened.close()


def _seed_load(store: LabelerPageStore, project_dir: Path) -> tuple[UUID, Page]:
    page = _make_page()
    page_id = _seed_ocr_page(store, page)
    # Re-load through the store so the test edits the same content the app would.
    loaded = load_page_from_store(store, page_id)
    assert loaded is not None
    return page_id, loaded
