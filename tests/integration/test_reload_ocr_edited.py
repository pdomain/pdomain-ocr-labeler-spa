"""Lane A / Task A4 — Reload OCR (Edited) re-OCRs the post-erase image.

Legacy "Reload OCR (Edited)" re-runs DocTR on the post-erase in-memory image.
The SPA's ``reload-ocr`` only read the on-disk source file. This test:

1. Erases a rectangle via ``POST .../words/{li}/{wi}/erase-pixels`` — which now
   persists the edited image as a blob the reload can read.
2. Posts ``reload-ocr`` with ``use_edited_image: true``.
3. Asserts OCR ran against the *erased* pixels (the loader received the edited
   image bytes, not the original on-disk file).
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
from PIL import Image

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str) -> dict[str, object]:
    return {"type": "Word", "text": text, "ground_truth_text": text, "bounding_box": _bbox(5, 5, 25, 18)}


def _make_page() -> Page:
    page_dict = {
        "width": 60,
        "height": 40,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 60, 40),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "block_category": "PARAGRAPH",
                "bounding_box": _bbox(0, 0, 60, 40),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "block_category": "LINE",
                        "bounding_box": _bbox(0, 0, 60, 20),
                        "items": [_word("teh")],
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


class _RecordingLoader:
    """Fake PageLoader that records whether reload OCR'd from edited bytes."""

    def __init__(self) -> None:
        self.edited_bytes_seen: bytes | None = None
        self.calls: list[int] = []

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> PageLoadOutcome:
        self.calls.append(page_index)
        self.edited_bytes_seen = edited_image_bytes
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=_make_page())

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


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


@pytest.mark.integration
def test_reload_ocr_use_edited_image_ocrs_erased_pixels(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    # On-disk source image: black square, distinct from the erased (white) image.
    Image.new("RGB", (60, 40), color=(0, 0, 0)).save(proj_dir / "001.png")

    settings = _make_settings(tmp_path, projects_root=proj_dir.parent)
    app = build_app(settings)

    with TestClient(app) as c:
        recorded: list[dict[str, Any]] = []
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        loader = _RecordingLoader()
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

        resp = c.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        page = _make_page()
        # Attach a black cv2 image; the erase op paints a white rectangle.
        page.cv2_numpy_page_image = np.zeros((40, 60, 3), dtype=np.uint8)

        page_id = uuid4()
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = c.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        # Erase a rectangle (fill 255 = white).
        resp = c.post(
            "/api/projects/book1/pages/0/words/0/0/erase-pixels",
            json={"bbox": {"x": 5, "y": 5, "width": 20, "height": 13}, "fill_value": 255},
        )
        assert resp.status_code == 200, resp.text

        # The edited image blob must have been persisted on the page state.
        assert pstate.edited_image_blob is not None, "erase did not persist an edited-image blob"

        # Reload OCR using the edited image.
        resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={"use_edited_image": True})
        assert resp.status_code == 202, resp.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]

        # The loader was handed the edited (erased) image bytes — NOT None.
        assert loader.edited_bytes_seen is not None, "reload-ocr did not pass the edited image to the loader"
        # Decode and confirm the erased region is now white (the edit took effect),
        # proving OCR ran against the post-erase pixels, not the black source file.
        import io

        edited_img = np.array(Image.open(io.BytesIO(loader.edited_bytes_seen)).convert("RGB"))
        # The erased rectangle (rows 5..17, cols 5..24) should be white.
        assert int(edited_img[10, 10, 0]) == 255, "erased region is not white in the reloaded image"


@pytest.mark.integration
def test_page_payload_exposes_has_edited_image_after_erase(tmp_path: Path) -> None:
    """Lane C / Task C2: the page payload's labeler extension must surface
    ``has_edited_image=True`` after an erase persists an edited-image blob, so
    the frontend can truthfully enable the "Reload OCR (Edited)" button.
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    Image.new("RGB", (60, 40), color=(0, 0, 0)).save(proj_dir / "001.png")

    settings = _make_settings(tmp_path, projects_root=proj_dir.parent)
    app = build_app(settings)

    with TestClient(app) as c:
        loader = _RecordingLoader()
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

        resp = c.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        page = _make_page()
        page.cv2_numpy_page_image = np.zeros((40, 60, 3), dtype=np.uint8)

        page_id = uuid4()
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = c.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        # Before any erase: the labeler extension reports no edited image.
        resp = c.get("/api/projects/book1/pages/0")
        assert resp.status_code == 200, resp.text
        ext_before = (resp.json().get("page_record") or {}).get("extensions", {}).get("labeler", {})
        assert ext_before.get("has_edited_image") in (False, None), ext_before

        # Erase a rectangle → persists an edited-image blob.
        resp = c.post(
            "/api/projects/book1/pages/0/words/0/0/erase-pixels",
            json={"bbox": {"x": 5, "y": 5, "width": 20, "height": 13}, "fill_value": 255},
        )
        assert resp.status_code == 200, resp.text
        assert pstate.edited_image_blob is not None

        # After the erase: the payload surfaces has_edited_image=True.
        resp = c.get("/api/projects/book1/pages/0")
        assert resp.status_code == 200, resp.text
        ext_after = (resp.json().get("page_record") or {}).get("extensions", {}).get("labeler", {})
        assert ext_after.get("has_edited_image") is True, ext_after
