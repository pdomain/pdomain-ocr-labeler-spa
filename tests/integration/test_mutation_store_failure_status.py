"""Wave 0.5: content mutators must not return silent 200 on store failure."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _make_page() -> Page:
    return Page.from_dict(
        {
            "width": 100,
            "height": 100,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, 100, 100),
            "items": [
                {
                    "type": "Block",
                    "child_type": "BLOCKS",
                    "block_category": "PARAGRAPH",
                    "items": [
                        {
                            "type": "Block",
                            "child_type": "WORDS",
                            "block_category": "LINE",
                            "items": [
                                {
                                    "type": "Word",
                                    "text": "hi",
                                    "ground_truth_text": "hi",
                                    "bounding_box": _bbox(0, 0, 10, 10),
                                    "word_labels": [],
                                }
                            ],
                            "bounding_box": _bbox(0, 0, 100, 20),
                        }
                    ],
                    "bounding_box": _bbox(0, 0, 100, 40),
                }
            ],
        }
    )


class _ExplodingStore:
    """LabelerPageStore stand-in that fails content writes."""

    def __init__(self, real: LabelerPageStore) -> None:
        self._real = real

    def get_page(self, page_id: Any) -> Any:
        return self._real.get_page(page_id)

    def save_page(self, agg: Any) -> None:
        raise OSError("injected store failure")

    @property
    def blobs(self) -> Any:
        return self._real.blobs

    def close(self) -> None:
        self._real.close()


@pytest.mark.integration
def test_gt_mutation_returns_503_when_store_write_fails(tmp_path: Path) -> None:
    """P1-MUTATION-200: store present + page_id + write fail → non-200."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )
    app = build_app(settings)
    page_id = uuid4()
    page = _make_page()

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        real_store: LabelerPageStore | None = getattr(app.state, "page_store", None)
        assert real_store is not None
        real_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))
        # Replace the wired store with one that fails on save_page.
        boom = _ExplodingStore(real_store)
        app.state.page_store = boom  # type: ignore[attr-defined]

        project_state = app.state.project_state
        pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page),
        )
        pstate.page_id = page_id
        pstate.generation = 1
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        mut = client.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "hello"},
        )
        assert mut.status_code == 503, mut.text
        body = mut.json()
        assert body.get("error") == "store_persist_failed"
        # In-memory edit still applied (generation advanced).
        assert pstate.generation == 2
        assert page.lines[0].words[0].ground_truth_text == "hello"
