"""Lane A / Task A1 — DocTR loader attaches cv2 image + reorganize_page.

``run_ocr`` must attach the cv2 page image onto ``page.cv2_numpy_page_image``
and call ``page.reorganize_page()`` (guarded by ``hasattr``) so that
subsequent ``word.refine_bbox(page_image)`` calls have an image to work
against (legacy parity: operations/ocr/page_operations.py:305-355).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrPageLoader
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache


class _FakePage:
    def __init__(self, source_identifier: str) -> None:
        self.source_identifier = source_identifier
        self.cv2_numpy_page_image: Any = None
        self.reorganize_calls = 0

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Page", "source_identifier": self.source_identifier}

    def reorganize_page(self) -> None:
        self.reorganize_calls += 1


@pytest.fixture
def stub_doctr(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDocument:
        def __init__(self, pages: list[_FakePage]) -> None:
            self.pages = pages

    def from_image_ocr_via_doctr(
        image_path: Any, *, source_identifier: str, predictor: Any, **kwargs: Any
    ) -> _FakeDocument:
        # **kwargs absorbs auto_rotate (the loader always passes auto_rotate=False
        # so OCR coords stay in the on-disk pixel space — C28 link 4).
        return _FakeDocument(pages=[_FakePage(source_identifier=source_identifier)])

    fake_module = SimpleNamespace(
        Document=SimpleNamespace(from_image_ocr_via_doctr=from_image_ocr_via_doctr),
    )
    monkeypatch.setitem(sys.modules, "pdomain_book_tools.ocr.document", fake_module)


@pytest.fixture
def stub_predictor_cache(monkeypatch: pytest.MonkeyPatch) -> PredictorCache:
    fake_module = SimpleNamespace(
        get_default_doctr_predictor=lambda: SimpleNamespace(kind="stock"),
        get_finetuned_torch_doctr_predictor=lambda *a, **kw: SimpleNamespace(kind="finetuned"),
    )
    monkeypatch.setitem(sys.modules, "pdomain_book_tools.ocr.doctr_support", fake_module)
    return PredictorCache()


def _project_with_real_png(tmp_path: Path) -> Project:
    p = tmp_path / "page_000.png"
    Image.new("RGB", (20, 12), color=(255, 255, 255)).save(p)
    return Project(
        project_id="proj1",
        project_root=tmp_path,
        image_paths=[p],
        ground_truth_map={},
        total_pages=1,
        current_page_index=0,
    )


def test_run_ocr_attaches_cv2_image_and_calls_reorganize(
    tmp_path: Path, stub_doctr: None, stub_predictor_cache: PredictorCache
) -> None:
    project = _project_with_real_png(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(0)
    page = outcome.payload
    assert isinstance(page.cv2_numpy_page_image, np.ndarray), "cv2 image was not attached"
    assert page.cv2_numpy_page_image.shape[:2] == (12, 20)
    assert page.reorganize_calls == 1, "reorganize_page() was not called"
