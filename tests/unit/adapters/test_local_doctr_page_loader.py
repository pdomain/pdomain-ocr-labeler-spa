"""Tests for ``LocalDoctrPageLoader`` — slice 8b-ii.

The loader implements ``core.page_state.PageLoader`` (the dispatch
protocol). At this slice it wires ``run_ocr`` only; ``load_labeled``
and ``load_cached`` return ``None`` until ``core/persistence/
user_page_envelope.py`` ships (a separate M3 slice).

Hermetic: ``pd_book_tools.ocr.document.Document.from_image_ocr_via_doctr``
is stubbed via ``sys.modules`` injection; ``PredictorCache`` is stubbed
in-process so we don't pull torch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pd_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrPageLoader
from pd_ocr_labeler_spa.core.models import Project
from pd_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource


def _make_project(tmp_path: Path, n_pages: int = 3) -> Project:
    image_paths = []
    for i in range(n_pages):
        p = tmp_path / f"page_{i:03d}.png"
        p.write_bytes(b"fake-png")
        image_paths.append(p)
    return Project(
        project_id="proj1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=len(image_paths),
        current_page_index=0,
    )


@pytest.fixture
def stub_pd_book_tools(monkeypatch: pytest.MonkeyPatch):
    """Inject fake ``pd_book_tools.ocr.document.Document``.

    ``from_image_ocr_via_doctr`` records call args and returns a
    ``Document``-shaped object whose ``pages[0]`` is the marker page.
    """

    calls: list[dict[str, Any]] = []

    class _FakePage:
        def __init__(self, source_identifier: str) -> None:
            self.source_identifier = source_identifier
            # Track add_ground_truth calls for slice "GT injection".
            self.ground_truth_calls: list[str] = []

        def to_dict(self) -> dict[str, Any]:
            """Stub for ``Page.to_dict`` used by the auto-cache-write
            slice. The build_envelope writer just stashes this verbatim
            into ``payload.page``; the value here is purely a marker.
            """
            return {"type": "Page", "source_identifier": self.source_identifier}

        def add_ground_truth(self, text: str) -> None:
            """Stub for ``Page.add_ground_truth``. Records calls so
            tests can assert injection behaviour."""
            self.ground_truth_calls.append(text)

    class _FakeDocument:
        def __init__(self, pages: list[_FakePage]) -> None:
            self.pages = pages

    def from_image_ocr_via_doctr(
        image_path: Any,
        *,
        source_identifier: str,
        predictor: Any,
    ) -> _FakeDocument:
        calls.append(
            {
                "image_path": image_path,
                "source_identifier": source_identifier,
                "predictor": predictor,
            }
        )
        return _FakeDocument(pages=[_FakePage(source_identifier=source_identifier)])

    fake_module = SimpleNamespace(
        Document=SimpleNamespace(from_image_ocr_via_doctr=from_image_ocr_via_doctr),
    )
    monkeypatch.setitem(sys.modules, "pd_book_tools.ocr.document", fake_module)
    return SimpleNamespace(calls=calls, FakePage=_FakePage)


@pytest.fixture
def stub_predictor_cache(monkeypatch: pytest.MonkeyPatch):
    """``PredictorCache`` that bypasses doctr_support entirely.

    The real cache imports ``pd_book_tools.ocr.doctr_support`` lazily;
    here we inject the stub module too so ``get_or_create`` can run
    without erroring.
    """

    fake_module = SimpleNamespace(
        get_default_doctr_predictor=lambda: SimpleNamespace(kind="stock"),
        get_finetuned_torch_doctr_predictor=lambda *a, **kw: SimpleNamespace(kind="finetuned"),
    )
    monkeypatch.setitem(sys.modules, "pd_book_tools.ocr.doctr_support", fake_module)
    return PredictorCache()


def test_loader_run_ocr_returns_page_load_outcome(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(1)
    assert isinstance(outcome, PageLoadOutcome)
    assert outcome.page_index == 1
    assert outcome.source == PageSource.OCR
    assert outcome.payload.source_identifier == "page_001.png"


def test_loader_run_ocr_passes_image_path_and_source_identifier(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    loader.run_ocr(0)
    call = stub_pd_book_tools.calls[0]
    expected_path = project.image_paths[0]
    assert call["image_path"] == expected_path
    assert call["source_identifier"] == expected_path.name


def test_loader_run_ocr_uses_predictor_from_cache(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    loader.run_ocr(0)
    loader.run_ocr(1)
    # Both calls received the same predictor (cache hit on the same key).
    assert stub_pd_book_tools.calls[0]["predictor"] is stub_pd_book_tools.calls[1]["predictor"]


def test_loader_run_ocr_raises_on_out_of_range_index(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path, n_pages=2)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    with pytest.raises(IndexError):
        loader.run_ocr(5)
    with pytest.raises(IndexError):
        loader.run_ocr(-1)


def test_loader_run_ocr_raises_page_image_not_found_when_file_missing(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Loader catches missing image *before* OCR — cheap fail.

    Subclass of FileNotFoundError per ``core/page_state.py`` contract.
    """
    project = _make_project(tmp_path, n_pages=2)
    project.image_paths[0].unlink()  # delete the file

    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    from pd_ocr_labeler_spa.core.page_state import PageImageNotFoundError

    with pytest.raises(PageImageNotFoundError):
        loader.run_ocr(0)
    # And no OCR was attempted.
    assert stub_pd_book_tools.calls == []


def test_load_labeled_returns_none_when_data_root_is_none(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Backward-compat: when ``data_root`` is unset, the labeled lane
    is a no-op (so the existing slice-8b-ii loader construction without
    persistence wiring keeps working)."""
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert loader.load_labeled(0) is None


def test_load_cached_returns_none_when_cache_root_is_none(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert loader.load_cached(0) is None


# ── slice 8b-iv: labeled / cached lanes wired through envelope reader ─────


def _make_loader_with_persistence(
    tmp_path: Path,
    predictor_cache: PredictorCache,
    *,
    data_root: Path | None = None,
    cache_root: Path | None = None,
    n_pages: int = 2,
) -> LocalDoctrPageLoader:
    project_root = tmp_path / "project_dir"
    project_root.mkdir(parents=True, exist_ok=True)
    project = _make_project(project_root, n_pages=n_pages)
    return LocalDoctrPageLoader(
        project=project,
        predictor_cache=predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        data_root=data_root,
        cache_root=cache_root,
    )


def _write_envelope_at(path: Path, payload_page: dict) -> None:
    import json

    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        USER_PAGE_SCHEMA_NAME,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
                "provenance": {"saved_at": "2026-01-01T00:00:00Z"},
                "source": {
                    "project_id": "project_dir",
                    "page_index": 0,
                    "page_number": 1,
                    "image_path": "page_000.png",
                },
                "payload": {"page": payload_page},
            }
        )
    )


def test_load_labeled_reads_envelope_from_data_root_lane(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """When the on-disk labeled-lane envelope exists for this page, the
    loader returns a ``PageLoadOutcome(source=FILESYSTEM, payload=
    UserPageEnvelope)``. Spec §1 lane 2 + §9 lines 32–40."""
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        UserPageEnvelope,
        labeled_envelope_path,
    )

    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    project_id = loader.project.project_id

    envelope_path = labeled_envelope_path(data_root, project_id, page_index=0)
    _write_envelope_at(envelope_path, {"index": 0, "name": "page_000.png"})

    outcome = loader.load_labeled(0)
    assert outcome is not None
    assert outcome.page_index == 0
    assert outcome.source == PageSource.FILESYSTEM
    assert isinstance(outcome.payload, UserPageEnvelope)
    assert outcome.payload.payload.page == {"index": 0, "name": "page_000.png"}


def test_load_labeled_returns_none_when_no_envelope_on_disk(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """No envelope at the expected path → ``None`` (loader falls
    through to the cached lane / OCR per spec)."""
    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    assert loader.load_labeled(0) is None


def test_load_labeled_returns_none_on_corrupt_envelope(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Corrupt JSON at the expected path → ``None`` (spec §9 lines
    32–40 — fall through, never crash)."""
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        labeled_envelope_path,
    )

    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    p = labeled_envelope_path(data_root, loader.project.project_id, page_index=0)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{corrupt}")
    assert loader.load_labeled(0) is None


def test_load_cached_reads_envelope_from_cache_root_lane(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """When the on-disk cached-lane envelope exists, the loader returns
    ``PageLoadOutcome(source=CACHED_OCR, payload=UserPageEnvelope)``.
    Spec §1 lane 3 + §9 lines 32–40."""
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        UserPageEnvelope,
        cached_envelope_path,
    )

    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, cache_root=cache_root)

    envelope_path = cached_envelope_path(cache_root, loader.project.project_id, 0)
    _write_envelope_at(envelope_path, {"index": 0})

    outcome = loader.load_cached(0)
    assert outcome is not None
    assert outcome.page_index == 0
    assert outcome.source == PageSource.CACHED_OCR
    assert isinstance(outcome.payload, UserPageEnvelope)


def test_load_cached_returns_none_when_no_envelope_on_disk(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, cache_root=cache_root)
    assert loader.load_cached(0) is None


def test_ensure_page_model_routes_through_labeled_lane_when_envelope_exists(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """End-to-end: ``ensure_page_model`` dispatcher takes the labeled
    lane FIRST when both lanes have files (spec §9 lines 32–36).
    OCR must NOT be invoked."""
    from pd_ocr_labeler_spa.core.page_state import ensure_page_model
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        cached_envelope_path,
        labeled_envelope_path,
    )
    from pd_ocr_labeler_spa.core.project_state import ProjectState

    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(
        tmp_path, stub_predictor_cache, data_root=data_root, cache_root=cache_root
    )
    project_id = loader.project.project_id

    _write_envelope_at(
        labeled_envelope_path(data_root, project_id, 0),
        {"index": 0, "name": "labeled-marker"},
    )
    _write_envelope_at(
        cached_envelope_path(cache_root, project_id, 0),
        {"index": 0, "name": "cached-marker"},
    )

    state = ProjectState()
    state.set_loaded_project(loader.project)
    outcome = ensure_page_model(state, 0, loader=loader)
    assert outcome is not None
    assert outcome.source == PageSource.FILESYSTEM
    # Labeled-lane envelope wins over cached-lane envelope.
    assert outcome.payload.payload.page["name"] == "labeled-marker"
    # OCR was NOT invoked.
    assert stub_pd_book_tools.calls == []


def test_ensure_page_model_routes_through_cached_lane_when_no_labeled(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """When labeled-lane envelope is missing but cached is present,
    cached wins; OCR is still skipped."""
    from pd_ocr_labeler_spa.core.page_state import ensure_page_model
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        cached_envelope_path,
    )
    from pd_ocr_labeler_spa.core.project_state import ProjectState

    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(
        tmp_path, stub_predictor_cache, data_root=data_root, cache_root=cache_root
    )
    _write_envelope_at(
        cached_envelope_path(cache_root, loader.project.project_id, 0),
        {"index": 0, "name": "cached-only"},
    )

    state = ProjectState()
    state.set_loaded_project(loader.project)
    outcome = ensure_page_model(state, 0, loader=loader)
    assert outcome is not None
    assert outcome.source == PageSource.CACHED_OCR
    assert stub_pd_book_tools.calls == []


def test_loader_conforms_to_page_loader_protocol(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Structural conformance via ``isinstance`` against the
    ``runtime_checkable`` Protocol."""
    from pd_ocr_labeler_spa.core.page_state import PageLoader

    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert isinstance(loader, PageLoader)


def test_loader_integrates_with_ensure_page_model(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """End-to-end: ``ensure_page_model`` dispatches through the
    loader's three lanes (labeled None → cached None → run_ocr) and
    caches the outcome."""
    from pd_ocr_labeler_spa.core.page_state import ensure_page_model
    from pd_ocr_labeler_spa.core.project_state import ProjectState

    project = _make_project(tmp_path, n_pages=2)
    state = ProjectState()
    state.set_loaded_project(project)

    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome1 = ensure_page_model(state, 0, loader=loader)
    assert outcome1 is not None
    assert outcome1.source == PageSource.OCR

    # Second call returns cache hit; OCR not re-invoked.
    outcome2 = ensure_page_model(state, 0, loader=loader)
    assert outcome2 is outcome1
    assert len(stub_pd_book_tools.calls) == 1


# ── Auto-cache-write side effect after run_ocr ───────────────────────────
#
# Slice "auto-cache-write". Legacy ref:
# pd-ocr-labeler/state/project_state.py:752-799 (auto-save block inside
# ensure_page_model). After a successful OCR run, the loader writes the
# cached envelope to disk so subsequent loads (this session or later)
# hit the cached lane instead of paying OCR cost again.
#
# Failure-mode contract (legacy lines 789-794): exceptions during cache
# write are log-and-swallowed — never derail the OCR call. The OCR
# outcome is still returned to the caller.


def test_run_ocr_writes_cached_envelope_when_cache_root_set(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """After run_ocr succeeds, a cached envelope file appears at
    cached_envelope_path(cache_root, project_id, page_index)."""
    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        cached_envelope_path,
    )

    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=cache_root,
    )

    loader.run_ocr(0)

    expected = cached_envelope_path(cache_root, "proj1", 0)
    assert expected.exists(), f"expected cached envelope at {expected}"


def test_cached_envelope_has_cached_source_lane(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Auto-cache-write must set ``provenance.source_lane='cached'``
    so a future read can distinguish a cache write from a labeled save.
    Pinned via build_envelope's source_lane override (slice 8b-v)."""
    import json

    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        cached_envelope_path,
    )

    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=cache_root,
    )
    loader.run_ocr(2)

    raw = json.loads(cached_envelope_path(cache_root, "proj1", 2).read_text())
    assert raw["provenance"]["source_lane"] == "cached"
    assert raw["source"]["page_index"] == 2
    assert raw["source"]["page_number"] == 3
    assert raw["source"]["image_path"] == "page_002.png"
    # Page dict was placed in payload.page verbatim from to_dict.
    assert raw["payload"]["page"] == {
        "type": "Page",
        "source_identifier": "page_002.png",
    }


def test_run_ocr_skips_cache_write_when_cache_root_none(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """``cache_root=None`` lane is a no-op (preserves the slice-8b-ii
    constructor signature). The OCR still runs and returns normally."""
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=None,
    )

    outcome = loader.run_ocr(0)
    assert outcome.source == PageSource.OCR
    # No directory was created; nothing was written.
    cache_root = tmp_path / "cache"
    assert not cache_root.exists()


def test_run_ocr_swallows_cache_write_failure(
    tmp_path: Path,
    stub_pd_book_tools,
    stub_predictor_cache: PredictorCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy parity (project_state.py:789-794): a write-time exception
    must be log-and-swallowed — the OCR outcome is returned regardless.
    Patches ``Path.write_text`` only on the cached envelope path so we
    don't break the rest of the suite."""
    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=cache_root,
    )

    # Force write failure during the cache write.
    import pd_ocr_labeler_spa.adapters.ocr.local_doctr as loader_module

    def fail_write(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(loader_module, "_write_cached_envelope_text", fail_write)

    outcome = loader.run_ocr(0)
    assert outcome.source == PageSource.OCR  # still returned

    # No file was successfully written. The cache page-images dir may
    # still be created by the helper before the write fails (or not at
    # all if the failure happens before mkdir); either way no envelope
    # JSON should exist.
    page_images_dir = cache_root / "page-images"
    if page_images_dir.exists():
        assert list(page_images_dir.glob("*_envelope.json")) == []


def test_cache_write_provenance_includes_predictor_keys(
    tmp_path: Path, stub_pd_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """OCRProvenance.models reflects the loader's detection + recognition
    keys so a re-read of the cached envelope can tell which models
    produced it. Legacy parity: ``_resolve_ocr_provenance_for_save`` at
    page_operations.py:1166 carries the predictor identity."""
    import json

    from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
        cached_envelope_path,
    )

    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="my-det",
        recognition_key="my-reco",
        hf_revision="abc1234",
        cache_root=cache_root,
    )
    loader.run_ocr(0)

    raw = json.loads(cached_envelope_path(cache_root, "proj1", 0).read_text())
    models = raw["provenance"]["ocr"]["models"]
    model_names = [m["name"] for m in models]
    assert "my-det" in model_names
    assert "my-reco" in model_names
