"""Lane A / Task A1 — refine_bboxes job runs end-to-end and mutates a bbox.

Posts a word-scope refine job (``mode=expand_only`` for a deterministic,
image-independent bbox change), drives the in-process runner to a terminal
event, and asserts the target word's bounding box grew.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str) -> dict[str, object]:
    return {"type": "Word", "text": text, "ground_truth_text": text, "bounding_box": _bbox(10, 10, 30, 22)}


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "bounding_box": _bbox(0, 0, 100, 40),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "bounding_box": _bbox(0, 0, 100, 20),
                        "items": [_word("teh"), _word("cat")],
                    }
                ],
            }
        ],
    }
    return Page.from_dict(page_dict)


def _make_settings(tmp_path: Path, *, projects_root: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


def _wrap_broker_publish(broker: JobEventBroker, sink: list[dict[str, Any]]) -> None:
    original = broker.publish

    async def recording_publish(job_id: str, event: dict[str, Any]) -> None:
        sink.append({"job_id": job_id, **event})
        await original(job_id, event)

    broker.publish = recording_publish  # type: ignore[method-assign]


def _wait_for_terminal(events: list[dict[str, Any]], *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(e.get("type") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.01)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


def _seed_page_in_store(store: LabelerPageStore, page_id: Any, page_index: int) -> None:
    record = PageRecord(page_id=page_id, page_index=page_index, source="ocr")
    store.save_page(PageAggregate(record))


@pytest.mark.integration
def test_refine_word_scope_expands_bbox(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _make_settings(tmp_path, projects_root=proj_dir.parent)
    app = build_app(settings)

    with TestClient(app) as c:
        recorded: list[dict[str, Any]] = []
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]

        resp = c.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore | None = getattr(c.app.state, "page_store", None)
        assert live_store is not None

        page = _make_page()
        # Attach a white cv2 image so the page has dimensions for expand clamping.
        page.cv2_numpy_page_image = np.full((300, 200, 3), 255, dtype=np.uint8)

        page_id = uuid4()
        _seed_page_in_store(live_store, page_id, page_index=0)

        project_state = c.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        # Capture the target word's bbox width before refine.
        target = page.lines[0].words[0]
        before = (target.bounding_box.minX, target.bounding_box.maxX)

        resp = c.post(
            "/api/projects/book1/pages/0/refine",
            json={"scope": "word", "mode": "expand_only", "padding_px": 5, "word_indices": [[0, 0]]},
        )
        assert resp.status_code == 202, resp.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        after = (target.bounding_box.minX, target.bounding_box.maxX)
        assert after != before, f"bbox unchanged after refine: {before} -> {after}"
        # expand_only grows the box: minX should decrease, maxX should increase.
        assert after[0] < before[0]
        assert after[1] > before[1]
